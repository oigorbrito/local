"""Cloi 2.1.0 SQLite startup differential, with no model generation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import compare


class CloiSqliteProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.identity = {"tag": "nemotron-3-nano:4b",
                         "digest": "d" * 64, "quantization": "Q4_K_M"}

    def execute(self, fail_mounted=False, fail_tmp=False):
        observed = []

        def fake_run(command, **kwargs):
            self.assertEqual(command[0], "node")
            self.assertTrue(command[1].endswith("/cloi_sqlite_probe.mjs"))
            self.assertEqual(kwargs["timeout"], 8)
            data = Path(command[2])
            self.assertEqual(kwargs["env"]["CLOI_DATA_DIR"], str(data))
            self.assertEqual(command[3], self.identity["tag"])
            mounted = "mounted-data" in str(data)
            observed.append("mounted" if mounted else "tmpfs")
            fail = fail_mounted if mounted else fail_tmp
            prefix = ("SQLITE_STAGE_NODE_STARTED\n"
                      "SQLITE_STAGE_IMPORT_BEGIN\n"
                      "SQLITE_STAGE_UPSTREAM_IMPORT_OK\n"
                      "SQLITE_STAGE_FS_WRITE_OK\n"
                      "SQLITE_STAGE_SESSION_CREATE_BEGIN\n")
            if fail:
                return {"code": None, "seconds": 8.0, "timeout": True,
                        "stdout": "", "stderr": prefix}
            data.mkdir(parents=True, exist_ok=True)
            (data / "cloi.db").write_bytes(b"synthetic")
            return {"code": 0, "seconds": 0.19, "timeout": False,
                    "stdout": "", "stderr": prefix +
                    "SQLITE_STAGE_SESSION_CREATED\n"
                    "SQLITE_STAGE_MESSAGE_PERSISTED\nSQLITE_PROBE_PASS\n"}

        with (patch.object(compare, "OUTPUT", self.output),
              patch.object(compare, "run", side_effect=fake_run)):
            exit_code = compare.cloi_sqlite_probe(self.identity["tag"],
                                                  self.identity)
        report = json.loads((self.output / "report.json").read_text())
        self.assertEqual(observed, ["mounted", "tmpfs"])
        self.assertEqual(report["mode"], "CLOI_UPSTREAM_SQLITE_WAL_NO_GENERATION")
        self.assertNotIn("/api/chat", json.dumps(report))
        return exit_code, report

    def test_both_filesystems_pass(self):
        code, report = self.execute()
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "SQLITE_BOTH_PASS")
        self.assertTrue(report["sqlite"]["mounted-results"]["passed"])
        self.assertTrue(report["sqlite"]["tmpfs"]["passed"])

    def test_mount_stall_with_tmpfs_success_is_explicit(self):
        code, report = self.execute(fail_mounted=True)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "SQLITE_MOUNT_SUSPECTED")
        self.assertTrue(report["sqlite"]["mounted-results"]["timed_out"])
        self.assertFalse(report["sqlite"]["mounted-results"]["database_present"])
        self.assertTrue(report["sqlite"]["tmpfs"]["passed"])

    def test_tmpfs_failure_never_claims_mount_only_problem(self):
        code, report = self.execute(fail_tmp=True)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "SQLITE_NOT_ISOLATED")


if __name__ == "__main__":
    unittest.main()
