#!/usr/bin/env python3
"""Paired real Nemotron repair: LOCAL-09 versus Cloi, scored by untouched tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request

SOURCE = Path("/app/benchmarks/nemotron4b/fixture")
OUTPUT = Path("/results")
OLLAMA = "http://127.0.0.1:11434"
TASK = (
    "Fix guard.py read_text_under_root(root, relative_path): allow files "
    "inside root, but reject absolute paths, ../ traversal and symbolic links "
    "that resolve outside root with ValueError or PermissionError. "
    "Do not modify tests. Run tests to check your fix."
)

def run(command, cwd=None, timeout=40, env=None):
    start = time.monotonic()
    try:
        proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True,
                              stdin=subprocess.DEVNULL,
                              timeout=timeout, env=env)
        return {"code": proc.returncode, "seconds": round(time.monotonic()-start, 3),
                "stdout": proc.stdout, "stderr": proc.stderr, "timeout": False}
    except subprocess.TimeoutExpired as e:
        def decode(x):
            return x.decode("utf-8", "replace") if isinstance(x, bytes) else (x or "")
        return {"code": None, "seconds": round(time.monotonic()-start, 3),
                "stdout": decode(e.stdout), "stderr": decode(e.stderr), "timeout": True}

def git(cwd, *args):
    p = run(["git", *args], cwd=cwd)
    if p["code"]:
        raise RuntimeError("git failed: " + p["stderr"][-500:])
    return p["stdout"]

def tests(cwd):
    return run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
               cwd=cwd, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})

def model_identity(model):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(OLLAMA + "/api/tags", timeout=8) as res:
            models = json.load(res).get("models", [])
    except Exception as e:
        raise RuntimeError("OLLAMA_NOT_REACHABLE_IN_DOCKER_HOST_NETWORK: " + str(e))
    found = [m for m in models if model in (m.get("name"), m.get("model"))]
    if len(found) != 1:
        raise RuntimeError("MODEL_NOT_INSTALLED_OR_AMBIGUOUS: " + model)
    m = found[0]
    quant = str(m.get("details", {}).get("quantization_level", "")).upper()
    if quant != "Q4_K_M":
        raise RuntimeError("EXPECTED_Q4_K_M_ACTUAL_" + quant)
    digest = m.get("digest")
    if not isinstance(digest, str) or len(digest) < 16:
        raise RuntimeError("MODEL_DIGEST_UNAVAILABLE")
    return {"tag": model, "digest": digest, "quantization": quant}

def prepare(workspace, arm):
    target = workspace / arm
    shutil.copytree(SOURCE, target)
    git(target, "init", "-q")
    git(target, "config", "user.name", "Fixture")
    git(target, "config", "user.email", "fixture@example.invalid")
    git(target, "add", ".")
    git(target, "commit", "-qm", "fixture")
    baseline = tests(target)
    if baseline["code"] != 1 or "FAILED" not in baseline["stderr"]:
        raise RuntimeError("BASELINE_MUST_FAIL_FUNCTIONAL_TESTS")
    return target

def save(path, content):
    path.write_text(content, encoding="utf-8")
    return {"sha256": hashlib.sha256(content.encode()).hexdigest(),
            "bytes": len(content.encode())}

def local09(repo, model, out, timeout):
    issue = out / "issue.json"
    issue.write_text(json.dumps({"problem_statement": TASK}), encoding="utf-8")
    patch = out / "candidate.patch"
    result = run([
        sys.executable, "/app/experiments/local07/ollama_adapter.py",
        "--repo", str(repo), "--issue-json", str(issue), "--model", model,
        "--report", str(out / "local-report.json"), "--patch", str(patch),
        "--response-json-path", str(out / "model-response.json"),
        "--timeout", str(min(timeout, 420))
    ], cwd=repo, timeout=timeout+15)
    if result["code"] == 0 and patch.is_file() and patch.stat().st_size:
        p = run(["git", "apply", "--check", str(patch)], cwd=repo)
        if p["code"] == 0:
            p = run(["git", "apply", str(patch)], cwd=repo)
        if p["code"] != 0:
            result["stderr"] += "\nPATCH_APPLY_ERROR " + p["stderr"]
            result["code"] = 1
    return result

def cloi(repo, model, out, timeout, startup_trace=False):
    data = out / "cloi-data"
    data.mkdir()
    config = {"configVersion": 2, "model": model, "host": OLLAMA,
              "escalationModel": None, "judgeAnswers": False,
              "temperature": 0, "think": None, "contextLength": 4096,
              "maxIterations": 14, "maxVerificationRetries": 1,
              "compaction": False}
    (data / "config.json").write_text(json.dumps(config), encoding="utf-8")
    env = {**os.environ, "CLOI_DATA_DIR": str(data), "OLLAMA_HOST": OLLAMA}
    cmd = ["node"]
    if startup_trace:
        cmd += ["--import", "/app/benchmarks/nemotron4b/cloi_startup_trace.mjs"]
    cmd += ["/opt/cloi/bin/cloi.js", "--cwd", str(repo),
            "--model", model, "--yes", TASK]
    return run(cmd, cwd=repo, timeout=timeout, env=env)

def cloi_preflight_probe(model, identity):
    """Bounded full-body decode through Cloi's Node provider, without inference."""
    out = OUTPUT / "cloi-preflight-probe"
    out.mkdir(exist_ok=False)
    probe = run(
        ["node", "/app/benchmarks/nemotron4b/cloi_probe.mjs", model],
        timeout=15,
        env={**os.environ, "CLOI_MODEL": model, "OLLAMA_HOST": OLLAMA},
    )
    save(out / "stdout.log", probe["stdout"][-12000:])
    save(out / "stderr.log", probe["stderr"][-12000:])
    stages = [line.strip() for line in probe["stderr"].splitlines()
              if line.strip().startswith("PROBE_")]
    passed = (probe["code"] == 0 and not probe["timeout"]
              and "PROBE_PREFLIGHT_PASS" in stages)
    report = {
        "schema": 1, "status": "PROBE_PASS" if passed else "PROBE_BLOCKED",
        "mode": "CLOI_NODE_PREFLIGHT_NO_GENERATION", "model": identity,
        "probe": {"completed": passed, "returncode": probe["code"],
                  "timed_out": probe["timeout"], "seconds": probe["seconds"],
                  "stages": stages}
    }
    (OUTPUT / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": report["status"], "probe": report["probe"]}),
          flush=True)
    return 0 if passed else 2


