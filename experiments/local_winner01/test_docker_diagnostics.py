"""Pure offline checks for Docker failure classification."""
import json
import unittest
from docker_diagnostics import classify_output, inspect_snapshot, exit_origin


class TestDockerDiagnostics(unittest.TestCase):
    def test_git_dubious_owner(self):
        self.assertEqual(classify_output("fatal: detected dubious ownership in repository"),
                         "GIT_DUBIOUS_OWNERSHIP")

    def test_git_index_denied(self):
        self.assertEqual(classify_output("fatal: Unable to create .git/index.lock: Permission denied"),
                         "GIT_INDEX_WRITE_DENIED")

    def test_git_denied(self):
        self.assertEqual(classify_output("fatal: permission denied"),
                         "GIT_ACCESS_DENIED")

    def test_file_denied(self):
        self.assertEqual(classify_output("/eval.sh: permission denied"),
                         "FILESYSTEM_ACCESS_DENIED")

    def test_unknown_stays_unknown(self):
        self.assertEqual(classify_output("test runner did not complete"), "UNKNOWN")

    def test_container_exit_128(self):
        state = inspect_snapshot(json.dumps({
            "Status": "exited", "ExitCode": 128, "OOMKilled": False, "Error": "",
            "StartedAt": "2026-10-26T19:00:00Z"
        }), 0)
        self.assertEqual(exit_origin(128, state), "CONTAINER_PROCESS")

    def test_unstarted_128(self):
        state = inspect_snapshot(json.dumps({
            "Status": "created", "ExitCode": 0, "OOMKilled": False, "Error": "",
            "StartedAt": "0001-01-01T00:00:00Z"
        }), 0)
        self.assertEqual(exit_origin(128, state), "DOCKER_CLI_OR_UNDETERMINED")

    def test_oci_error_without_leak(self):
        state = inspect_snapshot(json.dumps({
            "Status": "exited", "ExitCode": 128, "OOMKilled": False,
            "Error": "OCI runtime create failed", "StartedAt": "2026-10-26T19:00:00Z"
        }), 0)
        self.assertEqual(exit_origin(128, state), "DOCKER_RUNTIME")
        self.assertNotIn("OCI", json.dumps(state))

    def test_failed_inspect(self):
        self.assertEqual(exit_origin(128, inspect_snapshot("secret", 1)),
                         "UNKNOWN_WITHOUT_INSPECT")

    def test_bad_inspect_no_leak(self):
        result = inspect_snapshot("private content", 0)
        self.assertEqual(result["parse_error"], "INSPECT_JSON_INVALID")
        self.assertNotIn("private", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
