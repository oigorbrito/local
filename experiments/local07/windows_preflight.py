"""LOCAL-10 preflight: assess Windows/Ollama readiness without model inference.

Read-only HTTP GET /api/version, /api/tags and /api/ps to loopback.
No model pulls, generation calls, edits, installs, or benchmark repetitions.
"""
import argparse
import hashlib
import http.client
import json
import os
import pathlib
import platform
import sys
import time

MAX_BODY = 1048576


class PreflightFailure(RuntimeError):
    pass


def ollama_get(path, *, host="127.0.0.1", port=11434, timeout=5, transport=http.client.HTTPConnection):
    if host != "127.0.0.1" or not 1 <= port <= 65535:
        raise PreflightFailure("NON_LOOPBACK_BLOCKED")
    if path not in {"/api/version", "/api/tags", "/api/ps"}:
        raise PreflightFailure("ENDPOINT_BLOCKED")
    client = transport(host, port, timeout=timeout)
    try:
        client.request("GET", path, headers={"Accept": "application/json"})
        response = client.getresponse()
        if response.status != 200:
            raise PreflightFailure(f"HTTP_{response.status}_{path}")
        raw = response.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            raise PreflightFailure("RESPONSE_TOO_LARGE")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise PreflightFailure("BAD_OLLAMA_JSON") from exc
        if not isinstance(result, dict):
            raise PreflightFailure("BAD_OLLAMA_SCHEMA")
        return result
    finally:
        client.close()


def inspect(*, transport=http.client.HTTPConnection):
    version = ollama_get("/api/version", transport=transport)
    tags = ollama_get("/api/tags", transport=transport)
    ps = ollama_get("/api/ps", transport=transport)
    installed = tags.get("models", [])
    running = ps.get("models", [])
    if not isinstance(installed, list) or not isinstance(running, list):
        raise PreflightFailure("MODEL_LIST_SCHEMA")
    candidates = {"nemotron-3-nano:4b", "qwen3.5:2b", "qwen3.5:4b"}
    model_names = [m.get("name") for m in installed if isinstance(m, dict) and isinstance(m.get("name"), str)]
    resident = [m.get("name") for m in running if isinstance(m, dict) and isinstance(m.get("name"), str)]
    # Read-only inventory: no claims about throughput, VRAM peaks or model quality.
    return {
        "schema": 1,
        "status": "READ_ONLY_PREFLIGHT_PASS",
        "host_os": platform.system(),
        "python": platform.python_version(),
        "ollama_version": version.get("version"),
        "candidate_presence": {name: name in model_names for name in sorted(candidates)},
        "installed_names": sorted(model_names),
        "resident_names": sorted(resident),
        "generation_calls": 0,
        "validates": ["loopback_http", "model_inventory", "runtime_version"],
        "does_not_validate": ["model_generation", "patch_quality", "speed", "RAM_VRAM_peaks", "SWE_bench_resolution"]
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    args = p.parse_args()
    result = inspect()
    target = pathlib.Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "candidate_presence": result["candidate_presence"]}, sort_keys=True))


if __name__ == "__main__":
    main()
