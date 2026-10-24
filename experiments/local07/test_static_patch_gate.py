import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from static_patch_gate import grade, GateError, verify_patch

def git(root,*args):
    return subprocess.run(["git",*args],cwd=root,check=True,capture_output=True,text=True).stdout.strip()

class StaticTriage(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)/"repo"
        self.root.mkdir()
        git(self.root,"init","-q")
        git(self.root,"config","user.email","static@example.invalid")
        git(self.root,"config","user.name","Static Gate")
        (self.root/"target.py").write_text("def f():\n    return 1\n",encoding="utf-8")
        git(self.root,"add","target.py")
        git(self.root,"commit","-qm","base")
        self.issue={"base_commit":git(self.root,"rev-parse","HEAD"),"allowed_files":["target.py"]}
        self.patch=pathlib.Path(self.tmp.name)/"change.patch"
        self.patch.write_bytes(b"diff --git a/target.py b/target.py\n--- a/target.py\n+++ b/target.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 2\n")

    def test_patch_applicability_does_not_execute(self):
        with patch("static_patch_gate.cmd",wraps=__import__("static_patch_gate").cmd) as run:
            result=grade(self.root,self.issue,self.patch)
        self.assertEqual(result["status"],"PATCH_APPLICABLE_NOT_GRADED")
        self.assertEqual(result["test_status"],"NOT_RUN")
        self.assertFalse(result["host_candidate_execution"])
        self.assertEqual(git(self.root,"status","--porcelain"),"")
        self.assertTrue(all(call.args[0][0]=="git" for call in run.call_args_list))

    def test_invalid_path_and_headers_fail_closed(self):
        for data in [
            self.patch.read_bytes().replace(b"+++ b/target.py",b"+++ b/other.py"),
            self.patch.read_bytes()+b"diff --git a/other.py b/other.py\n",
            self.patch.read_bytes().replace(b"return 1",b"return 3\r"),
        ]:
            with self.subTest(data=data),self.assertRaises(GateError):
                verify_patch(data,["target.py"])

    def test_dirty_repo_rejected(self):
        (self.root/"outside.py").write_text("x=1\n")
        with self.assertRaisesRegex(GateError,"DIRTY_SOURCE"):
            grade(self.root,self.issue,self.patch)
