"""LOCAL-REAL-02 controlled completion: ONLY the skipped Phi-4 Mini trial.

Reads but never changes the original evidence directory. Explicitly unloads only
our timed-out Qwen7B, waits until Ollama reports zero loaded models, and refuses
unknown concurrent loads. /api/ps does not prove absence of queued external work;
run only on a dedicated Ollama instance with no other active users.
"""
from __future__ import annotations
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

import benchmark

TARGET = "phi4-mini:3.8b"
TIMED_OUT = "qwen2.5-coder:7b"
FIRST = "qwen3.5:4b-q4_K_M"
SECONDS = 240


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_previous(root: Path) -> tuple[dict, str, str, str]:
    root = root.resolve(strict=True)
    report_file = root / "report.json"
    original = report_file.read_bytes()
    manifest = json.loads(original)
    if manifest.get("schema") != 2 or manifest.get("models") != list(benchmark.MODELS):
        raise RuntimeError("INCOMPATIBLE_PREVIOUS_MANIFEST")
    for key, expected in [
        ("source_revision", benchmark.REVISION),
        ("source_path", benchmark.FILE),
        ("source_repo", benchmark.REPO),
        ("wall_seconds_per_generation", SECONDS),
    ]:
        if manifest.get(key) != expected:
            raise RuntimeError("BASELINE_OR_SETTINGS_DIFFER: " + key)
    old = manifest.get("results")
    if not isinstance(old, list) or len(old) != 2 or [x.get("model") for x in old] != [FIRST, TIMED_OUT]:
        raise RuntimeError("NOT_THE_TWO_TRIAL_ABORT_OR_ALREADY_COMPLETED")
    if old[0].get("status") != "FUNCTIONAL_FAIL" or old[1].get("status") != "GENERATION_TIMEOUT":
        raise RuntimeError("PREVIOUS_TRIAL_STATUS_DIFFERS")
    if (root / TARGET.replace(":", "_")).exists():
        raise RuntimeError("PHI_ALREADY_EXECUTED_IN_ORIGINAL")
    source_bytes = (root / "pinned_source.py").read_bytes()
    if sha256(source_bytes) != manifest.get("source_sha256"):
        raise RuntimeError("SOURCE_HASH_MISMATCH")
    git_blob = b"blob " + str(len(source_bytes)).encode() + b"\0" + source_bytes
    if hashlib.sha1(git_blob).hexdigest() != benchmark.PINNED_BLOB_SHA:
        raise RuntimeError("PINNED_GIT_BLOB_MISMATCH")
    oracle = Path(benchmark.__file__).with_name("test_real_case.py").read_bytes()
    if sha256(oracle) != manifest.get("oracle_sha256"):
        raise RuntimeError("ORACLE_HASH_MISMATCH")
    source = source_bytes.decode("utf-8")
    prompt = benchmark.user_prompt(source)
    prior_prompt = (root / FIRST.replace(":", "_") / "prompt.txt").read_text(encoding="utf-8")
    if prompt != prior_prompt:
        raise RuntimeError("PROMPT_DIFFERENT_FROM_PRIOR_TRIAL")
    original_inv = manifest.get("installed_model_digests")
    if not isinstance(original_inv, list) or TARGET not in {e.get("name") for e in original_inv if isinstance(e, dict)}:
        raise RuntimeError("MISSING_PREVIOUS_MODEL_DIGEST")
    return manifest, source, prompt, sha256(original)


def get_loaded() -> list[dict]:
    conn = http.client.HTTPConnection("127.0.0.1", 11434, timeout=8)
    try:
        conn.request("GET", "/api/ps")
        r = conn.getresponse()
        if r.status != 200:
            raise RuntimeError("OLLAMA_PS_HTTP_" + str(r.status))
        doc = json.loads(r.read(256_000))
        models = doc.get("models")
        if not isinstance(models, list) or not all(isinstance(e, dict) and isinstance(e.get("name"), str) for e in models):
            raise RuntimeError("OLLAMA_PS_BAD_SCHEMA")
        return models
    finally:
        conn.close()


def settle_prior(budget: float = 75, interval: float = 2) -> list[dict]:
    """Unload only the timed-out owned model; NEVER stop unrelated models."""
    loaded = get_loaded()
    others = [x["name"] for x in loaded if x["name"] != TIMED_OUT]
    if others:
        raise RuntimeError("OLLAMA_BUSY_OTHER_MODELS: " + ", ".join(others))
    if not loaded:
        return []
    print("UNLOAD_PREVIOUS", TIMED_OUT, flush=True)
    cp = subprocess.run(["ollama", "stop", TIMED_OUT], capture_output=True, text=True, timeout=30, check=False)
    if cp.returncode != 0:
        raise RuntimeError("OLLAMA_STOP_FAILED: " + cp.stderr[:300])
    start = time.monotonic()
    while time.monotonic() - start < budget:
        loaded = get_loaded()
        if not loaded:
            return []
        others = [x["name"] for x in loaded if x["name"] != TIMED_OUT]
        if others:
            raise RuntimeError("OLLAMA_BUSY_OTHER_MODELS_AFTER_STOP: " + ", ".join(others))
        time.sleep(interval)
    raise RuntimeError("UNLOAD_UNCONFIRMED: refuse potentially contaminated inference")


