"""Tool-assisted issue patch generation, separate from official functional grading."""
import argparse,json,pathlib,tempfile,subprocess,hashlib,re
from swebench_real import CASES,data,infer,cmd,select_target

def call_tool(action, root, target):
    name=action.get("tool")
    if name=="read":
        start=action.get("start",1)
        if type(start)!=int or start<1 or start>100000: raise ValueError("invalid start")
        text=target.read_text(encoding="utf-8").splitlines()
        return "\n".join(str(i+1)+": "+text[i] for i in range(start-1,min(start+119,len(text))))[:13000]
    if name=="search":
        term=action.get("term")
        if not isinstance(term,str) or not 2<=len(term)<=100: raise ValueError("invalid search")
        text=target.read_text(encoding="utf-8").splitlines()
        result=[str(i+1)+": "+line[:220] for i,line in enumerate(text) if term.lower() in line.lower()]
        return "\n".join(result[:35]) or "No match"
    if name=="edit":
        old,new=action.get("old"),action.get("new")
        if not isinstance(old,str) or not isinstance(new,str) or not old or old==new: raise ValueError("invalid edit")
        text=target.read_text(encoding="utf-8")
        if text.count(old)!=1:raise ValueError("edit span must match exactly once")
        target.write_text(text.replace(old,new,1),encoding="utf-8")
        test=subprocess.run(["python3","-m","py_compile",str(target)],cwd=root,capture_output=True,text=True,timeout=30)
        if test.returncode:target.write_text(text,encoding="utf-8");raise ValueError("syntax invalid: "+test.stderr[-1200:])
        return "EDIT_APPLIED and PY_COMPILE_PASS"
    if name=="test":
        check=subprocess.run(["python3","-m","py_compile",str(target)],cwd=root,capture_output=True,text=True,timeout=30)
        return "PY_COMPILE_PASS" if check.returncode==0 else "PY_COMPILE_FAIL: "+check.stderr[-1000:]
    if name=="finish":return "FINISHED"
    raise ValueError("unsupported tool")

def main():
    p=argparse.ArgumentParser();p.add_argument("--model",required=True);p.add_argument("--out",default="results");a=p.parse_args()
    out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
    instances=data();records=[]
    for iid,filename in CASES.items():
        logs=[];patch="";err="";calls=0
        try:
            ins=instances[iid]
            with tempfile.TemporaryDirectory() as d:
                root=pathlib.Path(d)/"repo"
                cmd(["git","clone","--quiet","https://github.com/"+ins["repo"]+".git",str(root)],timeout=240)
                cmd(["git","checkout","--quiet",ins["base_commit"]],cwd=root)
                target=select_target(root,filename,ins["repo"])
                relative=str(target.relative_to(root))
                system=("Fix a real issue in the checked out repository. You may use up to six tool calls "
                        "or fewer. Output exactly a JSON object for one action each turn. Available actions: "
                        '{"tool":"search","term":"string"}, {"tool":"read","start":1}, '
                        '{"tool":"edit","old":"exact text","new":"replacement"}, {"tool":"test"}, {"tool":"finish"}. '
                        "The read tool returns 120 lines from the selected file, search finds matching lines in that same file. "
                        "Edits apply only to that file and must preserve syntax. Return no Markdown. "
                        "Do not invent test results. Finish when done.\nIssue:\n"+ins["problem_statement"]+
                        "\nFile: "+relative+"\nInitial source preview:\n"+call_tool({"tool":"read","start":1},root,target))
                investigated=False;tested=False;edited=False
                for step in range(6):
                    raw,secs=infer(a.model,system)
                    calls+=1
                    entry={"step":step+1,"raw":raw,"seconds":secs}
                    try:
                        cleaned=raw.strip()
                        if cleaned.startswith(chr(96)*3):cleaned="\n".join(cleaned.splitlines()[1:-1])
                        act=json.loads(cleaned)
                        if act.get("tool")=="edit" and not investigated: raise ValueError("must search or read before edit")
                        if act.get("tool")=="finish" and edited and not tested: raise ValueError("must run test after edit")
                        response=call_tool(act,root,target)
                        if act.get("tool") in ("read","search"):investigated=True
                        if act.get("tool")=="edit":edited=True;tested=False
                        if act.get("tool")=="test":tested=True
                        entry["tool"]=act.get("tool")
                        entry["result"]=response
                        if act.get("tool")=="finish":
                            logs.append(entry);break
                    except Exception as exc:
                        entry["result"]="ERROR: "+repr(exc)
                    logs.append(entry)
                    system+=("\nAssistant response:\n"+raw[-4500:]+"\nTool observation:\n"+entry["result"][-7000:]+
                             "\nChoose the next tool. Return ONLY JSON.")
                patch=cmd(["git","diff","--",relative],cwd=root)
                if patch.strip():(out/(iid+".patch")).write_bytes(patch.encode())
        except Exception as exc:err=repr(exc)
        payload=json.dumps(logs,ensure_ascii=False).encode("utf-8")
        (out/(iid+".trace.json")).write_bytes(payload)
        records.append({"instance_id":iid,"patch_generated":bool(patch.strip()),"tool_calls":calls,
                        "trace_sha256":hashlib.sha256(payload).hexdigest(),"error":err,"functional_resolved":None})
        print(iid,"PATCH" if patch.strip() else "NO_PATCH", "calls",calls,flush=True)
    (out/"score.json").write_text(json.dumps({"model":a.model,"suite":"assisted-tools-v1",
         "patches":sum(r["patch_generated"] for r in records),
         "functional_resolved":"NOT_EVALUATED","cases":records},indent=2)+"\n")
if __name__=="__main__":main()
