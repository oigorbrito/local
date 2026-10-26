"""No-network tests for explicit local Ollama adapter."""
import json
import unittest
from unittest.mock import patch

from executor_bridge import ContractError, Request, parse_response
from ollama_adapter import generate


class FakeResponse:
    def __init__(self, data, status=200):
        self.data = data
        self.status = status
    def getheader(self, name):
        return None
    def read(self, n):
        return self.data[:n]


class FakeConnection:
    def __init__(self, response):
        self.response = response
        self.sent = None
    def request(self, method, path, body, headers):
        self.sent = (method, path, json.loads(body))
    def getresponse(self):
        return self.response
    def close(self):
        pass


class OllamaAdapterGate(unittest.TestCase):
    def setUp(self):
        self.request = Request("Fix calculator.py calculate()", ("calculator.py",), ())
        self.payload = json.dumps({"schema": 1, "file": "calculator.py", "content": "def calculate(x):\n    return x+2\n"})
    
    def test_mocked_protocol_and_bounded_generation(self):
        transport = FakeConnection(FakeResponse(json.dumps({"response": self.payload, "done": True}).encode()))
        with patch("ollama_adapter.http.client.HTTPConnection", return_value=transport) as factory:
            response = generate(self.request, "nemotron-3-nano:4b")
        self.assertEqual(parse_response(response, ("calculator.py",))[0], "calculator.py")
        self.assertEqual(transport.sent[0:2], ("POST", "/api/generate"))
        self.assertFalse(transport.sent[2]["stream"])
        self.assertEqual(transport.sent[2]["format"]["properties"]["file"]["enum"], ["calculator.py"])
        factory.assert_called_once_with("127.0.0.1", 11434, timeout=180)

    def test_fail_closed_transport(self):
        with self.assertRaises(ContractError):
            generate(self.request, "valid:tag", host="192.168.1.2")
        with self.assertRaises(ContractError):
            generate(self.request, "")
        bad = [FakeResponse(b"{}", 503), FakeResponse(b'{"response":"not json"}')]
        for response in bad:
            with self.subTest(response=response.data):
                with patch("ollama_adapter.http.client.HTTPConnection", return_value=FakeConnection(response)):
                    with self.assertRaises(ContractError):
                        generate(self.request, "nemotron-3-nano:4b")
