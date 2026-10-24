"""LOCAL-11: single explicit Windows Ollama integration smoke, NOT a benchmark.

Creates an isolated throwaway Git repository; calls the pinned local Ollama model
once through the existing LOCAL-09 adapter. Never runs generated code.
Records transport/contract/patch status separately and preserves failure evidence.
"""
import argparse
import hashlib
import json
import pathlib
import platform
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
SOURCE = "def calculate_total(items):\n    return sum(items)\n"
ISSUE = "In calculator.py, change calculate_total(items) so it returns sum(items) + 1. Modify only calculator.py. Return full Python source."


def run_git(root, *args):
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=20)
    if proc.returncode:
        raise RuntimeError("GIT_" + args[0].upper() + "_FAILED: " + proc.stderr[:200])
    return proc.stdout.strip()


def smoke(output_dir, model="nemotron-3-nano:4b", timeout=180):
    if model != "nemotron-3-nano:4b":
        raise ValueError("LOCAL11_PINNED_MODEL_ONLY")
    output_dir = pathlib.Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {"schema": 1, "gate": "LOCAL-11", "status": "STARTED",
              "model": model, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "host_os": platform.system(), "transport": "NOT_RUN",
              "response_contract": "NOT_RUN", "patch_validation": "NOT_RUN",
              "official_resolution": "NOT_EVALUATED", "inference_calls_attempted": 0}
    report_file = output_dir / "local11-report.json"
    try:
        with tempfile.TemporaryDirectory(prefix="local11-git-") as location:
            root = pathlib.Path(location)
            run_git(root, "init", "-q")
            run_git(root, "config", "user.email", "local11@example.invalid")
            run_git(root, "config", "user.name", "LOCAL-11")
            (root / "calculator.py").write_text(SOURCE, encoding="utf-8", newline="\n")
            run_git(root, "add", "calculator.py")
            run_git(root, "commit", "-qm", "LOCAL-11 disposable fixture")
            origin_sha = hashlib.sha256((root / "calculator.py").read_bytes()).hexdigest()
            issue_path = root / "issue.json"
            issue_path.write_text(json.dumps({"problem_statement": ISSUE}), encoding="utf-8")
            report["fixture_commit"] = run_git(root, "rev-parse", "HEAD")
            report["fixture_source_sha256"] = origin_sha
            command = [sys.executable, str(HERE / "ollama_adapter.py"),
                       "--repo", str(root), "--issue-json", str(issue_path),
                       "--model", model, "--timeout", str(timeout),
                       "--report", str(output_dir / "adapter-report.json"),
                       "--patch", str(output_dir / "candidate.patch")]
            report["inference_calls_attempted"] = 1
            start = time.perf_counter()
            try:
                proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout+30)
                report["elapsed_seconds"] = round(time.perf_counter()-start, 3)
                report["adapter_exit_code"] = proc.returncode
                if proc.returncode == 0:
                    report.update(status="PATCH_APPLICABLE_NOT_GRADED",
                                  transport="PASS",response_contract="PASS",patch_validation="PASS")
                    patch_bytes=(output_dir/"candidate.patch").read_bytes()
                    report["patch_sha256"] = hashlib.sha256(patch_bytes).hexdigest()
                    report["patch_bytes"] = len(patch_bytes)
                else:
                    report["status"]="ADAPTER_FAILED"
                    # Diagnostic class is evidence-limited: do not claim model failure.
                    report["stderr_tail"]=proc.stderr[-1800:]
            except subprocess.TimeoutExpired:
                report["elapsed_seconds"]=round(time.perf_counter()-start, 3)
                report["status"]="ADAPTER_TIMEOUT"
            if hashlib.sha256((root / "calculator.py").read_bytes()).hexdigest()!=origin_sha:
                report["status"]="SOURCE_INTEGRITY_FAILURE"
            report["source_unchanged"]=run_git(root, "status", "--porcelain") == "?? issue.json"
            if not report["source_unchanged"]:
                report["status"]="SOURCE_INTEGRITY_FAILURE"
    except Exception as exc:
        report["status"]="INFRA_ERROR"
        report["error"]=f"{type(exc).__name__}: {str(exc)[:500]}"
    finally:
        report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model",default="nemotron-3-nano:4b")
    parser.add_argument("--timeout", type=int, default=180)
    args=parser.parse_args()
    if not 1 <= args.timeout <= 420:
        parser.error("timeout must be 1..420")
    result=smoke(args.output_dir,args.model,args.timeout)
    print(json.dumps({"status":result["status"], "report":str(pathlib.Path(args.output_dir)/"local11-report.json")}))
    return 0 if result["status"]=="PATCH_APPLICABLE_NOT_GRADED" else 1

if __name__=="__main__":
    raise SystemExit(main())
