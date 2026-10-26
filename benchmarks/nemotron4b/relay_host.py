#!/usr/bin/env python3
"""Windows-side bridge: allowlisted Ollama API over Docker stdio, no container network.

Runs Docker with --network none. Each incoming request is validated and forwarded
only to Windows 127.0.0.1:11434. No other TCP endpoint is forwarded.
"""
import argparse
import base64
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

MAX_BODY = 2 * 1024 * 1024
MAX_REPLY = 8 * 1024 * 1024
PERMITTED = {("GET", "/api/tags"), ("POST", "/api/show"),
             ("POST", "/api/chat"), ("POST", "/api/generate")}
_stdout_lock = threading.Lock()


def send(proc, frame):
    with _stdout_lock:
        proc.stdin.write(json.dumps(frame, separators=(",", ":")) + "\n")
        proc.stdin.flush()


def validate(method, path, body, model):
    if (method, path) not in PERMITTED:
        raise ValueError("OLLAMA_ENDPOINT_FORBIDDEN")
    if len(body) > MAX_BODY:
        raise ValueError("OLLAMA_REQUEST_TOO_LARGE")
    if method == "GET":
        if body:
            raise ValueError("GET_BODY_FORBIDDEN")
        return body, False
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeError):
        raise ValueError("OLLAMA_REQUEST_INVALID_JSON")
    if not isinstance(payload, dict) or payload.get("model") != model:
        raise ValueError("OLLAMA_MODEL_MISMATCH")
    if path in ("/api/chat", "/api/generate"):
        options = payload.get("options", {})
        if not isinstance(options, dict):
            raise ValueError("OLLAMA_OPTIONS_INVALID")
        options.update({"temperature": 0, "num_ctx": 4096, "num_predict": 2048})
        payload["options"] = options
    return json.dumps(payload, separators=(",", ":")).encode("utf-8"), bool(payload.get("stream"))


def forward(proc, item, model, timeout, metrics_path, phase):
    ident = item.get("id")
    if not isinstance(ident, str) or len(ident) != 32:
        return
    connection = None
    status = "ERROR"
    prompt_tokens = 0
    output_tokens = 0
    payload_bytes = 0
    collected = bytearray()
    try:
        method = item.get("method")
        path = item.get("path")
        raw = base64.b64decode(item.get("body", ""), validate=True)
        body, streamed = validate(method, path, raw, model)
        connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=timeout + 50)
        connection.request(method, path, body=body, headers={
            "Content-Type": "application/json", "Connection": "close"
        })
        response = connection.getresponse()
        send(proc, {"kind": "start", "id": ident, "status": response.status})
        status = str(response.status)
        while True:
            chunk = response.readline() if streamed else response.read(65536)
            if not chunk:
                break
            payload_bytes += len(chunk)
            if not streamed and path == "/api/generate":
                collected.extend(chunk)
            if payload_bytes > MAX_REPLY:
                raise ValueError("OLLAMA_REPLY_TOO_LARGE")
            send(proc, {"kind": "chunk", "id": ident,
                        "body": base64.b64encode(chunk).decode("ascii")})
            if streamed:
                try:
                    data = json.loads(chunk)
                    if data.get("done"):
                        prompt_tokens = data.get("prompt_eval_count") or 0
                        output_tokens = data.get("eval_count") or 0
                except (ValueError, AttributeError):
                    pass
        if collected:
            try:
                data = json.loads(collected)
                prompt_tokens = data.get("prompt_eval_count") or 0
                output_tokens = data.get("eval_count") or 0
            except (ValueError, AttributeError):
                pass
        send(proc, {"kind": "end", "id": ident})
    except (OSError, ValueError, TypeError, KeyError) as exc:
        try:
            send(proc, {"kind": "error", "id": ident, "status": 502,
                        "message": str(exc)[:180]})
        except (OSError, ValueError):
            pass
        status = "ERROR_" + type(exc).__name__
    finally:
        if connection:
            connection.close()
        metrics = {"request_id": ident, "phase": phase, "http_status": status,
                   "prompt_tokens": prompt_tokens, "output_tokens": output_tokens,
                   "response_bytes": payload_bytes}
        with _stdout_lock:
            with metrics_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(metrics) + "\n")


def require_path(path):
    result = Path(path).resolve(strict=True)
    if not result.is_dir():
        raise ValueError("DIRECTORY_EXPECTED: " + str(result))
    if "," in str(result) or "\n" in str(result):
        raise ValueError("UNSUPPORTED_MOUNT_PATH")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("docker-image", "benchmark-dir", "adapter-dir", "results-dir", "model"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=420)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 5 or not 60 <= args.timeout <= 420:
        parser.error("repeats 1..5; timeout 60..420")
    benchmark = require_path(args.benchmark_dir)
    adapter = require_path(args.adapter_dir)
    results = require_path(args.results_dir)
    metrics_path = results / "relay-request-metrics.jsonl"
    if metrics_path.exists():
        raise RuntimeError("RESULTS_ALREADY_HAVE_METRICS")
    # Explicit Docker Engine is required. Nothing starts Docker Desktop implicitly.
    cmd = [
        "docker", "run", "--rm", "-i", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "128", "--memory", "3g", "--cpus", "2",
        "--tmpfs", "/tmp:rw,exec,nosuid,size=512m",
        "--mount", "type=bind,source=" + str(benchmark) +
                   ",target=/app/benchmarks/nemotron4b,readonly",
        "--mount", "type=bind,source=" + str(adapter) +
                   ",target=/app/experiments/local07,readonly",
        "--mount", "type=bind,source=" + str(results) + ",target=/results",
        args.docker_image, "--model", args.model, "--repeats", str(args.repeats),
        "--timeout", str(args.timeout),
    ]
    workers = []
    phase = "preflight"
    with subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=None, text=True, encoding="utf-8", bufsize=1) as child:
        try:
            for line in child.stdout:
                try:
                    item = json.loads(line)
                except ValueError:
                    print("INVALID_GUEST_BROKER_FRAME", file=sys.stderr)
                    continue
                if item.get("kind") == "phase":
                    phase = str(item.get("name", ""))[:80]
                    continue
                if item.get("kind") != "request":
                    print("UNEXPECTED_GUEST_BROKER_FRAME", file=sys.stderr)
                    continue
                worker = threading.Thread(
                    target=forward, args=(child, item, args.model, args.timeout, metrics_path, phase),
                    daemon=True,
                )
                worker.start()
                workers.append(worker)
        except KeyboardInterrupt:
            child.terminate()
        finally:
            for worker in workers:
                worker.join(timeout=2)
        exitcode = child.wait()
    report_path = results / "report.json"
    if report_path.is_file() and metrics_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        metrics = [json.loads(line) for line in metrics_path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        for row in report.get("runs", []):
            name = "r%02d-%s" % (row["repeat"], row["executor"])
            subset = [m for m in metrics if m.get("phase") == name]
            row["inference"] = {
                "calls": len(subset),
                "prompt_tokens_total": sum(m["prompt_tokens"] for m in subset),
                "output_tokens_total": sum(m["output_tokens"] for m in subset),
                "http_errors": sum(m["http_status"] != "200" for m in subset),
            }
        report["transport"] = "network-none; Ollama allowlist over Docker stdio"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
    if exitcode != 0:
        print("BENCHMARK_EXIT=" + str(exitcode) + " (inspect results directory)",
              file=sys.stderr)
    return exitcode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print("RELAY_HOST_BLOCKED: " + str(exc), file=sys.stderr)
        sys.exit(2)
