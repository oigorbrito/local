"""LOCAL-17 real issue preregistration: Git-pinned source, one case, no model calls."""
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from executor_bridge import ContractError, Request
from local17_real_issue_trial import (
    CASE_ID, DESCRIPTION, PINNED_COMMIT, PINNED_GIT_BLOB,
    PROFILE, TARGET_PATH, prepare_case, verify_pinned_source
)
from local16_workflow import ISSUE, MANIFEST, REQUEST


def git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True,
        capture_output=True, timeout=20
    ).stdout.strip()


class PreregisteredRealIssue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.repo = self.root / "checkout"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "LOCAL-17")
        git(self.repo, "config", "user.email", "local17@example.invalid")
        self.target = self.repo.joinpath(*pathlib.PurePosixPath(TARGET_PATH).parts)
        self.target.parent.mkdir(parents=True)
        self.target.write_text(
            "import pathlib\n"
            "class ContractError(ValueError):\n    pass\n"
            "def _external_path(path, root):\n"
            "    resolved = pathlib.Path(path).resolve()\n"
            "    if resolved.is_relative_to(root):\n"
            "        raise ContractError('EVIDENCE_INSIDE_SOURCE_REPOSITORY')\n"
            "    if resolved.is_symlink():\n"
            "        raise ContractError('EVIDENCE_SYMLINK_FORBIDDEN')\n"
            "    return resolved\n",
            encoding="utf-8"
        )
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "pinned flawed implementation")
        self.base = git(self.repo, "rev-parse", "HEAD")
        self.blob = git(self.repo, "rev-parse", "HEAD:" + TARGET_PATH)
        self.session = self.root / "session"

    def frozen(self):
        return patch.multiple(
            "local17_real_issue_trial",
            PINNED_COMMIT=self.base,
            PINNED_GIT_BLOB=self.blob
        )

    def test_real_git_preparation_with_no_generation_or_source_mutation(self):
        with self.frozen(), patch("profile_cli.generate") as model:
            prepared = prepare_case(self.repo, self.session)
            model.assert_not_called()
        self.assertEqual(prepared["status"], "REAL_ISSUE_PREPARED")
        self.assertEqual(prepared["case_id"], CASE_ID)
        self.assertEqual(prepared["base_commit"], self.base)
        self.assertEqual(prepared["base_blob_git_sha1"], self.blob)
        self.assertEqual(prepared["profile"], PROFILE)
        self.assertTrue(prepared["retrieval_top_2_contains_target"])
        self.assertEqual(prepared["inference_calls_attempted"], 0)
        self.assertEqual(prepared["real_issue_resolved"], "NOT_EVALUATED")
        self.assertFalse(prepared["candidate_code_executed"])
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        manifest = json.loads((self.session / MANIFEST).read_text())
        self.assertEqual(manifest["source_commit"], self.base)
        self.assertIn(TARGET_PATH, manifest["selected_files"])
        request = json.loads((self.session / REQUEST).read_text())
        self.assertIn(TARGET_PATH, request["allowed_files"])
        self.assertEqual(json.loads((self.session / ISSUE).read_text())["problem_statement"],
                         DESCRIPTION)

    def test_unpinned_commit_blocks_without_creating_session(self):
        with self.assertRaisesRegex(ContractError, "REAL_ISSUE_BASE_COMMIT_MISMATCH"):
            prepare_case(self.repo, self.session)
        self.assertFalse(self.session.exists())

    def test_changed_git_blob_blocks(self):
        with patch("local17_real_issue_trial.PINNED_COMMIT", self.base):
            with self.assertRaisesRegex(ContractError, "REAL_ISSUE_BASE_BLOB_MISMATCH"):
                prepare_case(self.repo, self.session)
        self.assertFalse(self.session.exists())

    def test_dirty_source_blocks_before_model_or_evidence(self):
        (self.repo / "extra.py").write_text("x=42\n")
        with self.frozen(), patch("profile_cli.generate") as model:
            with self.assertRaisesRegex(ContractError, "DIRTY_SOURCE_REPOSITORY"):
                prepare_case(self.repo, self.session)
            model.assert_not_called()
        self.assertFalse(self.session.exists())

    def test_retrieval_miss_is_explicit_failure_not_cherry_picked(self):
        with self.frozen(), patch("local17_real_issue_trial.prepare",
                                  return_value=Request(DESCRIPTION, ("another.py",), ())):
            with self.assertRaisesRegex(ContractError, "REAL_ISSUE_RETRIEVAL_MISS"):
                prepare_case(self.repo, self.session)
        self.assertFalse(self.session.exists())

    def test_frozen_case_is_bound_to_one_real_original_blob(self):
        self.assertEqual(len(PINNED_COMMIT), 40)
        self.assertEqual(len(PINNED_GIT_BLOB), 40)
        self.assertIn("reviewed_patch.py", DESCRIPTION)
        self.assertIn("_external_path", DESCRIPTION)
        self.assertIn("symlink", DESCRIPTION.lower())

    def test_real_baseline_shape_is_detectable_without_running_candidate(self):
        with self.frozen():
            self.assertEqual(verify_pinned_source(self.repo), self.repo.resolve())


if __name__ == "__main__":
    unittest.main()
