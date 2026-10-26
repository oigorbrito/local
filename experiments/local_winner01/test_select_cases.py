"""Offline tests for deterministic, no-repetition case freezing."""
import json
import unittest
from collections import Counter
from select_cases import extract, freeze, one, DATASET, SEED

OLD = [
    ("marshmallow-code__marshmallow-1343","marshmallow-code/marshmallow","2be2d83a1a9a6d3d9b85804f3ab545cecc409bb0"),
    ("marshmallow-code__marshmallow-1359","marshmallow-code/marshmallow","b40a0f4e33823e6d0f341f7e8684e359a99060d1"),
    ("pvlib__pvlib-python-1072","pvlib/pvlib-python","04a523fafbd61bc2e49420963b84ed8e2bd1b3cf"),
]
def dataset():
    data=[]
    for ident,repo,sha in OLD:
        data.append({"instance_id":ident,"repo":repo,"base_commit":sha})
    for i in range(20):
        ident=f"package{i % 5}__fix-{1200 + i}"
        data.append({"instance_id":ident,"repo":f"owner{i % 5}/package{i % 5}",
                     "base_commit":f"{i+1:040x}"})
    for row in data:
        row.update({
            "problem_statement":f"Fix behavior in {row['instance_id']} based on a real regression and preserve existing behavior.",
            "patch":"diff --git a/module.py b/module.py\n--- a/module.py\n+++ b/module.py\n@@ -1 +1 @@\n-old\n+new\n",
            "test_patch":"independent oracle only SECRET_PASSED_TO_EVALUATOR",
            "FAIL_TO_PASS":json.dumps([f"test_{row['instance_id']}"])})
    return json.dumps({"num_rows_total":23,
                       "rows":[{"row_idx":i,"row":row} for i,row in enumerate(data)]}).encode()

class SelectionTests(unittest.TestCase):
    def test_freeze_eight_unique_new_tasks(self):
        manifest,issues=freeze(dataset())
        self.assertEqual(len(manifest["cases"]),8)
        self.assertEqual(len(issues),8)
        self.assertEqual(Counter(c["stage"] for c in manifest["cases"]),{"ELIMINATION":3,"FINAL_HOLDOUT":5})
        self.assertLessEqual(max(Counter(c["source_repo"] for c in manifest["cases"]).values()),2)
        self.assertTrue(all(x["case_id"] not in {v[0] for v in OLD} for x in manifest["cases"]))
        self.assertEqual(manifest["status"],"CANDIDATE_ONLY_BASELINE_AND_ORACLE_NOT_YET_QUALIFIED")

    def test_gold_and_oracle_not_leaked_to_model(self):
        manifest,issues=freeze(dataset())
        serialized=json.dumps({"manifest":manifest,"issues":issues})
        self.assertNotIn("SECRET_PASSED_TO_EVALUATOR",serialized)
        self.assertNotIn("diff --git",serialized)
        self.assertNotIn("target_files",serialized)
        self.assertNotIn("FAIL_TO_PASS",serialized)

    def test_selection_independent_of_row_order(self):
        raw=dataset()
        original=json.loads(raw)
        original["rows"].reverse()
        a,_=freeze(raw)
        b,_=freeze(json.dumps(original).encode())
        self.assertEqual([x["case_id"] for x in a["cases"]],[x["case_id"] for x in b["cases"]])
        self.assertNotEqual(a["raw_dataset_sha256"],b["raw_dataset_sha256"])

    def test_old_cases_are_excluded(self):
        result,reason=one({"instance_id":OLD[0][0]})
        self.assertIsNone(result)
        self.assertEqual(reason,"HISTORIC_INSTANCE")

    def test_wrong_split_size_rejected(self):
        raw=json.loads(dataset())
        raw["num_rows_total"]=22
        with self.assertRaisesRegex(ValueError,"NOT_CANONICAL"):
            extract(json.dumps(raw).encode())

    def test_fewer_than_eight_different_repo_slots_rejected(self):
        raw=json.loads(dataset())
        for row in raw["rows"][3:]:
            row["row"]["repo"]="one/repo"
        with self.assertRaisesRegex(ValueError,"INSUFFICIENT_ELIGIBLE"):
            freeze(json.dumps(raw).encode())

    def test_dangerous_gold_paths_rejected_without_running(self):
        row=json.loads(dataset())["rows"][3]["row"]
        row["patch"]="diff --git a/../secret.py b/../secret.py\n"
        obj,reason=one(row)
        self.assertIsNone(obj)
        self.assertEqual(reason,"UNSAFE_GOLD_TARGET")

    def test_no_reconfiguration_after_protocol_freeze(self):
        with self.assertRaisesRegex(ValueError,"SELECTION_CONTRACT_CHANGED"):
            freeze(dataset(),first=4,final=4)

if __name__=="__main__":
    unittest.main()
