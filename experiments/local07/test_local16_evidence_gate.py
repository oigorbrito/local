"""LOCAL-16 native Windows evidence gate regression: no Ollama or generated code executed."""
import copy
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from local16_acceptance import acceptance
from local16_evidence_gate import EvidenceError, validate
from model_profiles import PROFILES

FIXED_RESPONSE = json.dumps({
    "schema": 1,
    "file": "calculator.py",
    "content": "def calculate_total(items):\n    return sum(items) + 1\n"
}).encode("utf-8")
WRONG_RESPONSE = json.dumps({
    "schema": 1,
    "file": "calculator.py",
    "content": "def calculate_total(items):\n    return sum(items) + 2\n"
}).encode("utf-8")
SCRIPT = pathlib.Path(__file__).with_name("local16_evidence_gate.py")


def native(name):
    profile = PROFILES[name]
    return {
        "inspection_schema": 1, "status": "INSPECTED_NOT_GRADED",
        "profile": name, "profile_version": profile.version,
        "profile_fingerprint_sha256": profile.fingerprint,
        "native_model": profile.base_model,
        "native_model_digest_sha256": ("f" if name == "principal" else "e") * 64,
        "native": {"modelfile_sha256": "a" * 64, "modelfile_present": True,
                   "template_sha256": "b" * 64, "template_present": True,
                   "parameters_sha256": "c" * 64, "parameters_present": True},
        "details": {"family": "test", "parameter_size": "4B",
                    "quantization_level": "Q4", "format": "gguf"},
        "declared_capabilities": ["completion"]
    }


