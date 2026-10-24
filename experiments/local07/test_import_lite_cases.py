import unittest

from import_lite_cases import ALLOWED, target_paths, transform


class DatasetImportContracts(unittest.TestCase):
    def test_expected_ids(self):
        self.assertEqual(len(ALLOWED), 3)

    def test_gold_only_in_evaluator(self):
        instance = "marshmallow-code__marshmallow-1343"
        row = {"instance_id": instance, "base_commit": "a"*40,
               "problem_statement": "Fix a real bug", "patch": "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n"}
        issue, evaluator = transform(row, instance)
        self.assertNotIn("target_files", issue)
        self.assertNotIn("patch", issue)
        self.assertEqual(evaluator["target_files"], ["src/a.py"])

    def test_conflicting_or_unsafe_paths_fail(self):
        for bad in ["diff --git a/../secret.py b/../secret.py",
                    "diff --git a/a.py b/b.py",
                    "diff --git a/a.txt b/a.txt"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                target_paths(bad)

    def test_wrong_instance_and_commit_fail(self):
        instance = "marshmallow-code__marshmallow-1343"
        row = {"instance_id": instance, "base_commit": "123",
               "problem_statement": "bug", "patch": "diff --git a/a.py b/a.py"}
        with self.assertRaises(ValueError):
            transform(row, instance)
        row["base_commit"] = "b"*40
        with self.assertRaises(ValueError):
            transform(row, "another")
