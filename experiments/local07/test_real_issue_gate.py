import json
import pathlib
import subprocess
import tempfile
import unittest

from real_issue_gate import GateError, evaluate


def git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return p.stdout.strip()


class RealIssueGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = pathlib.Path(self.temp.name)
        self.repo = self.parent / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "test@example.invalid")
        git(self.repo, "config", "user.name", "Gate Test")
        (self.repo / "calculator.py").write_text("def calculate_total(items):\n    return sum(items)\n", encoding="utf-8")
        git(self.repo, "add", "calculator.py")
        git(self.repo, "commit", "-qm", "pinned source")
        self.issue = self.parent / "issue.json"
        self.truth = self.parent / "evaluator.json"
        self.issue_data = {"schema": 1, "issue_id": "upstream__issue-1",
                           "base_commit": git(self.repo, "rev-parse", "HEAD"),
                           "problem_statement": "Fix calculator.py calculate_total for negative input"}
        self.eval_data = {"schema": 1, "issue_id": "upstream__issue-1", "target_files": ["calculator.py"]}
        self.save()

    def save(self):
        self.issue.write_text(json.dumps(self.issue_data), encoding="utf-8")
        self.truth.write_text(json.dumps(self.eval_data), encoding="utf-8")

    def test_pinned_retrieval_without_generation(self):
        result = evaluate(self.repo, self.issue, self.truth)
        self.assertEqual((result["recall_at_1"], result["recall_at_2"]), (1, 1))
        self.assertFalse(result["generation_attempted"])
        self.assertFalse(result["target_files_exposed_to_model"])
        self.assertEqual(result["issue_resolved"], "NOT_EVALUATED")

    def test_mismatched_base_refuses(self):
        self.issue_data["base_commit"] = "0" * 40
        self.save()
        with self.assertRaisesRegex(GateError, "COMMIT_MISMATCH"):
            evaluate(self.repo, self.issue, self.truth)

    def test_dirty_repo_refuses(self):
        (self.repo / "other.py").write_text("x = 3\n")
        with self.assertRaisesRegex(GateError, "DIRTY_CHECKOUT"):
            evaluate(self.repo, self.issue, self.truth)

    def test_mismatched_evaluator_refuses(self):
        self.eval_data["issue_id"] = "different"
        self.save()
        with self.assertRaisesRegex(GateError, "ISSUE_ID_MISMATCH"):
            evaluate(self.repo, self.issue, self.truth)

    def test_invalid_targets_refuses(self):
        for bad in ["../secret.py", "/tmp/leak.py", "test.txt"]:
            with self.subTest(bad=bad):
                self.eval_data["target_files"] = [bad]
                self.save()
                with self.assertRaisesRegex(GateError, "INVALID_TARGETS"):
                    evaluate(self.repo, self.issue, self.truth)

    def test_no_gold_target_retrieval_leak(self):
        # The source does not contain the arbitrary secret target. Retrieval is
        # expected to work solely from the public issue and repository.
        self.eval_data["target_files"] = ["private/only-for-grading.py"]
        self.save()
        result = evaluate(self.repo, self.issue, self.truth)
        self.assertEqual(result["recall_at_2"], 0)
        self.assertNotIn("target_files", result)
        self.assertFalse(result["target_files_exposed_to_model"])


if __name__ == "__main__":
    unittest.main()
