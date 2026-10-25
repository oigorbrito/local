import tempfile
import unittest
from pathlib import Path
from guard import read_text_under_root

class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "root"
        self.root.mkdir()
        (self.root / "ok.txt").write_text("safe", encoding="utf-8")
        (self.base / "secret.txt").write_text("sensitive", encoding="utf-8")

    def test_legitimate_file(self):
        self.assertEqual(read_text_under_root(self.root, "ok.txt"), "safe")

    def test_absent_file(self):
        with self.assertRaises(FileNotFoundError):
            read_text_under_root(self.root, "missing.txt")

    def test_parent_escape(self):
        with self.assertRaises((ValueError, PermissionError)):
            read_text_under_root(self.root, "../secret.txt")

    def test_absolute_escape(self):
        with self.assertRaises((ValueError, PermissionError)):
            read_text_under_root(self.root, str(self.base / "secret.txt"))

    def test_file_symlink_escape(self):
        (self.root / "alias.txt").symlink_to(self.base / "secret.txt")
        with self.assertRaises((ValueError, PermissionError)):
            read_text_under_root(self.root, "alias.txt")

    def test_directory_symlink_escape(self):
        (self.root / "alias").symlink_to(self.base, target_is_directory=True)
        with self.assertRaises((ValueError, PermissionError)):
            read_text_under_root(self.root, "alias/secret.txt")