def verify_model_digest(manifest: dict) -> str:
    expected = {m.get("name"): m.get("digest") for m in manifest["installed_model_digests"] if isinstance(m, dict)}
    actual = {m.get("name"): m.get("digest") for m in benchmark.ollama_inventory()}
    if TARGET not in actual or expected[TARGET] != actual[TARGET] or not actual[TARGET]:
        raise RuntimeError("PHI_MODEL_DIGEST_CHANGED_OR_MISSING")
    return actual[TARGET]


def run_one(root: Path, source: str, prompt: str, orig_manifest: dict, orig_hash: str, digest: str) -> dict:
    dest = root.with_name(root.name + "-phi-completion")
    dest.mkdir(parents=True, exist_ok=False)
    d = dest / TARGET.replace(":", "_")
    d.mkdir()
    (d / "prompt.txt").write_text(prompt, encoding="utf-8")
    (dest / "prior_report_snapshot.json").write_bytes((root / "report.json").read_bytes())
    (dest / "original_report_sha256.txt").write_text(orig_hash + "\n", encoding="ascii")
    (dest / "oracle_sha256.txt").write_text(orig_manifest["oracle_sha256"] + "\n", encoding="ascii")
    result = {"model": TARGET, "pass": False, "status": "GENERATION_ERROR", "seconds": None}
    worker = [sys.executable, str(Path(benchmark.__file__).resolve()), "--worker", "--model", TARGET,
              "--prompt", str(d / "prompt.txt"), "--output", str(d), "--seconds", str(SECONDS)]
    start = time.perf_counter()
    proc = subprocess.Popen(worker, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        timed_out = True
    result["seconds"] = round(time.perf_counter() - start, 2)
    (d / "worker_stdio.txt").write_text("STDOUT:\n" + stdout + "\nSTDERR:\n" + stderr, encoding="utf-8")
    if timed_out:
        result["status"] = "GENERATION_TIMEOUT"
    elif proc.returncode == 0:
        try:
            raw = (d / "raw_response.txt").read_text(encoding="utf-8")
            if not raw.strip():
                raise ValueError("EMPTY_VISIBLE_RESPONSE")
            data = json.loads(raw)
            if not isinstance(data, dict) or set(data) != {"code"} or not isinstance(data["code"], str):
                raise ValueError("INVALID_JSON_CONTRACT")
            merged = benchmark.validate_and_splice(source, data["code"])
            (d / "candidate_module.py").write_text(merged, encoding="utf-8", newline="\n")
            grades = benchmark.run_tests(merged, Path(benchmark.__file__).with_name("test_real_case.py"), d)
            result.update(grades)
            result["status"] = "PASS" if grades["pass"] else "FUNCTIONAL_FAIL"
        except (ValueError, SyntaxError, KeyError) as e:
            result["diagnostic"] = str(e)
            result["status"] = "EMPTY_VISIBLE_RESPONSE" if str(e) == "EMPTY_VISIBLE_RESPONSE" else "INVALID_CANDIDATE"
        except subprocess.TimeoutExpired:
            result["status"] = "TEST_TIMEOUT"
        except Exception as e:
            result["status"] = "EVALUATOR_ERROR"
            result["diagnostic"] = repr(e)
    else:
        result["diagnostic"] = f"WORKER_EXIT_{proc.returncode}"
    if (d / "generation.json").is_file():
        result["generation"] = json.loads((d / "generation.json").read_text(encoding="utf-8"))
    all_results = orig_manifest["results"] + [result]
    grades = [x for x in all_results if x.get("pass") is True]
    decision = {"status": "PROVISIONAL_SINGLE_REAL_ISSUE_LEAD" if len(grades) == 1 else "INCONCLUSIVE",
                "leader": grades[0]["model"] if len(grades) == 1 else None, "winner": None,
                "explanation": "Only one real issue; cannot establish model superiority"}
    report = {"schema": 3, "continuation_of": str(root), "original_report_sha256": orig_hash,
              "source_sha256": orig_manifest["source_sha256"], "oracle_sha256": orig_manifest["oracle_sha256"],
              "shared_protocol": orig_manifest["inference_protocol"], "common_prompt_sha256": sha256(prompt.encode("utf-8")),
              "model_digest": digest, "results": all_results, "decision": decision,
              "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "warning": "Ollama /api/ps confirms loaded models, not global idle requests; test on dedicated instance."}
    (dest / "completion_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("PHI_RESULT", json.dumps(result, ensure_ascii=False), flush=True)
    print("COMBINED_DECISION", json.dumps(decision, ensure_ascii=False), flush=True)
    print("EVIDENCE", str(dest), flush=True)
    return report


def main() -> None:
    p = argparse.ArgumentParser(description="Complete only Phi 4 Mini after Qwen7B hard timeout")
    p.add_argument("--evidence", type=Path, required=True)
    args = p.parse_args()
    manifest, source, prompt, original_hash = verify_previous(args.evidence)
    print("PREVIOUS_EVIDENCE_VERIFIED", original_hash, flush=True)
    digest = verify_model_digest(manifest)
    settle_prior()
    print("OLLAMA_NO_MODELS_LOADED", flush=True)
    run_one(args.evidence.resolve(), source, prompt, manifest, original_hash, digest)


if __name__ == "__main__":
    main()
