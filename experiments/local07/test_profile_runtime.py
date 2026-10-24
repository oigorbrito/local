"""Offline LOCAL-16 integration and adversarial transport regressions."""
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from executor_bridge import ContractError
from inspect_profiles import inspect, MAX_SHOW_BYTES
from model_profiles import PROFILES, select_profile
from ollama_adapter import generate
from profile_cli import run


class MockShowResponse:
    def __init__(self, content, status=200, length=None):
        self.content, self.status, self.length = content, status, length

    def getheader(self, key):
        return self.length if key == "Content-Length" else None

    def read(self, count):
        return self.content[:count]


class MockConnection:
    def __init__(self, response):
        self.response = response
        self.request_args = None
        self.closed = False

    def request(self, *args, **kwargs):
        self.request_args = (args, kwargs)

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True, capture_output=True
    ).stdout


class PolicyContractTests(unittest.TestCase):
    def test_profiles_are_versioned_and_fingerprinted(self):
        self.assertEqual(set(PROFILES), {"principal", "alternativo", "economico"})
        self.assertEqual(len({p.fingerprint for p in PROFILES.values()}), 3)
        for name in PROFILES:
            profile = select_profile(name)
            self.assertEqual(profile.version, "1.0.0")
            self.assertEqual(len(profile.fingerprint), 64)
            self.assertEqual(profile.manifest()["fingerprint_sha256"], profile.fingerprint)
            self.assertEqual(profile.options["temperature"], 0)
            altered = profile.options
            altered["temperature"] = 42
            self.assertEqual(profile.options["temperature"], 0)

    def test_unknown_profile_fail_closed(self):
        for name in ("other", "", None, [], ["principal"]):
            with self.subTest(name=name), self.assertRaises(ValueError):
                select_profile(name)

    def test_adapter_system_is_explicit_and_contract_preserved(self):
        from executor_bridge import Request
        profile = select_profile("principal")
        req = Request("Fix calculator.py calculate()", ("calculator.py",), ())
        generated = json.dumps({
            "schema": 1, "file": "calculator.py",
            "content": "def calculate(x):\n    return x+2\n"
        })
        conn = MockConnection(MockShowResponse(json.dumps({"response": generated}).encode()))
        with patch("ollama_adapter.http.client.HTTPConnection", return_value=conn):
            payload = generate(req, profile.base_model, system=profile.system, options=profile.options)
        self.assertIn(b"calculator.py", payload)
        args, kwargs = conn.request_args
        self.assertEqual(args[:2], ("POST", "/api/generate"))
        request_body = json.loads(kwargs["body"])
        self.assertEqual(request_body["system"], profile.system)
        self.assertEqual(request_body["options"], profile.options)
        self.assertFalse(request_body["stream"])
        self.assertEqual(request_body["format"], "json")
        self.assertTrue(conn.closed)

    def test_unverified_options_and_empty_policy_refused_without_network(self):
        from executor_bridge import Request
        req = Request("Fix calculator.py", ("calculator.py",), ())
        with patch("ollama_adapter.http.client.HTTPConnection") as network:
            for opts in ({"temperature": 1, "num_ctx": 4096, "num_predict": 2048}, {},
                         {"temperature": False, "num_ctx": 4096, "num_predict": 2048}):
                with self.subTest(opts=opts), self.assertRaises(ContractError):
                    generate(req, "qwen3.5:2b", options=opts)
            with self.assertRaises(ContractError):
                generate(req, "qwen3.5:2b", system="")
            network.assert_not_called()


class InspectionTests(unittest.TestCase):
    def test_read_only_native_audit_with_no_raw_modelfile_leak(self):
        native = {
            "modelfile": "FROM private/model/path\nSYSTEM secret-internal-metadata",
            "template": "{{ .Prompt }}",
            "parameters": "temperature 0.5",
            "details": {"family": "qwen", "quantization_level": "Q4_K_M"},
            "capabilities": ["completion", "tools"]
        }
        conn = MockConnection(MockShowResponse(json.dumps(native).encode()))
        with patch("inspect_profiles.http.client.HTTPConnection", return_value=conn):
            record = inspect("alternativo")
        args, kwargs = conn.request_args
        self.assertEqual(args[:2], ("POST", "/api/show"))
        self.assertEqual(json.loads(kwargs["body"])["model"], "qwen3.5:4b")
        self.assertEqual(record["status"], "INSPECTED_NOT_GRADED")
        self.assertEqual(record["details"]["family"], "qwen")
        self.assertEqual(record["declared_capabilities"], ["completion", "tools"])
        self.assertNotIn("secret-internal-metadata", json.dumps(record))
        self.assertEqual(len(record["native"]["modelfile_sha256"]), 64)
        self.assertTrue(conn.closed)

    def test_remote_endpoint_refused(self):
        with self.assertRaises(ContractError):
            inspect("principal", host="0.0.0.0")

    def test_native_audit_fail_closed(self):
        cases = (
            (b"not-json", 200, None),
            (b'{"foo":"bar"}', 200, None),
            (b'{"template":42}', 200, None),
            (b'{"template":"safe"}', 404, None),
            (b'{"template":"safe"}', 200, str(MAX_SHOW_BYTES + 1)),
            (b'{"template":"safe"}', 200, "bad-length"),
            (b"x" * (MAX_SHOW_BYTES + 1), 200, None)
        )
        for blob, status, length in cases:
            with self.subTest(status=status, blob_len=len(blob)):
                conn = MockConnection(MockShowResponse(blob, status, length))
                with patch("inspect_profiles.http.client.HTTPConnection", return_value=conn):
                    with self.assertRaises(ContractError):
                        inspect("economico")
                self.assertTrue(conn.closed)


class ProfileIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.temp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "local16@test")
        git(self.repo, "config", "user.name", "LOCAL-16")
        (self.repo / "calculator.py").write_text(
            "def calculate(x):\n    return x + 1\n", encoding="utf-8"
        )
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "base")
        self.issue = pathlib.Path(self.temp.name) / "issue.json"
        self.issue.write_text(json.dumps({
            "problem_statement": "Repair calculator.py calculate so it returns x + 2."
        }), encoding="utf-8")
        self.response = json.dumps({
            "schema": 1, "file": "calculator.py",
            "content": "def calculate(x):\n    return x + 2\n"
        }).encode()
        self.saved = pathlib.Path(self.temp.name) / "response.json"
        self.saved.write_bytes(self.response)
        self.report = pathlib.Path(self.temp.name) / "report.json"
        self.patch = pathlib.Path(self.temp.name) / "candidate.patch"

    def tearDown(self):
        self.temp.cleanup()

    def test_offline_replay_and_unmodified_checkout(self):
        with patch("profile_cli.generate") as no_network:
            report = run(
                self.repo, self.issue, "economico", self.report, self.patch,
                offline_response_json=self.saved
            )
        no_network.assert_not_called()
        self.assertEqual(report["status"], "PATCH_APPLICABLE_NOT_GRADED")
        self.assertEqual(report["execution"]["mode"], "offline_replay")
        self.assertFalse(report["execution"]["model_invoked"])
        self.assertEqual(report["execution"]["selected_profile"]["base_model"], "qwen3.5:2b")
        self.assertIn("+    return x + 2", self.patch.read_text())
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        self.assertEqual(git(self.repo, "worktree", "list").count("\n"), 1)
        self.assertIn("return x + 1", (self.repo / "calculator.py").read_text())

    def test_live_mode_uses_selected_policy_without_real_model(self):
        response_copy = pathlib.Path(self.temp.name) / "copy.json"
        with patch("profile_cli.generate", return_value=self.response) as model:
            report = run(
                self.repo, self.issue, "principal", self.report, self.patch,
                response_json_path=response_copy
            )
        self.assertEqual(model.call_args.args[1], "nemotron-3-nano:4b")
        self.assertEqual(model.call_args.kwargs["system"], PROFILES["principal"].system)
        self.assertEqual(model.call_args.kwargs["options"], PROFILES["principal"].options)
        self.assertEqual(report["execution"]["mode"], "local_inference")
        self.assertTrue(report["execution"]["model_invoked"])
        self.assertEqual(response_copy.read_bytes(), self.response)
        self.assertEqual(json.loads(self.report.read_text())["execution"]["selected_profile"]["version"], "1.0.0")

    def test_dirty_repo_rejected_before_model_generation(self):
        (self.repo / "calculator.py").write_text("value = 99\n", encoding="utf-8")
        with patch("profile_cli.generate") as model:
            with self.assertRaises(ContractError):
                run(self.repo, self.issue, "principal", self.report, self.patch)
            model.assert_not_called()
        self.assertFalse(self.report.exists())
        self.assertFalse(self.patch.exists())

    def test_repository_changed_during_generation_fails_closed(self):
        def mutate(*_args, **_kwargs):
            (self.repo / "calculator.py").write_text("value = 99\n", encoding="utf-8")
            return self.response
        with patch("profile_cli.generate", side_effect=mutate):
            with self.assertRaises(ContractError) as caught:
                run(self.repo, self.issue, "principal", self.report, self.patch)
        self.assertEqual(str(caught.exception), "DIRTY_SOURCE_REPOSITORY")
        self.assertFalse(self.report.exists())
        self.assertFalse(self.patch.exists())

    def test_colliding_paths_rejected(self):
        with self.assertRaises(ContractError):
            run(self.repo, self.issue, "economico", self.issue, self.patch,
                offline_response_json=self.saved)
        with self.assertRaises(ContractError):
            run(self.repo, self.issue, "economico", self.report, self.report,
                offline_response_json=self.saved)

    def test_invalid_response_has_no_results(self):
        self.saved.write_bytes(b'{"schema": 1, "file": "../etc/passwd", "content": "x=2"}')
        with self.assertRaises(ContractError):
            run(self.repo, self.issue, "principal", self.report, self.patch,
                offline_response_json=self.saved)
        self.assertFalse(self.report.exists())
        self.assertFalse(self.patch.exists())


if __name__ == "__main__":
    unittest.main()
