"""LOCAL-WINNER-01: offline reconciliation. No Ollama, Docker or candidate execution.
Reads only bounded JSON evidence. Reports cohorts separately. Never overwrites evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

NAMES = ("report.json", "rejudge-report.json", "completion_report.json", "score.json")
PATTERN = re.compile(r"^(local-(?:model-pilot|real-code|nemotron|bench)|local-bench)", re.I)
KNOWN = {
    "python-v1": ("deduplicate", "balanced", "intervals", "parse_log"),
    "python-v3": ("pagination", "money", "config", "cache"),
    "breadth-01": ("dedupe", "brackets", "intervals", "pagination", "logparse", "lru"),
    "swebench-lite-dev": ("marshmallow-code__marshmallow-1343", "marshmallow-code__marshmallow-1359", "pvlib__pvlib-python-1072"),
    "home-model-01": ("header_normalization", "invoice_cents", "calendar_merge", "config_parser", "inventory_transactions"),
    "local-27": ("guard.py:read_text_under_root:symlink-escape",),
    "local-real-02": ("oigorbrito/local:retrieve_context.py:ancestor-tests-examples", "oigorbrito/local:experiments/local07/retrieve_context.py:ancestor-tests-examples"),
    "local-12": ("calculator.py:calculate_total:sum-plus-one",),
}
# These fingerprints derive from archived, versioned HOME-MODEL-01 and LOCAL-REAL-02
# prompts/oracles. They prevent reusing a task under a different display name.
FINGERPRINTS = {
    "prompt_sha256": {
        "7921185b78b8ab2fb3b955d2fe8637fc66019d8de8e1ebc70b572edc92e82e15": "header_normalization",
        "423035a5b738bc5f24c11337301fb7b9abf28b308353acdc3af1113c76c6debf": "invoice_cents",
        "959f38abbf30f73bae386bbca13b3c87a0269fb4a03d1f139b9a038114a0581a": "calendar_merge",
        "90d155cb5c8a1617c10abbff1af6c530f930b6196f7a6db0f2ec083f1078e399": "config_parser",
        "e5c836c37bd2c1fb115b9080a77f0829cb20b5d62af8b33d6d8de5883ad75569": "inventory_transactions",
        "15e1169600821fbefb2d3e95107ff68a3d8ca16f7cc462950c17404a953186a3": "local-real-02",
    },
    "oracle_sha256": {
        "07e8d760a2670448389846309251e10521653b40a74db2b520c1facf596064f2": "header_normalization",
        "80bf8a65a56dc70ecbfc23c48eeb763e2f2fdb7726b4314554ba2744c7ebe1a0": "invoice_cents",
        "8b3a5e12dd5f8645168b91dabb043583b896fed9365f519410d1d38ee489b873": "calendar_merge",
        "ef07aa682ca2b3d9b7fb46161567ebe276999defd1a1fcc08951ca4c3d61ef5f": "config_parser",
        "8ec6d98bf0920a1164f189c15e9bd6b6a82c5ed417b645be8f7a4cfdb1d13ddc": "inventory_transactions",
        "80be32285f14bdadc5e87aaa8803d76bd0ef77e21e486e2f2fcac8bddfbf1611": "local-real-02",
    }
}

def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()

def safe_json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 3000000:
        raise ValueError("UNSAFE_REPORT_FILE")
    raw = path.read_bytes()
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("REPORT_MUST_BE_OBJECT")
    return obj, hash_bytes(raw)

def report_type(doc, filename):
    if filename == "rejudge-report.json" and doc.get("kind") == "OFFLINE_REJUDGE_ARCHIVED_RESPONSES":
        return "HOME_REJUDGE_V2"
    if filename == "completion_report.json" and doc.get("schema") == 3:
        return "REAL_PHI_COMPLETION"
    if doc.get("phase") == "RECOVERY02":
        return "REAL_RECOVERY02"
    if doc.get("mode") == "DIRECT_OLLAMA_SINGLE_SHOT_LOCAL_PILOT":
        return "HOME_ORIGINAL"
    if doc.get("schema") == 2 and doc.get("source_path") and isinstance(doc.get("results"), list):
        return "REAL_ORIGINAL"
    if doc.get("suite") and isinstance(doc.get("tasks"), list):
        return "CPU_SCREEN"
    return "UNKNOWN_FORMAT"

def rows(doc, flavor):
    if flavor == "HOME_ORIGINAL":
        source = doc.get("requests", [])
        return [{"case_id": r.get("task"), "model": r.get("model"),
                 "status": r.get("status"), "pass": r.get("solved"),
                 "seconds": r.get("wall_seconds")} for r in source if isinstance(r,dict)]
    if flavor == "HOME_REJUDGE_V2":
        source = doc.get("rejudged_rows", [])
        return [{"case_id": r.get("task"), "model": r.get("model"),
                 "status": r.get("new_status"), "pass": r.get("solved"),
                 "seconds": r.get("wall_seconds_original")} for r in source if isinstance(r,dict)]
    if flavor in ("REAL_ORIGINAL", "REAL_PHI_COMPLETION", "REAL_RECOVERY02"):
        source = doc.get("repairs", []) if flavor == "REAL_RECOVERY02" else doc.get("results", [])
        return [{"case_id": "local-real-02", "model": r.get("model"),
                 "status": r.get("status"), "pass": r.get("pass"),
                 "seconds": r.get("seconds")} for r in source if isinstance(r,dict)]
    if flavor == "CPU_SCREEN":
        return [{"case_id": r.get("task"), "model": doc.get("model"),
                 "status": "PASS" if r.get("pass") else "FAIL", "pass": r.get("pass"),
                 "seconds": r.get("seconds")} for r in doc.get("tasks", []) if isinstance(r,dict)]
    return []

def find_reports(roots, explicit):
    found = set()
    for path in explicit:
        if path.is_file() and path.name in NAMES:
            found.add(path)
        elif path.is_dir() and not path.is_symlink():
            found.update(q for name in NAMES if (q := path / name).is_file())
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            continue
        groups = [root] if PATTERN.match(root.name) else [x for x in root.iterdir()
                    if x.is_dir() and not x.is_symlink() and PATTERN.match(x.name)]
        for group in groups[:500]:
            descendants = [group]
            if (group / group.name).is_dir():
                descendants.append(group / group.name)
            for directory in descendants:
                for sub in (directory, directory / "runs",
                            directory / "runs" / "pilot01", directory / "runs" / "pilot02"):
                    if not sub.is_dir() or sub.is_symlink():
                        continue
                    for name in NAMES:
                        target = sub / name
                        if target.is_file() and not target.is_symlink():
                            found.add(target)
                    if sub.name in ("pilot01", "pilot02"):
                        for item in list(sub.iterdir())[:500]:
                            if item.is_dir() and not item.is_symlink():
                                for name in NAMES:
                                    p = item / name
                                    if p.is_file() and not p.is_symlink():
                                        found.add(p)
    return sorted(found, key=lambda x: str(x).lower())[:1000]

def integrity(reports):
    index = {r["path"]: r for r in reports}
    links = []
    for record in reports:
        obj = record["_doc"]
        kind = record["kind"]
        expected = []
        if kind == "HOME_REJUDGE_V2":
            expected.append((str(Path(obj.get("original_results","")) / "report.json"),
                             obj.get("original_report_sha256"),"HOME_ORIGINAL"))
        elif kind == "REAL_PHI_COMPLETION":
            expected.append((str(Path(obj.get("continuation_of","")) / "report.json"),
                             obj.get("original_report_sha256"),"REAL_ORIGINAL"))
        elif kind == "REAL_RECOVERY02":
            directory = str(Path(record["path"]).parent)
            if directory.endswith("-recovery02"):
                base = directory[:-len("-recovery02")]
                expected.extend([(str(Path(base) / "report.json"), obj.get("base_report_sha256"), "REAL_ORIGINAL"),
                                 (str(Path(base + "-phi-completion") / "completion_report.json"),
                                  obj.get("completion_report_sha256"),"REAL_PHI_COMPLETION")])
        for target, h, target_type in expected:
            linked = index.get(target)
            status = ("MISSING_LOCAL_EVIDENCE" if linked is None else
                      "VERIFIED" if linked["sha256"] == h and linked["kind"] == target_type else
                      "MISMATCH")
            links.append({"from": record["path"], "to": target, "status": status,
                          "expected_sha256": h, "actual_sha256": linked["sha256"] if linked else None})
    return links

HISTORIC_BASES = {
    ("marshmallow-code/marshmallow", "2be2d83a1a9a6d3d9b85804f3ab545cecc409bb0"): "marshmallow-code__marshmallow-1343",
    ("marshmallow-code/marshmallow", "b40a0f4e33823e6d0f341f7e8684e359a99060d1"): "marshmallow-code__marshmallow-1359",
    ("pvlib/pvlib-python", "04a523fafbd61bc2e49420963b84ed8e2bd1b3cf"): "pvlib__pvlib-python-1072",
}
VALID_SHA256 = re.compile(r"^[0-9a-f]{64}$")
VALID_SHA1 = re.compile(r"^[0-9a-f]{40}$")
VALID_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

def proposed_tasks(items):
    old = {x.lower(): family for family,names in KNOWN.items() for x in names}
    old.update({"brackets": "python-v1", "dedupe": "python-v1", "logparse": "python-v1"})
    if not isinstance(items, list) or len(items) > 100:
        raise ValueError("INVALID_PROPOSED_TASKS_LIST")
    seen = set()
    seen_bases = set()
    seen_prompts = set()
    seen_oracles = set()
    output = []
    for row in items:
        needed = ("case_id","source_repo","base_commit","prompt_sha256","oracle_sha256")
        if not isinstance(row,dict) or any(not isinstance(row.get(k),str) or not row[k].strip() for k in needed):
            raise ValueError("INCOMPLETE_CASE_IDENTITY")
        if (not VALID_REPO.fullmatch(row["source_repo"]) or
                not VALID_SHA1.fullmatch(row["base_commit"]) or
                not VALID_SHA256.fullmatch(row["prompt_sha256"]) or
                not VALID_SHA256.fullmatch(row["oracle_sha256"])):
            raise ValueError("INVALID_CASE_IDENTITY_FORMAT")
        if len(row["case_id"]) > 160:
            raise ValueError("CASE_ID_TOO_LONG")
        name = row["case_id"].lower()
        base_key = (row["source_repo"].lower(), row["base_commit"])
        status = "EXISTING_HISTORICAL_TASK" if name in old else "NEW_UNVERIFIED"
        match = old.get(name)
        if status == "NEW_UNVERIFIED" and base_key in HISTORIC_BASES:
            status, match = "EXISTING_HISTORICAL_BASE", HISTORIC_BASES[base_key]
        for key in ("prompt_sha256", "oracle_sha256"):
            if status == "NEW_UNVERIFIED" and row[key] in FINGERPRINTS[key]:
                status, match = "SAME_" + key.upper(), FINGERPRINTS[key][row[key]]
        if status == "NEW_UNVERIFIED":
            if name in seen:
                status = "DUPLICATE_IN_PROPOSED_SET"
            elif base_key in seen_bases:
                status = "DUPLICATE_BASE_IN_PROPOSED_SET"
            elif row["prompt_sha256"] in seen_prompts:
                status = "DUPLICATE_PROMPT_IN_PROPOSED_SET"
            elif row["oracle_sha256"] in seen_oracles:
                status = "DUPLICATE_ORACLE_IN_PROPOSED_SET"
        seen.add(name)
        seen_bases.add(base_key)
        seen_prompts.add(row["prompt_sha256"])
        seen_oracles.add(row["oracle_sha256"])
        output.append({"case_id":row["case_id"],"status":status,"historical_match":match})
    return output

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,action="append",default=[])
    p.add_argument("--evidence",type=Path,action="append",default=[])
    p.add_argument("--tasks",type=Path)
    p.add_argument("--output",type=Path,required=True)
    args = p.parse_args()
    roots = args.root or [Path.home(), Path.home() / "Downloads" / "local-bench-04", Path("D:/projetos")]
    paths = find_reports(roots,args.evidence)
    reports = []
    issues = []
    for file in paths:
        try:
            obj,hashed = safe_json(file)
            k = report_type(obj,file.name)
            reports.append({"path":str(file),"sha256":hashed,"kind":k,
                            "rows":rows(obj,k), "_doc":obj})
            if k == "UNKNOWN_FORMAT":
                issues.append({"path":str(file),"reason":"SCHEMA_UNRECOGNIZED"})
        except (ValueError, OSError, TypeError) as exc:
            issues.append({"path":str(file),"reason":type(exc).__name__})
    links = integrity(reports)
    proposed = proposed_tasks(json.loads(args.tasks.read_text(encoding="utf-8"))) if args.tasks else []
    valid_rejudge = {x["from"] for x in links if x["status"] == "VERIFIED"}
    original = [r for r in reports if r["kind"] == "HOME_ORIGINAL"]
    revised = [r for r in reports if r["kind"] == "HOME_REJUDGE_V2" and r["path"] in valid_rejudge]
    chosen = revised[-1] if revised else original[-1] if original else None
    selected = ({"cohort":"HOME-MODEL-01", "selected_report":chosen["path"],
                 "source":"VERIFIED_REJUDGE_V2" if chosen in revised else "ORIGINAL_UNREJUDGED",
                 "rows":chosen["rows"]} if chosen else None)
    real = [r for r in reports if r["kind"] == "REAL_ORIGINAL"]
    phi = [r for r in reports if r["kind"] == "REAL_PHI_COMPLETION" and r["path"] in valid_rejudge]
    last = phi[-1] if phi else real[-1] if real else None
    if last:
        selected_real = {"cohort":"LOCAL-REAL-02", "selected_first_stage":last["path"],
                         "rows":last["rows"],"distinct_issues":1,
                         "repairs_are_the_same_issue":True}
    else:
        selected_real = None
    mismatch = any(x["status"] == "MISMATCH" for x in links)
    missing_link = any(x["status"] == "MISSING_LOCAL_EVIDENCE" for x in links)
    duplicate = any(x["status"] != "NEW_UNVERIFIED" for x in proposed)
    recovery_reports = [r for r in reports if r["kind"] == "REAL_RECOVERY02"]
    recovery_fully_verified = any(
        sum(x["status"] == "VERIFIED" for x in links if x["from"] == r["path"]) == 2
        for r in recovery_reports)
    complete = bool(revised and phi and recovery_fully_verified)
    if mismatch:
        gate = "BLOCKED_HASH_MISMATCH"
    elif missing_link:
        gate = "BLOCKED_MISSING_LINKED_REPORT"
    elif duplicate:
        gate = "BLOCKED_DUPLICATE_TASK"
    elif not reports:
        gate = "BLOCKED_NO_REPORTS_FOUND"
    elif issues:
        gate = "BLOCKED_UNRECOGNIZED_REPORTS"
    elif not complete:
        gate = "BLOCKED_INCOMPLETE_HISTORY"
    elif proposed:
        gate = "READY_FOR_REVIEW"
    else:
        gate = "INVENTORY_COMPLETE_NO_TASKS"
    public = [{k:v for k,v in r.items() if k != "_doc"} for r in reports]
    outcome = {"schema":1, "phase":"LOCAL-WINNER-01", "inference_calls":0,
               "docker_calls":0, "reports":public,"correlations":links,
               "selected_home":selected,"selected_real":selected_real,
               "historical_case_groups":KNOWN,"candidate_cases":proposed,
               "unrecognized":issues,"history_complete":complete,"gate":gate,
               "note":"Old V1/V2/V3 and SWE-bench performance remains documented historical evidence, not rescored. Cohorts are never pooled."}
    if args.output.exists():
        p.error("output already exists: " + str(args.output))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(outcome,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("LOCAL_WINNER_01",json.dumps({"reports":len(public),"integrity":links,
          "selected_home":selected["source"] if selected else "NOT_FOUND",
          "gate":gate,"inference_calls":0,"output":str(args.output)},ensure_ascii=False))
    return 2 if gate.startswith("BLOCKED") else 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:
        print("RECONCILIATION_BLOCKED",type(exc).__name__,str(exc)[:200],file=sys.stderr)
        sys.exit(2)
