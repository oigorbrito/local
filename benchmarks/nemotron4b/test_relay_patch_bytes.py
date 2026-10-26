"""Regression tests for byte-exact Git patch generation and rejection evidence."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "experiments" / "local07"))
from integrated_edit import (PatchApplicabilityError, check_patch_index,
                             git_patch_bytes)


class PatchByteTests(unittest.TestCase):
    def make_repo(self, tmp):
        repo = Path(tmp) / "repo"
        shutil.copytree(HERE / "fixture", repo)
        commands = [
            ["git", "init", "-q"], ["git", "config", "user.name", "Fixture"],
            ["git", "config", "user.email", "fixture@example.invalid"],
            ["git", "add", "."], ["git", "commit", "-qm", "baseline"],
        ]
        for command in commands:
            subprocess.run(command, cwd=repo, check=True,
                           capture_output=True, timeout=20)
        return repo

    def test_real_git_diff_applies_with_native_line_endings(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(tmp)
            original = (repo / "guard.py").read_text(encoding="utf8")
            modified = original.replace('"""Deliberately vulnerable fixture."""',
                                        '"""Restricted path reader."""')
            (repo / "guard.py").write_bytes(modified.replace("\n", "\r\n").encode("utf8"))
            exact = subprocess.run(["git", "diff", "--binary", "--", "guard.py"],
                                   cwd=repo, check=True, capture_output=True).stdout
            actual = git_patch_bytes(repo, "diff", "--binary", "--", "guard.py")
            self.assertTrue(exact, "Fixture must produce a nonempty diff")
            self.assertEqual(actual, exact)
            # Git is allowed to normalize text according to platform configuration.
            # A valid test must compare raw bytes, not require CRLF in Git's output.
            check_patch_index(repo, actual)

    def test_synthetic_mixed_newlines_survive_diff_and_index_check(self):
        # Git for Windows may normalize CRLF in source into LF diff text.
        # Use a synthetic Git byte stream to exercise the regression regardless
        # of core.autocrlf, attributes or operating system.
        emitted = (b"diff --git a/guard.py b/guard.py\n"
                   b"index 1234567..abcdef0 100644\n"
                   b"--- a/guard.py\n+++ b/guard.py\n"
                   b"@@ -1 +1 @@\n-old\r\n+new\r\n")
        assert b"\r\n" in emitted and b"\n" in emitted
        with patch("integrated_edit.subprocess.run") as command:
            command.return_value.returncode = 0
            command.return_value.stdout = emitted
            command.return_value.stderr = b""
            actual = git_patch_bytes("/fixture", "diff", "--binary", "--", "guard.py")
            self.assertEqual(actual, emitted)
            self.assertEqual(command.call_args.kwargs["capture_output"], True)
            self.assertNotIn("text", command.call_args.kwargs)
            self.assertNotIn("encoding", command.call_args.kwargs)
            check_patch_index("/fixture", actual)
            self.assertEqual(command.call_args.kwargs["input"], emitted)
            self.assertEqual(command.call_args.args[0],
                             ["git", "apply", "--cached", "--check", "-"])
            self.assertNotIn("text", command.call_args.kwargs)

    def test_rejection_preserves_exact_failed_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(tmp)
            rejected = (b"diff --git a/guard.py b/guard.py\n"
                        b"--- a/guard.py\n+++ b/guard.py\n"
                        b"@@ -1 +1 @@\n-not-original-content\n+replacement\n")
            with self.assertRaises(PatchApplicabilityError) as caught:
                check_patch_index(repo, rejected)
            self.assertEqual(caught.exception.patch_bytes, rejected)
            self.assertIn("GIT_APPLY_CHECK_FAILED", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
