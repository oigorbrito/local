"""Offline regression checks for retained/unfinished model requests."""
import hashlib
import json
import sqlite3
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
            self.assertIn("no progress-stage events", diag["limitation"])

    def test_unfinished_request_records_last_progress_stage_without_model_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_results(root)
            item = {"id": "c" * 32, "method": "POST",
                    "path": "/api/chat", "body": "SECRET_PROMPT"}
            self.assertTrue(relay_host.record_request_start(
                root / "relay-request-metrics.jsonl", item, "r01-cloi"))
            relay_host.record_request_progress(
                root / "relay-request-metrics.jsonl", "c" * 32, "r01-cloi",
                "upstream_request_sent", 0.15)
            relay_host.record_request_progress(
                root / "relay-request-metrics.jsonl", "c" * 32, "r01-cloi",
                "upstream_headers_received", 90.0, http_status=200)
            relay_host.record_request_progress(
                root / "relay-request-metrics.jsonl", "c" * 32, "r01-cloi",
                "upstream_first_chunk", 94.0, response_bytes=30, http_status=200)
            diag = diagnose.analyze(root)
            phase = diag["phases"][0]
            self.assertEqual(len(phase["request_events"]), 3)
            self.assertEqual(phase["request_events"][-1]["stage"], "upstream_first_chunk")
            self.assertEqual(phase["unfinished_at_collection"][0]["path"], "/api/chat")
            self.assertIsNone(diag["limitation"])
            self.assertNotIn("SECRET_PROMPT", json.dumps(diag))

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

    def test_cloi_sqlite_counts_steps_without_exposing_session_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_results(root)
            data = root / "r01-cloi" / "cloi-data"
            data.mkdir(parents=True)
            conn = sqlite3.connect(str(data / "cloi.db"))
            conn.executescript("""
                CREATE TABLE sessions (id TEXT);
                CREATE TABLE messages (
                    role TEXT, tool_name TEXT, content TEXT
                );
                CREATE TABLE results (name TEXT);
                INSERT INTO sessions VALUES ('session');
                INSERT INTO messages VALUES ('user', NULL, 'SECRET_USER_PROMPT');
                INSERT INTO messages VALUES ('assistant', NULL, 'PRIVATE_MODEL_ANSWER');
                INSERT INTO messages VALUES ('tool', 'read_file', 'SECRET_TOOL_OUTPUT');
                INSERT INTO results VALUES ('handle');
            """)
            conn.close()
            diag = diagnose.analyze(root)
            session = diag["cloi_sessions"]["r01-cloi"]
            self.assertTrue(session["readable"])
            self.assertEqual(session["roles"],
                             {"assistant": 1, "tool": 1, "user": 1})
            self.assertEqual(session["tool_results_by_name"], {"read_file": 1})
            self.assertEqual(session["stored_results"], 1)
            serialized = json.dumps(diag)
            for secret in ("SECRET_USER_PROMPT", "PRIVATE_MODEL_ANSWER",
                           "SECRET_TOOL_OUTPUT"):
                self.assertNotIn(secret, serialized)

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
