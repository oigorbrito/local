"""Real guest stdio broker + HTTP/1.1 + pinned Node fetch semantics.

Tests guest.receive(), real pipes, routing by request_id and the actual
HTTP handler together. No Docker, Ollama, model generation or other network.
"""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

from test_relay_guest_http import JS


BOOTSTRAP = r"""
import os, sys, threading
from http.server import ThreadingHTTPServer
import relay_guest
relay_guest.GUEST_EVENTS = os.environ["GUEST_EVENTS_TEST"]
threading.Thread(target=relay_guest.receive, daemon=True).start()
server = ThreadingHTTPServer(("127.0.0.1", 0), relay_guest.Bridge)
server.daemon_threads = True
print("GUEST_READY_PORT=" + str(server.server_address[1]), file=sys.stderr, flush=True)
server.serve_forever()
"""


class RealStdioGuestTests(unittest.TestCase):
    def test_sequential_node_fetches_with_real_guest_receive_and_stdio(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable")
        with tempfile.TemporaryDirectory() as temp:
            records = Path(temp) / "guest-bridge-events.jsonl"
            guest = subprocess.Popen(
                [sys.executable, "-u", "-c", BOOTSTRAP],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, encoding="utf-8", bufsize=1,
                env={**os.environ,
                     "GUEST_EVENTS_TEST": str(records),
                     "PYTHONPATH": str(Path(__file__).resolve().parent)},
            )
            requests = []
            broker_errors = []
            def broker():
                try:
                    for line in guest.stdout:
                        frame = json.loads(line)
                        if frame.get("kind") != "request":
                            raise AssertionError("unexpected broker command")
                        reqid, route = frame["id"], frame["path"]
                        requests.append(route)
                        if route == "/api/tags":
                            data = json.dumps({
                                "models": [{"name": "nemotron-3-nano:4b"}]
                            }).encode()
                        elif route == "/api/show":
                            data = json.dumps({
                                "capabilities": ["completion", "tools"],
                                "modelfile": "x" * 22000,
                            }).encode()
                        else:
                            raise AssertionError("forbidden path: " + route)
                        for part in (
                            {"kind": "start", "id": reqid, "status": 200},
                            {"kind": "chunk", "id": reqid,
                             "body": base64.b64encode(data[:97]).decode("ascii")},
                            {"kind": "chunk", "id": reqid,
                             "body": base64.b64encode(data[97:]).decode("ascii")},
                            {"kind": "end", "id": reqid},
                        ):
                            guest.stdin.write(json.dumps(part) + "\n")
                            guest.stdin.flush()
                except Exception as exc:
                    broker_errors.append(type(exc).__name__)

            worker = threading.Thread(target=broker, daemon=True)
            worker.start()
            try:
                ready = guest.stderr.readline().strip()
                self.assertTrue(ready.startswith("GUEST_READY_PORT="), ready)
                port = int(ready.split("=", 1)[1])
                client = subprocess.run(
                    [node, "--input-type=module", "-e", JS,
                     f"http://127.0.0.1:{port}"],
                    capture_output=True, text=True, timeout=15,
                )
                self.assertEqual(client.returncode, 0, client.stderr[-1200:])
                self.assertEqual(json.loads(client.stdout)["rounds"], 4)
                self.assertEqual(requests,
                                 ["/api/tags", "/api/tags", "/api/show"] * 4)
                self.assertFalse(broker_errors, broker_errors)
                frames = [
                    json.loads(line) for line in records.read_text(encoding="utf8").splitlines()
                ]
                self.assertEqual(sum(f["stage"] == "metadata_response_sent" for f in frames),
                                 12)
                self.assertEqual(sum(f["stage"] == "stdin_reply_received" for f in frames),
                                 48)
                self.assertFalse(any(
                    f["stage"] == "metadata_error" for f in frames))
                self.assertFalse(any(
                    "body" in f or "content" in f or "prompt" in f for f in frames))
            finally:
                if guest.poll() is None:
                    guest.terminate()
                try:
                    guest.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    guest.kill()
                    guest.communicate(timeout=3)
                worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
