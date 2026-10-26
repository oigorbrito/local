"""LOCAL-WINNER-04: deterministic local inference capture, NOT a functional evaluator.

Requires qualified oracle reports for all eight cases. Fetches only Ollama
loopback /api/tags and /api/generate. Never executes or applies model patches.
Inputs are checked-out source snapshots supplied by the operator, not gold.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request
from winner04_preflight import CASES, oracle_valid

def sha(data):
    return hashlib.sha256(data).hexdigest()

def request(url, payload=None, timeout=60):
    raw = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=raw, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)

def must_qualified(root):
    for case in CASES:
        obj = json.loads((root / (case+".json")).read_text(encoding="utf-8"))
        if not oracle_valid(obj, case):
            raise RuntimeError("ORACLE_NOT_QUALIFIED:"+case)

def prompt_for(issue, snapshot, max_files=60, max_bytes=24000):
    if issue.get("issue_id") not in CASES:
        raise ValueError("NOT_FROZEN_CASE")
    files = []
    used = 0
    # Read only a bounded set of tracked Python sources; never copy .git, tests, gold.
    for path in sorted(snapshot.rglob("*.py")):
        relative = path.relative_to(snapshot)
        if any(x in {"tests","test",".git","__pycache__"} for x in relative.parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        data = path.read_bytes()
        if len(data) > 6000 or used+len(data) > max_bytes:
            continue
        used += len(data)
        files.append((str(relative).replace("\\","/"),data.decode("utf-8",errors="replace")))
        if len(files)>=max_files:
            break
    if not files:
        raise RuntimeError("NO_SOURCE_CONTEXT")
    text = ("Fix this issue in the provided source snapshot. Reply ONLY with "
            "a unified git diff, using paths relative to the repository root. "
            "Do not invent tests or claim success.\nIssue:\n"
            +issue["problem_statement"]+"\nSource files:\n")
    for name,body in files:
        text+="\n### "+name+"\n"+body+"\n"
    return text, [f[0] for f in files]

def run(args):
    if args.phase != "elimination":
        raise RuntimeError("HOLDOUT_LOCKED_UNTIL_FINALISTS_FIXED")
    if args.endpoint not in ("http://127.0.0.1:11434","http://localhost:11434"):
        raise RuntimeError("OLLAMA_LOOPBACK_ONLY")
    if args.output.exists():
        raise RuntimeError("OUTPUT_EXISTS")
    must_qualified(args.oracles)
    tags=request(args.endpoint+"/api/tags")
    present={m.get("name"):m.get("digest") for m in tags.get("models",[]) if isinstance(m,dict)}
    selected=json.loads(args.models.read_text(encoding="utf-8"))
    if set(selected)!= {"nemotron","lfm2.5","qwen3.5","ministral"}:
        raise RuntimeError("FOUR_FAMILIES_REQUIRED")
    if len(set(selected.values()))!=4 or any(name not in present or not present[name] for name in selected.values()):
        raise RuntimeError("MISSING_OR_DUPLICATED_LOCAL_MODEL")
    # Explicitly require a human-authored model map; no guessing which tag or quantization.
    manifest=json.loads(args.manifest.read_text(encoding="utf-8"))
    cases=manifest.get("cases",[])
    if [x["case_id"] for x in cases] != list(CASES) or [x.get("stage") for x in cases] != ["ELIMINATION"]*3+["FINAL_HOLDOUT"]*5:
        raise RuntimeError("FROZEN_MANIFEST_MISMATCH")
    args.output.mkdir(parents=True)
    ledger=[]
    for idx,case in enumerate(CASES[:3]):
        issue=json.loads((args.issues/case/"issue.json").read_text(encoding="utf-8"))
        if issue.get("base_commit") != cases[idx].get("base_commit"):
            raise RuntimeError("ISSUE_BASE_DRIFT")
        snapshot=args.snapshots/case
        prompt,sources=prompt_for(issue,snapshot)
        if sha(issue["problem_statement"].encode("utf-8")) != cases[idx]["prompt_sha256"]:
            raise RuntimeError("ISSUE_PROMPT_DRIFT")
        order=list(selected)
        if idx%2: order.reverse()
        for family in order:
            model=selected[family]
            started=time.monotonic()
            result={"case_id":case,"family":family,"model":model,"digest":present[model],
                    "phase":"ELIMINATION","prompt_sha256":sha(prompt.encode()),
                    "source_files":sources,"temperature":0,"num_predict":args.num_predict,
                    "num_ctx":args.num_ctx,"status":"INFERENCE_FAILED"}
            try:
                response=request(args.endpoint+"/api/generate",
                    {"model":model,"prompt":prompt,"stream":False,
                     "options":{"temperature":0,"num_predict":args.num_predict,"num_ctx":args.num_ctx}},
                    timeout=args.timeout)
                patch=response.get("response","")
                if isinstance(patch,str) and patch.strip():
                    patch_path=args.output/(str(idx)+"-"+family+".patch")
                    patch_path.write_text(patch,encoding="utf-8")
                    result.update({"status":"PATCH_CAPTURED_NOT_EVALUATED",
                                   "patch_sha256":sha(patch.encode()),
                                   "output_tokens":response.get("eval_count"),
                                   "input_tokens":response.get("prompt_eval_count"),
                                   "ollama_total_duration_ns":response.get("total_duration"),
                                   "patch_file":patch_path.name})
                else:
                    result["status"]="EMPTY_OUTPUT"
            except (OSError,ValueError,TimeoutError) as exc:
                result["error_class"]=type(exc).__name__
            result["elapsed_seconds"]=round(time.monotonic()-started,3)
            ledger.append(result)
            (args.output/"ledger.json").write_text(json.dumps({"schema":1,"status":"UNSCORED",
                "results":ledger,"warning":"Patches were not evaluated; never count as resolved."},
                indent=2)+"\n",encoding="utf-8")
    return len(ledger)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--phase",default="elimination")
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--issues",type=Path,required=True)
    p.add_argument("--snapshots",type=Path,required=True)
    p.add_argument("--oracles",type=Path,required=True)
    p.add_argument("--models",type=Path,required=True,help="JSON family to exact Ollama tag")
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--endpoint",default="http://127.0.0.1:11434")
    p.add_argument("--num-ctx",type=int,default=8192)
    p.add_argument("--num-predict",type=int,default=2048)
    p.add_argument("--timeout",type=int,default=600)
    args=p.parse_args()
    if not 512 <= args.num_ctx <= 32768 or not 128 <= args.num_predict <= 8192 or args.timeout < 60:
        p.error("INVALID_RESOURCE_BUDGET")
    try:
        n=run(args)
    except (OSError,ValueError,RuntimeError,KeyError) as exc:
        p.exit(2,"BLOCKED: "+str(exc)+"\n")
    print(json.dumps({"status":"GENERATIONS_CAPTURED_NOT_SCORED","trials":n,"output":str(args.output)}))

if __name__=="__main__":
    main()
