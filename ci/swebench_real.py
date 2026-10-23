import argparse,hashlib,json,pathlib,subprocess,tempfile,time,urllib.parse,urllib.request,ast,re
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
def select_target(root, filename, repo_name):
 candidates=[p for p in root.rglob(filename) if ".git" not in p.parts and "test" not in p.parts and "tests" not in p.parts]
 if repo_name=="pvlib/pvlib-python":
  priority=[p for p in candidates if p.relative_to(root).as_posix()=="pvlib/temperature.py"]
 elif repo_name=="marshmallow-code/marshmallow":
  priority=[p for p in candidates if p.relative_to(root).as_posix().endswith("marshmallow/"+filename)]
 else:
  priority=[]
 if len(priority)==1:return priority[0]
 if len(candidates)==1:return candidates[0]
 raise ValueError("cannot uniquely locate source: "+repr([p.relative_to(root).as_posix() for p in candidates[:12]]))

def excerpt(source, issue, limit=12500):
 if len(source)<=limit:return source
 try:
  tree=ast.parse(source)
  lines=source.splitlines(keepends=True)
  words=set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{3,}",issue.lower()))
  nodes=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and hasattr(n,"end_lineno")]
  scored=[]
  for n in nodes:
   segment="".join(lines[max(0,n.lineno-3):min(len(lines),n.end_lineno+2)])
   if len(segment)>limit:continue
   score=6*(n.name.lower() in words)+sum(1 for w in words if len(w)>5 and w in segment.lower())
   scored.append((score,n.lineno,segment))
  scored.sort(key=lambda x:(-x[0],x[1]))
  selected=[];used=0
  for score,line,segment in scored:
   if score<=0 or used+len(segment)>limit:continue
   selected.append((line,segment));used+=len(segment)
   if len(selected)>=4:break
  if not selected:raise ValueError("no relevant bounded source excerpt")
  return "\n\n".join("# SOURCE LINE "+str(line)+"\n"+part for line,part in sorted(selected))
 except SyntaxError as exc:raise ValueError("cannot parse source for extraction") from exc

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
    target=select_target(root,filename,inst["repo"]);relative=str(target.relative_to(root))
    source=target.read_text(encoding="utf-8")
    context=excerpt(source,inst["problem_statement"])
    prompt="Solve the issue by returning one exact Python file edit as JSON with string keys old,new. The old string must appear exactly once. No markdown, no extra keys, no unrelated changes.\nIssue:\n"+inst["problem_statement"]+"\nFile "+relative+" (selected excerpts from original source; old must match full source exactly):\n"+context
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
