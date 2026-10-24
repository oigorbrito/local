"""LOCAL-11 orchestration contract; no Ollama requests."""
import pathlib
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from windows_runtime_smoke import smoke


class WindowsSmokeTest(unittest.TestCase):
    def test_failure_isolated_and_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            real_run = subprocess.run
            def fake_run(command, **kwargs):
                if isinstance(command, list) and len(command) > 1 and "ollama_adapter.py" in str(command[1]):
                    repo = pathlib.Path(command[command.index("--repo") + 1])
                    self.assertEqual(real_run(["git", "status", "--porcelain"],
                                              cwd=repo, capture_output=True,
                                              text=True, check=True).stdout, "")
                    return subprocess.CompletedProcess(command, 1, stdout="", stderr="SYNTHETIC_ADAPTER_ERROR")
                return real_run(command, **kwargs)
            with patch("windows_runtime_smoke.subprocess.run", side_effect=fake_run):
                result = smoke(pathlib.Path(folder) / "run")
            self.assertEqual(result["status"], "ADAPTER_FAILED")
            self.assertEqual(result["inference_calls_attempted"], 1)
            self.assertIn("SYNTHETIC_ADAPTER_ERROR", result["stderr_tail"])
            self.assertTrue(result["source_unchanged"])

    def test_replay_uses_saved_response_without_generation(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            response = pathlib.Path(folder) / "saved.json"
            response.write_text(json.dumps({"schema": 1, "file": "calculator.py",
                           "content": "def calculate_total(items):\n    return sum(items) + 1\n"}), encoding="utf-8")
            report=smoke(pathlib.Path(folder)/"replay",response_json=response)
            self.assertEqual(report["inference_calls_attempted"],0)
            self.assertEqual(report["mode"],"OFFLINE_REPLAY")
            self.assertEqual(report["status"],"PATCH_APPLICABLE_NOT_GRADED")
            self.assertTrue(report["source_unchanged"])
            self.assertEqual(report["transport"], "NOT_EVALUATED")

    def test_wrong_model_rejected_before_inference(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                smoke(folder, model="qwen3.5:2b")
            self.assertEqual(list(pathlib.Path(folder).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
