"""LOCAL-20 end-to-end orchestration tests on disposable Git checkouts, no LLM calls."""
import hashlib
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from local20_pipeline import GATE_REPORT, GATE_EVENTS, run_pipeline
from model_profiles import PROFILES


def git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        check=True, timeout=20,
    ).stdout.strip()


class OneCommandGates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "LOCAL-20")
        git(self.repo, "config", "user.email", "local20@example.invalid")
        self.target = "calculator.py"
        (self.repo / self.target).write_text(
            "def calculate(x):\n    return x + 1\n", encoding="utf-8"
        )
        (self.repo / "other.py").write_text("def other():\n    return 1\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "baseline")
        self.head = git(self.repo, "rev-parse", "HEAD")
        self.blob = git(self.repo, "rev-parse", "HEAD:" + self.target)
        self.task = self.root / "task.txt"
        self.task.write_text(
            "Correct calculator.py calculate to return x + 2 instead of x + 1.",
            encoding="utf-8"
        )
        self.session = self.root / "new-session"
        self.response = json.dumps({
            "schema": 2, "file": self.target,
            "old": "return x + 1", "new": "return x + 2"
        }).encode("utf-8")

    def args(self, **kwargs):
        options = {
            "case_id": "local20__new-real-issue-002",
            "expected_head": self.head,
            "expected_blob": self.blob,
            "expected_task_sha256": hashlib.sha256(self.task.read_bytes()).hexdigest(),
            "target": self.target,
            "inspector": self.inspector,
        }
        options.update(kwargs)
        return options

    @staticmethod
    def inspector(name):
        profile = PROFILES[name]
        return {
            "status": "INSPECTED_NOT_GRADED", "profile": name,
            "native_model": profile.base_model,
            "profile_fingerprint_sha256": profile.fingerprint,
            "native_model_digest_sha256": "f" * 64,
            "native": {"modelfile_sha256": "a" * 64},
        }

    def execute(self, **kwargs):
        return run_pipeline(self.repo, self.session, self.task, **self.args(**kwargs))

    def test_one_invocation_automatically_advances_through_five_gates(self):
        with patch("profile_cli.generate", return_value=self.response) as model:
            result = self.execute()
            model.assert_called_once()
        self.assertEqual(result["status"], "PATCH_READY_NOT_FUNCTIONALLY_GRADED")
        self.assertEqual(result["inference_calls_completed"], 1)
        self.assertEqual([e["gate"] for e in result["events"]], [
            "PINNED_TASK_AND_PREPARATION", "MODEL_PREFLIGHT",
            "REAL_GENERATION", "RESPONSE_PERSISTENCE",
            "PATCH_CONTRACT_AND_STATIC_CHECK",
        ])
        self.assertTrue(all(e["status"] == "PASS" for e in result["events"]))
        self.assertEqual(result["functional_resolution"], "NOT_EVALUATED")
        self.assertFalse(result["candidate_code_executed"])
        self.assertFalse(result["candidate_tests_run"])
        self.assertEqual((self.session / "response.json").read_bytes(), self.response)
        self.assertIn("+    return x + 2", (self.session / "candidate.patch").read_text())
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        self.assertIn("return x + 1", (self.repo / self.target).read_text())
        durable = json.loads((self.session / GATE_REPORT).read_text())
        self.assertEqual(durable["status"], result["status"])
        self.assertEqual(len((self.session / GATE_EVENTS).read_text().splitlines()), 5)

    def test_anchor_failure_stops_downstream_and_preserves_raw_response(self):
        invalid = json.dumps({
            "schema": 2, "file": self.target,
            "old": "return x + 404", "new": "return x + 2"
        }).encode("utf-8")
        with patch("profile_cli.generate", return_value=invalid) as model:
            result = self.execute()
            model.assert_called_once()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["failed_gate"], "REAL_GENERATION")
        self.assertEqual(result["reason"], "EDIT_ANCHOR_NOT_FOUND")
        self.assertTrue(result["inference_attempt_recorded"])
        self.assertEqual((self.session / "response.json").read_bytes(), invalid)
        self.assertEqual(len(result["events"]), 3)
        self.assertFalse((self.session / "candidate.patch").exists())
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        with patch("profile_cli.generate") as second:
            repeat = self.execute()
            second.assert_not_called()
        self.assertEqual(repeat["status"], "BLOCKED")
        self.assertEqual(repeat["reason"], "INPUT_PATH_NOT_ISOLATED")
        self.assertEqual((self.session / "response.json").read_bytes(), invalid)

    def test_preflight_failure_consumes_session_without_model_call(self):
        with patch("profile_cli.generate") as model:
            result = self.execute(inspector=lambda _name: {"status": "NOT_FOUND"})
            model.assert_not_called()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["failed_gate"], "MODEL_PREFLIGHT")
        self.assertEqual(result["reason"], "MODEL_PREFLIGHT_FAILED")
        self.assertFalse((self.session / "generation-attempt.json").exists())
        self.assertTrue((self.session / GATE_REPORT).is_file())

    def test_head_pin_rejected_before_creation_or_model(self):
        with patch("profile_cli.generate") as model:
            result = self.execute(expected_head="0" * 40)
            model.assert_not_called()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "PINNED_HEAD_MISMATCH")
        self.assertFalse(self.session.exists())

    def test_consumed_case_rejected_without_model(self):
        with patch("profile_cli.generate") as model:
            result = self.execute(case_id="oigorbrito__local-evidence-symlink-001")
            model.assert_not_called()
        self.assertEqual(result["reason"], "CASE_ID_INVALID_OR_CONSUMED")
        self.assertFalse(self.session.exists())

    def test_target_retrieval_miss_does_not_invoke_model(self):
        def irrelevant_retrieval(_repo, evidence, _profile, _task):
            pathlib.Path(evidence).mkdir()
            return {"base_commit": self.head, "selected_files": ["other.py"]}
        with patch("local20_pipeline.create", side_effect=irrelevant_retrieval), \
             patch("profile_cli.generate") as model:
            result = self.execute()
            model.assert_not_called()
        self.assertEqual(result["reason"], "PINNED_TARGET_RETRIEVAL_MISS")
        self.assertEqual(result["failed_gate"], "PINNED_TASK_AND_PREPARATION")
        self.assertTrue((self.session / GATE_REPORT).is_file())


if __name__ == "__main__":
    unittest.main()
