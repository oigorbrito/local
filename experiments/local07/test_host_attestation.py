import unittest
from host_attestation import evaluate

BASE={"schema":1,"host_kind":"disposable_vm","ephemeral":True,"dedicated":True,
      "no_credentials":True,"no_personal_mounts":True,"disposal_verified":True,
      "container_image":"python@sha256:"+("a"*64),"operator_approved":True}

class HostAttestationTests(unittest.TestCase):
    def test_no_report_authorizes_execution_even_all_true(self):
        out=evaluate(dict(BASE),observed_os="Linux")
        self.assertEqual(out["status"],"ATTESTATION_COMPLETE_UNVERIFIED")
        self.assertFalse(out["untrusted_execution_authorized"])
        self.assertFalse(out["isolation_technically_verified"])

    def test_missing_flag_blocks(self):
        for field in ("ephemeral","dedicated","no_credentials",
                      "no_personal_mounts","disposal_verified","operator_approved"):
            with self.subTest(field=field):
                data=dict(BASE);data[field]=False
                self.assertEqual(evaluate(data,observed_os="Linux")["status"],"BLOCKED")

    def test_windows_host_blocked(self):
        self.assertEqual(evaluate(dict(BASE),observed_os="Windows")["status"],"BLOCKED")

    def test_unpinned_image_blocked(self):
        data=dict(BASE);data["container_image"]="python:latest"
        self.assertEqual(evaluate(data,observed_os="Linux")["status"],"BLOCKED")

    def test_invalid_schema_rejected(self):
        data=dict(BASE);data["secret_key"]="must-not-accept"
        with self.assertRaises(ValueError):
            evaluate(data,observed_os="Linux")

    def test_wrong_kind_blocked(self):
        data=dict(BASE);data["host_kind"]="personal_windows"
        self.assertEqual(evaluate(data,observed_os="Linux")["status"],"BLOCKED")
