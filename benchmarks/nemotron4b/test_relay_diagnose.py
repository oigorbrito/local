"""Offline regression checks for retained/unfinished model requests."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import diagnose
import relay_host


class DiagnosisTests(unittest.TestCase):
    def make_results(self, root):
        (root / "report.json").write_text(json.dumps({
            "schema": 2, "status": "BLOCKED_TRANSPORT_OR_TIMEOUT",
            "first_executor": "cloi",
            "blocking": {"reason": "EXECUTOR_WALL_TIMEOUT",
                         "executor": "cloi", "repeat": 1},
            "runs": [{"executor": "cloi", "repeat": 1,
                      "wall_seconds": 420.175, "timed_out": True,
                      "passed": False, "returncode": None}]
        }), encoding="utf8")

    def test_older_artifacts_never_claim_zero_pending_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_results(root)
            (root / "relay-request-metrics.jsonl").write_text(
                json.dumps({"request_id": "a" * 32,
                            "phase": "r01-cloi", "path": "/api/tags",
                            "http_status": "200"}) + "\n", encoding="utf8")
            diag = diagnose.analyze(root)
            self.assertEqual(diag["status"], "BLOCKED_TRANSPORT_OR_TIMEOUT")
            self.assertIn("cannot be reconstructed", diag["limitation"])
            self.assertEqual(diag["phases"][0]["coverage"],
                             "HISTORICAL_COMPLETED_ONLY")
            self.assertIsNone(diag["phases"][0]["requests_started"])

    def test_started_request_without_terminal_record_is_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_results(root)
            req = {"id": "b" * 32, "method": "POST",
                   "path": "/api/chat", "body": "SECRET_MODEL_PROMPT"}
            self.assertTrue(relay_host.record_request_start(
                root / "relay-request-metrics.jsonl", req, "r01-cloi"))
            persisted = (root / "relay-request-starts.jsonl").read_text()
            self.assertNotIn("SECRET_MODEL_PROMPT", persisted)
            diag = diagnose.analyze(root)
            phase = diag["phases"][0]
            self.assertEqual(phase["phase"], "r01-cloi")
            self.assertEqual(phase["requests_started"], 1)
            self.assertEqual(phase["requests_recorded"], 0)
            self.assertEqual(phase["unfinished_at_collection"][0]["path"], "/api/chat")
            self.assertIsNone(diag["limitation"])

    def test_raw_ndjson_attests_completion_without_exposing_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_results(root)
            rawdir = root / "raw-ollama-responses"
            rawdir.mkdir()
            payload = (json.dumps({"message": {"content": "PRIVATE_CONTENT"}, "done": False})
                       + "\n" + json.dumps({"done": True, "eval_count": 5}) + "\n").encode()
            (rawdir / "x.ndjson").write_bytes(payload)
            metrics = {
                "request_id": "a" * 32, "phase": "r01-cloi", "path": "/api/chat",
                "http_status": "200", "response_complete": True,
                "prompt_tokens": 10, "output_tokens": 5,
                "raw_response": {
                    "relative_path": "raw-ollama-responses/x.ndjson",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                },
            }
            (root / "relay-request-metrics.jsonl").write_text(
                json.dumps(metrics) + "\n", encoding="utf8")
            diag = diagnose.analyze(root)
            request = diag["phases"][0]["requests"][0]
            self.assertEqual(request["raw"]["ndjson_lines"], 2)
            self.assertTrue(request["raw"]["ollama_done_frame"])
            self.assertTrue(request["raw"]["sha256_ok"])
            self.assertNotIn("PRIVATE_CONTENT", json.dumps(diag))

    def test_unsafe_raw_path_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = diagnose.describe_response(root, {
                "path": "/api/chat",
                "raw_response": {"relative_path": "../secret.txt", "sha256": "x"}
            })
            self.assertEqual(raw["integrity"], "MISSING_OR_UNSAFE_PATH")


if __name__ == "__main__":
    unittest.main()
