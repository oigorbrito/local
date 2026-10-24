"""LOCAL-13: real-issue retrieval gate, no model calls and no gold-patch leakage.

Inputs are a pinned source checkout, user-visible issue statement, and separately
maintained evaluator metadata. Ground-truth paths are used ONLY after retrieval.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
from retrieve_context import retrieve


class GateError(ValueError):
    pass


def git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                       timeout=30, check=False)
    if p.returncode:
        raise GateError("GIT_" + args[0].upper() + "_FAILED")
    return p.stdout.strip()


def evaluate(repo, issue_path, evaluator_path):
    root = pathlib.Path(repo).resolve()
    if not (root / ".git").exists():
        raise GateError("NOT_GIT_CHECKOUT")
    if git(root, "status", "--porcelain"):
        raise GateError("DIRTY_CHECKOUT")
    head = git(root, "rev-parse", "HEAD")
    issue_data = pathlib.Path(issue_path).read_bytes()
    eval_data = pathlib.Path(evaluator_path).read_bytes()
    if len(issue_data) > 64 * 1024 or len(eval_data) > 64 * 1024:
        raise GateError("INPUT_TOO_LARGE")
    issue = json.loads(issue_data)
    truth = json.loads(eval_data)
    if set(issue) != {"schema", "issue_id", "base_commit", "problem_statement"}:
        raise GateError("ISSUE_SCHEMA")
    if set(truth) != {"schema", "issue_id", "target_files"}:
        raise GateError("EVALUATOR_SCHEMA")
    if issue["schema"] != 1 or truth["schema"] != 1:
        raise GateError("SCHEMA_VERSION")
    if issue["issue_id"] != truth["issue_id"]:
        raise GateError("ISSUE_ID_MISMATCH")
    if issue["base_commit"] != head:
        raise GateError("COMMIT_MISMATCH")
    statement = issue["problem_statement"]
    if not isinstance(statement, str) or not statement.strip() or len(statement) > 32000:
        raise GateError("INVALID_STATEMENT")
    targets = truth["target_files"]
    if not isinstance(targets, list) or not targets or len(targets) > 20:
        raise GateError("INVALID_TARGETS")
    for target in targets:
        if not isinstance(target, str) or not target.endswith(".py"):
            raise GateError("INVALID_TARGETS")
        rel = pathlib.PurePosixPath(target)
        if rel.is_absolute() or ".." in rel.parts or rel.as_posix() != target:
            raise GateError("INVALID_TARGETS")
    # Crucially: retrieval receives only source and the issue statement.
    # The private evaluator file is never passed to retrieval or a model.
    result = retrieve(root, statement)
    ranked = result["selected_files"]
    hit_1 = bool(ranked[:1] and ranked[0] in targets)
    hit_2 = any(x in targets for x in ranked[:2])
    return {
        "schema": 1, "gate": "LOCAL-13", "issue_id": issue["issue_id"],
        "base_commit": head,
        "statement_sha256": hashlib.sha256(statement.encode("utf-8")).hexdigest(),
        "evaluator_sha256": hashlib.sha256(eval_data).hexdigest(),
        "top_1": ranked[:1], "top_2": ranked[:2],
        "recall_at_1": int(hit_1), "recall_at_2": int(hit_2),
        "retrieved_count": len(ranked),
        "generation_attempted": False,
        "patch_validated": False,
        "issue_resolved": "NOT_EVALUATED",
        "target_files_exposed_to_model": False
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--issue-json", required=True)
    parser.add_argument("--evaluator-json", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = evaluate(args.repo, args.issue_json, args.evaluator_json)
    destination = pathlib.Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"gate": report["gate"], "recall_at_1": report["recall_at_1"],
                      "recall_at_2": report["recall_at_2"], "report": str(destination)}))


if __name__ == "__main__":
    main()
