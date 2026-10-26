"""End-to-end offline audit checks, using the real fixture and LOCAL-09 validator."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from offline_audit import audit_trial

HERE = Path(__file__).resolve().parent
ADAPTER = HERE.parents[1] / "experiments" / "local07"
FIXTURE = HERE / "fixture"
SAFE_SOURCE = '''"""Restricted path reader."""
from pathlib import Path

def read_text_under_root(root, relative_path):
    root = Path(root).resolve()
    relative_path = Path(relative_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("outside root")
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("outside root")
    return target.read_text(encoding="utf-8")
'''


class OfflineAuditTests(unittest.TestCase):
    def prepare(self, root, source):
        evidence = root / "evidence"
        trial = evidence / "r01-local09"
        trial.mkdir(parents=True)
        (evidence / "report.json").write_text("{}", encoding="utf8")
        payload = json.dumps({"schema": 1, "file": "guard.py", "content": source})
        (trial / "model-response.json").write_text(payload, encoding="utf8")
        rawdir = evidence / "raw-ollama-responses"
        rawdir.mkdir()
        raw = json.dumps({"response": payload, "prompt_eval_count": 100,
                          "eval_count": 40}).encode()
        (rawdir / "response.json").write_bytes(raw)
        metrics = {"phase": "r01-local09", "path": "/api/generate",
                   "raw_response": {
                       "relative_path": "raw-ollama-responses/response.json",
                       "sha256": hashlib.sha256(raw).hexdigest(),
                       "bytes": len(raw)}}
        (evidence / "relay-request-metrics.jsonl").write_text(
            json.dumps(metrics) + "\n", encoding="utf8")
        return evidence

    def test_valid_candidate_replays_and_passes_independent_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = self.prepare(root, SAFE_SOURCE)
            row = audit_trial(evidence, root / "audit", FIXTURE, ADAPTER)
            self.assertEqual(row["status"], "AUDITED")
            self.assertEqual(row["raw_response_link"], "MATCH")
            self.assertEqual(row["replay"]["status"], "ACCEPTED")
            self.assertTrue(row["direct"]["functional_passed"])
            self.assertTrue((root / "audit" / "candidate.patch").exists())

    def test_vulnerable_candidate_remains_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = (FIXTURE / "guard.py").read_text(encoding="utf8")
            evidence = self.prepare(root, original)
            row = audit_trial(evidence, root / "audit", FIXTURE, ADAPTER)
            self.assertEqual(row["status"], "AUDITED")
            self.assertFalse(row["direct"]["functional_passed"])
            self.assertNotEqual(row["direct"]["tests_exit"], 0)


if __name__ == "__main__":
    unittest.main()
