"""LOCAL-16 reviewed application: real Git replay, no generated-code execution."""
import hashlib
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from executor_bridge import ContractError
from profile_cli import run, save_outputs
from reviewed_patch import apply_reviewed, verify

def git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


class ReviewedPatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.repo = self.root / "source"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "LOCAL-16 review")
        git(self.repo, "config", "user.email", "local16@example.invalid")
        (self.repo / "calculator.py").write_text(
            "def calculate(x):\n    return x + 1\n", encoding="utf-8"
        )
        (self.repo / "other.py").write_text(
            "def other():\n    return 1\n", encoding="utf-8"
        )
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "baseline")
        self.base = git(self.repo, "rev-parse", "HEAD")
        self.issue = self.root / "issue.json"
        self.issue.write_text(json.dumps({
            "problem_statement": "In calculator.py repair calculate to return x + 2"
        }), encoding="utf-8")
        self.response = self.root / "model.json"
        self.response.write_text(json.dumps({
            "schema": 1,
            "file": "calculator.py",
            "content": "def calculate(x):\n    return x + 2\n"
        }), encoding="utf-8")
        self.report = self.root / "review.json"
        self.patch = self.root / "candidate.patch"
        run(self.repo, self.issue, "principal", self.report, self.patch,
            offline_response_json=self.response)

    def test_two_stage_review_and_apply_is_unstaged(self):
        reviewed, payload = verify(self.repo, self.report, self.patch)
        self.assertEqual(reviewed["status"], "PATCH_READY_FOR_REVIEW")
        self.assertEqual(payload, self.patch.read_bytes())
        self.assertEqual(reviewed["patch_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        applied = apply_reviewed(
            self.repo, self.report, self.patch, reviewed["patch_sha256"]
        )
        self.assertEqual(applied["status"], "PATCH_APPLIED_UNSTAGED")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), self.base)
        self.assertEqual(git(self.repo, "diff", "--cached", "--name-only"), "")
        self.assertEqual(git(self.repo, "diff", "--name-only"), "calculator.py")
        self.assertIn("return x + 2", (self.repo / "calculator.py").read_text())
        self.assertIn("return 1", (self.repo / "other.py").read_text())
        self.assertFalse(applied["code_execution"])
        self.assertFalse(applied["candidate_tests_run"])

    def test_wrong_approval_refuses_all_writes(self):
        with self.assertRaises(ContractError) as error:
            apply_reviewed(self.repo, self.report, self.patch, "0" * 64)
        self.assertEqual(str(error.exception), "APPROVAL_SHA256_MISMATCH")
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_missing_approval_refuses(self):
        with self.assertRaises(ContractError):
            apply_reviewed(self.repo, self.report, self.patch, None)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_modified_patch_rejected(self):
        with self.patch.open("ab") as stream:
            stream.write(b"\n# tampering")
        with self.assertRaises(ContractError) as error:
            verify(self.repo, self.report, self.patch)
        self.assertEqual(str(error.exception), "PATCH_DIGEST_MISMATCH")
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_modified_report_patch_sha_is_rejected(self):
        data = json.loads(self.report.read_text())
        data["validation"]["patch_sha256"] = "0" * 64
        self.report.write_text(json.dumps(data))
        with self.assertRaises(ContractError):
            verify(self.repo, self.report, self.patch)

    def test_baseline_commit_drift_rejected(self):
        (self.repo / "other.py").write_text("def other():\n    return 42\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "changed checkout")
        with self.assertRaises(ContractError) as error:
            verify(self.repo, self.report, self.patch)
        self.assertEqual(str(error.exception), "BASE_COMMIT_MISMATCH")

    def test_dirty_source_rejected(self):
        (self.repo / "calculator.py").write_text("x = 123\n")
        with self.assertRaises(ContractError) as error:
            verify(self.repo, self.report, self.patch)
        self.assertEqual(str(error.exception), "DIRTY_SOURCE_REPOSITORY")

    def test_out_of_scope_patch_rejected_even_when_rehashed(self):
        replacement = self.patch.read_bytes().replace(
            b"a/calculator.py b/calculator.py",
            b"a/other.py b/other.py"
        )
        self.patch.write_bytes(replacement)
        data = json.loads(self.report.read_text())
        data["validation"]["patch_sha256"] = hashlib.sha256(replacement).hexdigest()
        self.report.write_text(json.dumps(data))
        with self.assertRaises(ContractError):
            verify(self.repo, self.report, self.patch)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_evidence_inside_source_is_refused(self):
        inside = self.repo / "saved.patch"
        (self.repo / ".git" / "info" / "exclude").write_text("saved.patch\\n", encoding="utf-8")
        inside.write_bytes(self.patch.read_bytes())
        with self.assertRaises(ContractError) as error:
            verify(self.repo, self.report, inside)
        self.assertEqual(str(error.exception), "EVIDENCE_INSIDE_SOURCE_REPOSITORY")

    def test_profile_cli_never_writes_to_source_repository(self):
        inside = self.repo / "candidate.patch"
        with patch("profile_cli.generate") as generation:
            with self.assertRaises(ContractError) as error:
                run(self.repo, self.issue, "principal", self.root / "another-report.json",
                    inside)
        self.assertEqual(str(error.exception), "OUTPUT_INSIDE_SOURCE_REPOSITORY")
        self.assertFalse(inside.exists())
        generation.assert_not_called()

    def test_profile_cli_cannot_overwrite_report(self):
        old = self.report.read_bytes()
        with patch("profile_cli.generate") as generation:
            with self.assertRaises(ContractError) as error:
                run(self.repo, self.issue, "principal", self.report, self.root / "other.patch")
        self.assertEqual(str(error.exception), "OUTPUT_ALREADY_EXISTS")
        self.assertEqual(self.report.read_bytes(), old)
        generation.assert_not_called()

    def test_partial_output_cleanup(self):
        first = self.root / "first.json"
        with self.assertRaises(FileExistsError):
            save_outputs([(first, b"ok"), (first, b"wrong")])
        self.assertFalse(first.exists())

    def test_reviewer_command_line_check_and_apply(self):
        path = pathlib.Path(__file__).with_name("reviewed_patch.py")
        for args, expected in (
            (["--check"], "PATCH_READY_FOR_REVIEW"),
            (["--approve-sha256", hashlib.sha256(self.patch.read_bytes()).hexdigest()],
             "PATCH_APPLIED_UNSTAGED")
        ):
            proc = subprocess.run(
                ["python", str(path), "--repo", str(self.repo),
                 "--report", str(self.report), "--patch", str(self.patch), *args],
                text=True, capture_output=True, timeout=40
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["status"], expected)


if __name__ == "__main__":
    unittest.main()
