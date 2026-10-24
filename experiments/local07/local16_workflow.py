"""LOCAL-16 persistent task sessions with immutable retrieval and manual patch approval.

Only the explicit generate action can invoke Ollama. No automatic retry, fallback,
execution of model-produced source, commits, merge or candidate test execution.
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys

from executor_bridge import ContractError, MAX_ISSUE_CHARS, prepare
from integrated_edit import git
from model_profiles import PROFILES, select_profile
from profile_cli import provenance, run as generate_patch, save_outputs
from reviewed_patch import verify as review_patch, apply_reviewed

MANIFEST = "session.json"
ISSUE = "issue.json"
REQUEST = "request.json"
REPORT = "report.json"
PATCH = "candidate.patch"
RESPONSE = "response.json"
MAX_MANIFEST = 1024 * 1024
REASON = re.compile(r"^[A-Z][A-Z0-9_]{0,95}$")


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def read_bounded(path, limit=MAX_MANIFEST):
    with path.open("rb") as stream:
        blob = stream.read(limit + 1)
    if len(blob) > limit:
        raise ContractError("SESSION_ARTIFACT_TOO_LARGE")
    return blob


def location(session):
    path = pathlib.Path(session)
    if path.is_symlink():
        raise ContractError("SESSION_SYMLINK_FORBIDDEN")
    return path.resolve()


def tracked_sources(repo, selected):
    """Bind retrieved context to tracked Git source and current file bytes."""
    result = {}
    for name in selected:
        p = pathlib.PurePosixPath(name)
        if (not name or p.is_absolute() or ".." in p.parts
                or p.as_posix() != name or p.suffix != ".py"):
            raise ContractError("UNSAFE_RETRIEVED_FILE")
        full = repo.joinpath(*p.parts)
        if full.is_symlink() or not full.is_file() or not full.resolve().is_relative_to(repo):
            raise ContractError("INVALID_RETRIEVED_FILE")
        try:
            indexed = git(repo, "ls-files", "--error-unmatch", "--", name).strip()
        except RuntimeError as exc:
            raise ContractError("UNTRACKED_RETRIEVED_FILE") from exc
        if indexed != name:
            raise ContractError("UNTRACKED_RETRIEVED_FILE")
        result[name] = sha(full.read_bytes())
    return result


def create(repo, session, profile_name, task):
    profile = select_profile(profile_name)
    if not isinstance(task, str) or not task.strip() or len(task) > MAX_ISSUE_CHARS:
        raise ContractError("INVALID_ISSUE")
    root = pathlib.Path(repo).resolve()
    head = provenance(root)
    path = location(session)
    if path.is_relative_to(root):
        raise ContractError("SESSION_INSIDE_SOURCE_REPOSITORY")
    if path.exists():
        raise ContractError("SESSION_ALREADY_EXISTS")
    if not path.parent.is_dir():
        raise ContractError("SESSION_PARENT_MISSING")
    request = prepare(root, task)
    sources = tracked_sources(root, request.selected_files)
    if head != provenance(root):
        raise ContractError("SOURCE_CHANGED_DURING_PREPARATION")
    issue_blob = canonical({"problem_statement": task})
    request_blob = canonical(request.to_json())
    manifest = {
        "schema": 1, "profile": profile.manifest(),
        "source_root": str(root), "source_commit": head,
        "issue_sha256": sha(issue_blob),
        "request_sha256": sha(request_blob),
        "source_files_sha256": sources,
        "selected_files": list(request.selected_files),
        "selection_policy": "LOCAL_09_TOP_2"
    }
    path.mkdir()
    try:
        save_outputs([
            (path / ISSUE, issue_blob),
            (path / REQUEST, request_blob),
            (path / MANIFEST, canonical(manifest))
        ])
    except BaseException:
        path.rmdir()
        raise
    return {"status": "SESSION_PREPARED", "session": str(path),
            "profile": profile.name, "base_commit": head,
            "selected_files": list(request.selected_files),
            "request_sha256": sha(request_blob),
            "inference_calls_attempted": 0}


def load(session, *, check_sources=True):
    path = location(session)
    if not path.is_dir():
        raise ContractError("SESSION_NOT_FOUND")
    try:
        manifest = json.loads(read_bounded(path / MANIFEST).decode("utf-8"))
        issue_blob = read_bounded(path / ISSUE)
        request_blob = read_bounded(path / REQUEST)
        issue = json.loads(issue_blob)
        saved_request = json.loads(request_blob)
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ContractError("SESSION_INVALID_JSON") from exc
    if (not isinstance(manifest, dict) or manifest.get("schema") != 1
            or not isinstance(issue, dict) or set(issue) != {"problem_statement"}
            or sha(issue_blob) != manifest.get("issue_sha256")
            or sha(request_blob) != manifest.get("request_sha256")):
        raise ContractError("SESSION_EVIDENCE_MISMATCH")
    identity = manifest.get("profile")
    if not isinstance(identity, dict):
        raise ContractError("SESSION_PROFILE_INVALID")
    profile = select_profile(identity.get("name"))
    if identity != profile.manifest():
        raise ContractError("SESSION_POLICY_DRIFT")
    raw_root = manifest.get("source_root")
    if not isinstance(raw_root, str):
        raise ContractError("SESSION_REPOSITORY_INVALID")
    root = pathlib.Path(raw_root).resolve()
    if path.is_relative_to(root):
        raise ContractError("SESSION_INSIDE_SOURCE_REPOSITORY")
    if check_sources:
        if provenance(root) != manifest.get("source_commit"):
            raise ContractError("SESSION_BASE_COMMIT_DRIFT")
        request = prepare(root, issue["problem_statement"])
        if canonical(request.to_json()) != request_blob:
            raise ContractError("SESSION_CONTEXT_DRIFT")
        sources = tracked_sources(root, request.selected_files)
        if (sources != manifest.get("source_files_sha256")
                or list(request.selected_files) != manifest.get("selected_files")):
            raise ContractError("SESSION_SOURCE_DRIFT")
    return path, root, manifest, issue, saved_request


def generate(session, *, offline_response_json=None, timeout=180):
    path, root, manifest, _, _ = load(session)
    if any((path / key).exists() for key in (REPORT, PATCH, RESPONSE)):
        raise ContractError("SESSION_ALREADY_GENERATED")
    response_path = None if offline_response_json is None else pathlib.Path(offline_response_json).resolve()
    if response_path is not None and response_path.is_relative_to(root):
        raise ContractError("REPLAY_INSIDE_SOURCE_REPOSITORY")
    outcome = generate_patch(
        root, path / ISSUE, manifest["profile"]["name"],
        path / REPORT, path / PATCH, timeout=timeout,
        offline_response_json=response_path, response_json_path=path / RESPONSE
    )
    return {"status": outcome["status"], "session": str(path),
            "mode": outcome["execution"]["mode"],
            "profile": manifest["profile"]["name"],
            "patch_sha256": outcome["validation"]["patch_sha256"],
            "inference_calls_attempted": int(response_path is None),
            "human_review_required": True}


def check(session):
    path, root, manifest, _, request = load(session)
    if not all((path / item).is_file() for item in (REPORT, PATCH, RESPONSE)):
        raise ContractError("SESSION_NOT_GENERATED")
    try:
        report = json.loads(read_bounded(path / REPORT))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("SESSION_REPORT_INVALID") from exc
    if not isinstance(report, dict) or report.get("request") != request:
        raise ContractError("SESSION_REQUEST_MISMATCH")
    execution = report.get("execution")
    if not isinstance(execution, dict):
        raise ContractError("SESSION_EXECUTION_MISSING")
    if (execution.get("selected_profile") != manifest["profile"]
            or execution.get("system_policy_sha256") != manifest["profile"]["fingerprint_sha256"]
            or execution.get("mode") not in {"offline_replay", "local_inference"}
            or execution.get("model_invoked") is not (execution["mode"] == "local_inference")):
        raise ContractError("SESSION_EXECUTION_MISMATCH")
    if sha(read_bounded(path / RESPONSE, 256 * 1024)) != execution.get("response_sha256"):
        raise ContractError("SESSION_RESPONSE_MISMATCH")
    record, _ = review_patch(root, path / REPORT, path / PATCH)
    return {**record, "session": str(path), "human_review_required": True}


def approve(session, approved_sha256):
    check(session)
    path, root, _, _, _ = load(session)
    result = apply_reviewed(root, path / REPORT, path / PATCH, approved_sha256)
    return {**result, "session": str(path), "human_review_required": False}


def status(session):
    path, _, manifest, _, _ = load(session, check_sources=False)
    generated = (path / REPORT).is_file() and (path / PATCH).is_file()
    if generated:
        try:
            review = check(session)
            status_value = review["status"]
            digest = review["patch_sha256"]
        except (ContractError, OSError, RuntimeError, ValueError):
            status_value = "SOURCE_OR_PATCH_REQUIRES_INSPECTION"
            digest = None
    else:
        status_value = "SESSION_PREPARED"
        digest = None
    return {"status": status_value, "session": str(path),
            "profile": manifest["profile"], "patch_sha256": digest,
            "model_invoked_by_status": False}


def main():
    parser = argparse.ArgumentParser(description="LOCAL-16 one-task operator workflow")
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("new", help="Freeze task and retrieved context without inference")
    new.add_argument("--repo", required=True)
    new.add_argument("--session", required=True)
    new.add_argument("--profile", choices=tuple(PROFILES), default="principal")
    task_arg = new.add_mutually_exclusive_group(required=True)
    task_arg.add_argument("--task")
    task_arg.add_argument("--task-file")
    gen = sub.add_parser("generate", help="One explicit Ollama call or offline replay")
    gen.add_argument("--session", required=True)
    gen.add_argument("--offline-response-json")
    gen.add_argument("--timeout", type=int, default=180)
    checked = sub.add_parser("check", help="Independent LOCAL-14 review, no model")
    checked.add_argument("--session", required=True)
    applied = sub.add_parser("apply", help="Human-approved unstaged patch, no model")
    applied.add_argument("--session", required=True)
    applied.add_argument("--approve-sha256", required=True)
    current = sub.add_parser("status", help="Inspect session without model")
    current.add_argument("--session", required=True)
    args = parser.parse_args()
    try:
        if args.command == "new":
            task = args.task if args.task_file is None else read_bounded(
                pathlib.Path(args.task_file), MAX_ISSUE_CHARS
            ).decode("utf-8")
            result = create(args.repo, args.session, args.profile, task)
        elif args.command == "generate":
            result = generate(args.session,
                              offline_response_json=args.offline_response_json,
                              timeout=args.timeout)
        elif args.command == "check":
            result = check(args.session)
        elif args.command == "apply":
            result = approve(args.session, args.approve_sha256)
        else:
            result = status(args.session)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ContractError, OSError, RuntimeError, ValueError, UnicodeError, KeyError) as exc:
        code = str(exc)
        reason = code if REASON.fullmatch(code) else "WORKFLOW_OPERATION_FAILED"
        print(json.dumps({"status": "BLOCKED", "reason": reason}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
