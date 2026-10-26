"""LOCAL-WINNER-02: qualify exact SWE-bench dev case identities and patch applicability.

No models, code execution, test imports, or Docker. Fetch only public benchmark
rows and Git commits, then check gold/test patch *structure and applicability*.
Never upload patch contents, oracles, prompts or reference source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

from select_cases import DATASET, API, MAX_BYTES, extract, freeze
from reconcile import hash_bytes

EXPECTED_DATASET_SHA256 = "b82cf1a71e34f752a1870335f1f987f41256ecf2ca33b9c96a5f2aa811533627"
EXPECTED_SELECTION_IDS = (
    "pvlib__pvlib-python-1854",
    "sqlfluff__sqlfluff-2419",
    "pyvista__pyvista-4315",
    "sqlfluff__sqlfluff-1625",
    "pydicom__pydicom-1256",
    "pylint-dev__astroid-1196",
    "pvlib__pvlib-python-1707",
    "pydicom__pydicom-901",
)
SHA = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
DIFF = re.compile(r"^diff --git a/(.+) b/(.+)$", re.M)
DENIED = ("GIT binary patch", "Binary files ", "rename from ", "rename to ",
          "copy from ", "copy to ", "new file mode 120000",
          "old mode 120000", "Subproject commit ")
VALID_STATUS = {"APPLICABLE_STATIC_ONLY", "FETCH_FAILED", "SOURCE_COMMIT_MISMATCH",
                "UNSAFE_REFERENCE_PATCH", "GOLD_PATCH_NOT_APPLICABLE",
                "TEST_PATCH_NOT_APPLICABLE", "PATCH_DATASET_IDENTITY_MISMATCH",
                "GIT_VALIDATION_ERROR"}


def official_rows():
    query = urllib.parse.urlencode({
        "dataset":DATASET, "config":"default", "split":"dev",
        "offset":0, "length":100
    })
    req = urllib.request.Request(API+"?"+query,headers={"User-Agent":"local-winner02-qualification/1"})
    with urllib.request.urlopen(req, timeout=45) as response:
        raw = response.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:
        raise ValueError("DATASET_RESPONSE_TOO_LARGE")
    return raw


def patch_paths(blob):
    if not isinstance(blob,str) or len(blob)>100000 or not blob.strip():
        raise ValueError("UNSAFE_OR_EMPTY_PATCH")
    if any(denied in blob for denied in DENIED) or "\x00" in blob:
        raise ValueError("DISALLOWED_REFERENCE_DIFF")
    paths = DIFF.findall(blob)
    if not paths or len(paths)>30:
        raise ValueError("PATCH_FILE_COUNT_INVALID")
    for before, after in paths:
        for entry in (before,after):
            if (entry.startswith("/") or entry.startswith("./") or "\\" in entry
                or any(p in ("", ".", "..") for p in entry.split("/"))
                or any(ord(ch)<32 for ch in entry)):
                raise ValueError("UNSAFE_REFERENCE_PATH")
    return paths


def run_git(directory, args, timeout=80, env=None):
    return subprocess.run(["git",*args],cwd=directory,capture_output=True,text=True,
         timeout=timeout,check=False,env=env,encoding="utf-8",errors="replace")


def safe_git_result(result):
    # No output from git (which could contain patch text, file contents, URLs)
    # is included in public artifacts.
    return {"returncode":result.returncode}


def validate_case(repo, commit, gold, tests, git_timeout=90):
    if not REPO.fullmatch(repo) or not SHA.fullmatch(commit):
        raise ValueError("REPO_OR_COMMIT_NOT_VALID")
    try:
        gold_paths=patch_paths(gold)
        test_paths=patch_paths(tests)
    except ValueError:
        return {"status":"UNSAFE_REFERENCE_PATCH","gold_path_count":0,"test_path_count":0}

    with tempfile.TemporaryDirectory(prefix="winner02-") as tmp:
        root=Path(tmp)
        env=os.environ.copy()
        env.update({"GIT_TERMINAL_PROMPT":"0", "GIT_LFS_SKIP_SMUDGE":"1",
                    "GIT_CONFIG_NOSYSTEM":"1", "GIT_OPTIONAL_LOCKS":"0"})
        # No scripts or project code executed: git object transport and diff only.
        cmds = [
            ["init","--quiet"],
            ["remote","add","origin",f"https://github.com/{repo}.git"],
            ["-c","protocol.version=2","fetch","--quiet","--no-tags","--depth=1","origin",commit],
            ["-c","advice.detachedHead=false","checkout","--quiet","--detach","FETCH_HEAD"],
        ]
        for index,args in enumerate(cmds):
            try:
                p=run_git(root,args,git_timeout,env)
            except subprocess.TimeoutExpired:
                return {"status":"FETCH_FAILED","failed_stage":index}
            if p.returncode!=0:
                return {"status":"FETCH_FAILED","failed_stage":index}
        actual=run_git(root,["rev-parse","HEAD"],10,env)
        if actual.returncode!=0 or actual.stdout.strip()!=commit:
            return {"status":"SOURCE_COMMIT_MISMATCH"}
        if run_git(root,["status","--porcelain"],10,env).stdout.strip():
            return {"status":"GIT_VALIDATION_ERROR"}

        # Gold/test bytes never enter the uploaded report.
        gold_file=root.parent/("gold-"+root.name+".patch")
        tests_file=root.parent/("test-"+root.name+".patch")
        gold_file.write_bytes(gold.encode("utf-8"))
        tests_file.write_bytes(tests.encode("utf-8"))
        try:
            p=run_git(root,["apply","--check",str(gold_file)],20,env)
            if p.returncode!=0:
                return {"status":"GOLD_PATCH_NOT_APPLICABLE",
                        "gold_path_count":len(gold_paths),"test_path_count":len(test_paths)}
            p=run_git(root,["apply",str(gold_file)],20,env)
            if p.returncode!=0:
                return {"status":"GIT_VALIDATION_ERROR"}
            p=run_git(root,["apply","--check",str(tests_file)],20,env)
            if p.returncode!=0:
                return {"status":"TEST_PATCH_NOT_APPLICABLE",
                        "gold_path_count":len(gold_paths),"test_path_count":len(test_paths)}
            return {"status":"APPLICABLE_STATIC_ONLY","gold_path_count":len(gold_paths),
                    "test_path_count":len(test_paths),"source_sha":actual.stdout.strip()}
        finally:
            gold_file.unlink(missing_ok=True)
            tests_file.unlink(missing_ok=True)


def qualify(raw, git_timeout=90, limit=None):
    if hash_bytes(raw)!=EXPECTED_DATASET_SHA256:
        raise ValueError("CANONICAL_DATASET_BYTES_CHANGED")
    manifest,_=freeze(raw)
    selected=manifest["cases"]
    if tuple(x["case_id"] for x in selected)!=EXPECTED_SELECTION_IDS:
        raise ValueError("SELECTION_CHANGED")
    indexed={row["instance_id"]:row for row in extract(raw)}
    rows=[]
    for item in selected if limit is None else selected[:limit]:
        x=indexed[item["case_id"]]
        if any(hash_bytes(x[k].encode("utf-8"))!=item[hash_field]
               for k,hash_field in (("problem_statement","prompt_sha256"),
                                   ("test_patch","oracle_sha256"),
                                   ("patch","gold_patch_sha256"))):
            result={"status":"PATCH_DATASET_IDENTITY_MISMATCH"}
        else:
            result=validate_case(item["source_repo"],item["base_commit"],
                                 x["patch"],x["test_patch"],git_timeout)
        assert result["status"] in VALID_STATUS
        rows.append({"case_id":item["case_id"],"stage":item["stage"],
                     "source_repo":item["source_repo"],"base_commit":item["base_commit"],
                     "gold_patch_sha256":item["gold_patch_sha256"],
                     "test_patch_sha256":item["oracle_sha256"],**result,
                     "functional_tests_executed":False,
                     "gold_resolved":None,"baseline_reproduced":None})
        print("STATIC_CASE",item["case_id"],result["status"],flush=True)
    good=sum(x["status"]=="APPLICABLE_STATIC_ONLY" for x in rows)
    status = ("ALL_STATIC_APPLICABLE_ORACLE_NOT_EVALUATED" if good==len(rows)==8 else
              "PARTIAL_STATIC_CHECKS" if limit is not None else "BLOCKED_STATIC_QUALIFICATION")
    return {"schema":1,"phase":"LOCAL-WINNER-02","dataset":DATASET,"split":"dev",
            "dataset_sha256":hash_bytes(raw),"cases_expected":8,"cases_inspected":len(rows),
            "static_applicable":good,"status":status,
            "model_generations":0,"tests_executed":0,
            "note":"No functional score. Reference patches were checked, not executed. No gold/test patch bytes in this report.",
            "cases":rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    g=parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--official-fetch",action="store_true")
    g.add_argument("--dataset-file",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--git-timeout",type=int,default=90)
    a=parser.parse_args()
    if a.output.exists():
        parser.error("refuse overwrite of previous evidence")
    if not 20<=a.git_timeout<=180:
        parser.error("git timeout must be 20..180 seconds")
    raw=official_rows() if a.official_fetch else a.dataset_file.read_bytes()
    report=qualify(raw,a.git_timeout)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("QUALIFICATION",json.dumps({"status":report["status"],
          "count":report["static_applicable"],"model_generations":0,
          "output":str(a.output)}),flush=True)
    return 0 if report["status"]=="ALL_STATIC_APPLICABLE_ORACLE_NOT_EVALUATED" else 2


if __name__=="__main__":
    try:
        sys.exit(main())
    except (OSError,ValueError,TypeError,json.JSONDecodeError) as err:
        print("STATIC_QUALIFICATION_ABORT",type(err).__name__,str(err)[:180],file=sys.stderr)
        sys.exit(2)
