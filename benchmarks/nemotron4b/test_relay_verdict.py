"""Offline regression tests for functional verdicts and fail-closed trial scheduling."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import compare


class VerdictTests(unittest.TestCase):
    def test_correct_patch_counts_even_if_agent_exit_is_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(compare, "git", side_effect=[
                "guard.py\n", "", "diff --git a/guard.py b/guard.py\n+safe\n"
            ]), patch.object(compare, "tests", return_value={
                "code": 0, "stdout": "", "stderr": ""
            }):
                verdict = compare.grade(Path(tmp), Path(tmp), {
                    "code": 1, "timeout": False,
                })
            self.assertTrue(verdict["functional_passed"])
            self.assertTrue(verdict["passed"])
            self.assertFalse(verdict["executor_completed"])
            self.assertTrue((Path(tmp) / "result.patch").exists())

    def test_bad_patch_does_not_pass_when_process_exits_successfully(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(compare, "git", side_effect=[
                "guard.py\n", "", "diff --git a/guard.py b/guard.py\n+bad\n"
            ]), patch.object(compare, "tests", return_value={
                "code": 1, "stdout": "", "stderr": "FAILED"
            }):
                verdict = compare.grade(Path(tmp), Path(tmp), {
                    "code": 0, "timeout": False,
                })
            self.assertFalse(verdict["passed"])
            self.assertTrue(verdict["executor_completed"])

    def test_transport_timeout_aborts_remaining_trials(self):
        self.assertEqual(compare.infrastructure_failure({
            "timeout": True, "stderr": "", "code": None,
        }), "EXECUTOR_WALL_TIMEOUT")
        self.assertEqual(compare.infrastructure_failure({
            "timeout": False, "stderr": "TimeoutError: timed out", "code": 1,
        }), "OLLAMA_REQUEST_TIMEOUT")
        self.assertEqual(compare.infrastructure_failure({
            "timeout": False, "stderr": "Cannot reach Ollama at http://127.0.0.1:11434", "code": 1,
        }), "OLLAMA_UNREACHABLE")

    def test_alternating_order_preserves_equal_exposure(self):
        for first in ("cloi", "local09"):
            order = [compare.order_for_repeat(i, first) for i in range(1, 6)]
            self.assertEqual(order[0][0], first)
            for i, pair in enumerate(order):
                self.assertEqual(set(pair), {"cloi", "local09"})
                if i:
                    self.assertEqual(pair, tuple(reversed(order[i - 1])))
            self.assertEqual(sum(pair.count("cloi") for pair in order), 5)
            self.assertEqual(sum(pair.count("local09") for pair in order), 5)
        with self.assertRaises(ValueError):
            compare.order_for_repeat(1, "unknown")

    def test_patch_rejection_is_not_mistaken_for_transport_failure(self):
        self.assertIsNone(compare.infrastructure_failure({
            "timeout": False,
            "stderr": "GIT_APPLY_CHECK_FAILED: patch failed: guard.py:1",
            "code": 1,
        }))


if __name__ == "__main__":
    unittest.main()
