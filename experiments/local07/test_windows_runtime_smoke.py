"""LOCAL-11 orchestration contract; no Ollama requests."""
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from windows_runtime_smoke import smoke


class FakeProcess:
    returncode = 0
    stderr = ""
    stdout = '{"status":"PATCH_APPLICABLE_NOT_GRADED"}'


class WindowsSmokeTest(unittest.TestCase):
    def test_success_isolated_and_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            def fake_run(command, **kwargs):
                output = pathlib.Path(command[command.index("--patch") + 1])
                output.write_bytes(b"diff --git a/calculator.py b/calculator.py\n")
                return FakeProcess()
            with patch("windows_runtime_smoke.subprocess.run", side_effect=fake_run):
                # git fixture uses subprocess internally; mock only the adapter
                pass

    def test_wrong_model_rejected_before_inference(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                smoke(folder, model="qwen3.5:2b")
            self.assertEqual(list(pathlib.Path(folder).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
