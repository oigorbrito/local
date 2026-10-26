#!/usr/bin/env python3
"""Offline diagnosis of LOCAL-27 run artifacts; no Ollama, Docker or code execution.

Never prints prompts, response content, filesystem source text, or secrets.
Preserves uncertainty when a timed-out daemon worker did not flush its metrics.
"""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

GENERATION = {"/api/chat", "/api/generate"}


def load_jsonl(path):
    if not path.is_file():
        return []
    rows = []
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"INVALID_JSONL {path.name}:{no}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"INVALID_JSONL_ROW {path.name}:{no}")
        rows.append(obj)
    return rows


def describe_response(root, record):
    raw = record.get("raw_response")
    if not isinstance(raw, dict):
        return {"saved": False}
    relative = raw.get("relative_path")
    if not isinstance(relative, str):
        return {"saved": False, "integrity": "INVALID_PATH"}
    base = root.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(base) or not candidate.is_file():
        return {"saved": False, "integrity": "MISSING_OR_UNSAFE_PATH"}
    import hashlib
    content = candidate.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    result = {
        "saved": True,
        "bytes": len(content),
        "sha256_ok": digest == raw.get("sha256"),
    }
    if not result["sha256_ok"]:
        return result
    if record.get("path") in GENERATION and relative.endswith(".ndjson"):
        # Inspect only completion counters; never include model-produced text.
        completed = False
        lines = 0
        for chunk in content.splitlines():
            if not chunk.strip():
                continue
            lines += 1
            try:
                frame = json.loads(chunk)
            except ValueError:
                continue
            if isinstance(frame, dict) and frame.get("done") is True:
                completed = True
        result.update({"ndjson_lines": lines, "ollama_done_frame": completed})
    return result


def cloi_session_summary(root, repeat):
    """Count persisted agent steps from a disposable SQLite WAL-aware copy.

    Cloi's original database can contain private messages, tool arguments, and
    source code. Never query those columns and never write into its directory.
    """
    source = root / ("r%02d-cloi" % repeat) / "cloi-data" / "cloi.db"
    if not source.is_file() or source.is_symlink():
        return {"database_present": False}
    with tempfile.TemporaryDirectory(prefix="local27-cloi-session-") as tmp:
        local = Path(tmp)
        for suffix in ("", "-wal", "-shm"):
            path = source.with_name(source.name + suffix)
            if path.is_file() and not path.is_symlink():
                shutil.copyfile(path, local / path.name)
        try:
            db = sqlite3.connect(str(local / source.name), timeout=3)
            try:
                rows = db.execute(
                    "SELECT role, COUNT(*) FROM messages GROUP BY role"
                ).fetchall()
                tools = db.execute(
                    "SELECT tool_name, COUNT(*) FROM messages "
                    "WHERE role = 'tool' AND tool_name IS NOT NULL "
                    "GROUP BY tool_name"
                ).fetchall()
                sessions = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                results = db.execute("SELECT COUNT(*) FROM results").fetchone()[0]
            finally:
                db.close()
        except sqlite3.DatabaseError as exc:
            return {"database_present": True,
                    "readable": False, "error_type": type(exc).__name__}
    return {
        "database_present": True, "readable": True,
        "sessions": sessions, "roles": dict(rows),
        "tool_results_by_name": dict(tools), "stored_results": results,
    }


def analyze(root):
    report_path = root / "report.json"
    if not report_path.is_file():
        raise ValueError("MISSING_REPORT: " + str(report_path))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    cloi_sessions = {
        "r%02d-cloi" % r["repeat"]: cloi_session_summary(root, r["repeat"])
        for r in report.get("runs", []) if r.get("executor") == "cloi"
    }
    metrics = load_jsonl(root / "relay-request-metrics.jsonl")
    starts = load_jsonl(root / "relay-request-starts.jsonl")
    events = load_jsonl(root / "relay-request-events.jsonl")
    completed_ids = {r.get("request_id") for r in metrics}
    phases = {}
    for item in metrics:
        phase = item.get("phase", "unknown")
        phases.setdefault(phase, []).append(item)
    for item in starts:
        phases.setdefault(item.get("phase", "unknown"), [])
    for item in events:
        phases.setdefault(item.get("phase", "unknown"), [])
    summary = []
    for phase, records in phases.items():
        initiated = [r for r in starts if r.get("phase") == phase]
        unsettled = [
            {"id": r.get("request_id"),
             "method": r.get("method"), "path": r.get("path")}
            for r in initiated if r.get("request_id") not in completed_ids
        ]
        phase_events = [
            {"stage": r.get("stage"),
             "elapsed_seconds": r.get("elapsed_seconds"),
             "response_bytes": r.get("response_bytes"),
             "http_status": r.get("http_status"),
             "request_id": r.get("request_id")}
            for r in events if r.get("phase") == phase
        ]
        requests = []
        for r in records:
            requests.append({
                "method": r.get("method"),
                "path": r.get("path"),
                "http_status": r.get("http_status"),
                "elapsed_seconds": r.get("elapsed_seconds"),
                "response_complete": r.get("response_complete"),
                "usage_available": r.get("usage_available"),
                "prompt_tokens": r.get("prompt_tokens"),
                "output_tokens": r.get("output_tokens"),
                "response_bytes": r.get("response_bytes"),
                "error_type": r.get("error_type"),
                "raw": describe_response(root, r),
            })
        summary.append({
            "phase": phase,
            "requests_started": len(initiated) if starts else None,
            "requests_recorded": len(records),
            "unfinished_at_collection": unsettled,
            "coverage": ("REQUEST_STARTS_AVAILABLE" if starts
                         else "HISTORICAL_COMPLETED_ONLY"),
            "request_events": phase_events,
            "requests": requests,
        })
    return {
        "status": report.get("status"),
        "blocking": report.get("blocking"),
        "first_executor": report.get("first_executor"),
        "model": report.get("model"),
        "cloi_sessions": cloi_sessions,
        "runs": [
            {"executor": r.get("executor"), "repeat": r.get("repeat"),
             "seconds": r.get("wall_seconds"), "timed_out": r.get("timed_out"),
             "passed": r.get("passed"), "returncode": r.get("returncode"),
             "changed_files": r.get("changed_files"),
             "external_tests_passed": r.get("external_tests_passed")}
            for r in report.get("runs", [])
        ],
        "phases": summary,
        "limitation": ("No start records in this historical run: requests left in flight "
                       "when the container exited cannot be reconstructed."
                       if not starts else
                       "Request-start records available, but there are no progress-stage "
                       "events in this run; stalled network stage remains unknown."
                       if not events else None),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.results)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            parser.error("output already exists; refusing overwrite")
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print("LOCAL27_DIAGNOSE_ERROR: " + str(exc), file=sys.stderr)
        sys.exit(2)