def cloi_startup_probe(model, identity):
    """Execute pinned Cloi CLI but never allow model generation to leave Docker.

    The parent relay rejects /api/chat and /api/generate before forwarding.
    Session existence plus the expected diagnostic rejection attest startup.
    """
    os.write(1, b'{"kind":"phase","name":"cloi-startup-probe"}\n')
    out = OUTPUT / "cloi-startup-probe"
    out.mkdir(exist_ok=False)
    # Import-check the *full upstream entrypoint* without creating a session
    # or contacting Ollama. The earlier provider probe imports only ollama.js.
    # This distinguishes import/module stalls from later bootstrap failures.
    bootstrap = run(
        ["node", "--import", "/app/benchmarks/nemotron4b/cloi_startup_trace.mjs",
         "/opt/cloi/bin/cloi.js", "--help"],
        timeout=6, env={**os.environ, "OLLAMA_HOST": OLLAMA},
    )
    save(out / "bootstrap.stdout.log", bootstrap["stdout"][-8000:])
    save(out / "bootstrap.stderr.log", bootstrap["stderr"][-8000:])
    bootstrap_passed = bootstrap["code"] == 0 and not bootstrap["timeout"]
    if bootstrap_passed:
        with tempfile.TemporaryDirectory(prefix="nemotron-startup-") as temp:
            repo = prepare(Path(temp), "cloi-startup")
            attempt = cloi(repo, model, out, 20, startup_trace=True)
    else:
        attempt = {"code": None, "timeout": True, "seconds": 0,
                   "stdout": "", "stderr": "SKIPPED: CLI_MODULE_BOOTSTRAP_FAILED"}
    save(out / "stdout.log", attempt["stdout"][-12000:])
    save(out / "stderr.log", attempt["stderr"][-12000:])
    dbfile = out / "cloi-data" / "cloi.db"
    counts = {}
    if dbfile.is_file():
        try:
            connection = sqlite3.connect(f"file:{dbfile}?mode=ro", uri=True, timeout=2)
            try:
                counts["sessions"] = connection.execute(
                    "SELECT COUNT(*) FROM sessions").fetchone()[0]
                counts["messages"] = dict(connection.execute(
                    "SELECT role, COUNT(*) FROM messages GROUP BY role").fetchall())
            finally:
                connection.close()
        except sqlite3.DatabaseError:
            counts["sqlite_unreadable"] = True
    expected_denial = "DIAGNOSTIC_GENERATION_BLOCKED" in (
        attempt["stderr"] + attempt["stdout"])
    reached_generation = expected_denial and counts.get("sessions", 0) >= 1
    completed = reached_generation and not attempt["timeout"] and bootstrap_passed
    # Preserve only metadata from the diagnostic channel; never return
    # request/response bodies or file/source content.
    traces = []
    for line in attempt["stderr"].splitlines():
        if line.startswith("STARTUP_TRACE "):
            try:
                item = json.loads(line[len("STARTUP_TRACE "):])
                if item.get("event") in (
                    "cli_module_bootstrap", "request_created",
                    "request_body_sent", "response_headers",
                    "response_trailers", "request_error"
                ) and item.get("route") in (
                    None, "/api/tags", "/api/show", "/api/chat", "/api/generate"
                ):
                    traces.append({
                        "event": item["event"], "route": item.get("route"),
                        "ms": item.get("ms"),
                        "request_id": item.get("request_id"),
                        "status": item.get("status"),
                        "error_name": item.get("error_name"),
                        "error_code": item.get("error_code"),
                    })
            except (ValueError, TypeError, KeyError):
                pass
    result = {
        "schema": 1,
        "status": "STARTUP_REACHED_GENERATION_GATE" if completed
                  else "STARTUP_BLOCKED",
        "mode": "CLOI_REAL_CLI_STARTUP_WITH_GENERATION_DENIED",
        "model": identity,
        "startup": {"completed": completed,
                    "returncode": attempt["code"],
                    "timed_out": attempt["timeout"],
                    "seconds": attempt["seconds"],
                    "session_database_present": dbfile.is_file(),
                    "counts": counts,
                    "cli_help": {"passed": bootstrap_passed,
                                 "timed_out": bootstrap["timeout"],
                                 "seconds": bootstrap["seconds"]},
                    "request_trace": traces,
                    "generation_denial_observed": expected_denial},
    }
    (OUTPUT / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "startup": result["startup"]}),
          flush=True)
    return 0 if completed else 2


