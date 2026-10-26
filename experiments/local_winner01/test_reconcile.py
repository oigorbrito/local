"""Offline regressions for LOCAL-WINNER-01. No network, Ollama or Docker."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from reconcile import find_reports, safe_json, report_type, rows, integrity, proposed_tasks, hash_bytes

def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return path

class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fixture(self):
        old = write(self.root / "local-model-pilot-20261026-100800/report.json",
            {"mode": "DIRECT_OLLAMA_SINGLE_SHOT_LOCAL_PILOT",
             "requests": [{"task":"calendar_merge","model":"phi4-mini:3.8b",
                           "status":"CALL_NOT_ALLOWLISTED","solved":False,"wall_seconds":19.56,
                           "private_code":"DO_NOT_COPY"}]})
        new = write(self.root / "local-model-pilot-20261026-100800-rejudge-v2/rejudge-report.json",
            {"kind":"OFFLINE_REJUDGE_ARCHIVED_RESPONSES","schema":2,
             "original_results":str(old.parent),"original_report_sha256":hash_bytes(old.read_bytes()),
             "rejudged_rows":[{"task":"calendar_merge","model":"phi4-mini:3.8b",
                               "new_status":"PASS","solved":True,"wall_seconds_original":19.56}]})
        real = write(self.root / "local-real-code-20261026-111812/report.json",
            {"schema":2,"source_repo":"oigorbrito/local",
             "source_path":"experiments/local07/retrieve_context.py",
             "results":[{"model":"qwen3.5:4b-q4_K_M","status":"FUNCTIONAL_FAIL","pass":False}]})
        comp = write(self.root / "local-real-code-20261026-111812-phi-completion/completion_report.json",
            {"schema":3,"continuation_of":str(real.parent),"original_report_sha256":hash_bytes(real.read_bytes()),
             "results":[{"model":"qwen3.5:4b-q4_K_M","status":"FUNCTIONAL_FAIL","pass":False},
                        {"model":"phi4-mini:3.8b","status":"INVALID_CANDIDATE","pass":False}]})
        repair = write(self.root / "local-real-code-20261026-111812-recovery02/report.json",
            {"phase":"RECOVERY02","base_report_sha256":hash_bytes(real.read_bytes()),
             "completion_report_sha256":hash_bytes(comp.read_bytes()),
             "repairs":[{"model":"phi4-mini:3.8b","status":"INVALID_CANDIDATE","pass":False}]})
        return [old, new, real, comp, repair]

    def test_discovery_all_five_reports(self):
        expected = self.fixture()
        self.assertEqual(set(find_reports([self.root],[])),set(expected))

    def test_linked_hashes_verified(self):
        files=self.fixture()
        report=[]
        for f in files:
            obj,sha=safe_json(f)
            flavor=report_type(obj,f.name)
            report.append({"path":str(f),"sha256":sha,"kind":flavor,"_doc":obj,"rows":rows(obj,flavor)})
        self.assertEqual([x["status"] for x in integrity(report)],["VERIFIED"]*4)
        self.assertEqual(report[1]["rows"][0]["pass"],True)

    def test_corrupting_original_blocks_link(self):
        files=self.fixture()
        first=json.loads(files[0].read_text())
        first["requests"][0]["solved"] = True
        write(files[0],first)
        rec=[]
        for f in files:
            obj,sha=safe_json(f)
            rec.append({"path":str(f),"sha256":sha,"kind":report_type(obj,f.name),"_doc":obj})
        self.assertIn("MISMATCH",[x["status"] for x in integrity(rec)])

    def test_known_case_by_name_and_fingerprint(self):
        base={"source_repo":"oigorbrito/local","base_commit":"a"*40,"oracle_sha256":"b"*64,"prompt_sha256":"c"*64}
        data=[{**base,"case_id":"calendar_merge"},
              {**base,"case_id":"renamed_case",
               "oracle_sha256":"8b3a5e12dd5f8645168b91dabb043583b896fed9365f519410d1d38ee489b873"},
              {**base,"case_id":"fresh_case"},
              {**base,"case_id":"fresh_case"}]
        output=proposed_tasks(data)
        self.assertEqual([x["status"] for x in output],
          ["EXISTING_HISTORICAL_TASK","SAME_ORACLE_SHA256",
           "NEW_UNVERIFIED","DUPLICATE_IN_PROPOSED_SET"])

    def test_reject_unknown_report_format(self):
        p=write(self.root/"local-model-pilot-unknown/report.json",{"secret":"DO_NOT_EXPORT"})
        doc,_=safe_json(p)
        self.assertEqual(report_type(doc,p.name),"UNKNOWN_FORMAT")
        self.assertEqual(rows(doc,"UNKNOWN_FORMAT"),[])

    def test_invalid_task_identity(self):
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_CASE_IDENTITY"):
            proposed_tasks([{"case_id":"fresh"}])

if __name__=="__main__":
    unittest.main()
