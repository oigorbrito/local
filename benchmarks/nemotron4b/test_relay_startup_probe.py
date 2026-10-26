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
        def simulate(repo, model, out, timeout):
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

    def execute(self, *, db_present, code, timed_out, text):
        with (patch.object(compare, "OUTPUT", self.output),
              patch.object(compare, "prepare", return_value=self.output / "fixture"),
              patch.object(compare, "cloi", side_effect=self.fake_cloi(
                  db_present=db_present, code=code,
                  timed_out=timed_out, text=text))):
            code = compare.cloi_startup_probe(self.identity["tag"], self.identity)
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

    def test_timed_out_cli_is_always_blocked(self):
        code, report = self.execute(
            db_present=True, code=None, timed_out=True,
            text="DIAGNOSTIC_GENERATION_BLOCKED")
        self.assertEqual(code, 2)
        self.assertTrue(report["startup"]["timed_out"])
        self.assertFalse(report["startup"]["completed"])


if __name__ == "__main__":
    unittest.main()
