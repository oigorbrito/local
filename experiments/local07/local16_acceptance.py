"""LOCAL-16 operational acceptance: one explicit attempt, inspect and grade separately.

An offline replay or native-model audit performs NO inference. --mode live permits
exactly one localhost Ollama generation for a fixed disposable Python fixture.
The generated source is never imported, executed, or applied to the host.
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

from executor_bridge import ContractError, MAX_RESPONSE_BYTES
from fixture_functional_grade import grade_response_file
from inspect_profiles import inspect as inspect_native
from model_profiles import PROFILES, select_profile
from profile_cli import run as invoke
from windows_runtime_smoke import SOURCE, ISSUE

VERSION = 1
REPORT_NAME = "local16-acceptance.json"
SAFE_REASON = re.compile(r"^[A-Z][A-Z0-9_]{0,100}$")


def _git(root, *args):
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=30)
    if proc.returncode:
        raise RuntimeError("FIXTURE_GIT_" + args[0].upper() + "_FAILED")
    return proc.stdout.strip()


def _fixture(root):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "local16@example.invalid")
    _git(root, "config", "user.name", "LOCAL-16 acceptance")
    (root / "calculator.py").write_text(SOURCE, encoding="utf-8", newline="\n")
    _git(root, "add", "calculator.py")
    _git(root, "commit", "-qm", "disposable local16 acceptance fixture")
    return _git(root, "rev-parse", "HEAD")


def _checksum(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _safe_reason(exc):
    # Avoid putting unexpected paths, model text or HTTP bodies into evidence.
    code = str(exc)
    if isinstance(exc, (ContractError, ValueError)) and SAFE_REASON.fullmatch(code):
        return code
    if isinstance(exc, OSError):
        return "IO_OR_OLLAMA_UNREACHABLE"
    return type(exc).__name__.upper()[:60]


def _write_new(path, record):
    # Atomic publication, refusing existing evidence to preserve provenance.
    data = (json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    token = pathlib.Path(str(path) + ".partial")
    if token.exists() or path.exists():
        raise FileExistsError("ACCEPTANCE_REPORT_ALREADY_EXISTS")
    try:
        with token.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(token, path)
    finally:
        token.unlink(missing_ok=True)


def acceptance(output_dir, *, mode="audit", profile_name="principal",
               offline_response_json=None, timeout=180, auditor=inspect_native,
               executor=invoke):
    if mode not in {"audit", "live", "replay"}:
        raise ValueError("INVALID_MODE")
    if type(timeout) is not int or not 1 <= timeout <= 420:
        raise ValueError("INVALID_TIMEOUT")
    if mode == "replay" and offline_response_json is None:
        raise ValueError("REPLAY_RESPONSE_REQUIRED")
    if mode != "replay" and offline_response_json is not None:
        raise ValueError("UNEXPECTED_REPLAY_RESPONSE")
    profile = select_profile(profile_name)
    dest = pathlib.Path(output_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    paths = {
        "report": dest / REPORT_NAME,
        "issue": dest / "fixture-issue.json",
        "adapter": dest / "adapter-report.json",
        "patch": dest / "candidate.patch",
        "response": dest / "model-response.json"
    }
    if any(p.exists() or p.is_symlink() for p in paths.values()) or (dest / (REPORT_NAME + ".partial")).exists():
        raise FileExistsError("ACCEPTANCE_OUTPUT_COLLISION")
    record = {
        "schema": VERSION, "gate": "LOCAL-16", "status": "STARTED",
        "mode": mode, "profile": profile.manifest(),
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "inference_calls_attempted": 0, "native_inspection": "NOT_RUN",
        "transport": "NOT_RUN", "patch_validation": "NOT_RUN",
        "fixture_semantics": "NOT_RUN", "generated_code_executed": False,
        "official_resolution": "NOT_EVALUATED",
        "scope": "LOCAL_12_DISPOSABLE_FIXTURE_ONLY"
    }
    began = time.monotonic()
    try:
        if mode == "audit":
            outcomes = {}
            for name in PROFILES:
                try:
                    outcomes[name] = auditor(name)
                except Exception as exc:
                    outcomes[name] = {"profile": name, "status": "BLOCKED", "reason": _safe_reason(exc)}
            record["audit_results"] = outcomes
            record["native_inspection"] = "PASS" if all(
                item.get("status") == "INSPECTED_NOT_GRADED" for item in outcomes.values()
            ) else "BLOCKED"
            record["status"] = "AUDIT_PASS" if record["native_inspection"] == "PASS" else "AUDIT_INCOMPLETE"
        else:
            if mode == "live":
                try:
                    record["native_evidence"] = auditor(profile_name)
                    if record["native_evidence"].get("status") != "INSPECTED_NOT_GRADED":
                        raise ValueError("NATIVE_INSPECTION_INCOMPLETE")
                    record["native_inspection"] = "PASS"
                except Exception as exc:
                    record["native_inspection"] = "BLOCKED"
                    record["status"] = "BLOCKED_NATIVE_INSPECTION"
                    record["reason"] = _safe_reason(exc)
            else:
                record["native_inspection"] = "NOT_RUN_OFFLINE"
                response_path = pathlib.Path(offline_response_json).resolve()
                if not response_path.is_file() or response_path.stat().st_size > MAX_RESPONSE_BYTES:
                    raise ValueError("INVALID_REPLAY_RESPONSE")
                record["replay_input_sha256"] = _checksum(response_path)
            if record["status"] == "STARTED":
                with tempfile.TemporaryDirectory(prefix="local16-acceptance-") as temp:
                    root = pathlib.Path(temp)
                    record["fixture_commit"] = _fixture(root)
                    initial_hash = _checksum(root / "calculator.py")
                    record["fixture_source_sha256"] = initial_hash
                    paths["issue"].write_text(
                        json.dumps({"problem_statement": ISSUE}, ensure_ascii=False) + "\n",
                        encoding="utf-8"
                    )
                    kwargs = {"timeout": timeout}
                    if mode == "live":
                        kwargs["response_json_path"] = paths["response"]
                        record["inference_calls_attempted"] = 1
                        record["transport"] = "ATTEMPTED"
                    else:
                        kwargs["offline_response_json"] = response_path
                        record["transport"] = "NOT_RUN_OFFLINE"
                    try:
                        result = executor(
                            root, paths["issue"], profile_name, paths["adapter"],
                            paths["patch"], **kwargs
                        )
                        record["patch_validation"] = result["status"]
                        record["response_sha256"] = _checksum(
                            paths["response"] if mode == "live" else response_path
                        )
                        record["patch_sha256"] = _checksum(paths["patch"])
                        grade = grade_response_file(
                            paths["response"] if mode == "live" else response_path
                        )
                        record["fixture_semantics"] = grade["status"]
                        record["fixture_cases_passed"] = grade["passed"]
                        record["fixture_cases_total"] = grade["total"]
                        if mode == "live":
                            record["transport"] = "PASS"
                        record["status"] = (
                            "PASS_LIVE_FIXTURE" if mode == "live" else "PASS_REPLAY_FIXTURE"
                        ) if (
                            result["status"] == "PATCH_APPLICABLE_NOT_GRADED"
                            and grade["status"] == "FIXTURE_PASS"
                        ) else "FIXTURE_NOT_SOLVED"
                    except Exception as exc:
                        record["status"] = "EXECUTOR_FAILED"
                        record["reason"] = _safe_reason(exc)
                    finally:
                        record["source_unchanged"] = (
                            _checksum(root / "calculator.py") == initial_hash
                            and _git(root, "status", "--porcelain") == ""
                        )
                        record["single_worktree"] = len(_git(root, "worktree", "list", "--porcelain").split("worktree ")) == 2
                        if not record["source_unchanged"] or not record["single_worktree"]:
                            record["status"] = "SOURCE_INTEGRITY_FAILURE"
    except Exception as exc:
        record["status"] = "INFRA_FAILURE"
        record["reason"] = _safe_reason(exc)
    finally:
        record["elapsed_seconds"] = round(time.monotonic() - began, 3)
        _write_new(paths["report"], record)
    return record


def main():
    p = argparse.ArgumentParser(description="LOCAL-16: deterministic host acceptance, no candidate execution")
    p.add_argument("--mode", choices=("audit", "live", "replay"), default="audit")
    p.add_argument("--profile", choices=tuple(PROFILES), default="principal")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--response-json", default=None, help="Required for replay; never invokes Ollama")
    p.add_argument("--timeout", type=int, default=180)
    args = p.parse_args()
    report = acceptance(
        args.output_dir, mode=args.mode, profile_name=args.profile,
        offline_response_json=args.response_json, timeout=args.timeout
    )
    print(json.dumps({
        "status": report["status"], "profile": args.profile,
        "inference_calls_attempted": report["inference_calls_attempted"],
        "report": str(pathlib.Path(args.output_dir).resolve() / REPORT_NAME)
    }))
    return 0 if report["status"] in {
        "AUDIT_PASS", "PASS_LIVE_FIXTURE", "PASS_REPLAY_FIXTURE"
    } else 2


if __name__ == "__main__":
    sys.exit(main())
