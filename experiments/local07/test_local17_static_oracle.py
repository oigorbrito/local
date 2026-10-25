"""LOCAL-17 independent static-path contract tests, including real Git replay."""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from executor_bridge import ContractError
from local16_workflow import create, generate
from local17_real_issue_trial import DESCRIPTION, TARGET_PATH
from local17_static_oracle import assess_source, evaluate_session

ORIGINAL = (
    "import pathlib\n"
    "class ContractError(ValueError):\n    pass\n"
    "def _external_path(path, root):\n"
    "    resolved = pathlib.Path(path).resolve()\n"
    "    if resolved.is_relative_to(root):\n"
    "        raise ContractError('EVIDENCE_INSIDE_SOURCE_REPOSITORY')\n"
    "    if resolved.is_symlink():\n"
    "        raise ContractError('EVIDENCE_SYMLINK_FORBIDDEN')\n"
    "    return resolved\n"
)
CORRECT = ORIGINAL.replace(
    "    resolved = pathlib.Path(path).resolve()\n",
    "    original = pathlib.Path(path)\n"
    "    if original.is_symlink():\n"
    "        raise ContractError('EVIDENCE_SYMLINK_FORBIDDEN')\n"
    "    resolved = original.resolve()\n"
)
WRONG = ORIGINAL.replace(
    "    if resolved.is_symlink():\n"
    "        raise ContractError('EVIDENCE_SYMLINK_FORBIDDEN')\n",
    ""
)


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          text=True, timeout=30).stdout.strip()


class StaticBehaviorTests(unittest.TestCase):
    def test_original_real_defect_has_negative_control(self):
        result = assess_source(ORIGINAL, ORIGINAL)
        self.assertEqual(result["status"], "STATIC_BEHAVIOR_FAIL")
        self.assertEqual(result["passed"], 3)
        self.assertFalse(result["cases"]["external_symlink_rejected"]["passed"])
        self.assertEqual(result["cases"]["external_symlink_rejected"]["observed"],
                         "EXTERNAL_PATH")
        self.assertFalse(result["candidate_executed"])

    def test_corrected_path_semantics_are_simulated(self):
        result = assess_source(CORRECT, ORIGINAL)
        self.assertEqual(result["status"], "STATIC_BEHAVIOR_CASES_PASS_NOT_RESOLVED")
        self.assertEqual(result["passed"], 4)
        self.assertEqual(result["total"], 4)
        self.assertTrue(all(x["passed"] for x in result["cases"].values()))
        self.assertFalse(result["candidate_executed"])

    def test_direct_path_alias_is_supported(self):
        candidate = CORRECT.replace("pathlib.Path(path)", "Path(path)")
        result = assess_source(candidate, ORIGINAL)
        self.assertEqual(result["status"], "STATIC_BEHAVIOR_CASES_PASS_NOT_RESOLVED")

    def test_wrong_patch_does_not_pass(self):
        result = assess_source(WRONG, ORIGINAL)
        self.assertEqual(result["status"], "STATIC_BEHAVIOR_FAIL")
        self.assertLess(result["passed"], result["total"])

    def test_reject_every_path_is_not_success(self):
        candidate = ORIGINAL.replace(
            "    resolved = pathlib.Path(path).resolve()\n",
            "    if pathlib.Path(path).is_symlink():\n"
            "        raise ContractError('EVIDENCE_SYMLINK_FORBIDDEN')\n"
            "    resolved = pathlib.Path(path).resolve()\n"
            "    raise ContractError('EVIDENCE_INSIDE_SOURCE_REPOSITORY')\n"
        )
        result = assess_source(candidate, ORIGINAL)
        self.assertEqual(result["status"], "STATIC_BEHAVIOR_FAIL")
        self.assertFalse(result["cases"]["external_file_accepted"]["passed"])

    def test_other_python_behavior_cannot_be_changed(self):
        candidate = CORRECT.replace("class ContractError(ValueError):",
                                    "class ContractError(RuntimeError):")
        result = assess_source(candidate, ORIGINAL)
        self.assertEqual(result["status"], "STATIC_ORACLE_INCONCLUSIVE")
        self.assertEqual(result["reason"], "OUTSIDE_TARGET_AST_CHANGED")

    def test_added_side_effect_cannot_be_executed_or_promoted(self):
        with tempfile.TemporaryDirectory() as d:
            sentinel = pathlib.Path(d) / "DO-NOT-CREATE"
            dangerous = CORRECT.replace(
                "    original = pathlib.Path(path)\n",
                "    original = pathlib.Path(path)\n"
                f"    __import__('pathlib').Path({str(sentinel)!r}).touch()\n"
            )
            result = assess_source(dangerous, ORIGINAL)
            self.assertEqual(result["status"], "STATIC_ORACLE_INCONCLUSIVE")
            self.assertEqual(result["reason"], "STATEMENT_NOT_ALLOWED")
            self.assertFalse(sentinel.exists())
            self.assertFalse(result["candidate_executed"])

    def test_dynamic_code_execution_is_not_interpreted(self):
        dangerous = CORRECT.replace(
            "    original = pathlib.Path(path)\n",
            "    original = pathlib.Path(path)\n"
            "    eval('1 + 2')\n"
        )
        result = assess_source(dangerous, ORIGINAL)
        self.assertEqual(result["status"], "STATIC_ORACLE_INCONCLUSIVE")
        self.assertFalse(result["candidate_executed"])

    def test_syntax_error_is_inconclusive_not_solved(self):
        result = assess_source("def broken(", ORIGINAL)
        self.assertEqual(result["status"], "STATIC_ORACLE_INCONCLUSIVE")
        self.assertEqual(result["reason"], "INVALID_PYTHON_SYNTAX")

    def test_changed_function_signature_is_inconclusive(self):
        candidate = CORRECT.replace("_external_path(path, root)",
                                    "_external_path(path, root, mode=None)")
        result = assess_source(candidate, ORIGINAL)
        self.assertEqual(result["status"], "STATIC_ORACLE_INCONCLUSIVE")

    def test_unsupported_loop_is_inconclusive(self):
        candidate = CORRECT.replace(
            "    original = pathlib.Path(path)\n",
            "    for i in range(1):\n        pass\n"
            "    original = pathlib.Path(path)\n"
        )
        result = assess_source(candidate, ORIGINAL)
        self.assertEqual(result["status"], "STATIC_ORACLE_INCONCLUSIVE")


class SessionOracleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = pathlib.Path(self.temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "LOCAL-17 static")
        git(self.repo, "config", "user.email", "local17@example.invalid")
        self.source = self.repo.joinpath(*pathlib.PurePosixPath(TARGET_PATH).parts)
        self.source.parent.mkdir(parents=True)
        self.source.write_text(ORIGINAL, encoding="utf-8")
        git(self.repo, "add", TARGET_PATH)
        git(self.repo, "commit", "-qm", "baseline")
        self.head = git(self.repo, "rev-parse", "HEAD")
        self.blob = git(self.repo, "rev-parse", "HEAD:" + TARGET_PATH)
        self.session = self.base / "session"
        self.response = self.base / "model.json"
        self.response.write_text(
            json.dumps({"schema": 1, "file": TARGET_PATH, "content": CORRECT}),
            encoding="utf-8"
        )

    def frozen(self):
        from unittest.mock import patch as p
        return p.multiple("local17_real_issue_trial",
                          PINNED_COMMIT=self.head,
                          PINNED_GIT_BLOB=self.blob)

    def replay(self):
        create(self.repo, self.session, "principal", DESCRIPTION)
        with patch("profile_cli.generate") as model:
            result = generate(self.session, offline_response_json=self.response)
            model.assert_not_called()
        self.assertEqual(result["status"], "PATCH_APPLICABLE_NOT_GRADED")
        return result

    def test_real_git_offline_replay_then_independent_oracle(self):
        with self.frozen(), patch("local17_static_oracle.PINNED_COMMIT", self.head):
            self.replay()
            result = evaluate_session(self.session)
        self.assertEqual(result["status"], "STATIC_BEHAVIOR_CASES_PASS_NOT_RESOLVED")
        self.assertEqual(result["passed"], 4)
        self.assertEqual(result["patch_review_status"], "PATCH_READY_FOR_REVIEW")
        self.assertEqual(result["generation_mode"], "offline_replay")
        self.assertEqual(result["issue_resolved"], "NOT_EVALUATED")
        self.assertFalse(result["host_candidate_code_executed"])
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        self.assertEqual(result["response_sha256"],
                         hashlib.sha256((self.session / "response.json").read_bytes()).hexdigest())

    def test_baseline_repo_drift_refuses_oracle(self):
        with self.frozen(), patch("local17_static_oracle.PINNED_COMMIT", self.head):
            self.replay()
            (self.repo / "unrelated.py").write_text("x=1\n", encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "DIRTY_SOURCE_REPOSITORY"):
                evaluate_session(self.session)

    def test_session_patch_modified_is_rejected_before_oracle(self):
        with self.frozen(), patch("local17_static_oracle.PINNED_COMMIT", self.head):
            self.replay()
            with (self.session / "candidate.patch").open("ab") as file:
                file.write(b"garbage")
            with self.assertRaises(ContractError):
                evaluate_session(self.session)


if __name__ == "__main__":
    unittest.main()
