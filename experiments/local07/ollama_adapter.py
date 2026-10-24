"""Explicit opt-in, localhost-only Ollama adapter for LOCAL-09.

No background calls, no model auto-selection, no system commands from model output.
The response passes through executor_bridge.parse_response and LOCAL-07 safe patch validation.
"""
import argparse
import http.client
import json
import pathlib

from executor_bridge import ContractError, MAX_RESPONSE_BYTES, prepare, parse_response, replay


def generate(request, model, *, host="127.0.0.1", port=11434, timeout=180):
    if host not in {"127.0.0.1", "localhost", "::1"} or not (1 <= port <= 65535):
        raise ContractError("ONLY_LOOPBACK_OLLAMA_ALLOWED")
    if not isinstance(model, str) or not model or len(model) > 128 or any(c.isspace() for c in model):
        raise ContractError("INVALID_MODEL_IDENTIFIER")
    prompt = (
        "Produce ONLY a JSON object with exactly keys schema (integer 1), file "
        "(one allowed path), and content (complete modified Python source). "
        "Never return markdown, shell commands, or explanation.\n"
        + json.dumps(request.to_json(), ensure_ascii=False)
    )
    body = json.dumps({
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 2048},
        "prompt": prompt
    }).encode("utf-8")
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("POST", "/api/generate", body=body, headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            raise ContractError("OLLAMA_HTTP_ERROR_" + str(response.status))
        if response.getheader("Content-Length"):
            try:
                if int(response.getheader("Content-Length")) > MAX_RESPONSE_BYTES * 2:
                    raise ContractError("OLLAMA_RESPONSE_TOO_LARGE")
            except ValueError as exc:
                raise ContractError("INVALID_RESPONSE_LENGTH") from exc
        blob = response.read(MAX_RESPONSE_BYTES * 2 + 1)
        if len(blob) > MAX_RESPONSE_BYTES * 2:
            raise ContractError("OLLAMA_RESPONSE_TOO_LARGE")
    finally:
        conn.close()
    try:
        outer = json.loads(blob.decode("utf-8"))
        if not isinstance(outer, dict) or not isinstance(outer.get("response"), str):
            raise ContractError("OLLAMA_SCHEMA_MISMATCH")
        payload = outer["response"].encode("utf-8")
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("OLLAMA_INVALID_JSON") from exc
    parse_response(payload, request.selected_files)
    return payload


def main():
    p = argparse.ArgumentParser(description="EXPLICIT local model invocation only")
    for name in ("repo", "issue-json", "model", "report", "patch"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--timeout", type=int, default=180)
    a = p.parse_args()
    if not 1 <= a.timeout <= 420:
        raise ContractError("INVALID_TIMEOUT")
    issue = json.loads(pathlib.Path(a.issue_json).read_text(encoding="utf-8"))["problem_statement"]
    request = prepare(a.repo, issue)
    payload = generate(request, a.model, timeout=a.timeout)
    report, patch = replay(a.repo, issue, payload)
    pathlib.Path(a.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    pathlib.Path(a.patch).write_text(patch, encoding="utf-8", newline="\n")
    print(json.dumps({"status": report["status"], "patch_sha256": report["validation"]["patch_sha256"]}))


if __name__ == "__main__":
    main()
