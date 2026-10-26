"""Full Cloi CLI startup probe tests without real Node, Docker or Ollama."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import compare


class FullStartupProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.identity = {
            "tag": "nemotron-3-nano:4b",
            "quantization": "Q4_K_M", "digest": "d" * 64,
        }

    def fake_cloi(self, *, db_present, code, timed_out, text):
        def simulate(repo, model, out, timeout, startup_trace=False):
            self.assertTrue(startup_trace)
            self.assertEqual(model, self.identity["tag"])
            self.assertEqual(timeout, 20)
            self.assertEqual(out, self.output / "cloi-startup-probe")
            if db_present:
                data = out / "cloi-data"
                data.mkdir()
                conn = sqlite3.connect(str(data / "cloi.db"))
                conn.executescript("""
                    CREATE TABLE sessions(id TEXT);
                    CREATE TABLE messages(role TEXT, content TEXT);
                    INSERT INTO sessions VALUES ('session');
                    INSERT INTO messages VALUES ('user','PRIVATE_MODEL_PROMPT');
                """)
                conn.close()
            return {"code": code, "timeout": timed_out, "seconds": 1.1,
                    "stderr": text, "stdout": ""}
        return simulate

    def execute(self, *, db_present, code, timed_out, text, bootstrap_fail=False):
        probe = {"code": 1 if bootstrap_fail else 0,
                 "timeout": bootstrap_fail,
                 "seconds": 6.0 if bootstrap_fail else 0.1,
                 "stdout": "", "stderr": ""}
        with (patch.object(compare, "OUTPUT", self.output),
              patch.object(compare, "prepare", return_value=self.output / "fixture") as prep,
              patch.object(compare, "run", return_value=probe) as bootstrap,
              patch.object(compare, "cloi", side_effect=self.fake_cloi(
                  db_present=db_present, code=code,
                  timed_out=timed_out, text=text)) as executor):
            code = compare.cloi_startup_probe(self.identity["tag"], self.identity)
        self.assertEqual(bootstrap.call_count, 1)
        self.assertIn("--help", bootstrap.call_args.args[0])
        self.assertEqual(bootstrap.call_args.kwargs["timeout"], 6)
        if bootstrap_fail:
            executor.assert_not_called()
            prep.assert_not_called()
        else:
            executor.assert_called_once()
        report = json.loads((self.output / "report.json").read_text())
        return code, report

    def test_real_cli_reaches_denied_generation_after_session(self):
        code, report = self.execute(
            db_present=True, code=1, timed_out=False,
            text="Model call failed: DIAGNOSTIC_GENERATION_BLOCKED")
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "STARTUP_REACHED_GENERATION_GATE")
        self.assertEqual(report["startup"]["counts"]["sessions"], 1)
        self.assertEqual(report["startup"]["counts"]["messages"]["user"], 1)
        self.assertNotIn("PRIVATE_MODEL_PROMPT", json.dumps(report))

    def test_no_session_still_blocks_even_with_expected_denial(self):
        code, report = self.execute(
            db_present=False, code=1, timed_out=False,
            text="DIAGNOSTIC_GENERATION_BLOCKED")
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "STARTUP_BLOCKED")
        self.assertFalse(report["startup"]["session_database_present"])

    def test_cli_module_bootstrap_timeout_prevents_agent_start(self):
        code, report = self.execute(
            db_present=False, code=0, timed_out=False,
            text="", bootstrap_fail=True)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "STARTUP_BLOCKED")
        self.assertFalse(report["startup"]["cli_help"]["passed"])
        self.assertTrue(report["startup"]["cli_help"]["timed_out"])

    def test_http_trace_retains_only_route_and_event_metadata(self):
        observed = ("STARTUP_TRACE " + json.dumps({
            "event": "request_created", "route": "/api/show",
            "ms": 157, "request_id": 1, "private_extra": "SECRET_MODEL_BYTES"
        }) + "\n" + "Model call failed: DIAGNOSTIC_GENERATION_BLOCKED")
        code, report = self.execute(
            db_present=True, code=1, timed_out=False, text=observed)
        self.assertEqual(code, 0)
        self.assertEqual(report["startup"]["request_trace"][0],
                         {"event": "request_created", "route": "/api/show",
                          "ms": 157, "request_id": 1, "status": None,
                          "error_name": None, "error_code": None})
        self.assertNotIn("SECRET_MODEL_BYTES", json.dumps(report))

    def test_timed_out_cli_is_always_blocked(self):
        code, report = self.execute(
            db_present=True, code=None, timed_out=True,
            text="DIAGNOSTIC_GENERATION_BLOCKED")
        self.assertEqual(code, 2)
        self.assertTrue(report["startup"]["timed_out"])
        self.assertFalse(report["startup"]["completed"])


if __name__ == "__main__":
    unittest.main()
