"""LOCAL-16: explicit, one-file patch application after human SHA-256 approval.

No inferred authorization: validation and application are separate CLI invocations.
No generated code execution, tests, commits, resets, shell interpolation or auto-merge.
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess

from executor_bridge import ContractError
from static_patch_gate import grade, verify_patch

HASH = re.compile(r"^[0-9a-f]{64}$")
MAX_REPORT_BYTES = 1024 * 1024
MAX_PATCH_BYTES = 256000


def _git(root, *parts, input_bytes=None):
    proc = subprocess.run(
        ["git", *parts], cwd=root, input=input_bytes, capture_output=True,
        timeout=60
    )
    if proc.returncode != 0:
        raise ContractError("GIT_" + parts[0].upper().replace("-", "_") + "_FAILED")
    return proc.stdout.decode("utf-8", errors="replace").strip()


def _read_bounded(path, limit, kind):
    with path.open("rb") as stream:
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise ContractError(kind + "_TOO_LARGE")
    return payload


def _external_path(path, root):
    resolved = pathlib.Path(path).resolve()
    if resolved.is_relative_to(root):
        raise ContractError("EVIDENCE_INSIDE_SOURCE_REPOSITORY")
    if resolved.is_symlink():
        raise ContractError("EVIDENCE_SYMLINK_FORBIDDEN")
    return resolved


def _root(repo):
    root = pathlib.Path(repo).resolve()
    if not (root / ".git").exists():
        raise ContractError("REQUIRES_GIT_CHECKOUT")
    if _git(root, "status", "--porcelain"):
        raise ContractError("DIRTY_SOURCE_REPOSITORY")
    return root


def verify(repo, report_file, patch_file):
    root = _root(repo)
    report_path = _external_path(report_file, root)
    patch_path = _external_path(patch_file, root)
    try:
        report = json.loads(_read_bounded(report_path, MAX_REPORT_BYTES, "REPORT"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("REPORT_INVALID_JSON") from exc
    if not isinstance(report, dict) or report.get("schema") != 1:
        raise ContractError("REPORT_INVALID_SCHEMA")
    if report.get("status") != "PATCH_APPLICABLE_NOT_GRADED":
        raise ContractError("REPORT_UNAPPROVED_STATUS")
    validation = report.get("validation")
    request = report.get("request")
    if not isinstance(validation, dict) or not isinstance(request, dict):
        raise ContractError("REPORT_INCOMPLETE")
    allowed = request.get("allowed_files")
    if (not isinstance(allowed, list) or not 1 <= len(allowed) <= 2
            or any(not isinstance(p, str) for p in allowed)):
        raise ContractError("INVALID_ALLOWLIST")
    head = _git(root, "rev-parse", "HEAD")
    if head != validation.get("commit"):
        raise ContractError("BASE_COMMIT_MISMATCH")
    patch = _read_bounded(patch_path, MAX_PATCH_BYTES, "PATCH")
    sha = hashlib.sha256(patch).hexdigest()
    if sha != validation.get("patch_sha256"):
        raise ContractError("PATCH_DIGEST_MISMATCH")
    try:
        path = verify_patch(patch, allowed)
    except ValueError as exc:
        raise ContractError("PATCH_SCOPE_INVALID") from exc
    if path != validation.get("edited_file"):
        raise ContractError("EDITED_FILE_MISMATCH")
    destination = root.joinpath(*pathlib.PurePosixPath(path).parts)
    if not destination.is_file() or destination.is_symlink() or not destination.resolve().is_relative_to(root):
        raise ContractError("INVALID_DESTINATION")
    if hashlib.sha256(destination.read_bytes()).hexdigest() != validation.get("source_sha256"):
        raise ContractError("SOURCE_BLOB_MISMATCH")
    gate = grade(root, {"base_commit": head, "allowed_files": allowed}, patch_path)
    if gate["status"] != "PATCH_APPLICABLE_NOT_GRADED":
        raise ContractError("STATIC_PATCH_GATE_FAILED")
    _git(root, "apply", "--check", "-", input_bytes=patch)
    return {
        "schema": 1, "status": "PATCH_READY_FOR_REVIEW",
        "repo_head": head, "path": path,
        "patch_sha256": sha, "source_sha256": validation["source_sha256"],
        "official_resolution": "NOT_EVALUATED",
        "code_execution": False, "candidate_tests_run": False
    }, patch


def apply_reviewed(repo, report_file, patch_file, approved_sha256):
    review, patch = verify(repo, report_file, patch_file)
    if not isinstance(approved_sha256, str) or not HASH.fullmatch(approved_sha256):
        raise ContractError("APPROVAL_SHA256_REQUIRED")
    if approved_sha256 != review["patch_sha256"]:
        raise ContractError("APPROVAL_SHA256_MISMATCH")
    root = _root(repo)
    if _git(root, "rev-parse", "HEAD") != review["repo_head"]:
        raise ContractError("BASE_COMMIT_MISMATCH")
    _git(root, "apply", "--check", "-", input_bytes=patch)
    _git(root, "apply", "-", input_bytes=patch)
    # No tests, commits or generated-code execution: only a visible unstaged diff.
    return {**review, "status": "PATCH_APPLIED_UNSTAGED",
            "code_execution": False, "candidate_tests_run": False}


def main():
    parser = argparse.ArgumentParser(
        description="Validate candidate; apply only with an explicit reviewed SHA256"
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--patch", required=True)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--approve-sha256", metavar="HASH")
    args = parser.parse_args()
    try:
        if args.check:
            result, _ = verify(args.repo, args.report, args.patch)
        else:
            result = apply_reviewed(
                args.repo, args.report, args.patch, args.approve_sha256
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ContractError, OSError) as exc:
        # Error codes only: never print generated source or filesystem payload.
        code = str(exc)
        print(json.dumps({"status": "BLOCKED",
                          "reason": code if code.isupper() and len(code) <= 96 else "IO_ERROR"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
