import argparse, hashlib, json, pathlib, subprocess, tempfile, time, urllib.request, re

CASES=[
 {"id":"pagination_off_by_one","spec":"Repair paginate(items,page,size). Page is one-indexed, invalid inputs must return []. Preserve existing public API.",
  "source":"def paginate(items,page,size):\n    if size <= 0 or page < 1: return []\n    start=page*size\n    return items[start:start+size]\n",
  "tests":"assert paginate(list(range(8)),1,3)==[0,1,2]\nassert paginate(list(range(8)),2,3)==[3,4,5]\nassert paginate([1],0,1)==[]\nassert paginate([1],2,1)==[]"},
 {"id":"lru_recency","spec":"Repair Cache: reads refresh recency and eviction must remove least recently used key. Preserve get/set API and zero capacity behavior.",
  "source":"class Cache:\n    def __init__(self,capacity):\n        self.capacity=capacity\n        self.items={}\n    def get(self,key):\n        return self.items.get(key)\n    def set(self,key,value):\n        self.items[key]=value\n        if len(self.items)>self.capacity:\n            self.items.pop(next(iter(self.items)))\n",
  "tests":"c=Cache(2)\nc.set('a',1);c.set('b',2);assert c.get('a')==1\nc.set('c',3);assert c.get('b') is None\nassert c.get('a')==1 and c.get('c')==3\nz=Cache(0);z.set('a',1);assert z.get('a') is None"},
 {"id":"interval_boundary","spec":"Repair merge(intervals): ranges touching at endpoints must merge, unsorted inputs accepted, no input mutation.",
  "source":"def merge(intervals):\n    result=[]\n    for a,b in intervals:\n        if result and a < result[-1][1]:\n            result[-1][1]=max(result[-1][1],b)\n        else:\n            result.append([a,b])\n    return result\n",
  "tests":"x=[[4,5],[1,3],[3,4]]\nassert merge(x)==[[1,5]]\nassert x==[[4,5],[1,3],[3,4]]\nassert merge([])==[]\nassert merge([[1,2],[8,9]])==[[1,2],[8,9]]"}
]
def clean(s):
    tick=chr(96)*3
    blocks=re.findall(re.escape(tick)+r"(?:python|py)?\s*\n(.*?)"+re.escape(tick),s,re.S|re.I)
    return blocks[0].strip()+"\n" if len(blocks)==1 else s
def run_tests(source,tests):
    with tempfile.TemporaryDirectory() as d:
        p=pathlib.Path(d)
        (p/"solution.py").write_bytes(source.encode())
        (p/"test.py").write_text("from solution import *\n"+tests+"\n",encoding="utf-8")
        cmd=["docker","run","--rm","--network","none","--memory","512m","--cpus","1",
             "--pids-limit","64","--read-only","--security-opt","no-new-privileges",
             "-v",str(p.resolve())+":/work:ro","-w","/work","python:3.12-slim","python","-B","test.py"]
        proc=subprocess.run(cmd,text=True,capture_output=True,timeout=40)
        return proc.returncode==0,(proc.stderr or proc.stdout)[-1000:]
def generate(model,prompt):
    req=urllib.request.Request("http://localhost:11434/api/generate",
        data=json.dumps({"model":model,"prompt":prompt,"stream":False,
                         "options":{"temperature":0,"num_ctx":4096,"num_predict":1536}}).encode(),
        headers={"Content-Type":"application/json"})
    start=time.monotonic()
    with urllib.request.urlopen(req,timeout=600) as resp: data=json.load(resp)
    return data.get("response",""),round(time.monotonic()-start,2)
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--model",required=True);ap.add_argument("--out",default="results")
    a=ap.parse_args()
    root=pathlib.Path(a.out);root.mkdir(parents=True,exist_ok=True)
    rows=[]
    for case in CASES:
        cid=case["id"]
        assert run_tests(case["source"],case["tests"])[0] is False,"broken fixture must fail"
        prompt=("You are repairing existing Python code. Return the complete corrected file as Python source only. "
                "No markdown. Preserve public API and unrelated behavior.\nIssue: "+case["spec"]+
                "\nExisting source:\n"+case["source"])
        passed=False;detail="";seconds=0;raws=[]
        for attempt in range(2):
            try:
                raw,duration=generate(a.model,prompt)
                raws.append(raw);seconds+=duration
                candidate=clean(raw)
                passed,detail=run_tests(candidate,case["tests"])
                if passed:break
                prompt=("Your previous replacement failed tests. Return the complete corrected Python file, "
                        "without markdown. Issue: "+case["spec"]+"\nYour replacement:\n"+candidate+
                        "\nTest failure:\n"+detail[-700:])
            except Exception as exc:
                detail=repr(exc);break
        raw="\n---ATTEMPT---\n".join(raws).encode()
        (root/(cid+".raw.txt")).write_bytes(raw)
        row={"case":cid,"resolved":passed,"attempts":len(raws),"inference_seconds":round(seconds,2),
             "sha256":hashlib.sha256(raw).hexdigest(),"failure":"" if passed else detail}
        rows.append(row)
        print(a.model,cid,"PASS" if passed else "FAIL","attempts",len(raws),flush=True)
    score={"suite":"repair-fixtures-v1","model":a.model,"passed":sum(x["resolved"] for x in rows),
           "total":len(rows),"cases":rows}
    (root/"score.json").write_text(json.dumps(score,indent=2)+"\n")
    print(json.dumps({"model":a.model,"passed":score["passed"],"total":score["total"]}),flush=True)
if __name__=="__main__":main()
