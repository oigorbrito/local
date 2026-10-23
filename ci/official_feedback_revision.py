"""One controlled revision from official failed-test names, no gold patch.
New candidate starts at base_commit, not previously mutated tree.
"""
import argparse,hashlib,json,pathlib,re,tempfile
from swebench_real import CASES,data,infer,cmd,select_target,excerpt

def parse_action(raw):
    payload=raw.strip()
    fence=chr(96)*3
    if payload.startswith(fence):
        payload="\n".join(payload.splitlines()[1:-1]).strip()
    obj,end=json.JSONDecoder().raw_decode(payload)
    if payload[end:].strip() or not isinstance(obj,dict) or set(obj)!={"old","new"}:
        raise ValueError("expected one JSON object containing exactly old,new")
    if not all(isinstance(obj[k],str) for k in ("old","new")):
        raise ValueError("old/new must be strings")
    if not obj["old"] or obj["old"]==obj["new"]:
        raise ValueError("no-op edit")
    return obj

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--model",required=True)
    p.add_argument("--report",required=True)
    p.add_argument("--patches",required=True)
    p.add_argument("--out",default="results")
    args=p.parse_args()
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    gate=json.loads(pathlib.Path(args.report).read_text(encoding="utf-8"))
    failures={x["instance_id"]:x for x in gate["cases"]}
    instances=data()
    scores=[]
    for iid,filename in CASES.items():
        response="";error="";seconds=None;valid=False
        prior=pathlib.Path(args.patches)/(iid+".patch")
        original_patch=prior.read_text(encoding="utf-8") if prior.exists() else ""
        try:
            if not original_patch:raise ValueError("missing initial patch: fail closed")
            report=failures[iid]
            if report["resolved"]:raise ValueError("already resolved, not eligible")
            if not report["failing_target_tests"]:raise ValueError("no target failures")
            inst=instances[iid]
            with tempfile.TemporaryDirectory() as directory:
                root=pathlib.Path(directory)/"repo"
                cmd(["git","clone","--quiet","https://github.com/"+inst["repo"]+".git",str(root)],timeout=240)
                cmd(["git","checkout","--quiet",inst["base_commit"]],cwd=root)
                target=select_target(root,filename,inst["repo"])
                relative=str(target.relative_to(root))
                source=target.read_text(encoding="utf-8")
                context=excerpt(source,inst["problem_statement"],limit=12500)
                prompt=("Revise a failed code patch for the ORIGINAL checked-out Python source. "
                        "The prior patch did not resolve the issue. You are shown only test names "
                        "and failures, NOT their expected solutions. Respond with exactly ONE JSON "
                        "object with string keys old,new, containing a unique exact replacement "
                        "against ORIGINAL source. No markdown. Do not modify tests.\nIssue:\n"+
                        inst["problem_statement"]+"\nSource path: "+relative+
                        "\nRelevant source:\n"+context+
                        "\nFailed previous patch (DO NOT assume already applied):\n"+
                        original_patch[-6500:]+
                        "\nOfficial failing target tests:\n"+
                        "\n".join(map(str,report["failing_target_tests"]))[-3000:]+
                        "\nOfficial regressions:\n"+
                        "\n".join(map(str,report["regression_test_names"]))[-2000:])
                response,seconds=infer(args.model,prompt)
                edit=parse_action(response)
                if source.count(edit["old"])!=1:raise ValueError("replacement is not unique in original source")
                target.write_text(source.replace(edit["old"],edit["new"],1),encoding="utf-8")
                cmd(["python3","-m","py_compile",str(target)],cwd=root)
                patch=cmd(["git","diff","--",relative],cwd=root)
                if not patch.strip():raise ValueError("no patch")
                (out/(iid+".patch")).write_text(patch,encoding="utf-8")
                valid=True
        except Exception as exc:error=repr(exc)
        raw=response.encode("utf-8")
        (out/(iid+".response.txt")).write_bytes(raw)
        scores.append({"instance_id":iid,"valid_patch":valid,"inference_seconds":seconds,
                       "response_sha256":hashlib.sha256(raw).hexdigest(),
                       "error":error,"functional_resolved":None})
        print(iid,"PATCH" if valid else "NO_PATCH",error,flush=True)
    (out/"score.json").write_text(json.dumps({"model":args.model,"suite":"official-feedback-revision-v1",
       "valid_patches":sum(x["valid_patch"] for x in scores),
       "functional_resolved":None,"cases":scores},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":
    main()
