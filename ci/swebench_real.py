import argparse,hashlib,json,pathlib,subprocess,tempfile,time,urllib.parse,urllib.request
CASES={"marshmallow-code__marshmallow-1343":"schema.py","marshmallow-code__marshmallow-1359":"fields.py","pvlib__pvlib-python-1072":"temperature.py"}
def cmd(args,cwd=None,timeout=180):
 return subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=timeout,check=True).stdout
def data():
 params=urllib.parse.urlencode({"dataset":"SWE-bench/SWE-bench_Lite","config":"default","split":"dev","offset":0,"length":100})
 with urllib.request.urlopen("https://datasets-server.huggingface.co/rows?"+params,timeout=90) as r: j=json.load(r)
 return {e["row"]["instance_id"]:e["row"] for e in j["rows"]}
def infer(model,prompt):
 req=urllib.request.Request("http://localhost:11434/api/generate",data=json.dumps({"model":model,"prompt":prompt,"stream":False,"options":{"temperature":0,"num_ctx":8192,"num_predict":1536}}).encode(),headers={"Content-Type":"application/json"})
 t=time.monotonic()
 with urllib.request.urlopen(req,timeout=600) as r: j=json.load(r)
 return j.get("response",""),round(time.monotonic()-t,2)
def parse(s):
 s=s.strip();tick=chr(96)*3
 if s.startswith(tick):s="\n".join(s.splitlines()[1:-1])
 j=json.loads(s)
 if not isinstance(j,dict) or set(j)!={"old","new"} or not all(isinstance(j[k],str) for k in ("old","new")) or not j["old"] or j["old"]==j["new"]:raise ValueError("invalid exact-edit JSON")
 return j
def main():
 p=argparse.ArgumentParser();p.add_argument("--model",required=True);p.add_argument("--out",default="results");a=p.parse_args()
 out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
 instances=data();rows=[]
 for iid,filename in CASES.items():
  raw="";secs=0;error="";valid=False
  try:
   inst=instances[iid]
   with tempfile.TemporaryDirectory() as d:
    root=pathlib.Path(d)/"repo"
    cmd(["git","clone","--quiet","https://github.com/"+inst["repo"]+".git",str(root)],timeout=240)
    cmd(["git","checkout","--quiet",inst["base_commit"]],cwd=root)
    matches=list(root.rglob(filename))
    if len(matches)!=1:raise ValueError("file lookup missing or ambiguous")
    target=matches[0];relative=str(target.relative_to(root))
    source=target.read_text(encoding="utf-8")
    if len(source)>30000:raise ValueError("file too large: fail closed")
    prompt="Solve the issue by returning one exact Python file edit as JSON with string keys old,new. The old string must appear exactly once. No markdown, no extra keys, no unrelated changes.\nIssue:\n"+inst["problem_statement"]+"\nFile "+relative+":\n"+source
    raw,secs=infer(a.model,prompt);edit=parse(raw)
    if source.count(edit["old"])!=1:raise ValueError("old span is not unique")
    target.write_text(source.replace(edit["old"],edit["new"],1),encoding="utf-8")
    cmd(["python3","-m","py_compile",str(target)],cwd=root)
    patch=cmd(["git","diff","--",relative],cwd=root)
    if not patch.strip():raise ValueError("empty diff")
    (out/(iid+".patch")).write_bytes(patch.encode());valid=True
  except Exception as exc:error=repr(exc)
  b=raw.encode();(out/(iid+".response.txt")).write_bytes(b)
  rows.append({"instance_id":iid,"valid_patch":valid,"seconds":secs,"sha256":hashlib.sha256(b).hexdigest(),"error":error,"functional_resolved":None})
  print(iid,"VALID_PATCH" if valid else "INVALID_PATCH",flush=True)
 score={"suite":"swebench-lite-dev-targeted-v1","model":a.model,"valid_patches":sum(r["valid_patch"] for r in rows),"functional_resolved":None,"cases":rows}
 (out/"score.json").write_text(json.dumps(score,indent=2)+"\n")
 print(json.dumps({"model":a.model,"valid_patches":score["valid_patches"],"functional":"NOT_EVALUATED"}),flush=True)
if __name__=="__main__":main()
