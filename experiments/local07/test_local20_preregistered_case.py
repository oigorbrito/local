"""Pre-register a second genuine bug, frozen independently of the model.

This test checks Git provenance, task identity, retrieval and the known
baseline defect; it never sends a prompt to Ollama or executes a candidate.
"""
import hashlib
import pathlib
import subprocess
import tempfile
import unittest

from executor_bridge import prepare
from local20_pipeline import pinned_inputs

CASE = "oigorbrito__local-anchor-separation-002"
PINNED_HEAD = "11fd231cf2ebd27151b1390621c61dd2cf7a1af5"
PINNED_BLOB = "ce1d7b4a37d73e1f595645d759542ba478991898"
TASK_SHA256 = "058509e618b98848a34880805a4aad1a97cfc42c6d0c65413243af3ff6cc6261"
TARGET = "experiments/local07/executor_bridge.py"
TASK = pathlib.Path(__file__).parent / "cases" / "anchor-reasons-002.txt"
REPO = pathlib.Path(__file__).resolve().parents[2]


class FrozenAnchorCase(unittest.TestCase):
    def test_pinned_real_bug_is_retrieved_without_generation(self):
        # Read committed Git bytes rather than the worktree's CRLF-converted
        # representation on Windows. The frozen SHA remains byte-exact.
        committed_task = subprocess.run(
            ["git", "show", "HEAD:" + TASK.relative_to(REPO).as_posix()],
            cwd=REPO, check=True, capture_output=True, timeout=40,
        ).stdout
        self.assertEqual(hashlib.sha256(committed_task).hexdigest(), TASK_SHA256)
        self.assertEqual(
            len(CASE), len("oigorbrito__local-anchor-separation-002")
        )
        with tempfile.TemporaryDirectory(prefix="local20-case-") as tmp:
            frozen_task = pathlib.Path(tmp) / "task.txt"
            frozen_task.write_bytes(committed_task)
            self.assertEqual(hashlib.sha256(frozen_task.read_bytes()).hexdigest(), TASK_SHA256)
            trial = pathlib.Path(tmp) / "trial"
            session = pathlib.Path(tmp) / "new-session"
            subprocess.run(
                ["git", "worktree", "add", "--detach", str(trial), PINNED_HEAD],
                cwd=REPO, check=True, capture_output=True, text=True, timeout=40,
            )
            try:
                root, task = pinned_inputs(
                    trial, session, frozen_task, case_id=CASE,
                    expected_head=PINNED_HEAD, expected_blob=PINNED_BLOB,
                    expected_task_sha256=TASK_SHA256, target=TARGET,
                )
                request = prepare(root, task, output_schema=2)
                self.assertIn(TARGET, request.selected_files)
                self.assertEqual(request.to_json()["output_contract"]["schema"], 2)
                original = (root / TARGET).read_text(encoding="utf-8")
                self.assertIn('if content.count(source["old"]) != 1:', original)
                self.assertIn('raise ContractError("EDIT_ANCHOR_NOT_UNIQUE")', original)
                self.assertNotIn('raise ContractError("EDIT_ANCHOR_NOT_FOUND")', original)
                self.assertEqual(
                    subprocess.run(["git", "status", "--porcelain"], cwd=root,
                                   capture_output=True, text=True, check=True).stdout, ""
                )
                self.assertFalse(session.exists())
            finally:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(trial)],
                    cwd=REPO, check=True, capture_output=True, text=True, timeout=40,
                )


if __name__ == "__main__":
    unittest.main()
