"""Deterministic protocol integration checks using a fake Ollama (no Docker or GPU).

Checks framing and token accounting of both streamed chat and unstreamed
generation, then ensures unsafe Ollama routes fail closed.
"""
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import relay_host


MODEL = "nemotron-3-nano:4b"


class _FakeInput:
    def __init__(self):
        self.frames = []

    def write(self, text):
        self.frames.append(json.loads(text))

    def flush(self):
        pass


class _FakeProc:
    def __init__(self):
        self.stdin = _FakeInput()


class _FakeResponse:
    status = 200

    def __init__(self, pieces):
        self.pieces = list(pieces)

    def readline(self):
        return self.read(65536)

    def read(self, size):
        return self.pieces.pop(0) if self.pieces else b""


class _FakeConnection:
    def __init__(self, pieces):
        self.response = _FakeResponse(pieces)
        self.requests = []

    def request(self, method, path, body, headers):
        self.requests.append((method, path, json.loads(body) if body else None))

    def getresponse(self):
        return self.response

    def close(self):
        pass


class RelayTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.metrics = Path(self.temp.name) / "metrics.jsonl"
        self.proc = _FakeProc()
        self.ident = "a" * 32

    def relay(self, route, request, pieces):
        fake = _FakeConnection(pieces)
        frame = {
            "kind": "request", "id": self.ident,
            "method": "POST", "path": route,
            "body": base64.b64encode(json.dumps(request).encode()).decode(),
        }
        with patch.object(relay_host.http.client, "HTTPConnection", return_value=fake):
            relay_host.forward(self.proc, frame, MODEL, 20, self.metrics, "r01-local09")
        metrics = json.loads(self.metrics.read_text().splitlines()[-1])
        return fake, self.proc.stdin.frames, metrics

    def test_unstreamed_generate_roundtrip_and_limits(self):
        payload = json.dumps({
            "response": '{"schema":1,"file":"guard.py","content":"pass\\n"}',
            "prompt_eval_count": 83, "eval_count": 29,
        }).encode()
        fake, frames, metrics = self.relay(
            "/api/generate",
            {"model": MODEL, "stream": False,
             "options": {"temperature": 0.9, "num_ctx": 100000,
                         "num_predict": 99999}},
            [payload[:21], payload[21:]],
        )
        self.assertEqual([f["kind"] for f in frames], ["start", "chunk", "chunk", "end"])
        self.assertEqual(b"".join(base64.b64decode(f["body"]) for f in frames
                                  if f["kind"] == "chunk"), payload)
        self.assertEqual(metrics["prompt_tokens"], 83)
        self.assertEqual(metrics["output_tokens"], 29)
        self.assertTrue(metrics["response_complete"])
        self.assertTrue(metrics["usage_available"])
        self.assertGreaterEqual(metrics["elapsed_seconds"], 0)
        self.assertEqual(metrics["path"], "/api/generate")
        raw = metrics["raw_response"]
        self.assertIsNotNone(raw)
        evidence = Path(self.temp.name) / raw["relative_path"]
        self.assertEqual(evidence.read_bytes(), payload)
        self.assertEqual(raw["bytes"], len(payload))
        options = fake.requests[0][2]["options"]
        self.assertEqual((options["num_ctx"], options["num_predict"], options["temperature"]),
                         (4096, 2048, 0))

    def test_streamed_chat_roundtrip_and_final_usage(self):
        chunks = [
            json.dumps({"message": {"tool_calls": [{"function": {
                "name": "read_file", "arguments": {"path": "guard.py"}}}]},
                "done": False}).encode() + b"\n",
            json.dumps({"done": True, "prompt_eval_count": 31, "eval_count": 7}).encode() + b"\n",
        ]
        fake, frames, metrics = self.relay(
            "/api/chat", {"model": MODEL, "stream": True}, chunks,
        )
        self.assertEqual([f["kind"] for f in frames], ["start", "chunk", "chunk", "end"])
        self.assertEqual(b"".join(base64.b64decode(f["body"]) for f in frames
                                  if f["kind"] == "chunk"), b"".join(chunks))
        self.assertEqual((metrics["prompt_tokens"], metrics["output_tokens"]), (31, 7))
        self.assertTrue(metrics["response_complete"])
        self.assertTrue(metrics["usage_available"])
        self.assertEqual(metrics["path"], "/api/chat")
        raw = metrics["raw_response"]
        self.assertEqual((Path(self.temp.name) / raw["relative_path"]).read_bytes(),
                         b"".join(chunks))
        self.assertEqual(fake.requests[0][1], "/api/chat")

    def test_disallowed_route_never_contacts_ollama(self):
        frame = {"kind": "request", "id": self.ident, "method": "POST",
                 "path": "/api/pull",
                 "body": base64.b64encode(json.dumps({"model": MODEL}).encode()).decode()}
        with patch.object(relay_host.http.client, "HTTPConnection") as network:
            relay_host.forward(self.proc, frame, MODEL, 20, self.metrics, "preflight")
            network.assert_not_called()
        self.assertEqual([item["kind"] for item in self.proc.stdin.frames], ["error"])
        self.assertEqual(self.proc.stdin.frames[0]["status"], 502)
        denied = json.loads(self.metrics.read_text())
        self.assertFalse(denied["response_complete"])
        self.assertFalse(denied["usage_available"])
        self.assertEqual(denied["error_type"], "ValueError")
        self.assertIsNone(denied["raw_response"])

    def test_model_mismatch_does_not_forward(self):
        frame = {"kind": "request", "id": self.ident, "method": "POST",
                 "path": "/api/chat",
                 "body": base64.b64encode(
                     json.dumps({"model": "not-our-model"}).encode()).decode()}
        with patch.object(relay_host.http.client, "HTTPConnection") as network:
            relay_host.forward(self.proc, frame, MODEL, 20, self.metrics, "r01-cloi")
            network.assert_not_called()
        self.assertEqual(self.proc.stdin.frames[0]["kind"], "error")


if __name__ == "__main__":
    unittest.main()
