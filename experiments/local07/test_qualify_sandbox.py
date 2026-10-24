import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
from qualify_sandbox import qualify

DIGEST="python@sha256:"+("a"*64)

class SandboxQualificationTest(unittest.TestCase):
    def test_explicit_qualification_contract(self):
        status={"uid":65534,"cap_eff":"0000000000000000","root_writable":False,"outbound_network":"BLOCKED"}
        calls=[]
        def fake(args,**kwargs):
            calls.append(args)
            if args[:2]==["docker","image"]:
                return subprocess.CompletedProcess(args,0,b"[]",b"")
            return subprocess.CompletedProcess(args,0,("LOCAL14_PROBE="+json.dumps(status)+"\n").encode(),b"")
        with tempfile.TemporaryDirectory() as d:
            result=qualify(DIGEST,pathlib.Path(d)/"report.json",runner=fake)
            self.assertTrue(result["qualified"])
            self.assertEqual(len(calls),2)
            self.assertIn("--pull",calls[1])
            self.assertIn("never",calls[1])
            self.assertIn("--network",calls[1])
            self.assertIn("none",calls[1])
            self.assertIn("--read-only",calls[1])
            self.assertTrue((pathlib.Path(d)/"report.json").is_file())

    def test_fail_closed_observations(self):
        for field,value in [("uid",0),("cap_eff","0000000000000001"),
                            ("root_writable",True),("outbound_network","CONNECTED")]:
            status={"uid":65534,"cap_eff":"0000000000000000","root_writable":False,"outbound_network":"BLOCKED"}
            status[field]=value
            def fake(args,**kwargs):
                if args[:2]==["docker","image"]:
                    return subprocess.CompletedProcess(args,0,b"[]",b"")
                return subprocess.CompletedProcess(args,0,("LOCAL14_PROBE="+json.dumps(status)+"\n").encode(),b"")
            with tempfile.TemporaryDirectory() as d:
                with self.subTest(field=field):
                    self.assertFalse(qualify(DIGEST,pathlib.Path(d)/"x.json",runner=fake)["qualified"])

    def test_no_implicit_download_or_execution_on_invalid_image(self):
        with tempfile.TemporaryDirectory() as d:
            runner=Mock()
            with self.assertRaises(ValueError):
                qualify("python:latest",pathlib.Path(d)/"x.json",runner=runner)
            runner.assert_not_called()
