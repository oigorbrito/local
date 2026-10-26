#!/usr/bin/env python3
"""Windows-side bridge: allowlisted Ollama API over Docker stdio, no container network.

Runs Docker with --network none. Each incoming request is validated and forwarded
only to Windows 127.0.0.1:11434. No other TCP endpoint is forwarded.
"""
import argparse
import base64
import http.client
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

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


def record_request_start(metrics_path, item, phase):
    """Persist request intent before launching a worker that may outlive Docker.

    Excludes request bodies and prompts. A missing matching terminal metrics
    record now reliably identifies a request unfinished at process exit.
    """
    ident = item.get("id")
    if not isinstance(ident, str) or len(ident) != 32:
        return False
    record = {
        "request_id": ident,
        "phase": phase,
        "method": str(item.get("method", ""))[:16],
        "path": str(item.get("path", ""))[:120],
        "started_unix_seconds": round(time.time(), 3),
    }
    with _stdout_lock:
        with (metrics_path.parent / "relay-request-starts.jsonl").open(
            "a", encoding="utf-8"
        ) as stream:
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")
    return True


def record_request_progress(metrics_path, ident, phase, stage, elapsed_seconds,
                            response_bytes=0, http_status=None):
    """Record bounded, content-free stages while a request is still in flight.

    Terminal metrics may never be written after a subprocess wall timeout. This
    journal lets us distinguish blocked connect/headers from slow generation.
    """
    record = {
        "request_id": ident, "phase": phase, "stage": stage,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "response_bytes": response_bytes, "http_status": http_status,
    }
    with _stdout_lock:
        with (metrics_path.parent / "relay-request-events.jsonl").open(
            "a", encoding="utf-8"
        ) as stream:
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")


