"""Grouped offline gate for the executor response protocol, no model calls."""
import json
import pathlib
import subprocess
import tempfile
import unittest

from executor_bridge import ContractError, MAX_RESPONSE_BYTES, parse_response, prepare, replay


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


class ExecutorContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "local09@test")
        git(self.root, "config", "user.name", "LOCAL-09")
        (self.root / "calculator.py").write_text("def calculate(x):\n    return x + 1\n", encoding="utf-8")
        (self.root / "unrelated.py").write_text("def unrelated():\n    return 9\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "base")
        self.issue = "Repair calculator.py calculate so it returns x + 2."

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, **override):
        x = {"schema": 1, "file": "calculator.py", "content": "def calculate(x):\n    return x + 2\n"}
        x.update(override)
        return json.dumps(x).encode("utf-8")

    def test_replay_end_to_end_and_source_immutability(self):
        before = git(self.root, "status", "--porcelain")
        report, patch = replay(self.root, self.issue, self.payload())
        self.assertEqual(report["status"], "PATCH_APPLICABLE_NOT_GRADED")
        self.assertIn("calculator.py", report["request"]["allowed_files"])
        self.assertIn("+    return x + 2", patch)
        self.assertEqual(git(self.root, "status", "--porcelain"), before)
        self.assertEqual((self.root / "calculator.py").read_text(), "def calculate(x):\n    return x + 1\n")

    def test_schema_fail_closed(self):
        bad = [
            b"garbage", b"\xff", b"[]",
            self.payload(schema=2), self.payload(file="../calculator.py"),
            self.payload(file="unrelated.py"), self.payload(content=5),
            self.payload(extra="unsafe"), b" " * (MAX_RESPONSE_BYTES + 1)
        ]
        request = prepare(self.root, self.issue)
        for payload in bad:
            with self.subTest(payload=payload[:40]), self.assertRaises(ContractError):
                parse_response(payload, request.selected_files)

    def test_explicit_localized_request_and_replay(self):
        request = prepare(self.root, self.issue, output_schema=2)
        expected = request.to_json()["output_contract"]
        self.assertEqual(expected["schema"], 2)
        self.assertIn("old", expected)
        self.assertNotIn("content", expected)
        response = json.dumps({
            "schema": 2, "file": "calculator.py",
            "old": "return x + 1", "new": "return x + 2"
        }).encode("utf-8")
        report, patch = replay(self.root, self.issue, response, output_schema=2)
        self.assertEqual(report["request"]["output_contract"]["schema"], 2)
        self.assertEqual(report["status"], "PATCH_APPLICABLE_NOT_GRADED")
        self.assertIn("+    return x + 2", patch)
        with self.assertRaisesRegex(ContractError, "RESPONSE_CONTRACT_VERSION_MISMATCH"):
            replay(self.root, self.issue, self.payload(), output_schema=2)

    def test_localized_anchors_fail_closed_with_distinct_reasons(self):
        for old, expected in (
            ("return x + 404", "EDIT_ANCHOR_NOT_FOUND"),
            (chr(10), "EDIT_ANCHOR_NOT_UNIQUE"),
        ):
            candidate = json.dumps({
                "schema": 2, "file": "calculator.py",
                "old": old, "new": "return x + 2",
            }).encode("utf-8")
            with self.subTest(reason=expected), self.assertRaisesRegex(ContractError, expected):
                replay(self.root, self.issue, candidate)
            self.assertEqual(git(self.root, "status", "--porcelain").strip(), "")

    def test_invalid_syntax_and_dirty_source(self):
        with self.assertRaises(SyntaxError):
            replay(self.root, self.issue, self.payload(content="def calculate("))
        (self.root / "calculator.py").write_text("x = 123\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            replay(self.root, self.issue, self.payload())
