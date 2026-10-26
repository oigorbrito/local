"""LOCAL-20: one invocation progresses through independent, bounded local gates.

An accepted gate immediately starts the next one. A rejected gate consumes the
session and records the reason; there is no model retry, fallback, candidate
execution, patch application, Git mutation or automatic merge.
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import time

from executor_bridge import ContractError, MAX_ISSUE_CHARS, MAX_RESPONSE_BYTES
from local16_workflow import (
    ATTEMPT, FAILURE, MANIFEST, PATCH, REPORT, REQUEST, RESPONSE,
    canonical, check, create, generate, native_valid, inspect_native,
)
from model_profiles import select_profile
from profile_cli import provenance, save_outputs

CASE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{3,99}$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GATE_REPORT = "pipeline-report.json"
GATE_EVENTS = "pipeline-events.jsonl"
USED_CASE_IDS = frozenset({"oigorbrito__local-evidence-symlink-001"})


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def git_blob(repo, target):
    process = subprocess.run(
        ["git", "rev-parse", "HEAD:" + target],
        cwd=repo, capture_output=True, text=True, timeout=30,
    )
    if process.returncode != 0:
        raise ContractError("PINNED_TARGET_NOT_TRACKED")
    return process.stdout.strip()


def pinned_inputs(repo, session, task_file, *, expected_head, expected_blob,
                  expected_task_sha256, target, case_id):
    root = pathlib.Path(repo).resolve()
    evidence = pathlib.Path(session)
    source = pathlib.Path(task_file)
    if not CASE_ID.fullmatch(case_id) or case_id in USED_CASE_IDS:
        raise ContractError("CASE_ID_INVALID_OR_CONSUMED")
    if not SHA1.fullmatch(expected_head) or not SHA1.fullmatch(expected_blob):
        raise ContractError("INVALID_GIT_PIN")
    if not SHA256.fullmatch(expected_task_sha256):
        raise ContractError("INVALID_TASK_PIN")
    relative = pathlib.PurePosixPath(target)
    if (not target or relative.is_absolute() or ".." in relative.parts
            or relative.as_posix() != target or relative.suffix != ".py"):
        raise ContractError("INVALID_PINNED_TARGET")
    # Refuse paths that would overwrite old evidence or use data from
    # inside the checkout as mutable test descriptions.
    if (evidence.exists() or evidence.is_symlink()
            or source.is_symlink() or not source.is_file()
            or source.resolve().is_relative_to(root)):
        raise ContractError("INPUT_PATH_NOT_ISOLATED")
    if provenance(root) != expected_head:
        raise ContractError("PINNED_HEAD_MISMATCH")
    path = root.joinpath(*relative.parts)
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ContractError("PINNED_TARGET_UNSAFE")
    if git_blob(root, target) != expected_blob:
        raise ContractError("PINNED_BLOB_MISMATCH")
    with source.open("rb") as stream:
        task_bytes = stream.read(MAX_ISSUE_CHARS + 1)
    if len(task_bytes) > MAX_ISSUE_CHARS or digest(task_bytes) != expected_task_sha256:
        raise ContractError("PINNED_TASK_MISMATCH")
    try:
        task = task_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("PINNED_TASK_ENCODING") from exc
    if not task.strip():
        raise ContractError("EMPTY_PINNED_TASK")
    return root, task


def run_pipeline(repo, session, task_file, *, case_id, expected_head,
                 expected_blob, expected_task_sha256, target, timeout=300,
                 profile="principal-localizado", inspector=inspect_native,
                 session_generator=generate, session_checker=check):
    """One complete, non-executing repair attempt with frozen provenance."""
    if type(timeout) is not int or not 1 <= timeout <= 420:
        raise ContractError("INVALID_TIMEOUT")
    if select_profile(profile).output_schema != 2:
        raise ContractError("LOCALIZED_PROFILE_REQUIRED")
    events = []
    path = pathlib.Path(session).resolve()
    created = False
    state = {
        "schema": 1, "case_id": case_id,
        "status": "IN_PROGRESS", "profile": profile,
        "expected_head": expected_head, "expected_blob": expected_blob,
        "target": target, "expected_task_sha256": expected_task_sha256,
        "inference_calls_completed": "UNKNOWN",
        "candidate_code_executed": False, "candidate_tests_run": False,
        "functional_resolution": "NOT_EVALUATED", "events": events,
    }

    def gate(name, operation):
        started = time.monotonic()
        try:
            detail = operation()
        except Exception:
            row = {"gate": name, "status": "BLOCKED",
                   "elapsed_seconds": round(time.monotonic() - started, 3)}
            events.append(row)
            if created:
                with (path / GATE_EVENTS).open("ab") as stream:
                    stream.write(canonical(row))
            raise
        row = {"gate": name, "status": "PASS",
               "elapsed_seconds": round(time.monotonic() - started, 3)}
        if isinstance(detail, dict):
            row.update(detail)
        events.append(row)
        if created:
            with (path / GATE_EVENTS).open("ab") as stream:
                stream.write(canonical(row))
        print(json.dumps(row, ensure_ascii=False), flush=True)
        return detail

    def prepare_gate():
        nonlocal created
        root, task = pinned_inputs(
            repo, path, task_file, expected_head=expected_head,
            expected_blob=expected_blob,
            expected_task_sha256=expected_task_sha256,
            target=target, case_id=case_id,
        )
        result = create(root, path, profile, task)
        created = True
        if target not in result["selected_files"]:
            raise ContractError("PINNED_TARGET_RETRIEVAL_MISS")
        return {"source_commit": result["base_commit"],
                "selected_files": result["selected_files"]}

    def preflight_gate():
        manifest = json.loads((path / MANIFEST).read_text(encoding="utf-8"))
        observed = inspector(profile)
        if not native_valid(observed, manifest):
            raise ContractError("MODEL_PREFLIGHT_FAILED")
        return {"native_model_digest_sha256": observed["native_model_digest_sha256"]}

    def generation_gate():
        result = session_generator(path, timeout=timeout, inspector=inspector)
        if result["status"] != "PATCH_APPLICABLE_NOT_GRADED":
            raise ContractError("MODEL_PATCH_NOT_APPLICABLE")
        state["inference_calls_completed"] = 1 if result["mode"] == "local_inference" else 0
        if state["inference_calls_completed"] != 1:
            raise ContractError("LIVE_INFERENCE_REQUIRED")
        return {"mode": result["mode"], "patch_sha256": result["patch_sha256"]}

    def persistence_gate():
        reply = path / RESPONSE
        report = path / REPORT
        patch = path / PATCH
        if any(not p.is_file() or p.is_symlink() for p in (reply, report, patch)):
            raise ContractError("GENERATION_ARTIFACT_MISSING")
        with reply.open("rb") as stream:
            payload = stream.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ContractError("RESPONSE_TOO_LARGE")
        saved = json.loads(report.read_text(encoding="utf-8"))
        if saved["execution"]["response_sha256"] != digest(payload):
            raise ContractError("RESPONSE_DIGEST_MISMATCH")
        actual_patch = digest(patch.read_bytes())
        if actual_patch != saved["validation"]["patch_sha256"]:
            raise ContractError("PATCH_DIGEST_MISMATCH")
        return {"response_sha256": digest(payload), "patch_sha256": actual_patch}

    def contract_gate():
        reviewed = session_checker(path)
        if reviewed.get("status") != "PATCH_READY_FOR_REVIEW":
            raise ContractError("STATIC_PATCH_GATE_FAILED")
        if reviewed.get("path") != target:
            raise ContractError("UNEXPECTED_EDIT_TARGET")
        return {"patch_sha256": reviewed["patch_sha256"], "edited_file": target}

    try:
        gate("PINNED_TASK_AND_PREPARATION", prepare_gate)
        gate("MODEL_PREFLIGHT", preflight_gate)
        gate("REAL_GENERATION", generation_gate)
        gate("RESPONSE_PERSISTENCE", persistence_gate)
        gate("PATCH_CONTRACT_AND_STATIC_CHECK", contract_gate)
        state["status"] = "PATCH_READY_NOT_FUNCTIONALLY_GRADED"
        state["next_gate"] = "QUALIFIED_ISOLATED_FUNCTIONAL_EVALUATION"
        return state
    except (ContractError, OSError, RuntimeError, ValueError, TimeoutError) as exc:
        reason = str(exc)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,100}", reason):
            reason = "PIPELINE_OPERATION_FAILED"
        state["status"] = "BLOCKED"
        state["reason"] = reason
        state["failed_gate"] = events[-1]["gate"] if events else "PREPARATION"
        # The durable attempt record, not the wrapper, owns call permission.
        if created and (path / ATTEMPT).is_file():
            state["inference_attempt_recorded"] = True
        return state
    finally:
        if created:
            save_outputs([(path / GATE_REPORT, canonical(state))])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "session", "task-file", "case-id", "expected-head",
                 "expected-blob", "expected-task-sha256", "target"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--profile", default="principal-localizado")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    try:
        result = run_pipeline(
            args.repo, args.session, args.task_file, case_id=args.case_id,
            expected_head=args.expected_head, expected_blob=args.expected_blob,
            expected_task_sha256=args.expected_task_sha256,
            target=args.target, timeout=args.timeout, profile=args.profile,
        )
    except (ContractError, OSError, ValueError) as exc:
        result = {"status": "BLOCKED", "reason": str(exc)
                  if re.fullmatch(r"[A-Z][A-Z0-9_]{0,100}", str(exc))
                  else "PIPELINE_PREPARATION_FAILED"}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["status"] == "PATCH_READY_NOT_FUNCTIONALLY_GRADED" else 2


if __name__ == "__main__":
    sys.exit(main())
