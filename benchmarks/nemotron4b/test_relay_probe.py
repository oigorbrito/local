"""No-generation Cloi preflight: bounded stages and fail-closed exit."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import compare


class CloiProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.identity = {"tag": "nemotron-3-nano:4b", "digest": "d" * 64,
                         "quantization": "Q4_K_M"}

    def call_probe(self, *, code, timeout, stderr):
        result = {
            "code": code, "timeout": timeout, "seconds": 15.0 if timeout else 0.35,
            "stdout": "", "stderr": stderr,
        }
        with (patch.object(compare, "OUTPUT", self.directory),
              patch.object(compare, "run", return_value=result) as subprocess):
            status = compare.cloi_preflight_probe(self.identity["tag"], self.identity)
        report = json.loads((self.directory / "report.json").read_text())
        self.assertEqual(subprocess.call_count, 1)
        argv = subprocess.call_args.args[0]
        self.assertEqual(argv[0], "node")
        self.assertTrue(argv[1].endswith("cloi_probe.mjs"))
        self.assertNotIn("/api/chat", " ".join(argv))
        self.assertNotIn("/api/generate", " ".join(argv))
        self.assertEqual(subprocess.call_args.kwargs["timeout"], 15)
        self.assertEqual(report["mode"], "CLOI_NODE_PREFLIGHT_NO_GENERATION")
        return status, report

    def test_all_node_stages_pass(self):
        status, report = self.call_probe(
            code=0, timeout=False,
            stderr="\n".join([
                "PROBE_NODE_STARTED", "PROBE_TAGS_HTTP_OK",
                "PROBE_TAGS_JSON_PARSED", "PROBE_SHOW_REQUEST_BEGIN",
                "PROBE_SHOW_JSON_PARSED", "PROBE_PREFLIGHT_PASS",
            ]) + "\n",
        )
        self.assertEqual(status, 0)
        self.assertEqual(report["status"], "PROBE_PASS")
        self.assertTrue(report["probe"]["completed"])

    def test_unfinished_show_is_not_misclassified_as_success(self):
        status, report = self.call_probe(
            code=None, timeout=True,
            stderr="PROBE_NODE_STARTED\nPROBE_TAGS_JSON_PARSED\n"
                   "PROBE_SHOW_REQUEST_BEGIN\n",
        )
        self.assertEqual(status, 2)
        self.assertEqual(report["status"], "PROBE_BLOCKED")
        self.assertTrue(report["probe"]["timed_out"])
        self.assertNotIn("PROBE_SHOW_JSON_PARSED", report["probe"]["stages"])


if __name__ == "__main__":
    unittest.main()
