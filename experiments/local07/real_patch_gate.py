"""LOCAL-14: fail-closed patch triage; never run candidate code on the host.

The runner only launches tests in an explicitly supplied local Docker image.
It never builds/pulls an image, mounts host secrets, or enables network access.
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import tempfile

DIFF = re.compile(rb"^diff --git a/([^\r\n]+) b/([^\r\n]+)$", re.M)
SHA = re.compile(r"^[0-9a-f]{40}$")
IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$")
ALLOWED_TEST = {"python -m pytest -q", "python -m unittest discover -q"}

class GateError(ValueError):
    pass

def cmd(args, *, cwd=None, input=None, timeout=90):
    return subprocess.run(args, cwd=cwd, input=input, capture_output=True, timeout=timeout)

def verify_patch(patch, allowed):
    if not patch or len(patch) > 256000 or b"\x00" in patch or b"\r" in patch:
        raise GateError("PATCH_UNSAFE_BYTES")
    paths = DIFF.findall(patch)
    if not paths or len(paths) != 1 or patch.count(b"diff --git ") != 1:
        raise GateError("PATCH_MULTIFILE_OR_EMPTY")
    a, b = paths[0]
    try:
        aa, bb = a.decode("utf-8"), b.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GateError("INVALID_PATH_ENCODING") from exc
    normalized = pathlib.PurePosixPath(aa)
    if (aa != bb or aa not in allowed or not aa.endswith(".py") or
        normalized.is_absolute() or ".." in normalized.parts or
        normalized.as_posix() != aa):
        raise GateError("PATCH_OUT_OF_SCOPE")
    if (b"GIT binary patch" in patch or b"new file mode" in patch or
        b"deleted file mode" in patch or b"rename from " in patch or
        b"copy from " in patch or b"old mode " in patch or b"new mode " in patch):
        raise GateError("PATCH_UNSUPPORTED_OPERATION")
    return aa

def grade(repo, issue, patch_file, image=None, test_command=None, run_tests=False):
    root = pathlib.Path(repo).resolve()
    if not (root / ".git").exists():
        raise GateError("NOT_GIT_CHECKOUT")
    status = cmd(["git", "status", "--porcelain"], cwd=root)
    if status.returncode or status.stdout.strip():
        raise GateError("DIRTY_SOURCE")
    head = cmd(["git", "rev-parse", "HEAD"], cwd=root)
    if head.returncode or head.stdout.decode().strip() != issue["base_commit"]:
        raise GateError("COMMIT_MISMATCH")
    allowed = issue.get("allowed_files")
    if (not isinstance(allowed, list) or not allowed or len(allowed) > 2 or
        any(not isinstance(x,str) or x.startswith("/") or ".." in pathlib.PurePosixPath(x).parts for x in allowed)):
        raise GateError("INVALID_ALLOWLIST")
    data = pathlib.Path(patch_file).read_bytes()
    target = verify_patch(data, allowed)
    source_target = root.joinpath(*pathlib.PurePosixPath(target).parts)
    if (source_target.is_symlink() or not source_target.is_file() or
        not source_target.resolve().is_relative_to(root)):
        raise GateError("INVALID_SOURCE_TARGET")
    result = {"schema":1,"gate":"LOCAL-14","base_commit":issue["base_commit"],
              "patch_sha256":hashlib.sha256(data).hexdigest(),"edited_file":target,
              "patch_applicable":False,"test_status":"NOT_RUN",
              "official_resolution":"NOT_EVALUATED","host_candidate_execution":False}
    with tempfile.TemporaryDirectory(prefix="local14-") as temp:
        checkout = pathlib.Path(temp)/"checkout"
        create = cmd(["git","worktree","add","--detach",str(checkout),issue["base_commit"]],cwd=root)
        if create.returncode:
            raise GateError("WORKTREE_CREATE_FAILED")
        try:
            validate = cmd(["git","apply","--cached","--check","-"],cwd=checkout,input=data)
            if validate.returncode:
                result["status"]="PATCH_NOT_APPLICABLE"
                return result
            result["patch_applicable"]=True
            result["status"]="PATCH_APPLICABLE_NOT_GRADED"
            if not run_tests:
                return result
            if not image or not IMAGE.fullmatch(image):
                raise GateError("PINNED_LOCAL_IMAGE_REQUIRED")
            if test_command not in ALLOWED_TEST:
                raise GateError("TEST_COMMAND_NOT_ALLOWED")
            # Applying patch does not execute it. Testing is Docker-only.
            apply=cmd(["git","apply","--index","-"],cwd=checkout,input=data)
            if apply.returncode:
                raise GateError("PATCH_APPLY_FAILED")
            docker=cmd(["docker","image","inspect",image],timeout=30)
            if docker.returncode:
                raise GateError("IMAGE_NOT_PRESENT_NO_PULL")
            container=cmd(["docker","run","--rm","--network","none","--read-only",
                           "--cap-drop","ALL","--security-opt","no-new-privileges",
                           "--pids-limit","128","--memory","2g","--cpus","2",
                           "--user","65534:65534","--tmpfs","/tmp:rw,nosuid,noexec,size=128m",
                           "--mount",f"type=bind,src={checkout},dst=/src,readonly",
                           "--workdir","/src",image,
                           "sh","-c",test_command],timeout=240)
            result["test_status"]="PASS" if container.returncode==0 else "FAIL"
            result["status"]="PUBLIC_TESTS_PASS" if container.returncode==0 else "PUBLIC_TESTS_FAIL"
            result["test_exit_code"]=container.returncode
            result["stdout_tail"]=container.stdout.decode("utf-8",errors="replace")[-1500:]
            result["stderr_tail"]=container.stderr.decode("utf-8",errors="replace")[-1500:]
            return result
        finally:
            cmd(["git","worktree","remove","--force",str(checkout)],cwd=root)

def main():
    p=argparse.ArgumentParser()
    for arg in ("repo","issue-json","patch","output"):
        p.add_argument("--"+arg,required=True)
    p.add_argument("--run-tests",action="store_true")
    p.add_argument("--image")
    p.add_argument("--test-command")
    args=p.parse_args()
    spec=json.loads(pathlib.Path(args.issue_json).read_text(encoding="utf-8"))
    if set(spec)!={"schema","base_commit","allowed_files"} or spec["schema"]!=1 or not SHA.fullmatch(spec["base_commit"]):
        raise GateError("ISSUE_SPEC_INVALID")
    report=grade(args.repo,spec,args.patch,args.image,args.test_command,args.run_tests)
    target=pathlib.Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"test_status":report["test_status"],"output":str(target)}))

if __name__=="__main__":
    main()
