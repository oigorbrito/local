import json
import pathlib
import tempfile
import unittest

from fixture_functional_grade import evaluate_fixture, grade_response_file


class FunctionalFixtureOracle(unittest.TestCase):
    def test_pure_function_success(self):
        r = evaluate_fixture("def calculate_total(items):\n    return sum(items) + 1\n")
        self.assertEqual((r["status"], r["passed"], r["total"]), ("FIXTURE_PASS", 4, 4))

    def test_wrong_behavior_rejected(self):
        for code in [
            "def calculate_total(items):\n    return sum(items)\n",
            "def calculate_total(items):\n    return sum(items) + 2\n",
        ]:
            with self.subTest(code=code):
                self.assertEqual(evaluate_fixture(code)["status"], "FIXTURE_FAIL")

    def test_unsafe_and_unexpected_ast_rejected_without_execution(self):
        for code in [
            "import os\ndef calculate_total(items):\n    return sum(items) + 1\n",
            "def calculate_total(items):\n    __import__('os').system('echo unsafe')\n    return sum(items)+1\n",
            "def calculate_total(items):\n    return eval('sum(items)+1')\n",
            "def calculate_total(items):\n    while True: pass\n",
            "def calculate_total(items):\n    return (sum(items)+1).__class__\n",
        ]:
            with self.subTest(code=code):
                self.assertEqual(evaluate_fixture(code)["status"], "UNSUPPORTED_AST")

    def test_grade_saved_response_contract_and_hash(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "model-response.json"
            path.write_text(json.dumps({
                "schema": 1, "file": "calculator.py",
                "content": "def calculate_total(items):\n    return sum(items) + 1\n"
            }), encoding="utf-8")
            grade = grade_response_file(path)
            self.assertEqual(grade["status"], "FIXTURE_PASS")
            self.assertFalse(grade["generated_code_executed"])
            self.assertEqual(len(grade["response_sha256"]), 64)
            path.write_text(json.dumps({"schema": 1, "file": "../calculator.py", "content": "pass"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                grade_response_file(path)
