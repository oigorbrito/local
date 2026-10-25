"""LOCAL-16 operator session acceptance on real Git repositories; never invokes Ollama."""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from executor_bridge import ContractError
from local16_workflow import (
    REPORT, PATCH, REQUEST, RESPONSE, ISSUE, MANIFEST, NATIVE, ATTEMPT, FAILURE,
    create, load, generate, check, approve, status, tracked_sources,
)
from model_profiles import PROFILES

def native_evidence(name):
    return {
        "status": "INSPECTED_NOT_GRADED",
        "profile": name,
        "native_model": PROFILES[name].base_model,
        "profile_fingerprint_sha256": PROFILES[name].fingerprint,
        "native_model_digest_sha256": "f" * 64,
        "native": {"modelfile_sha256": "a" * 64}
    }


SCRIPT = pathlib.Path(__file__).with_name("local16_workflow.py")
RESPONSE_BODY = {
    "schema": 1, "file": "calculator.py",
    "content": "def calculate(x):\n    return x + 2\n",
}


def git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, text=True,
        capture_output=True, check=True, timeout=20
    ).stdout.strip()


class WorkflowSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.repo = self.root / "checkout"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Local Workflow")
        git(self.repo, "config", "user.email", "local16@example.invalid")
        (self.repo / "calculator.py").write_text(
            "def calculate(x):\n    return x + 1\n", encoding="utf-8"
        )
        (self.repo / "misc.py").write_text(
            "def miscellany():\n    return 3\n", encoding="utf-8"
        )
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "base")
        self.session = self.root / "session"
        self.response = self.root / "mock-response.json"
        self.response.write_text(json.dumps(RESPONSE_BODY), encoding="utf-8")
        self.task = "Fix calculator.py calculate so the function returns x + 2."

    def prepared(self, profile="principal"):
        record = create(self.repo, self.session, profile, self.task)
        self.assertEqual(record["status"], "SESSION_PREPARED")
        return record

    def replayed(self):
        self.prepared()
        with patch("profile_cli.generate") as network:
            result = generate(self.session, offline_response_json=self.response)
        network.assert_not_called()
        self.assertEqual(result["mode"], "offline_replay")
        self.assertEqual(result["inference_calls_attempted"], 0)
        return result

    def test_full_session_replay_review_manual_apply(self):
        result = self.replayed()
        self.assertEqual(result["status"], "PATCH_APPLICABLE_NOT_GRADED")
        self.assertEqual(status(self.session)["status"], "PATCH_READY_FOR_REVIEW")
        checked = check(self.session)
        self.assertEqual(checked["status"], "PATCH_READY_FOR_REVIEW")
        digest = hashlib.sha256((self.session / PATCH).read_bytes()).hexdigest()
        self.assertEqual(checked["patch_sha256"], digest)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        with patch("profile_cli.generate") as model:
            applied = approve(self.session, digest)
            model.assert_not_called()
        self.assertEqual(applied["status"], "PATCH_APPLIED_UNSTAGED")
        self.assertIn("return x + 2", (self.repo / "calculator.py").read_text())
        self.assertIn("return 3", (self.repo / "misc.py").read_text())
        self.assertEqual(git(self.repo, "diff", "--cached", "--name-only"), "")
        self.assertEqual(git(self.repo, "diff", "--name-only"), "calculator.py")
        self.assertEqual(status(self.session)["status"], "SOURCE_OR_PATCH_REQUIRES_INSPECTION")
        self.assertFalse(applied["code_execution"])

    def test_live_generation_pins_native_identity_and_can_be_reviewed(self):
        self.prepared("alternativo")
        payload = json.dumps(RESPONSE_BODY).encode("utf-8")
        native_reads = []
        def inspector(name):
            native_reads.append(name)
            return native_evidence(name)
        with patch("profile_cli.generate", return_value=payload) as model:
            result = generate(self.session, inspector=inspector)
        self.assertEqual(result["mode"], "local_inference")
        self.assertEqual(result["native_identity"], "VERIFIED")
        self.assertEqual(result["inference_calls_attempted"], 1)
        self.assertEqual(native_reads, ["alternativo", "alternativo"])
        model.assert_called_once()
        evidence = json.loads((self.session / NATIVE).read_text())
        self.assertEqual(evidence["before"]["native_model_digest_sha256"], "f" * 64)
        self.assertEqual(evidence["status"], "VERIFIED")
        self.assertEqual(check(self.session)["status"], "PATCH_READY_FOR_REVIEW")
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_live_inspection_blocks_before_network_generation(self):
        self.prepared()
        with patch("profile_cli.generate") as model:
            with self.assertRaisesRegex(ContractError, "NATIVE_INSPECTION_BLOCKED"):
                generate(self.session, inspector=lambda _name: {"status": "NOT_FOUND"})
            model.assert_not_called()
        for name in (REPORT, RESPONSE, PATCH, NATIVE):
            self.assertFalse((self.session / name).exists())

    def test_digest_drift_after_live_generation_blocks_approval(self):
        self.prepared()
        reads = []
        def inspector(name):
            result = native_evidence(name)
            reads.append(name)
            if len(reads) == 2:
                result["native_model_digest_sha256"] = "0" * 64
            return result
        with patch("profile_cli.generate", return_value=json.dumps(RESPONSE_BODY).encode()) as model:
            with self.assertRaisesRegex(ContractError, "NATIVE_MODEL_IDENTITY_DRIFT"):
                generate(self.session, inspector=inspector)
        model.assert_called_once()
        self.assertEqual(len(reads), 2)
        self.assertEqual(json.loads((self.session / NATIVE).read_text())["status"],
                         "DRIFT_OR_INCOMPLETE")
        with self.assertRaisesRegex(ContractError, "NATIVE_IDENTITY_UNVERIFIED"):
            check(self.session)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_unreachable_post_generation_inspection_refuses_review(self):
        self.prepared()
        calls = []
        def inspector(name):
            calls.append(name)
            if len(calls) == 2:
                raise OSError("private-system-failure-details")
            return native_evidence(name)
        with patch("profile_cli.generate", return_value=json.dumps(RESPONSE_BODY).encode()):
            with self.assertRaisesRegex(ContractError, "POST_INSPECTION_BLOCKED"):
                generate(self.session, inspector=inspector)
        self.assertEqual(json.loads((self.session / NATIVE).read_text())["status"],
                         "POST_INSPECTION_BLOCKED")
        self.assertNotIn("private-system-failure-details",
                         (self.session / NATIVE).read_text())
        with self.assertRaisesRegex(ContractError, "NATIVE_IDENTITY_UNVERIFIED"):
            check(self.session)

    def test_missing_native_evidence_fails_live_review(self):
        self.prepared()
        with patch("profile_cli.generate", return_value=json.dumps(RESPONSE_BODY).encode()):
            generate(self.session, inspector=native_evidence)
        (self.session / NATIVE).unlink()
        with self.assertRaisesRegex(ContractError, "NATIVE_IDENTITY_EVIDENCE_MISSING"):
            check(self.session)

    def test_failed_live_attempt_is_consumed_and_never_auto_retries(self):
        self.prepared()
        with patch("profile_cli.generate", side_effect=ContractError("MODEL_TIMEOUT")) as model:
            with self.assertRaisesRegex(ContractError, "MODEL_TIMEOUT"):
                generate(self.session, inspector=native_evidence)
            self.assertEqual(model.call_count, 1)
        self.assertTrue((self.session / ATTEMPT).is_file())
        self.assertEqual(status(self.session)["status"], "GENERATION_INCOMPLETE_REQUIRES_NEW_SESSION")
        with patch("profile_cli.generate") as model:
            with self.assertRaisesRegex(ContractError, "SESSION_ALREADY_GENERATED"):
                generate(self.session, inspector=native_evidence)
            model.assert_not_called()

    def test_failure_evidence_sanitized_and_no_retry(self):
        self.prepared()
        with patch("profile_cli.generate", side_effect=TimeoutError("SECRET_PROMPT")) as model:
            with self.assertRaises(TimeoutError):
                generate(self.session, inspector=native_evidence)
            model.assert_called_once()
        evidence = json.loads((self.session / FAILURE).read_text())
        self.assertEqual(evidence["phase"], "MODEL_REQUEST_OR_RESPONSE")
        self.assertEqual(evidence["category"], "TIMEOUT")
        self.assertFalse(evidence["model_delivery_confirmed"])
        self.assertNotIn("SECRET_PROMPT", (self.session / FAILURE).read_text())
        with patch("profile_cli.generate") as second:
            with self.assertRaisesRegex(ContractError, "SESSION_ALREADY_GENERATED"):
                generate(self.session, inspector=native_evidence)
            second.assert_not_called()

    def test_validation_failure_stage(self):
        self.prepared()
        with patch("profile_cli.generate", return_value=b'{"schema":3}') as model:
            with self.assertRaises(ContractError):
                generate(self.session, inspector=native_evidence)
            model.assert_called_once()
        evidence = json.loads((self.session / FAILURE).read_text())
        self.assertEqual(evidence["phase"], "RESPONSE_VALIDATION")
        self.assertEqual(evidence["category"], "CONTRACT")

    def test_concurrent_live_invocations_admit_only_one_model_call(self):
        self.prepared()
        barrier = threading.Barrier(2, timeout=20)
        def inspector(name):
            if threading.current_thread() != threading.main_thread():
                # Both workers reach the native preflight before attempting to
                # reserve the same exclusive generation record.
                if not hasattr(threading.current_thread(), "already_barriered"):
                    threading.current_thread().already_barriered = True
                    barrier.wait()
            return native_evidence(name)
        payload = json.dumps(RESPONSE_BODY).encode("utf-8")
        def worker(_):
            try:
                generate(self.session, inspector=inspector)
                return "PASS"
            except (ContractError, OSError):
                return "BLOCKED"
        with patch("profile_cli.generate", return_value=payload) as model:
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(worker, range(2)))
        self.assertEqual(sorted(outcomes), ["BLOCKED", "PASS"])
        self.assertEqual(model.call_count, 1)
        self.assertEqual(check(self.session)["status"], "PATCH_READY_FOR_REVIEW")
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_attempt_manifest_tamper_blocks_review_and_apply(self):
        self.replayed()
        attempt_path = self.session / ATTEMPT
        attempt = json.loads(attempt_path.read_text())
        attempt["model_call_authorized"] = True
        attempt_path.write_text(json.dumps(attempt), encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "SESSION_ATTEMPT_RECORD_MISMATCH"):
            check(self.session)
        sha256 = hashlib.sha256((self.session / PATCH).read_bytes()).hexdigest()
        with self.assertRaises(ContractError):
            approve(self.session, sha256)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_context_and_task_evidence_is_frozen_without_inference(self):
        self.prepared("economico")
        manifest = json.loads((self.session / MANIFEST).read_text())
        self.assertEqual(manifest["profile"], PROFILES["economico"].manifest())
        self.assertEqual(manifest["selection_policy"], "LOCAL_09_TOP_2")
        self.assertIn("calculator.py", manifest["selected_files"])
        self.assertEqual(manifest["source_files_sha256"]["calculator.py"],
                         hashlib.sha256((self.repo / "calculator.py").read_bytes()).hexdigest())
        self.assertTrue((self.session / REQUEST).is_file())
        self.assertEqual(load(self.session)[2], manifest)
        self.assertEqual(status(self.session)["status"], "SESSION_PREPARED")
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_no_inference_without_explicit_generate(self):
        with patch("profile_cli.generate") as model:
            self.prepared()
            status(self.session)
            with self.assertRaises(ContractError):
                check(self.session)
            model.assert_not_called()

    def test_issue_edit_is_rejected(self):
        self.prepared()
        (self.session / ISSUE).write_text('{"problem_statement":"Replace everything"}')
        with patch("profile_cli.generate") as model:
            with self.assertRaisesRegex(ContractError, "SESSION_EVIDENCE_MISMATCH"):
                generate(self.session)
            model.assert_not_called()

    def test_forged_request_is_rejected(self):
        self.prepared()
        (self.session / REQUEST).write_text("{}")
        with self.assertRaisesRegex(ContractError, "SESSION_EVIDENCE_MISMATCH"):
            generate(self.session, offline_response_json=self.response)

    def test_profile_drift_is_refused(self):
        self.prepared()
        manifest = json.loads((self.session / MANIFEST).read_text())
        manifest["profile"]["fingerprint_sha256"] = "0" * 64
        (self.session / MANIFEST).write_text(json.dumps(manifest))
        with patch("profile_cli.generate") as model:
            with self.assertRaisesRegex(ContractError, "SESSION_POLICY_DRIFT"):
                generate(self.session)
            model.assert_not_called()

    def test_untracked_ignored_source_is_not_a_target(self):
        (self.repo / ".git" / "info" / "exclude").write_text("ignored.py\n")
        (self.repo / "ignored.py").write_text("def ignored():\n    return 12\n")
        with self.assertRaisesRegex(ContractError, "UNTRACKED_RETRIEVED_FILE"):
            tracked_sources(self.repo, ("ignored.py",))
        self.assertFalse(self.session.exists())

    def test_dirty_source_refused_before_prepare(self):
        (self.repo / "calculator.py").write_text("def calculate(x):\n    return 500\n")
        with self.assertRaisesRegex(ContractError, "DIRTY_SOURCE_REPOSITORY"):
            self.prepared()
        self.assertFalse(self.session.exists())

    def test_source_commit_change_blocks_reuse(self):
        self.prepared()
        (self.repo / "misc.py").write_text("def miscellany():\n    return 8\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "moving baseline")
        with patch("profile_cli.generate") as model:
            with self.assertRaisesRegex(ContractError, "SESSION_BASE_COMMIT_DRIFT"):
                generate(self.session)
            model.assert_not_called()

    def test_no_session_dir_inside_checkout(self):
        with self.assertRaisesRegex(ContractError, "SESSION_INSIDE_SOURCE_REPOSITORY"):
            create(self.repo, self.repo / "session", "principal", self.task)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_output_is_immutable_and_repeat_generation_is_blocked(self):
        self.replayed()
        first = (self.session / PATCH).read_bytes()
        with patch("profile_cli.generate") as model:
            with self.assertRaisesRegex(ContractError, "SESSION_ALREADY_GENERATED"):
                generate(self.session)
            model.assert_not_called()
        self.assertEqual(first, (self.session / PATCH).read_bytes())

    def test_review_refuses_response_modified_after_generation(self):
        self.replayed()
        (self.session / RESPONSE).write_bytes(b"modified")
        with self.assertRaisesRegex(ContractError, "SESSION_RESPONSE_MISMATCH"):
            check(self.session)
        with self.assertRaises(ContractError):
            approve(self.session, hashlib.sha256((self.session / PATCH).read_bytes()).hexdigest())
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_review_refuses_report_profile_swapped(self):
        self.replayed()
        path = self.session / REPORT
        body = json.loads(path.read_text())
        body["execution"]["selected_profile"] = PROFILES["economico"].manifest()
        path.write_text(json.dumps(body), encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "SESSION_EXECUTION_MISMATCH"):
            check(self.session)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_review_refuses_request_swapped(self):
        self.replayed()
        path = self.session / REPORT
        body = json.loads(path.read_text())
        body["request"]["issue"] = "unrelated request"
        path.write_text(json.dumps(body), encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "SESSION_REQUEST_MISMATCH"):
            check(self.session)

    def test_wrong_approval_cannot_modify_checkout(self):
        self.replayed()
        with self.assertRaisesRegex(ContractError, "APPROVAL_SHA256_MISMATCH"):
            approve(self.session, "0" * 64)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_invalid_replay_contract_fails_before_outputs(self):
        self.prepared()
        self.response.write_bytes(b'{"schema": 3}')
        with patch("profile_cli.generate") as model:
            with self.assertRaises(ContractError):
                generate(self.session, offline_response_json=self.response)
            model.assert_not_called()
        for path in (REPORT, PATCH, RESPONSE):
            self.assertFalse((self.session / path).exists())

    def test_cli_subcommands_with_real_git_and_no_model(self):
        def call(*args):
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), *args], capture_output=True,
                text=True, timeout=40
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            return json.loads(completed.stdout)
        call("new", "--repo", str(self.repo),
             "--session", str(self.session), "--profile", "principal", "--task", self.task)
        response = call("generate", "--session", str(self.session),
                        "--offline-response-json", str(self.response))
        self.assertEqual(response["inference_calls_attempted"], 0)
        review = call("check", "--session", str(self.session))
        self.assertEqual(review["status"], "PATCH_READY_FOR_REVIEW")
        applied = call("apply", "--session", str(self.session),
                       "--approve-sha256", review["patch_sha256"])
        self.assertEqual(applied["status"], "PATCH_APPLIED_UNSTAGED")
        self.assertFalse(applied["code_execution"])


if __name__ == "__main__":
    unittest.main()
