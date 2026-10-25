#!/usr/bin/env python3
"""Paired real Nemotron repair: LOCAL-09 versus Cloi, scored by untouched tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
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

def cloi(repo, model, out, timeout):
    data = out / "cloi-data"
    data.mkdir()
    config = {"configVersion": 2, "model": model, "host": OLLAMA,
              "escalationModel": None, "judgeAnswers": False,
              "temperature": 0, "think": None, "contextLength": 4096,
              "maxIterations": 14, "maxVerificationRetries": 1,
              "compaction": False}
    (data / "config.json").write_text(json.dumps(config), encoding="utf-8")
    env = {**os.environ, "CLOI_DATA_DIR": str(data), "OLLAMA_HOST": OLLAMA}
    return run(["node", "/opt/cloi/bin/cloi.js", "--cwd", str(repo),
                "--model", model, "--yes", TASK],
               cwd=repo, timeout=timeout, env=env)

def grade(repo, out, attempt):
    changed = git(repo, "diff", "--name-only").splitlines()
    untracked = git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    patch = git(repo, "diff", "--binary", "HEAD", "--")
    save(out / "result.patch", patch)
    verification = tests(repo)
    save(out / "independent-tests.log", verification["stdout"] + verification["stderr"])
    return {"passed": attempt["code"] == 0 and not attempt["timeout"]
            and changed == ["guard.py"] and not untracked
            and bool(patch.strip()) and verification["code"] == 0,
            "changed_files": changed, "untracked_files": untracked,
            "external_tests_passed": verification["code"] == 0}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default="nemotron-3-nano:4b")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--timeout", type=int, default=420)
    a = p.parse_args()
    if not 1 <= a.repeats <= 5 or not 60 <= a.timeout <= 600:
        p.error("repeats 1..5, timeout 60..600")
    if not OUTPUT.is_dir() or not SOURCE.is_dir():
        raise RuntimeError("MISSING_READONLY_REPO_OR_OUTPUT_VOLUME")
    identity = model_identity(a.model)
    records = []
    for repetition in range(1, a.repeats+1):
        for arm in (("local09", "cloi") if repetition % 2 else ("cloi", "local09")):
            name = "r%02d-%s" % (repetition, arm)
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
    summary = {
        arm: {"passed": sum(r["passed"] for r in records if r["executor"] == arm),
              "total": a.repeats,
              "median_seconds": round(statistics.median(
                  r["wall_seconds"] for r in records if r["executor"] == arm), 3)}
        for arm in ("local09", "cloi")
    }
    report = {"schema": 1, "status": "MEASURED_NOT_RANKED", "model": identity,
              "suite": "symlink-escape-v1", "prompt": TASK, "summary": summary,
              "config": {"num_ctx": 4096, "temperature": 0,
                         "local09_num_predict": 2048,
                         "cloi_num_predict": "Ollama model default - not fixed",
                         "cloi_max_iterations": 14,
                         "cloi_commit": "1da62db7aa3aed8b1e65f1e3fb69a89cf00707b9"},
              "runs": records}
    (OUTPUT / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "report": "/results/report.json"}))
    return 0 if all(r["passed"] for r in records) else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}), file=sys.stderr)
        sys.exit(2)
