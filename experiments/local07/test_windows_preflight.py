"""Mocked transport contract tests: offline, no Ollama server required."""
import json
import unittest
from windows_preflight import MAX_BODY, PreflightFailure, inspect, ollama_get


class Response:
    def __init__(self, payload, code=200):
        self.status=code
        self.payload=payload
    def read(self, n):
        return self.payload[:n]


class Transport:
    calls=[]
    replies={}
    def __init__(self, host, port, timeout):
        assert host=="127.0.0.1" and port==11434
        self.path=None
    def request(self, method, path, headers=None):
        assert method=="GET"
        Transport.calls.append(path)
        self.path=path
    def getresponse(self):
        return Transport.replies[self.path]
    def close(self):
        pass


class WindowsPreflightContract(unittest.TestCase):
    def setUp(self):
        Transport.calls=[]
        Transport.replies={
            "/api/version":Response(b'{"version":"0.test"}'),
            "/api/tags":Response(json.dumps({"models":[{"name":"qwen3.5:2b"}]}).encode()),
            "/api/ps":Response(b'{"models":[]}')
        }
    def test_end_to_end_read_only(self):
        r=inspect(transport=Transport)
        self.assertEqual(r["status"],"READ_ONLY_PREFLIGHT_PASS")
        self.assertTrue(r["candidate_presence"]["qwen3.5:2b"])
        self.assertFalse(r["candidate_presence"]["nemotron-3-nano:4b"])
        self.assertEqual(r["generation_calls"],0)
        self.assertEqual(Transport.calls,["/api/version","/api/tags","/api/ps"])
    def test_reject_non_read_only_paths(self):
        with self.assertRaises(PreflightFailure):ollama_get("/api/generate",transport=Transport)
        with self.assertRaises(PreflightFailure):ollama_get("/api/tags",host="0.0.0.0",transport=Transport)
        self.assertEqual(Transport.calls,[])
    def test_bad_json_http_and_oversize(self):
        for value in [Response(b"{notjson"),Response(b'{"error":"no"}',503),Response(b"{" + b" "*(MAX_BODY+1))]:
            Transport.replies["/api/tags"]=value
            with self.subTest(value=value),self.assertRaises(PreflightFailure):inspect(transport=Transport)
    def test_bad_schema(self):
        Transport.replies["/api/ps"]=Response(b'{"models":{}}')
        with self.assertRaises(PreflightFailure):inspect(transport=Transport)