def cloi_sqlite_probe(model, identity):
    """Compare upstream Session.create WAL startup on the mounted volume vs tmpfs.

    Both subprocesses run the same pinned Cloi module with the same model, CPU
    and Node version; only CLOI_DATA_DIR changes. No agent or model call runs.
    """
    os.write(1, b'{"kind":"phase","name":"cloi-sqlite-probe"}\n')
    out = OUTPUT / "cloi-sqlite-probe"
    out.mkdir(exist_ok=False)
    trials = {}
    with tempfile.TemporaryDirectory(prefix="cloi-sqlite-tmpfs-") as temp:
        locations = (("mounted-results", out / "mounted-data"),
                     ("tmpfs", Path(temp) / "data"))
        for kind, data in locations:
            probe = run(
                ["node", "/app/benchmarks/nemotron4b/cloi_sqlite_probe.mjs",
                 str(data), model],
                timeout=8,
                env={**os.environ, "CLOI_DATA_DIR": str(data)},
            )
            save(out / (kind + ".stdout.log"), probe["stdout"][-8000:])
            save(out / (kind + ".stderr.log"), probe["stderr"][-8000:])
            stages = [line.strip() for line in probe["stderr"].splitlines()
                      if line.strip().startswith("SQLITE_")]
            passed = (probe["code"] == 0 and not probe["timeout"]
                      and "SQLITE_PROBE_PASS" in stages)
            trials[kind] = {
                "passed": passed, "returncode": probe["code"],
                "timed_out": probe["timeout"], "seconds": probe["seconds"],
                "stages": stages,
                "database_present": (data / "cloi.db").is_file(),
            }
    if trials["mounted-results"]["passed"] and trials["tmpfs"]["passed"]:
        status = "SQLITE_BOTH_PASS"
    elif trials["tmpfs"]["passed"] and not trials["mounted-results"]["passed"]:
        status = "SQLITE_MOUNT_SUSPECTED"
    else:
        status = "SQLITE_NOT_ISOLATED"
    result = {"schema": 1, "status": status,
              "mode": "CLOI_UPSTREAM_SQLITE_WAL_NO_GENERATION",
              "model": identity, "sqlite": trials}
    (OUTPUT / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({"status": status, "sqlite": trials}), flush=True)
    return 0 if status == "SQLITE_BOTH_PASS" else 2


def grade(repo, out, attempt):
    changed = git(repo, "diff", "--name-only").splitlines()
    untracked = git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    patch = git(repo, "diff", "--binary", "HEAD", "--")
    save(out / "result.patch", patch)
    verification = tests(repo)
    save(out / "independent-tests.log", verification["stdout"] + verification["stderr"])
    functional = (changed == ["guard.py"] and not untracked
                  and bool(patch.strip()) and verification["code"] == 0)
    # Code correctness and process reliability are separate experimental outcomes.
    # A process that exits nonzero after writing a correct patch must not be
    # mis-scored as a failed patch; its process failure remains visible.
    return {"passed": functional, "functional_passed": functional,
            "executor_completed": attempt["code"] == 0 and not attempt["timeout"],
            "changed_files": changed, "untracked_files": untracked,
            "external_tests_passed": verification["code"] == 0}


def order_for_repeat(repetition, first_executor):
    """Alternate order without changing model, task, or per-arm budgets."""
    if first_executor not in ("local09", "cloi"):
        raise ValueError("INVALID_FIRST_EXECUTOR")
    other = "cloi" if first_executor == "local09" else "local09"
    return (first_executor, other) if repetition % 2 else (other, first_executor)


