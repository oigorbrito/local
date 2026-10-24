import json
import pathlib
import subprocess
import tempfile
import unittest
from integrated_edit import assess

def git(root,*args):
    return subprocess.run(['git',*args],cwd=root,check=True,capture_output=True,text=True).stdout

class IntegrationGate(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
        git(self.root,'init','-q');git(self.root,'config','user.email','local@test');git(self.root,'config','user.name','LOCAL Gate')
        (self.root/'target.py').write_text('def calculator(x):\n    return x+1\n',encoding='utf8')
        (self.root/'other.py').write_text('def other(x):\n    return x\n',encoding='utf8')
        git(self.root,'add','.');git(self.root,'commit','-qm','base')
        self.issue='Fix target.py calculator function; it must return x+2.'
    def tearDown(self):self.tmp.cleanup()
    def test_integrated_patch_and_immutable_base(self):
        before=git(self.root,'status','--porcelain')
        report,patch=assess(self.root,self.issue,'target.py','def calculator(x):\n    return x+2\n')
        self.assertEqual(report['result'],'PATCH_APPLICABLE_NOT_GRADED')
        self.assertIn('target.py',report['selected_files']);self.assertIn('+    return x+2',patch)
        self.assertEqual(git(self.root,'status','--porcelain'),before)
        self.assertEqual((self.root/'target.py').read_text(),'def calculator(x):\n    return x+1\n')
        self.assertEqual(git(self.root,'worktree','list').count('\n'),1)
    def test_guards(self):
        for path,source in [('other.py','def other(x):\n    return 2\n'),('../target.py','x=2\n'),('target.py','def broken(')]:
            with self.subTest(path=path),self.assertRaises((ValueError,SyntaxError)):assess(self.root,self.issue,path,source)
        (self.root/'target.py').write_text('x=3\n')
        with self.assertRaises(ValueError):assess(self.root,self.issue,'target.py','x=4\n')
