"""LOCAL-16: offline attestation of existing Windows audit + live fixture evidence.

Consumes reports already produced on the Windows host, without contacting Ollama,
performing inference, executing generated code, applying patches or rerunning tests.
Checks stored bytes, semantic fixture oracle, patch format, policy and model identity.
This is an evidence consistency gate, NOT cryptographic authentication of the host.
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys

from executor_bridge import ContractError, MAX_RESPONSE_BYTES
from fixture_functional_grade import grade_response_file
from model_profiles import PROFILES
from static_patch_gate import verify_patch
from windows_runtime_smoke import SOURCE, ISSUE

MAX_REPORT_BYTES = 1024 * 1024
MAX_PATCH_BYTES = 256000
DIGEST = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


class EvidenceError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise EvidenceError(code)


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def read_bytes(path, limit, label):
    file = pathlib.Path(path)
    require(file.is_file() and not file.is_symlink(), label + "_FILE_MISSING")
    with file.open("rb") as stream:
        result = stream.read(limit + 1)
    require(len(result) <= limit, label + "_TOO_LARGE")
    return result


def read_json(path, label, limit=MAX_REPORT_BYTES):
    blob = read_bytes(path, limit, label)
    try:
        document = json.loads(blob.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(label + "_INVALID_JSON") from exc
    require(isinstance(document, dict), label + "_INVALID_SCHEMA")
    return document, sha(blob)


def digest_ok(value):
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


def native_ok(native, profile):
    if not isinstance(native, dict):
        return False
    if (native.get("status") != "INSPECTED_NOT_GRADED"
            or native.get("profile") != profile.name
            or native.get("native_model") != profile.base_model
            or native.get("profile_fingerprint_sha256") != profile.fingerprint
            or not digest_ok(native.get("native_model_digest_sha256"))):
        return False
    details = native.get("native")
    if not isinstance(details, dict):
        return False
    return any(digest_ok(details.get(name + "_sha256")) for name in ("modelfile", "template"))


def validate(audit_dir, live_dir):
    audit_dir = pathlib.Path(audit_dir)
    live_dir = pathlib.Path(live_dir)
    audit, audit_sha = read_json(audit_dir / "local16-acceptance.json", "AUDIT")
    live, live_sha = read_json(live_dir / "local16-acceptance.json", "LIVE")
    profile = PROFILES["principal"]
    require(audit.get("schema") == 1 and audit.get("gate") == "LOCAL-16"
            and audit.get("status") == "AUDIT_PASS" and audit.get("mode") == "audit"
            and audit.get("native_inspection") == "PASS"
            and audit.get("inference_calls_attempted") == 0
            and audit.get("generated_code_executed") is False,
            "AUDIT_CONTRACT_MISMATCH")
    results = audit.get("audit_results")
    require(isinstance(results, dict) and set(results) == set(PROFILES),
            "AUDIT_PROFILE_SET_MISMATCH")
    for name, selected in PROFILES.items():
        require(native_ok(results[name], selected), "AUDIT_NATIVE_PROFILE_INVALID")
    require(live.get("schema") == 1 and live.get("gate") == "LOCAL-16"
            and live.get("status") == "PASS_LIVE_FIXTURE"
            and live.get("mode") == "live"
            and live.get("profile") == profile.manifest()
            and live.get("scope") == "LOCAL_12_DISPOSABLE_FIXTURE_ONLY",
            "LIVE_CONTRACT_MISMATCH")
    require(live.get("inference_calls_attempted") == 1
            and live.get("transport") == "PASS"
            and live.get("native_inspection") == "PASS"
            and live.get("native_post_generation_verified") is True
            and live.get("patch_validation") == "PATCH_APPLICABLE_NOT_GRADED"
            and live.get("fixture_semantics") == "FIXTURE_PASS"
            and live.get("fixture_cases_passed") == 4
            and live.get("fixture_cases_total") == 4
            and live.get("source_unchanged") is True
            and live.get("single_worktree") is True
            and live.get("generated_code_executed") is False
            and live.get("official_resolution") == "NOT_EVALUATED",
            "LIVE_GATE_INVARIANTS_MISMATCH")
    require(native_ok(live.get("native_evidence"), profile),
            "LIVE_NATIVE_PROFILE_INVALID")
    native = live["native_evidence"]
    for field in ("native_model_digest_sha256", "profile_fingerprint_sha256", "native"):
        require(native.get(field) == results["principal"].get(field),
                "AUDIT_LIVE_NATIVE_DRIFT")
    # Old on-host reports recorded only a boolean post-generation check.
    # Treat those as legacy assertions, never as an independent second read.
    after = live.get("native_evidence_after")
    if after is not None:
        require(native_ok(after, profile), "LIVE_POST_NATIVE_PROFILE_INVALID")
        for field in ("native_model", "native_model_digest_sha256",
                      "profile_fingerprint_sha256", "native"):
            require(native.get(field) == after.get(field),
                    "LIVE_POST_NATIVE_IDENTITY_DRIFT")
        post_identity = "SAVED_BEFORE_AFTER_SNAPSHOTS_VERIFIED"
    else:
        post_identity = "REPORTED_BY_LOCAL_ACCEPTANCE"
    source_hash = sha(SOURCE.encode("utf-8"))
    require(live.get("fixture_source_sha256") == source_hash,
            "FIXTURE_SOURCE_MISMATCH")
    base = live.get("fixture_commit")
    require(isinstance(base, str) and COMMIT.fullmatch(base) is not None,
            "FIXTURE_COMMIT_INVALID")
    issue, _ = read_json(live_dir / "fixture-issue.json", "FIXTURE_ISSUE")
    require(issue == {"problem_statement": ISSUE}, "FIXTURE_ISSUE_MISMATCH")
    adapter, adapter_sha = read_json(live_dir / "adapter-report.json", "ADAPTER")
    execution = adapter.get("execution")
    validation = adapter.get("validation")
    request = adapter.get("request")
    require(adapter.get("schema") == 1
            and adapter.get("status") == "PATCH_APPLICABLE_NOT_GRADED"
            and isinstance(execution, dict) and isinstance(validation, dict)
            and isinstance(request, dict), "ADAPTER_CONTRACT_MISMATCH")
    require(execution.get("mode") == "local_inference"
            and execution.get("model_invoked") is True
            and execution.get("selected_profile") == profile.manifest()
            and execution.get("system_policy_sha256") == profile.fingerprint,
            "ADAPTER_PROVENANCE_MISMATCH")
    require(request.get("schema") == 1
            and request.get("issue") == ISSUE
            and isinstance(request.get("allowed_files"), list)
            and "calculator.py" in request["allowed_files"],
            "ADAPTER_REQUEST_MISMATCH")
    require(validation.get("commit") == base
            and validation.get("edited_file") == "calculator.py"
            and validation.get("source_sha256") == source_hash,
            "ADAPTER_PATCH_METADATA_MISMATCH")
    response = read_bytes(live_dir / "model-response.json", MAX_RESPONSE_BYTES, "RESPONSE")
    response_hash = sha(response)
    require(response_hash == live.get("response_sha256")
            and response_hash == execution.get("response_sha256"),
            "RESPONSE_DIGEST_MISMATCH")
    patch = read_bytes(live_dir / "candidate.patch", MAX_PATCH_BYTES, "PATCH")
    patch_hash = sha(patch)
    require(patch_hash == live.get("patch_sha256")
            and patch_hash == validation.get("patch_sha256")
            and len(patch) == validation.get("patch_bytes"),
            "PATCH_DIGEST_MISMATCH")
    try:
        target = verify_patch(patch, ["calculator.py"])
    except ValueError as exc:
        raise EvidenceError("PATCH_FORMAT_OR_SCOPE_INVALID") from exc
    require(target == "calculator.py", "PATCH_WRONG_TARGET")
    try:
        oracle = grade_response_file(live_dir / "model-response.json")
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError("RESPONSE_ORACLE_INVALID") from exc
    require(oracle.get("status") == "FIXTURE_PASS"
            and oracle.get("passed") == 4 and oracle.get("total") == 4
            and oracle.get("generated_code_executed") is False,
            "INDEPENDENT_FIXTURE_ORACLE_FAILED")
    return {
        "schema": 1, "gate": "LOCAL-16-EVIDENCE",
        "status": "WINDOWS_FIXTURE_EVIDENCE_CONSISTENT",
        "audit_profiles_verified": sorted(PROFILES),
        "profile": profile.name,
        "installed_model_digest_sha256": native["native_model_digest_sha256"],
        "model_policy_fingerprint_sha256": profile.fingerprint,
        "inference_calls_reported": 1,
        "fixture_cases_independently_checked": 4,
        "patch_sha256": patch_hash,
        "response_sha256": response_hash,
        "input_report_sha256": {"audit": audit_sha, "live": live_sha,
                                "adapter": adapter_sha},
        "model_identity_post_generation": post_identity,
        "source_integrity": "REPORTED_BY_LOCAL_ACCEPTANCE",
        "candidate_code_executed_by_verifier": False,
        "general_issue_resolution": "NOT_EVALUATED",
        "host_report_authenticity": "NOT_CRYPTOGRAPHICALLY_ATTESTED",
        "performance_benchmark": "NOT_EVALUATED"
    }


def main():
    parser = argparse.ArgumentParser(description="Offline verification of existing LOCAL-16 Windows results")
    parser.add_argument("--audit-dir", required=True)
    parser.add_argument("--live-dir", required=True)
    parser.add_argument("--output", help="Optional new JSON summary path, refuses overwrites")
    args = parser.parse_args()
    try:
        result = validate(args.audit_dir, args.live_dir)
        if args.output:
            out = pathlib.Path(args.output)
            require(not out.exists() and not out.is_symlink() and out.parent.is_dir(),
                    "VERDICT_OUTPUT_COLLISION_OR_DIRECTORY_MISSING")
            with out.open("xb") as stream:
                stream.write((json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (EvidenceError, ContractError, OSError, ValueError) as exc:
        code = str(exc)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,100}", code):
            code = "EVIDENCE_VALIDATION_FAILED"
        print(json.dumps({"status": "BLOCKED", "reason": code}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
