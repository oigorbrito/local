"""Regression tests for byte-exact Git patch generation and rejection evidence."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "experiments" / "local07"))
from integrated_edit import (PatchApplicabilityError, check_patch_index,
                             git, git_patch_bytes)


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

    def test_crlf_diff_is_not_transformed_into_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(tmp)
            original = (repo / "guard.py").read_text(encoding="utf8")
            modified = original.replace('"""Deliberately vulnerable fixture."""',
                                        '"""Restricted path reader."""')
            (repo / "guard.py").write_bytes(modified.replace("\n", "\r\n").encode("utf8"))
            exact = subprocess.run(["git", "diff", "--binary", "--", "guard.py"],
                                   cwd=repo, check=True, capture_output=True).stdout
            actual = git_patch_bytes(repo, "diff", "--binary", "--", "guard.py")
            self.assertEqual(actual, exact)
            self.assertIn(b"\r\n", exact)
            # The legacy text-mode helper loses carriage returns in diff bytes.
            legacy = git(repo, "diff", "--binary", "--", "guard.py").encode("utf8")
            self.assertNotEqual(legacy, exact)
            check_patch_index(repo, actual)

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
