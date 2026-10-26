"""Offline checks for the no-network Ollama bridge contract. No Ollama/Docker calls."""
import base64
import json
import unittest

from relay_host import validate

MODEL = "nemotron-3-nano:4b"


class RelayContractTests(unittest.TestCase):
    def test_model_is_fixed_and_generation_limits_match(self):
        for path in ("/api/chat", "/api/generate"):
            with self.subTest(path=path):
                request = json.dumps({
                    "model": MODEL, "stream": path == "/api/chat",
                    "options": {"num_ctx": 100000, "temperature": 0.8,
                                "num_predict": 40960},
                }).encode()
                payload, stream = validate("POST", path, request, MODEL)
                options = json.loads(payload)["options"]
                self.assertEqual(options["num_ctx"], 4096)
                self.assertEqual(options["num_predict"], 2048)
                self.assertEqual(options["temperature"], 0)
                self.assertEqual(stream, path == "/api/chat")

    def test_other_models_and_control_endpoints_are_blocked(self):
        for path in ("/api/pull", "/api/delete", "/api/create", "/api/ps",
                     "/", "http://127.0.0.1:12345/api/chat"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate("POST", path, json.dumps({"model": MODEL}).encode(), MODEL)
        with self.assertRaisesRegex(ValueError, "MODEL_MISMATCH"):
            validate("POST", "/api/chat",
                     json.dumps({"model": "another-model"}).encode(), MODEL)

    def test_tags_only_get_no_body_and_valid_show(self):
        self.assertEqual(validate("GET", "/api/tags", b"", MODEL), (b"", False))
        with self.assertRaises(ValueError):
            validate("GET", "/api/tags", b"credentials", MODEL)
        body = json.dumps({"model": MODEL}).encode()
        self.assertEqual(validate("POST", "/api/show", body, MODEL),
                         (body, False))

    def test_oversized_and_invalid_inputs_rejected(self):
        with self.assertRaises(ValueError):
            validate("POST", "/api/chat", b"x" * (2 * 1024 * 1024 + 1), MODEL)
        with self.assertRaises(ValueError):
            validate("POST", "/api/chat", b"not-json", MODEL)
        with self.assertRaises(ValueError):
            validate("POST", "/api/chat",
                     json.dumps({"model": MODEL, "options": []}).encode(), MODEL)


if __name__ == "__main__":
    unittest.main()
