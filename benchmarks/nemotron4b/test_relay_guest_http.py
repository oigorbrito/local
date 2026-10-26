"""Real localhost HTTP/1.1 + Undici sequential Cloi preflight regression.

No Ollama, Docker, model inference or remote network. Uses the actual guest
Bridge handler with a deterministic local fake broker for headers and bodies.
"""
import base64
from http.server import ThreadingHTTPServer
import json
import shutil
import subprocess
import threading
import unittest
from unittest.mock import patch

import relay_guest


JS = r"""
const base = process.argv[1];
let rounds = 0;
for (let i = 0; i < 4; i++) {
  // This intentionally matches Cloi's isReachable implementation: it reads
  // res.ok but *does not* consume the first GET's response body.
  const first = await fetch(base + '/api/tags', {
    signal: AbortSignal.timeout(3000)
  });
  if (first.status !== 200 || first.headers.get('connection') !== 'close')
    throw Error('FIRST_RESPONSE_CONNECTION_NOT_CLOSED');
  const second = await fetch(base + '/api/tags', {
    signal: AbortSignal.timeout(3000)
  });
  const tags = await second.json();
  if (!tags.models.some(m => m.name === 'nemotron-3-nano:4b'))
    throw Error('TAGS_BODY_NOT_CONSUMED');
  const show = await fetch(base + '/api/show', {
    method: 'POST', headers: {'content-type': 'application/json'},
    body: JSON.stringify({model:'nemotron-3-nano:4b'}),
    signal: AbortSignal.timeout(3000)
  });
  const capabilities = (await show.json()).capabilities;
  if (!capabilities.includes('tools')) throw Error('SHOW_BODY_INCOMPLETE');
  rounds++;
}
console.log(JSON.stringify({result:'PASS', rounds}));
"""


class GuestUndiciTests(unittest.TestCase):
    def test_unconsumed_first_tags_does_not_break_second_tags_or_show(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node not present; Windows and Linux CI have Node")
        created = []
        payloads = {
            "/api/tags": json.dumps({
                "models": [{"name": "nemotron-3-nano:4b"}]
            }).encode(),
            "/api/show": json.dumps({
                "capabilities": ["completion", "tools"], "model": "x" * 22000
            }).encode(),
        }

        def reply(frame):
            self.assertEqual(frame["kind"], "request")
            route = frame["path"]
            self.assertIn(route, payloads)
            created.append(route)
            with relay_guest._pending_lock:
                queue = relay_guest._pending[frame["id"]]
            payload = payloads[route]
            queue.put({"kind": "start", "status": 200})
            for chunk in (payload[:271], payload[271:]):
                if chunk:
                    queue.put({
                        "kind": "chunk",
                        "body": base64.b64encode(chunk).decode("ascii")
                    })
            queue.put({"kind": "end"})

        with patch.object(relay_guest, "emit", side_effect=reply):
            server = ThreadingHTTPServer(("127.0.0.1", 0), relay_guest.Bridge)
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                proc = subprocess.run(
                    [node, "--input-type=module", "-e", JS,
                     "http://127.0.0.1:%d" % port],
                    capture_output=True, text=True, timeout=12
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1000:])
        self.assertEqual(json.loads(proc.stdout)["rounds"], 4)
        self.assertEqual(
            created,
            ["/api/tags", "/api/tags", "/api/show"] * 4
        )


if __name__ == "__main__":
    unittest.main()
