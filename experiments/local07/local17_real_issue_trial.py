"""LOCAL-17: preregistered real defect in the LOCAL repository, zero model calls.

This is an actual bug in the pinned reviewed_patch.py, not a synthetic fixture:
_external_path resolves the input before checking is_symlink, which makes the
evidence-symlink prohibition ineffective for links that resolve to normal files.

Only prepares a frozen, independently auditable LOCAL-16 session. Generation,
candidate application and candidate execution are NOT part of this command.
"""
import argparse
import ast
import json
import pathlib
import re
import sys

from executor_bridge import ContractError, prepare
from integrated_edit import git
from local16_workflow import create as create_session
from profile_cli import provenance

CASE_ID = "oigorbrito__local-evidence-symlink-001"
PINNED_COMMIT = "a3e80e82788d798faa1a83b5a99762412cdaf61b"
TARGET_PATH = "experiments/local07/reviewed_patch.py"
PINNED_GIT_BLOB = "bfed49f4603e6f54c240dc633acc4aaf80e7ccda"
PROFILE = "principal"
DESCRIPTION = (
    "A security regression exists in experiments/local07/reviewed_patch.py. "
    "The _external_path validation is documented to reject evidence "
    "supplied through symbolic links, but an input symlink to a normal "
    "evidence file outside the source repository is accepted instead. "
    "Reproduction: with a clean checkout, create a real JSON evidence "
    "file outside the Git repository, create a symlink path pointing to "
    "it, and pass that symlink path to _external_path(path, root). "
    "Observed: the function accepts the input. Expected: reject this "
    "symlink with EVIDENCE_SYMLINK_FORBIDDEN, continue accepting ordinary "
    "file paths outside the repository, and keep rejecting paths inside "
    "the repository. Preserve the public function interface. "
    "Change only experiments/local07/reviewed_patch.py. "
    "Do not execute candidate code or modify other files."
)
UPPER = re.compile(r"^[A-Z][A-Z0-9_]{0,100}$")


def verify_pinned_source(repo):
    root = pathlib.Path(repo).resolve()
    head = provenance(root)
    if head != PINNED_COMMIT:
        raise ContractError("REAL_ISSUE_BASE_COMMIT_MISMATCH")
    try:
        blob = git(root, "rev-parse", "HEAD:" + TARGET_PATH).strip()
    except RuntimeError as exc:
        raise ContractError("REAL_ISSUE_BLOB_UNAVAILABLE") from exc
    if blob != PINNED_GIT_BLOB:
        raise ContractError("REAL_ISSUE_BASE_BLOB_MISMATCH")
    source = root.joinpath(*pathlib.PurePosixPath(TARGET_PATH).parts)
    if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(root):
        raise ContractError("REAL_ISSUE_TARGET_PATH_INVALID")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    target = next((node for node in tree.body
                   if isinstance(node, ast.FunctionDef)
                   and node.name == "_external_path"), None)
    if target is None:
        raise ContractError("REAL_ISSUE_FUNCTION_MISSING")
    # The already-frozen blob ensures these checks characterize precisely
    # the known broken source, not a heuristic over a modified candidate.
    return root


def prepare_case(repo, session):
    root = verify_pinned_source(repo)
    request = prepare(root, DESCRIPTION)
    if TARGET_PATH not in request.selected_files[:2]:
        # Record the retrieval miss rather than cherry-picking another task.
        raise ContractError("REAL_ISSUE_RETRIEVAL_MISS")
    output = create_session(root, session, PROFILE, DESCRIPTION)
    if TARGET_PATH not in output["selected_files"]:
        raise ContractError("REAL_ISSUE_RETRIEVAL_DRIFT")
    return {
        "schema": 1,
        "gate": "LOCAL-17",
        "case_id": CASE_ID,
        "status": "REAL_ISSUE_PREPARED",
        "base_commit": PINNED_COMMIT,
        "base_blob_git_sha1": PINNED_GIT_BLOB,
        "source_path": TARGET_PATH,
        "profile": PROFILE,
        "session": output["session"],
        "retrieval_top_2_contains_target": True,
        "inference_calls_attempted": 0,
        "candidate_code_executed": False,
        "model_patch_generated": False,
        "real_issue_resolved": "NOT_EVALUATED",
        "evaluator_truth_exposed_to_model": False
    }


def main():
    parser = argparse.ArgumentParser(description="Prepare one preregistered real Git bug, no LLM calls")
    parser.add_argument("--repo", required=True, help="Clean worktree at pinned LOCAL-17 base commit")
    parser.add_argument("--session", required=True, help="New evidence directory outside checkout")
    args = parser.parse_args()
    try:
        print(json.dumps(prepare_case(args.repo, args.session), sort_keys=True))
        return 0
    except (OSError, SyntaxError, RuntimeError, ValueError, KeyError) as exc:
        code = str(exc)
        reason = code if UPPER.fullmatch(code) else "REAL_ISSUE_PREPARATION_BLOCKED"
        print(json.dumps({"status": "BLOCKED", "reason": reason, "case_id": CASE_ID}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
