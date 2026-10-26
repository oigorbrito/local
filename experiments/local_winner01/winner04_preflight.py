"""LOCAL-WINNER-04 preflight: fail-closed, no LLM calls or code execution.

Example:
 python experiments/local_winner01/winner04_preflight.py --oracle-dir evidence/oracles --output winner04-preflight.json
The oracle directory must contain one independently produced official WINNER-03
report per frozen issue, named <case_id>.json.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

CASES = (
    "pvlib__pvlib-python-1854", "sqlfluff__sqlfluff-2419",
    "pyvista__pyvista-4315", "sqlfluff__sqlfluff-1625",
    "pydicom__pydicom-1256", "pylint-dev__astroid-1196",
    "pvlib__pvlib-python-1707", "pydicom__pydicom-901",
)
FAMILIES = ("nemotron", "lfm2.5", "qwen3.5", "ministral")
EXPECTED_COUNTS = (3, 5)


def oracle_valid(obj, case):
    if not isinstance(obj, dict) or obj.get("case_id") != case:
        return False
    if obj.get("status") != "FUNCTIONAL_ORACLE_QUALIFIED":
        return False
    b, g = obj.get("baseline"), obj.get("gold")
    if not isinstance(b, dict) or not isinstance(g, dict):
        return False
    if b.get("status") != "GRADED" or b.get("f2p_failed", 0) < 1:
        return False
    if g.get("status") != "GRADED" or g.get("resolved") is not True:
        return False
    expected = obj.get("f2p_expected")
    return (isinstance(expected, int) and expected > 0
            and g.get("f2p_passed") == expected and g.get("f2p_failed") == 0
            and g.get("p2p_failed") == 0
            and b.get("tests_parsed") is True
            and g.get("tests_parsed") is True
            and b.get("environment_failure") is False
            and g.get("environment_failure") is False)


def check_models(endpoint):
    if not endpoint.startswith("http://127.0.0.1:") and not endpoint.startswith("http://localhost:"):
        raise ValueError("OLLAMA_ENDPOINT_MUST_BE_LOOPBACK")
    try:
        with urllib.request.urlopen(endpoint + "/api/tags", timeout=5) as r:
            models = json.load(r).get("models", [])
    except (OSError, ValueError, KeyError):
        return {"status": "OLLAMA_UNREACHABLE", "models": []}
    rows = [{"name": x.get("name"), "digest": x.get("digest"),
             "size": x.get("size")} for x in models if isinstance(x, dict)]
    return {"status": "MODELS_DISCOVERED", "models": rows,
            "note": "Tags/digests must be explicitly mapped to four candidates; discovery is not a benchmark."}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--oracle-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--ollama", default="http://127.0.0.1:11434")
    args = p.parse_args()
    if args.output.exists():
        p.error("OUTPUT_EXISTS")
    results = []
    for case in CASES:
        file = args.oracle_dir / (case + ".json")
        if not file.is_file():
            results.append({"case_id": case, "status": "ORACLE_MISSING"})
            continue
        raw = file.read_bytes()
        try:
            obj = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            obj = None
        results.append({"case_id": case,
                        "status": "QUALIFIED" if oracle_valid(obj, case) else "ORACLE_NOT_QUALIFIED",
                        "report_sha256": hashlib.sha256(raw).hexdigest()})
    all_pass = all(r["status"] == "QUALIFIED" for r in results)
    models = check_models(args.ollama)
    report = {"schema": 1, "experiment": "LOCAL-WINNER-04",
              "status": "READY_FOR_LOCAL_GENERATION_PREPARATION" if all_pass else "BLOCKED_FUNCTIONAL_ORACLES",
              "cases": results, "ollama": models, "inference_calls": 0,
              "candidate_count": 4, "elimination_count": EXPECTED_COUNTS[0],
              "final_count": EXPECTED_COUNTS[1],
              "note": "Discovery only; no model scored, no inference called. Oracle reports must be independently validated."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "qualified": sum(r["status"] == "QUALIFIED" for r in results),
                      "total": len(results), "inference_calls": 0}))
    return 0 if all_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
