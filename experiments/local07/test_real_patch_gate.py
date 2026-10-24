import pathlib
import subprocess
import tempfile
import unittest

from real_patch_gate import GateError, grade, verify_patch


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True, check=True).stdout.strip()


class RealPatchGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)/"repo"
        self.root.mkdir()
        git(self.root,"init","-q")
        git(self.root,"config","user.email","gate@example.invalid")
        git(self.root,"config","user.name","Gate")
        (self.root/"calculator.py").write_text("def value():\n    return 1\n",encoding="utf-8")
        git(self.root,"add",".")
        git(self.root,"commit","-qm","base")
        self.spec={"schema":1,"base_commit":git(self.root,"rev-parse","HEAD"),
                   "allowed_files":["calculator.py"]}
        self.patch=pathlib.Path(self.tmp.name)/"candidate.patch"
        self.patch.write_bytes(b"diff --git a/calculator.py b/calculator.py\n"
                               b"--- a/calculator.py\n+++ b/calculator.py\n"
                               b"@@ -1,2 +1,2 @@\n def value():\n-    return 1\n+    return 2\n")

    def test_applicable_without_candidate_execution(self):
        report=grade(self.root,self.spec,self.patch)
        self.assertEqual(report["status"],"PATCH_APPLICABLE_NOT_GRADED")
        self.assertEqual(report["test_status"],"NOT_RUN")
        self.assertFalse(report["host_candidate_execution"])
        self.assertEqual(git(self.root,"status","--porcelain"),"")

    def test_bad_patch_not_mistaken_for_model_failure(self):
        self.patch.write_bytes(self.patch.read_bytes().replace(b"return 1",b"return 999"))
        report=grade(self.root,self.spec,self.patch)
        self.assertEqual(report["status"],"PATCH_NOT_APPLICABLE")
        self.assertFalse(report["patch_applicable"])

    def test_scope_and_binary_denied(self):
        for extra in [b"diff --git a/other.py b/other.py\n",
                      b"GIT binary patch\n",
                      b"rename from calculator.py\n",
                      b"\x00",b"\r\n"]:
            with self.subTest(extra=extra),self.assertRaises(GateError):
                verify_patch(self.patch.read_bytes()+extra,["calculator.py"])

    def test_gold_paths_do_not_authorize_edit(self):
        with self.assertRaisesRegex(GateError,"PATCH_OUT_OF_SCOPE"):
            grade(self.root,{**self.spec,"allowed_files":["other.py"]},self.patch)

    def test_dirty_source_refused(self):
        (self.root/"extra.txt").write_text("dirty",encoding="utf-8")
        with self.assertRaisesRegex(GateError,"DIRTY_SOURCE"):
            grade(self.root,self.spec,self.patch)

    def test_no_docker_requested_by_default(self):
        from unittest.mock import patch
        with patch("real_patch_gate.cmd", wraps=__import__("real_patch_gate").cmd) as run:
            grade(self.root,self.spec,self.patch)
        self.assertFalse(any(call.args[0][0]=="docker" for call in run.call_args_list))

    def test_explicit_test_mode_requires_pinned_image(self):
        with self.assertRaisesRegex(GateError,"PINNED_LOCAL_IMAGE_REQUIRED"):
            grade(self.root,self.spec,self.patch,run_tests=True)
