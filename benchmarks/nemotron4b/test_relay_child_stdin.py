"""Prove agent child processes cannot read the guest broker's stdin.

Uses real parent and child Python processes; no Docker, Node, Ollama or model
calls. This is a transport ownership test, not a mocked API-only assertion.
"""
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import compare


PARENT = r"""
import sys
sys.path.insert(0, sys.argv[1])
import compare
print("PARENT_READY", flush=True)
child = compare.run([sys.executable, "-c",
    "import sys; data=sys.stdin.buffer.read(); "
    "print('CHILD_BROKER_BYTES=' + str(len(data)))"], timeout=3)
print(child["stdout"].strip(), flush=True)
print("PARENT_FRAME=" + sys.stdin.readline().strip(), flush=True)
"""


class ExclusiveStdinTests(unittest.TestCase):
    def test_all_runner_subprocesses_use_explicit_devnull(self):
        fake = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch.object(compare.subprocess, "run", return_value=fake) as call:
            result = compare.run(["example-command"], timeout=3)
        self.assertEqual(result["code"], 0)
        self.assertEqual(call.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_real_child_cannot_steal_broker_frame(self):
        proc = subprocess.Popen(
            [sys.executable, "-u", "-c", PARENT, str(Path(compare.__file__).parent)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
        )
        try:
            self.assertEqual(proc.stdout.readline().strip(), "PARENT_READY")
            remaining, errors = proc.communicate(
                input='{"kind":"end","id":"CONTROL_FRAME_PRIVATE"}\n',
                timeout=8,
            )
        except BaseException:
            proc.kill()
            proc.communicate()
            raise
        self.assertEqual(proc.returncode, 0, errors[-1000:])
        self.assertIn("CHILD_BROKER_BYTES=0", remaining)
        self.assertIn(
            'PARENT_FRAME={"kind":"end","id":"CONTROL_FRAME_PRIVATE"}',
            remaining,
        )
        self.assertNotIn("CONTROL_FRAME_PRIVATE", errors)


if __name__ == "__main__":
    unittest.main()