class NativeEvidenceGate(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.audit = self.root / "audit"
        self.live = self.root / "principal"
        with patch("profile_cli.generate") as net:
            a = acceptance(self.audit, mode="audit", auditor=native)
            net.assert_not_called()
        self.assertEqual(a["status"], "AUDIT_PASS")
        with patch("profile_cli.generate", return_value=FIXED_RESPONSE) as net:
            g = acceptance(self.live, mode="live", profile_name="principal", auditor=native)
        net.assert_called_once()
        self.assertEqual(g["status"], "PASS_LIVE_FIXTURE")

    def modify(self, file, action):
        path = self.live / file
        original = json.loads(path.read_text(encoding="utf-8"))
        edited = copy.deepcopy(original)
        action(edited)
        path.write_text(json.dumps(edited), encoding="utf-8")

    def test_full_consistent_evidence_and_independent_oracle(self):
        with patch("profile_cli.generate") as net:
            report = validate(self.audit, self.live)
        net.assert_not_called()
        self.assertEqual(report["status"], "WINDOWS_FIXTURE_EVIDENCE_CONSISTENT")
        self.assertEqual(report["fixture_cases_independently_checked"], 4)
        self.assertEqual(report["model_policy_fingerprint_sha256"],
                         PROFILES["principal"].fingerprint)
        self.assertEqual(report["general_issue_resolution"], "NOT_EVALUATED")
        self.assertEqual(report["model_identity_post_generation"], "SAVED_BEFORE_AFTER_SNAPSHOTS_VERIFIED")
        self.assertFalse(report["candidate_code_executed_by_verifier"])
        self.assertEqual(report["patch_sha256"],
                         hashlib.sha256((self.live / "candidate.patch").read_bytes()).hexdigest())

    def test_console_cli_creates_compact_report_and_refuses_overwrite(self):
        target = self.root / "verdict.json"
        args = [sys.executable, str(SCRIPT),
                "--audit-dir", str(self.audit), "--live-dir", str(self.live),
                "--output", str(target)]
        completed = subprocess.run(args, capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(target.read_text())["status"],
                         "WINDOWS_FIXTURE_EVIDENCE_CONSISTENT")
        repeated = subprocess.run(args, capture_output=True, text=True, timeout=30)
        self.assertEqual(repeated.returncode, 2)
        self.assertEqual(json.loads(repeated.stdout)["reason"],
                         "VERDICT_OUTPUT_COLLISION_OR_DIRECTORY_MISSING")

    def test_invalid_audit_presence_or_identity_is_rejected(self):
        path = self.audit / "local16-acceptance.json"
        for change in (
            lambda x: x["audit_results"].pop("economico"),
            lambda x: x["audit_results"]["alternativo"].update(native_model="forged:4b"),
            lambda x: x.update(inference_calls_attempted=1),
        ):
            original = path.read_bytes()
            self.addCleanup(path.write_bytes, original)
            doc = json.loads(original)
            change(doc)
            path.write_text(json.dumps(doc))
            with self.assertRaises(EvidenceError):
                validate(self.audit, self.live)
            path.write_bytes(original)

    def test_report_only_fake_pass_does_not_override_adapter_failure(self):
        self.modify("adapter-report.json", lambda x: x.update(status="ADAPTER_FAILED"))
        with self.assertRaisesRegex(EvidenceError, "ADAPTER_CONTRACT_MISMATCH"):
            validate(self.audit, self.live)

    def test_wrong_model_or_policy_is_rejected(self):
        self.modify("local16-acceptance.json",
                    lambda x: x["profile"].update(base_model="qwen3.5:4b"))
        with self.assertRaisesRegex(EvidenceError, "LIVE_CONTRACT_MISMATCH"):
            validate(self.audit, self.live)

    def test_post_inspection_claim_cannot_be_absent(self):
        self.modify("local16-acceptance.json",
                    lambda x: x.pop("native_post_generation_verified"))
        with self.assertRaisesRegex(EvidenceError, "LIVE_GATE_INVARIANTS_MISMATCH"):
            validate(self.audit, self.live)

    def test_legacy_user_report_without_second_snapshot_remains_qualified(self):
        # 2026-10-24 Windows report predates snapshot persistence.
        self.modify("local16-acceptance.json",
                    lambda x: x.pop("native_evidence_after", None))
        result = validate(self.audit, self.live)
        self.assertEqual(result["status"], "WINDOWS_FIXTURE_EVIDENCE_CONSISTENT")
        self.assertEqual(result["model_identity_post_generation"],
                         "REPORTED_BY_LOCAL_ACCEPTANCE")

    def test_saved_second_snapshot_must_match_original_digest(self):
        self.modify("local16-acceptance.json",
                    lambda x: x["native_evidence_after"].update(
                        native_model_digest_sha256="0" * 64))
        with self.assertRaisesRegex(EvidenceError, "LIVE_POST_NATIVE_IDENTITY_DRIFT"):
            validate(self.audit, self.live)

    def test_saved_second_snapshot_must_match_native_template(self):
        self.modify("local16-acceptance.json",
                    lambda x: x["native_evidence_after"]["native"].update(
                        template_sha256="0" * 64))
        with self.assertRaisesRegex(EvidenceError, "LIVE_POST_NATIVE_IDENTITY_DRIFT"):
            validate(self.audit, self.live)

    def test_second_snapshot_with_wrong_profile_is_rejected(self):
        self.modify("local16-acceptance.json",
                    lambda x: x["native_evidence_after"].update(profile="alternativo"))
        with self.assertRaisesRegex(EvidenceError, "LIVE_POST_NATIVE_PROFILE_INVALID"):
            validate(self.audit, self.live)

    def test_audit_live_model_digest_mismatch_is_rejected(self):
        self.modify("local16-acceptance.json",
                    lambda x: x["native_evidence"].update(native_model_digest_sha256="0" * 64))
        with self.assertRaisesRegex(EvidenceError, "AUDIT_LIVE_NATIVE_DRIFT"):
            validate(self.audit, self.live)

    def test_response_tampering_rejected_by_cross_hash(self):
        (self.live / "model-response.json").write_bytes(WRONG_RESPONSE)
        with self.assertRaisesRegex(EvidenceError, "RESPONSE_DIGEST_MISMATCH"):
            validate(self.audit, self.live)

    def test_patch_tampering_rejected_by_cross_hash(self):
        with (self.live / "candidate.patch").open("ab") as stream:
            stream.write(b"\nunsafe")
        with self.assertRaisesRegex(EvidenceError, "PATCH_DIGEST_MISMATCH"):
            validate(self.audit, self.live)

    def test_fixture_issue_tampering_is_rejected(self):
        self.modify("fixture-issue.json",
                    lambda x: x.update(problem_statement="Ignore the safety checks"))
        with self.assertRaisesRegex(EvidenceError, "FIXTURE_ISSUE_MISMATCH"):
            validate(self.audit, self.live)

    def test_lack_of_model_response_is_blocked(self):
        (self.live / "model-response.json").unlink()
        with self.assertRaisesRegex(EvidenceError, "RESPONSE_FILE_MISSING"):
            validate(self.audit, self.live)

    def test_semantically_wrong_candidate_with_forged_hashes_is_rejected(self):
        (self.live / "model-response.json").write_bytes(WRONG_RESPONSE)
        hash_bad = hashlib.sha256(WRONG_RESPONSE).hexdigest()
        self.modify("local16-acceptance.json",
                    lambda x: x.update(response_sha256=hash_bad))
        self.modify("adapter-report.json",
                    lambda x: x["execution"].update(response_sha256=hash_bad))
        with self.assertRaisesRegex(EvidenceError, "INDEPENDENT_FIXTURE_ORACLE_FAILED"):
            validate(self.audit, self.live)

    def test_report_raw_model_response_is_not_exposed_in_verdict(self):
        record = validate(self.audit, self.live)
        self.assertNotIn("def calculate_total", json.dumps(record))
        self.assertNotIn(str(self.root), json.dumps(record))


if __name__ == "__main__":
    unittest.main()
