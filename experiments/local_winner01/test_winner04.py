"""Offline contracts for LOCAL-WINNER-04. No Ollama, Docker or inference."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(ROOT))
from winner04_preflight import CASES, oracle_valid
from winner04_generate import prompt_for

class Winner04Contracts(unittest.TestCase):
    def test_exactly_eight_unique_cases(self):
        self.assertEqual(len(CASES), 8)
        self.assertEqual(len(set(CASES)), 8)

    def test_oracle_rejects_missing_or_ungraded(self):
        for case in CASES:
            self.assertFalse(oracle_valid({}, case))
            self.assertFalse(oracle_valid({"case_id":case,"status":"FUNCTIONAL_ORACLE_QUALIFIED"},case))
            self.assertFalse(oracle_valid({"case_id":case,"status":"BLOCKED_BASELINE_NOT_REPRODUCED"},case))

    def test_oracle_rejects_fake_gold_success(self):
        case=CASES[0]
        record={"case_id":case,"status":"FUNCTIONAL_ORACLE_QUALIFIED",
                "f2p_expected":1,
                "baseline":{"status":"GRADED","f2p_failed":1,
                            "tests_parsed":True,"environment_failure":False},
                "gold":{"status":"GRADED","resolved":True,"f2p_passed":1,
                        "f2p_failed":0,"p2p_failed":1,"tests_parsed":True,
                        "environment_failure":False}}
        self.assertFalse(oracle_valid(record,case))
        record["gold"]["p2p_failed"]=0
        self.assertTrue(oracle_valid(record,case))

    def test_prompt_never_includes_test_folder(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"src").mkdir()
            (root/"tests").mkdir()
            (root/"src"/"logic.py").write_text("def f(): return 1\n")
            (root/"tests"/"test_logic.py").write_text("PRIVATE_ORACLE")
            prompt,paths=prompt_for({"issue_id":CASES[0],
                "problem_statement":"Correct a bug"},root)
            self.assertEqual(paths,["src/logic.py"])
            self.assertNotIn("PRIVATE_ORACLE",prompt)
            self.assertIn("Correct a bug",prompt)

if __name__=="__main__":
    unittest.main()