def forward(proc, item, model, timeout, metrics_path, phase, block_generation=False):
    ident = item.get("id")
    if not isinstance(ident, str) or len(ident) != 32:
        return
    started_at = time.monotonic()
    connection = None
    status = "ERROR"
    prompt_tokens = 0
    output_tokens = 0
    usage_available = False
    response_complete = False
    error_type = None
    payload_bytes = 0
    chunks_seen = 0
    last_progress_at = started_at
    collected = bytearray()
    raw_record = None
    try:
        method = item.get("method")
        path = item.get("path")
        raw = base64.b64decode(item.get("body", ""), validate=True)
        body, streamed = validate(method, path, raw, model)
        if block_generation and path in ("/api/chat", "/api/generate"):
            record_request_progress(metrics_path, ident, phase,
                                    "generation_blocked_before_upstream",
                                    time.monotonic() - started_at)
            raise ValueError("DIAGNOSTIC_GENERATION_BLOCKED")
        connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=timeout + 50)
        connection.request(method, path, body=body, headers={
            "Content-Type": "application/json", "Connection": "close"
        })
        record_request_progress(metrics_path, ident, phase, "upstream_request_sent",
                                time.monotonic() - started_at)
        response = connection.getresponse()
        record_request_progress(metrics_path, ident, phase, "upstream_headers_received",
                                time.monotonic() - started_at,
                                http_status=response.status)
        send(proc, {"kind": "start", "id": ident, "status": response.status})
        status = str(response.status)
        while True:
            chunk = response.readline() if streamed else response.read(65536)
            if not chunk:
                break
            payload_bytes += len(chunk)
            chunks_seen += 1
            now = time.monotonic()
            if chunks_seen == 1 or now - last_progress_at >= 15:
                record_request_progress(
                    metrics_path, ident, phase,
                    "upstream_first_chunk" if chunks_seen == 1 else "upstream_stream_progress",
                    now - started_at, response_bytes=payload_bytes,
                    http_status=response.status)
                last_progress_at = now
            if path in ("/api/generate", "/api/chat"):
                collected.extend(chunk)
            if payload_bytes > MAX_REPLY:
                raise ValueError("OLLAMA_REPLY_TOO_LARGE")
            send(proc, {"kind": "chunk", "id": ident,
                        "body": base64.b64encode(chunk).decode("ascii")})
            if streamed:
                try:
                    data = json.loads(chunk)
                    if data.get("done"):
                        record_request_progress(metrics_path, ident, phase,
                                                "upstream_model_done",
                                                time.monotonic() - started_at,
                                                response_bytes=payload_bytes,
                                                http_status=response.status)
                        usage_available = ("prompt_eval_count" in data
                                           and "eval_count" in data)
                        prompt_tokens = data.get("prompt_eval_count") or 0
                        output_tokens = data.get("eval_count") or 0
                except (ValueError, AttributeError):
                    pass
        if collected and not streamed:
            try:
                data = json.loads(collected)
                usage_available = ("prompt_eval_count" in data
                                   and "eval_count" in data)
                prompt_tokens = data.get("prompt_eval_count") or 0
                output_tokens = data.get("eval_count") or 0
            except (ValueError, AttributeError):
                pass
        send(proc, {"kind": "end", "id": ident})
        response_complete = True
        record_request_progress(metrics_path, ident, phase, "guest_end_forwarded",
                                time.monotonic() - started_at,
                                response_bytes=payload_bytes, http_status=response.status)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        error_type = type(exc).__name__
        try:
            send(proc, {"kind": "error", "id": ident, "status": 502,
                        "message": str(exc)[:180]})
        except (OSError, ValueError):
            pass
        status = "ERROR_" + type(exc).__name__
    finally:
        if connection:
            connection.close()
        if collected and path in ("/api/generate", "/api/chat"):
            # Keep the original Ollama reply even if JSON contract validation
            # later rejects it; this stores response bytes, not the user prompt.
            evidence = metrics_path.parent / "raw-ollama-responses"
            evidence.mkdir(exist_ok=True)
            file = evidence / (ident + (".ndjson" if streamed else ".json"))
            with file.open("xb") as stream:
                stream.write(collected)
            raw_record = {
                "relative_path": file.relative_to(metrics_path.parent).as_posix(),
                "sha256": hashlib.sha256(collected).hexdigest(),
                "bytes": len(collected),
            }
        metrics = {"request_id": ident, "phase": phase, "http_status": status,
                   "method": item.get("method"), "path": item.get("path"),
                   "elapsed_seconds": round(time.monotonic() - started_at, 3),
                   "response_complete": response_complete,
                   "usage_available": usage_available, "error_type": error_type,
                   "prompt_tokens": prompt_tokens, "output_tokens": output_tokens,
                   "response_bytes": payload_bytes, "raw_response": raw_record}
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
    parser.add_argument("--first-executor", choices=("local09", "cloi"),
                        default="local09")
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--startup-probe", action="store_true")
    args = parser.parse_args()
    if args.probe_only and args.startup_probe:
        parser.error("probe-only and startup-probe are mutually exclusive")
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
        "--first-executor", args.first_executor,
    ]
    if args.probe_only:
        cmd.append("--probe-only")
    if args.startup_probe:
        cmd.append("--startup-probe")
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
                if not record_request_start(metrics_path, item, phase):
                    print("INVALID_RELAY_REQUEST_ID", file=sys.stderr)
                    continue
                worker = threading.Thread(
                    target=forward, args=(child, item, args.model, args.timeout,
                                          metrics_path, phase, args.startup_probe),
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
            generation = [m for m in subset
                          if m.get("path") in ("/api/chat", "/api/generate")]
            row["inference"] = {
                "calls": len(subset),
                "generation_calls": len(generation),
                "prompt_tokens_total": sum(m["prompt_tokens"] for m in generation),
                "output_tokens_total": sum(m["output_tokens"] for m in generation),
                "generation_usage_missing": sum(
                    not m.get("usage_available", False) for m in generation),
                "http_errors": sum(m["http_status"] != "200" for m in subset),
                "incomplete_responses": sum(
                    not m.get("response_complete", False) for m in subset),
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
