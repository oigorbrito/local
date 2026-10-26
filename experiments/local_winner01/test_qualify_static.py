"""LOCAL-WINNER-02 offline qualification contracts; never fetches Git or calls a model."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import qualify_static as q


def fake_dataset():
    # This is intentionally NOT the official dataset hash; qualification must
    # reject substituted rows without touching the network or Git.
    return b'{"num_rows_total":23,"rows":[]}'

def diff(path="pkg/api.py"):
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-old\n+new\n"

class StaticQualificationTests(unittest.TestCase):
    def test_patch_parser_single(self):
        self.assertEqual(q.patch_paths(diff()),[("pkg/api.py","pkg/api.py")])

    def test_patch_rejects_parent_escape(self):
        with self.assertRaisesRegex(ValueError,"UNSAFE_REFERENCE_PATH"):
            q.patch_paths(diff("../private.py"))

    def test_patch_rejects_symlink_and_binary(self):
        for bad in (diff()+"new file mode 120000\n",
                    diff()+"GIT binary patch\n",
                    diff()+"rename from secret\n"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError,"DISALLOWED_REFERENCE_DIFF"):
                    q.patch_paths(bad)

    def test_substituted_dataset_is_fatal_without_fetch(self):
        with patch.object(q,"validate_case") as v:
            with self.assertRaisesRegex(ValueError,"CANONICAL_DATASET_BYTES_CHANGED"):
                q.qualify(fake_dataset())
            v.assert_not_called()

    def test_sha_and_repository_input_validation(self):
        with self.assertRaisesRegex(ValueError,"REPO_OR_COMMIT_NOT_VALID"):
            q.validate_case("../private","a"*40,diff(),diff())
        with self.assertRaisesRegex(ValueError,"REPO_OR_COMMIT_NOT_VALID"):
            q.validate_case("owner/repo","zz",diff(),diff())

    def test_unsafe_patch_refused_before_clone(self):
        with patch.object(q,"run_git") as git:
            out=q.validate_case("owner/repo","a"*40,diff("../escape"),diff())
            self.assertEqual(out["status"],"UNSAFE_REFERENCE_PATCH")
            git.assert_not_called()

    def test_good_case_mocked_git_qualifies_statics_without_running_tests(self):
        calls=[]
        def git(root,args,timeout=80,env=None):
            calls.append(args)
            stdout="a"*40+"\n" if args[:2]==["rev-parse","HEAD"] else ""
            return MagicMock(returncode=0,stdout=stdout,stderr="")
        with patch.object(q,"run_git",side_effect=git):
            out=q.validate_case("owner/repo","a"*40,diff("src/tool.py"),diff("tests/test_tool.py"))
        self.assertEqual(out["status"],"APPLICABLE_STATIC_ONLY")
        self.assertEqual(out["gold_path_count"],1)
        self.assertEqual(out["test_path_count"],1)
        self.assertTrue(any(a[:2]==["apply","--check"] for a in calls))
        self.assertFalse(any("pytest" in a or "python" in a for args in calls for a in args))

    def test_failed_git_fetch_classified_not_functional(self):
        with patch.object(q,"run_git",return_value=MagicMock(returncode=128,stderr="FAIL")):
            out=q.validate_case("owner/repo","a"*40,diff(),diff())
        self.assertEqual(out["status"],"FETCH_FAILED")
        self.assertNotIn("stderr",out)

    def test_model_input_not_created_by_static_module(self):
        self.assertFalse(hasattr(q,"call_ollama"))
        self.assertNotIn("gold_patch",q.VALID_STATUS)

if __name__=="__main__":
    unittest.main()
