"""Freeze eight previously unused SWE-bench Lite/dev tasks. No model calls.
Gold/test patches are used for eligibility checks and hashed; they are NEVER
written into issue.json or model-facing manifest. Existing known instances,
source commit baselines and synthetic fixtures are excluded.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
from reconcile import HISTORIC_BASES, KNOWN, proposed_tasks, hash_bytes

DATASET = "princeton-nlp/SWE-bench_Lite"
API = "https://datasets-server.huggingface.co/rows"
SEED = "LOCAL-WINNER-01-freeze-2026-10-26-v1"
ID = re.compile(r"^[a-zA-Z0-9_./-]+__[a-zA-Z0-9_./-]+-\d+$")
PYFILE = re.compile(r"^diff --git a/([^\r\n]+) b/([^\r\n]+)$", re.MULTILINE)
SHA1 = re.compile(r"^[0-9a-f]{40}$")
MAX_BYTES = 4_000_000

def fetch():
    query = urllib.parse.urlencode({"dataset":DATASET,"config":"default","split":"dev",
                                    "offset":0,"length":100})
    req = urllib.request.Request(API + "?" + query, headers={"User-Agent":"local-winner01-freeze/1"})
    with urllib.request.urlopen(req,timeout=40) as resp:
        raw = resp.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:
        raise ValueError("DATASET_TOO_LARGE")
    return raw

def extract(raw):
    if len(raw)>MAX_BYTES:
        raise ValueError("DATASET_TOO_LARGE")
    body = json.loads(raw)
    if not isinstance(body,dict) or body.get("num_rows_total")!=23 or not isinstance(body.get("rows"),list) or len(body["rows"])!=23:
        raise ValueError("NOT_CANONICAL_LITE_DEV_SPLIT")
    rows = []
    seen = set()
    for entry in body["rows"]:
        if not isinstance(entry,dict) or not isinstance(entry.get("row"),dict):
            raise ValueError("INVALID_DATASET_ROW")
        x=entry["row"]
        ident=x.get("instance_id")
        if not isinstance(ident,str) or not ID.fullmatch(ident) or ident in seen:
            raise ValueError("INVALID_OR_DUPLICATE_INSTANCE_ID")
        seen.add(ident)
        rows.append(x)
    return rows

def one(row):
    identity=row["instance_id"]
    if identity in KNOWN["swebench-lite-dev"]:
        return None,"HISTORIC_INSTANCE"
    repo=row.get("repo")
    base=row.get("base_commit")
    if (not isinstance(repo,str) or not isinstance(base,str) or
            not SHA1.fullmatch(base)):
        return None,"INVALID_REPO_OR_COMMIT"
    if (repo.lower(),base) in HISTORIC_BASES:
        return None,"HISTORIC_COMMIT"
    problem=row.get("problem_statement")
    gold=row.get("patch")
    oracle=row.get("test_patch")
    if not all(isinstance(x,str) and x.strip() for x in (problem,gold,oracle)):
        return None,"MISSING_PROBLEM_OR_ORACLE"
    if len(problem)>32000 or len(gold)>20000 or len(oracle)>40000:
        return None,"INPUT_TOO_LONG"
    matched=PYFILE.findall(gold)
    if len(matched)!=1 or matched[0][0]!=matched[0][1]:
        return None,"NOT_SINGLE_FILE_CHANGE"
    target=matched[0][0]
    if not target.endswith(".py") or ".." in target.split("/") or target.startswith("/"):
        return None,"UNSAFE_GOLD_TARGET"
    try:
        f2p=json.loads(row.get("FAIL_TO_PASS",""))
    except (ValueError,TypeError):
        return None,"MISSING_TEST_IDS"
    if not isinstance(f2p,list) or not f2p or not all(isinstance(x,str) for x in f2p):
        return None,"MISSING_TEST_IDS"
    statement_bytes=problem.encode("utf-8")
    oracle_bytes=oracle.encode("utf-8")
    candidate={"case_id":identity,"source_repo":repo,"base_commit":base,
        "prompt_sha256":hash_bytes(statement_bytes),"oracle_sha256":hash_bytes(oracle_bytes),
        "gold_patch_sha256":hash_bytes(gold.encode("utf-8")),
        "fail_to_pass_count":len(f2p),"model_input":{"schema":1,"issue_id":identity,
                                                      "base_commit":base,"problem_statement":problem}}
    return candidate,None

def freeze(raw, first=3, final=5, max_per_repo=2):
    if first!=3 or final!=5 or max_per_repo!=2:
        raise ValueError("SELECTION_CONTRACT_CHANGED")
    all_rows=extract(raw)
    eligible,excluded=[],[]
    for row in all_rows:
        item,reason=one(row)
        if item is None:
            excluded.append({"case_id":row["instance_id"],"reason":reason})
        else:
            eligible.append(item)
    ordered=sorted(eligible,key=lambda item:(hashlib.sha256((SEED+":"+item["case_id"]).encode()).hexdigest(),item["case_id"]))
    chosen=[]
    per_repo={}
    used_bases=set()
    for item in ordered:
        key=(item["source_repo"].lower(),item["base_commit"])
        if key in used_bases:
            excluded.append({"case_id":item["case_id"],"reason":"DUPLICATE_REPO_BASE"})
            continue
        if per_repo.get(item["source_repo"],0)>=max_per_repo:
            excluded.append({"case_id":item["case_id"],"reason":"REPO_QUOTA"})
            continue
        chosen.append(item)
        used_bases.add(key)
        per_repo[item["source_repo"]]=per_repo.get(item["source_repo"],0)+1
        if len(chosen)==first+final:
            break
    if len(chosen)!=8:
        raise ValueError(f"INSUFFICIENT_ELIGIBLE_INDEPENDENT_ISSUES: {len(chosen)}")
    evidence_check=proposed_tasks(chosen)
    if any(r["status"]!="NEW_UNVERIFIED" for r in evidence_check):
        raise ValueError("HISTORICAL_COLLISION_DETECTED: " + repr(evidence_check))
    manifest={"schema":1,"phase":"LOCAL-WINNER-01-CASE-FREEZE",
        "dataset":DATASET,"split":"dev","rows_total":23,"raw_dataset_sha256":hash_bytes(raw),
        "selection_seed":SEED,"rule":"sha256(seed:instance_id) ascending, max 2 distinct base commits per repo",
        "status":"CANDIDATE_ONLY_BASELINE_AND_ORACLE_NOT_YET_QUALIFIED",
        "elimination_count":first,"final_count":final,"cases":[],"excluded":excluded,
        "no_gold_or_test_source_passed_to_model":True}
    issues={}
    for index,item in enumerate(chosen):
        stage="ELIMINATION" if index<first else "FINAL_HOLDOUT"
        public={k:v for k,v in item.items() if k!="model_input"}
        public["stage"]=stage
        manifest["cases"].append(public)
        issues[item["case_id"]]=item["model_input"]
    return manifest,issues

def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dataset-file",type=Path)
    g.add_argument("--fetch-official",action="store_true",
                  help="Explicitly fetch only SWE-bench Lite/dev public rows; never runs models")
    p.add_argument("--output-dir",type=Path,required=True)
    args=p.parse_args()
    root=args.output_dir.resolve()
    if root.exists():
        p.error("output-dir already exists (no overwrite)")
    raw=fetch() if args.fetch_official else args.dataset_file.read_bytes()
    manifest,issues=freeze(raw)
    root.mkdir(parents=True)
    for name,issue in issues.items():
        folder=root / name
        folder.mkdir()
        (folder/"issue.json").write_text(json.dumps(issue,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (root/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":manifest["status"],"dataset_sha256":manifest["raw_dataset_sha256"],
                      "cases":[{"id":x["case_id"],"stage":x["stage"],"repo":x["source_repo"]}
                               for x in manifest["cases"]],
                      "out":str(root),"inference_calls":0},ensure_ascii=False))

if __name__=="__main__":
    main()