def infrastructure_failure(attempt):
    """Stop a paired experiment when Ollama/transport state may contaminate later arms."""
    if attempt["timeout"]:
        return "EXECUTOR_WALL_TIMEOUT"
    stderr = attempt.get("stderr", "")
    if "TimeoutError: timed out" in stderr or "BROKER_TIMEOUT" in stderr:
        return "OLLAMA_REQUEST_TIMEOUT"
    if ("Cannot reach Ollama at" in stderr or "BROKER_PIPE_CLOSED" in stderr
            or "OLLAMA_NOT_REACHABLE" in stderr):
        return "OLLAMA_UNREACHABLE"
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default="nemotron-3-nano:4b")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--timeout", type=int, default=420)
    p.add_argument("--first-executor", choices=("local09", "cloi"),
                   default="local09")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--probe-only", action="store_true",
                       help="run Node Cloi preflight/JSON handshake, no generation")
    group.add_argument("--startup-probe", action="store_true",
                       help="run real Cloi CLI, with all generation blocked upstream")
    group.add_argument("--sqlite-probe", action="store_true",
                       help="compare pinned Cloi SQLite startup on mounted volume vs tmpfs")
    a = p.parse_args()
    if not 1 <= a.repeats <= 5 or not 60 <= a.timeout <= 420:
        p.error("repeats 1..5, timeout 60..420")
    if not OUTPUT.is_dir() or not SOURCE.is_dir():
        raise RuntimeError("MISSING_READONLY_REPO_OR_OUTPUT_VOLUME")
    identity = model_identity(a.model)
    if a.probe_only:
        return cloi_preflight_probe(a.model, identity)
    if a.startup_probe:
        return cloi_startup_probe(a.model, identity)
    if a.sqlite_probe:
        return cloi_sqlite_probe(a.model, identity)
    records = []
    blocked = None
    for repetition in range(1, a.repeats+1):
        for arm in order_for_repeat(repetition, a.first_executor):
            name = "r%02d-%s" % (repetition, arm)
            os.write(1, (json.dumps({"kind": "phase", "name": name}) + "\n").encode("utf-8"))
            out = OUTPUT / name
            out.mkdir(exist_ok=False)
            with tempfile.TemporaryDirectory(prefix="nemotron-repair-") as tmp:
                repo = prepare(Path(tmp), name)
                start = time.monotonic()
                attempt = (local09(repo, a.model, out, a.timeout) if arm == "local09"
                           else cloi(repo, a.model, out, a.timeout))
                try:
                    verdict = grade(repo, out, attempt)
                except Exception as e:
                    verdict = {"passed": False, "grade_error": str(e)}
                row = {"repeat": repetition, "executor": arm,
                       "wall_seconds": round(time.monotonic()-start, 3),
                       "returncode": attempt["code"], "timed_out": attempt["timeout"],
                       **verdict,
                       "stdout": save(out / "stdout.log", attempt["stdout"][-128000:]),
                       "stderr": save(out / "stderr.log", attempt["stderr"][-128000:])}
                records.append(row)
                print(json.dumps({"executor": arm, "repeat": repetition,
                                  "passed": row["passed"], "seconds": row["wall_seconds"]}),
                      flush=True)
                reason = infrastructure_failure(attempt)
                if reason:
                    blocked = {"reason": reason, "executor": arm, "repeat": repetition}
                    print(json.dumps({"status": "BLOCKED_AFTER_ATTEMPT", **blocked}),
                          file=sys.stderr, flush=True)
                    break
        if blocked:
            break
    summary = {}
    for arm in ("local09", "cloi"):
        subset = [r for r in records if r["executor"] == arm]
        summary[arm] = {"passed": sum(r["passed"] for r in subset),
                        "total": len(subset), "requested": a.repeats,
                        "median_seconds": (round(statistics.median(
                            r["wall_seconds"] for r in subset), 3) if subset else None)}
    report = {"schema": 2, "status": (
              "BLOCKED_TRANSPORT_OR_TIMEOUT" if blocked else "MEASURED_NOT_RANKED"),
              "blocking": blocked, "model": identity,
              "first_executor": a.first_executor,
              "suite": "symlink-escape-v1", "prompt": TASK, "summary": summary,
              "config": {"num_ctx": 4096, "temperature": 0,
                         "local09_num_predict": 2048,
                         "cloi_num_predict": 2048, "relay_enforces_generation": True,
                         "cloi_max_iterations": 14,
                         "cloi_commit": "1da62db7aa3aed8b1e65f1e3fb69a89cf00707b9"},
              "runs": records}
    (OUTPUT / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "report": "/results/report.json"}))
    if blocked:
        return 2
    return 0 if all(r["passed"] for r in records) else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}), file=sys.stderr)
        sys.exit(2)
