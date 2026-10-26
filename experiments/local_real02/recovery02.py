"""LOCAL-REAL-02/RECOVERY-02: single bounded repair from immutable evidence.

Never executes candidate code on the host. Candidate testing uses Docker with
network disabled, read-only root, non-root UID, capability drop, limited memory
and PIDs, and only a temporary isolated directory bind-mounted read-only.

No comparisons with a baseline lacking a candidate. No autonomous model retries.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

BENCH_SHA = "ad212e91449df8a5885ba76c4e2d9979cb128e950afec20cdfd7cb4e0988bde6"
TEST_SHA = "80be32285f14bdadc5e87aaa8803d76bd0ef77e21e486e2f2fcac8bddfbf1611"
MODELS = ("qwen3.5:4b-q4_K_M", "qwen2.5-coder:7b", "phi4-mini:3.8b")
FIXABLE = (MODELS[0], MODELS[2])


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked_file(path: Path, expected: str) -> bytes:
    raw = path.read_bytes()
    if sha(raw) != expected:
        raise RuntimeError(f"INTEGRITY_MISMATCH: {path}")
    return raw


def load_benchmark(folder: Path):
    checked_file(folder / "benchmark.py", BENCH_SHA)
    checked_file(folder / "test_real_case.py", TEST_SHA)
    spec = importlib.util.spec_from_file_location("benchmark", folder / "benchmark.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("BASE_BENCHMARK_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if tuple(module.MODELS) != MODELS:
        raise RuntimeError("MODEL_LINEUP_CHANGED")
    return module


def verify_history(original: Path, completion: Path, bench) -> tuple[dict, dict, str, str]:
    raw = (original / "report.json").read_bytes()
    old = json.loads(raw)
    new = json.loads((completion / "completion_report.json").read_bytes())
    if old.get("schema") != 2 or new.get("schema") != 3:
        raise RuntimeError("HISTORY_SCHEMA_MISMATCH")
    if old.get("models") != list(MODELS) or new.get("original_report_sha256") != sha(raw):
        raise RuntimeError("HISTORY_NOT_CORRELATED")
    if len(old.get("results", [])) != 2 or len(new.get("results", [])) != 3:
        raise RuntimeError("HISTORY_TRIAL_COUNT_MISMATCH")
    if new["results"][:2] != old["results"]:
        raise RuntimeError("HISTORY_RESULTS_DRIFT")
    statuses = [(r.get("model"), r.get("status"), r.get("pass")) for r in new["results"]]
    expected = [(MODELS[0], "FUNCTIONAL_FAIL", False), (MODELS[1], "GENERATION_TIMEOUT", False),
                (MODELS[2], "INVALID_CANDIDATE", False)]
    if statuses != expected:
        raise RuntimeError(f"HISTORY_OUTCOME_MISMATCH: {statuses}")
    if old.get("source_revision") != bench.REVISION or old.get("source_path") != bench.FILE:
        raise RuntimeError("PINNED_SOURCE_REVISION_MISMATCH")
    if old.get("source_repo") != bench.REPO or old.get("wall_seconds_per_generation") != 240:
        raise RuntimeError("PROTOCOL_MISMATCH")
    if old.get("inference_protocol") != new.get("shared_protocol"):
        raise RuntimeError("INFERENCE_PROTOCOL_MISMATCH")
    source_bytes = (original / "pinned_source.py").read_bytes()
    if sha(source_bytes) != old.get("source_sha256") or sha(source_bytes) != new.get("source_sha256"):
        raise RuntimeError("SOURCE_SHA_MISMATCH")
    blob = b"blob " + str(len(source_bytes)).encode() + b"\0" + source_bytes
    if hashlib.sha1(blob).hexdigest() != bench.PINNED_BLOB_SHA:
        raise RuntimeError("SOURCE_GIT_BLOB_MISMATCH")
    if old.get("oracle_sha256") != TEST_SHA or new.get("oracle_sha256") != TEST_SHA:
        raise RuntimeError("ORACLE_SHA_MISMATCH")
    source = source_bytes.decode("utf-8")
    prompt = bench.user_prompt(source)
    if (original / MODELS[0].replace(":", "_") / "prompt.txt").read_text(encoding="utf-8") != prompt:
        raise RuntimeError("ORIGINAL_PROMPT_MISMATCH")
    if new.get("common_prompt_sha256") != sha(prompt.encode("utf-8")):
        raise RuntimeError("CONTINUATION_PROMPT_MISMATCH")
    for model in FIXABLE:
        evidence = original if model == MODELS[0] else completion
        gen_dir = evidence / model.replace(":", "_")
        raw_answer = (gen_dir / "raw_response.txt").read_text(encoding="utf-8")
        data = json.loads(raw_answer)
        if not isinstance(data, dict) or set(data) != {"code"} or not isinstance(data["code"], str):
            raise RuntimeError("MISSING_RECOVERABLE_CODE: " + model)
    return old, new, source, sha(raw)


def build_feedback(bench, source: str, prior: str, old_result: dict, prior_log: str) -> str:
    """Same recovery contract; model-specific observed feedback, no oracle source."""
    feedback = ["One repair opportunity after a failed attempt.",
                "Return ONLY JSON with key code containing the complete replacement retrieve() function.",
                "Do not modify any other function, add imports, or write commentary.",
                "Previous attempt did NOT resolve the issue."]
    if old_result["status"] == "INVALID_CANDIDATE":
        try:
            ast.parse(prior)
        except SyntaxError as exc:
            feedback.append(f"Compiler error: {exc.msg} at line {exc.lineno}.")
        else:
            feedback.append("Prior candidate violated the replacement contract.")
    else:
        failed = old_result.get("failures")
        if isinstance(failed, list):
            feedback.append("Failed independent checks: " + ", ".join(str(x) for x in failed[:15]))
        # Give bounded excerpt from test output (no test file or oracle code).
        if prior_log:
            feedback.append("Recorded test diagnostics (up to 4000 chars):\n" + prior_log[-4000:])
    feedback.append("YOUR PREVIOUS FUNCTION:\n" + prior[:16000])
    feedback.append("ORIGINAL TASK AND SOURCE:\n" + bench.user_prompt(source))
    return "\n\n".join(feedback)


def docker_command(image: str, bind_dir: Path) -> list[str]:
    return ["docker", "run", "--rm", "--pull=never", "--network", "none",
            "--read-only", "--cap-drop=ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "64", "--memory", "384m", "--cpus", "1",
            "--user", "65534:65534", "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
            "--mount", f"type=bind,src={bind_dir.resolve()},dst=/work,readonly",
            "--workdir", "/work", image, "python", "-I", "/work/test_real_case.py"]


def docker_preflight(image: str):
    cp = subprocess.run(["docker", "image", "inspect", image, "--format", "{{.Id}}"],
                        capture_output=True, text=True, timeout=20)
    if cp.returncode != 0 or not cp.stdout.strip():
        raise RuntimeError("DOCKER_IMAGE_NOT_LOCAL: pull a trusted image with 'docker pull " + image + "'")
    image_id = cp.stdout.strip()
    # Use immutable image ID for this run, rather than a floating tag.
    # An EMPTY temporary bind: the preflight never exposes the host temp directory.
    with tempfile.TemporaryDirectory(prefix="recovery02-probe-") as td:
        args = docker_command(image_id, Path(td))
        args[-1] = "-c"
        args += ["print('ISOLATED_PYTHON_OK')"]
        cp = subprocess.run(args, capture_output=True, text=True, timeout=40)
    if cp.returncode != 0 or "ISOLATED_PYTHON_OK" not in cp.stdout:
        raise RuntimeError("DOCKER_ISOLATED_PREFLIGHT_FAILED: " + cp.stderr[-500:])
    return image_id


def grade_in_docker(source: str, tests: Path, image_id: str, out: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="local-recovery02-") as td:
        root = Path(td)
        (root / "retrieve_context.py").write_text(source, encoding="utf-8", newline="\n")
        (root / "test_real_case.py").write_bytes(tests.read_bytes())
        cp = subprocess.run(docker_command(image_id, root), capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=40)
    (out / "test_result.txt").write_text((cp.stdout + "\n" + cp.stderr)[-30000:], encoding="utf-8")
    n = re.search(r"Ran (\d+) tests?", cp.stderr)
    if not n:
        raise RuntimeError("DOCKER_TESTS_DID_NOT_START: " + cp.stderr[-600:])
    fails = re.findall(r"^(?:FAIL|ERROR): (\S+)", cp.stderr, re.M)
    return {"pass": cp.returncode == 0 and bool(n), "tests": int(n.group(1)) if n else None,
            "failures": fails, "exit_code": cp.returncode}


def ollama_loaded() -> list[str]:
    import http.client
    c = http.client.HTTPConnection("127.0.0.1", 11434, timeout=10)
    try:
        c.request("GET", "/api/ps")
        r = c.getresponse()
        if r.status != 200:
            raise RuntimeError("OLLAMA_PS_BAD_STATUS")
        o = json.loads(r.read(100000))
        if not isinstance(o.get("models"), list):
            raise RuntimeError("OLLAMA_PS_BAD_SCHEMA")
        return [x["name"] for x in o["models"] if isinstance(x, dict) and isinstance(x.get("name"), str)]
    finally:
        c.close()


def ensure_idle_or_abort():
    loaded = ollama_loaded()
    if loaded:
        raise RuntimeError("OLLAMA_BUSY: " + repr(loaded) + "; do not disturb other work")


def settle_after_timeout(model: str):
    # Abort if unrelated models are active. Do not kill arbitrary processes.
    seen = ollama_loaded()
    if any(name != model for name in seen):
        raise RuntimeError("OLLAMA_BUSY_OTHER_WORK_AFTER_TIMEOUT")
    if model in seen:
        cp = subprocess.run(["ollama", "stop", model], capture_output=True, timeout=35)
        if cp.returncode:
            raise RuntimeError("OLLAMA_STOP_OWN_GENERATION_FAILED")
    for _ in range(30):
        seen = ollama_loaded()
        if not seen:
            return
        if any(name != model for name in seen):
            raise RuntimeError("OLLAMA_BUSY_OTHER_WORK_AFTER_STOP")
        time.sleep(2)
    raise RuntimeError("OLLAMA_NOT_QUIESCENT")


def one_repair(bench, model: str, prompt: str, source: str, out: Path,
               tests: Path, image_id: str, seconds: int) -> dict:
    out.mkdir()
    (out / "repair_prompt.txt").write_text(prompt, encoding="utf-8")
    job = [sys.executable, str(Path(bench.__file__).resolve()), "--worker", "--model", model,
           "--prompt", str(out / "repair_prompt.txt"), "--output", str(out), "--seconds", str(seconds)]
    begin = time.perf_counter()
    proc = subprocess.Popen(job, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        timed_out = True
    elapsed = round(time.perf_counter() - begin, 2)
    (out / "worker_stdio.txt").write_text("STDOUT:\n" + stdout + "\nSTDERR:\n" + stderr, encoding="utf-8")
    result = {"model": model, "status": "GENERATION_TIMEOUT" if timed_out else "GENERATION_ERROR",
              "pass": False, "seconds": elapsed}
    if timed_out:
        settle_after_timeout(model)
    elif proc.returncode == 0:
        try:
            raw = (out / "raw_response.txt").read_text(encoding="utf-8")
            if not raw.strip():
                raise ValueError("EMPTY_VISIBLE_RESPONSE")
            data = json.loads(raw)
            if not isinstance(data, dict) or set(data) != {"code"} or not isinstance(data["code"], str):
                raise ValueError("INVALID_RESPONSE_CONTRACT")
            merged = bench.validate_and_splice(source, data["code"])
            (out / "candidate_module.py").write_text(merged, encoding="utf-8", newline="\n")
            grade = grade_in_docker(merged, tests, image_id, out)
            result.update(grade)
            result["status"] = "PASS" if grade["pass"] else "FUNCTIONAL_FAIL"
        except (ValueError, SyntaxError) as exc:
            result["status"] = "INVALID_CANDIDATE"
            result["diagnostic"] = str(exc)
        except subprocess.TimeoutExpired:
            result["status"] = "TEST_TIMEOUT"
    if (out / "generation.json").exists():
        result["generation"] = json.loads((out / "generation.json").read_text(encoding="utf-8"))
    return result


def run(args):
    bench = load_benchmark(args.base.resolve())
    old, complete, source, orig_hash = verify_history(args.evidence.resolve(), args.completion.resolve(), bench)
    tests = args.base / "test_real_case.py"
    out = args.output or args.evidence.with_name(args.evidence.name + "-recovery02")
    out = out.resolve()
    if out.exists():
        raise RuntimeError("OUTPUT_ALREADY_EXISTS: " + str(out))
    initial_models = {m.get("name"): m.get("digest") for m in old.get("installed_model_digests", []) if isinstance(m, dict)}
    current_models = {m.get("name"): m.get("digest") for m in bench.ollama_inventory()}
    for model in FIXABLE:
        if not initial_models.get(model) or initial_models.get(model) != current_models.get(model):
            raise RuntimeError("MODEL_DIGEST_CHANGED_OR_MISSING: " + model)
    image_id = docker_preflight(args.image)
    # Reconfirm source before any generation, inside the same Docker evaluation contract.
    with tempfile.TemporaryDirectory(prefix="local-recovery02-oracle-") as td:
        checks = Path(td)
        original = grade_in_docker(source, tests, image_id, checks)
        reference = source.replace(
            "if any(p in {'tests','test','docs','examples','.venv','site-packages','__pycache__'} for p in path.parts): continue",
            "if any(p in {'tests','test','docs','examples','.venv','site-packages','__pycache__'} for p in pathlib.PurePath(relative).parts): continue")
        if reference == source:
            raise RuntimeError("REFERENCE_TRANSFORMATION_NOT_APPLICABLE")
        gold = grade_in_docker(reference, tests, image_id, checks)
        if original["pass"] or original["tests"] != 5 or not gold["pass"] or gold["tests"] != 5:
            raise RuntimeError("DOCKER_ORACLE_BASELINE_OR_REFERENCE_INVALID")
    ensure_idle_or_abort()
    out.mkdir(parents=True)
    start = {"schema": 1, "phase": "RECOVERY02", "state": "IN_PROGRESS",
             "created_at_utc": datetime.now(timezone.utc).isoformat(),
             "base_report_sha256": orig_hash,
             "completion_report_sha256": sha((args.completion / "completion_report.json").read_bytes()),
             "source_sha256": old["source_sha256"], "oracle_sha256": TEST_SHA,
             "docker_image_id": image_id, "model_digests": {m: current_models[m] for m in FIXABLE}, "docker_mode": "network_none+read_only+nonroot+capdrop+limits",
             "budget_seconds_per_repair": args.seconds,
             "baseline_original": original, "baseline_reference": gold,
             "old_results": complete["results"], "repairs": [], "winner": None}

    def save():
        (out / "report.json").write_text(json.dumps(start, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save()
    original_model_results = {r["model"]: r for r in complete["results"]}
    for model in MODELS:
        if model == MODELS[1]:
            result = {"model": model, "attempted": False, "status": "NO_CANDIDATE_AFTER_TIMEOUT",
                      "pass": False, "reason": "First stage timed out without recoverable source"}
        else:
            ensure_idle_or_abort()
            evidence = args.evidence if model == MODELS[0] else args.completion
            folder = evidence / model.replace(":", "_")
            prior = json.loads((folder / "raw_response.txt").read_text(encoding="utf-8"))["code"]
            log = (folder / "test_result.txt").read_text(encoding="utf-8") if (folder / "test_result.txt").is_file() else ""
            feedback = build_feedback(bench, source, prior, original_model_results[model], log)
            result = one_repair(bench, model, feedback, source, out / model.replace(":", "_"), tests, image_id, args.seconds)
            result["attempted"] = True
        start["repairs"].append(result)
        save()
        print("RECOVERY_RESULT", json.dumps(result, ensure_ascii=False), flush=True)
    start["state"] = "COMPLETED"
    start["decision"] = {"status": "RECOVERY_FINISHED_NO_GENERAL_WINNER", "winner": None,
                          "recovered_correct": [r["model"] for r in start["repairs"] if r.get("pass")],
                          "reason": "One heterogeneous repair opportunity on a single issue cannot rank models generally"}
    save()
    print("DECISION", json.dumps(start["decision"], ensure_ascii=False), flush=True)
    print("EVIDENCE", str(out), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--completion", type=Path, required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--image", default="python:3.12-slim")
    p.add_argument("--seconds", type=int, default=240)
    args = p.parse_args()
    if not 60 <= args.seconds <= 360:
        p.error("--seconds must be 60..360")
    try:
        run(args)
    except Exception as exc:
        print("RECOVERY_ABORT", type(exc).__name__, str(exc), file=sys.stderr, flush=True)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()

