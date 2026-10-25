"""LOCAL-16 end-to-end acceptance gates on disposable Git fixtures, no model calls."""
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from local16_acceptance import acceptance, REPORT_NAME
from model_profiles import PROFILES

GOOD = json.dumps({
    "schema": 1, "file": "calculator.py",
    "content": "def calculate_total(items):\n    return sum(items) + 1\n"
}).encode("utf-8")
WRONG = json.dumps({
    "schema": 1, "file": "calculator.py",
    "content": "def calculate_total(items):\n    return sum(items) + 2\n"
}).encode("utf-8")


def fake_native(name):
    return {
        "profile": name, "status": "INSPECTED_NOT_GRADED",
        "profile_fingerprint_sha256": PROFILES[name].fingerprint,
        "native_model": PROFILES[name].base_model,
        "native_model_digest_sha256": "f" * 64,
        "native": {"modelfile_sha256": "a" * 64}
    }


class AcceptanceGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.output = self.root / "output"
        self.response = self.root / "response.json"
        self.response.write_bytes(GOOD)

    def tearDown(self):
        self.tmp.cleanup()

    def report(self):
        return json.loads((self.output / REPORT_NAME).read_text(encoding="utf-8"))

    def test_audit_all_profiles_without_inference(self):
        calls = []
        def native(name):
            calls.append(name)
            return fake_native(name)
        with patch("profile_cli.generate") as generation:
            result = acceptance(self.output, mode="audit", auditor=native)
        self.assertEqual(result["status"], "AUDIT_PASS")
        self.assertEqual(set(calls), set(PROFILES))
        self.assertEqual(self.report()["inference_calls_attempted"], 0)
        generation.assert_not_called()
        self.assertFalse((self.output / "fixture-issue.json").exists())

    def test_incomplete_native_inventory_explicitly_blocked(self):
        def native(name):
            if name == "economico":
                raise OSError("sensitive host path")
            return fake_native(name)
        result = acceptance(self.output, mode="audit", auditor=native)
        self.assertEqual(result["status"], "AUDIT_INCOMPLETE")
        self.assertEqual(result["audit_results"]["economico"]["reason"], "IO_OR_OLLAMA_UNREACHABLE")
        self.assertNotIn("sensitive host path", json.dumps(self.report()))
        self.assertEqual(result["inference_calls_attempted"], 0)

    def test_replay_non_executing_semantic_pass(self):
        with patch("profile_cli.generate") as generation:
            result = acceptance(self.output, mode="replay", profile_name="economico",
                                offline_response_json=self.response)
        generation.assert_not_called()
        self.assertEqual(result["status"], "PASS_REPLAY_FIXTURE")
        self.assertEqual(result["patch_validation"], "PATCH_APPLICABLE_NOT_GRADED")
        self.assertEqual(result["fixture_semantics"], "FIXTURE_PASS")
        self.assertEqual(result["fixture_cases_passed"], 4)
        self.assertEqual(result["inference_calls_attempted"], 0)
        self.assertFalse(result["generated_code_executed"])
        self.assertTrue(result["source_unchanged"])
        self.assertTrue(result["single_worktree"])
        self.assertEqual(self.report()["status"], result["status"])
        self.assertTrue((self.output / "candidate.patch").is_file())

    def test_replay_applicable_but_semantically_wrong(self):
        self.response.write_bytes(WRONG)
        result = acceptance(self.output, mode="replay", offline_response_json=self.response)
        self.assertEqual(result["status"], "FIXTURE_NOT_SOLVED")
        self.assertEqual(result["patch_validation"], "PATCH_APPLICABLE_NOT_GRADED")
        self.assertEqual(result["fixture_semantics"], "FIXTURE_FAIL")
        self.assertEqual(result["fixture_cases_passed"], 0)
        self.assertTrue(result["source_unchanged"])

    def test_live_is_exactly_one_generation_with_audited_model(self):
        calls = []
        def model(*args, **kwargs):
            calls.append((args, kwargs))
            return GOOD
        with patch("profile_cli.generate", side_effect=model):
            result = acceptance(self.output, mode="live",
                                profile_name="alternativo", auditor=fake_native)
        self.assertEqual(result["status"], "PASS_LIVE_FIXTURE")
        self.assertEqual(result["inference_calls_attempted"], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][1], "qwen3.5:4b")
        self.assertEqual(result["fixture_cases_passed"], 4)
        self.assertTrue(result["source_unchanged"])
        self.assertEqual(result["official_resolution"], "NOT_EVALUATED")
        self.assertTrue(result["native_post_generation_verified"])
        self.assertTrue((self.output / "model-response.json").is_file())

    def test_changed_native_model_digest_blocks_success_claim(self):
        reads = []
        def drift(name):
            data = fake_native(name)
            reads.append(name)
            if len(reads) == 2:
                data["native_model_digest_sha256"] = "0" * 64
            return data
        with patch("profile_cli.generate", return_value=GOOD):
            result = acceptance(self.output, mode="live", auditor=drift)
        self.assertEqual(len(reads), 2)
        self.assertEqual(result["status"], "NATIVE_MODEL_DRIFT")
        self.assertEqual(result["native_inspection"], "DRIFT")
        self.assertEqual(result["fixture_semantics"], "FIXTURE_PASS")
        self.assertFalse(result["generated_code_executed"])

    def test_changed_template_hash_blocks_success_claim(self):
        reads = []
        def drift(name):
            data = fake_native(name)
            reads.append(name)
            if len(reads) == 2:
                data["native"]["modelfile_sha256"] = "b" * 64
            return data
        with patch("profile_cli.generate", return_value=GOOD):
            result = acceptance(self.output, mode="live", auditor=drift)
        self.assertEqual(result["status"], "NATIVE_MODEL_DRIFT")

    def test_live_native_audit_blocks_without_inference(self):
        def reject(_):
            raise RuntimeError("private raw Ollama metadata")
        with patch("profile_cli.generate") as generation:
            result = acceptance(self.output, mode="live", auditor=reject)
        self.assertEqual(result["status"], "BLOCKED_NATIVE_INSPECTION")
        self.assertEqual(result["inference_calls_attempted"], 0)
        self.assertNotIn("private raw", json.dumps(result))
        generation.assert_not_called()

    def test_invalid_generated_contract_no_patch_or_semantic_claim(self):
        with patch("profile_cli.generate", return_value=b'{"schema":99}'):
            result = acceptance(self.output, mode="live", auditor=fake_native)
        self.assertEqual(result["status"], "EXECUTOR_FAILED")
        self.assertEqual(result["fixture_semantics"], "NOT_RUN")
        self.assertEqual(result["inference_calls_attempted"], 1)
        self.assertFalse((self.output / "candidate.patch").exists())
        self.assertTrue(result["source_unchanged"])

    def test_invalid_replay_size_is_reported_fail_closed(self):
        self.response.write_bytes(b"x" * (256 * 1024 + 1))
        with patch("profile_cli.generate") as generation:
            result = acceptance(self.output, mode="replay", offline_response_json=self.response)
        self.assertEqual(result["status"], "INFRA_FAILURE")
        self.assertEqual(result["reason"], "INVALID_REPLAY_RESPONSE")
        generation.assert_not_called()

    def test_collision_refuses_overwriting_successful_evidence(self):
        first = acceptance(self.output, mode="replay", offline_response_json=self.response)
        recorded = (self.output / REPORT_NAME).read_bytes()
        with patch("profile_cli.generate") as generation:
            with self.assertRaises(FileExistsError):
                acceptance(self.output, mode="live", auditor=fake_native)
        generation.assert_not_called()
        self.assertEqual(recorded, (self.output / REPORT_NAME).read_bytes())
        self.assertEqual(first["status"], "PASS_REPLAY_FIXTURE")

    def test_live_source_modification_is_detected(self):
        def destructive(repo, issue_path, profile, report, patch, **_kw):
            (pathlib.Path(repo) / "calculator.py").write_text("oops = 9\n", encoding="utf-8")
            raise RuntimeError("private stack info")
        result = acceptance(self.output, mode="live", auditor=fake_native, executor=destructive)
        self.assertEqual(result["status"], "SOURCE_INTEGRITY_FAILURE")
        self.assertFalse(result["source_unchanged"])
        self.assertNotIn("private stack", json.dumps(result))
        self.assertEqual(result["inference_calls_attempted"], 1)

    def test_cli_offline_entrypoint(self):
        proc = subprocess.run(
            ["python", str(pathlib.Path(__file__).with_name("local16_acceptance.py")),
             "--mode", "replay", "--profile", "principal",
             "--response-json", str(self.response), "--output-dir", str(self.output)],
            capture_output=True, text=True, timeout=40
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "PASS_REPLAY_FIXTURE")


if __name__ == "__main__":
    unittest.main()
