import argparse,hashlib,json,pathlib,subprocess,tempfile,time,urllib.request
tasks=[
("dedupe","Write def solve(items): return integers uniquely in original order.","assert solve([1,2,1,3]) == [1,2,3]\nassert solve([]) == []"),
("brackets","Write def solve(s): check balanced (), [], {} brackets ignoring other characters.","assert solve('([])') is True\nassert solve('([)]') is False\nassert solve('x{a}') is True"),
("intervals","Write def solve(intervals): merge overlapping or touching integer [start,end] ranges and return sorted lists.","assert solve([[1,3],[2,4],[8,9]]) == [[1,4],[8,9]]\nassert solve([]) == []"),
("pagination","Write def solve(items,page,size): one-indexed pagination; invalid page or size returns [].","assert solve(list(range(7)),2,3) == [3,4,5]\nassert solve([1],0,2) == []"),
("logparse","Write def solve(lines): parse 'LEVEL: message' strings to {'level':...,'message':...} dicts; skip malformed lines.","assert solve(['INFO: a','bad','ERROR: b:c']) == [{'level':'INFO','message':'a'},{'level':'ERROR','message':'b:c'}]"),
("lru","Write class Cache(capacity), methods set(key,value), get(key) -> value or None; least recently used eviction; get refreshes; capacity zero disables storage.","c=Cache(2)\nc.set('a',1);c.set('b',2);assert c.get('a')==1\nc.set('c',3);assert c.get('b') is None\nassert c.get('c')==3")
]
def main():
 p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--out',default='results');a=p.parse_args()
 out=pathlib.Path(a.out);out.mkdir(exist_ok=True,parents=True)
 rows=[]
 for key,spec,tests in tasks:
  prompt="Return only complete Python source code, no markdown or explanations. "+spec
  response='';duration=None;passed=False;detail=''
  try:
   req=urllib.request.Request('http://localhost:11434/api/generate',data=json.dumps({'model':a.model,'prompt':prompt,'stream':False,'options':{'temperature':0,'num_ctx':4096,'num_predict':1024}}).encode(),headers={'Content-Type':'application/json'})
   started=time.monotonic()
   with urllib.request.urlopen(req,timeout=600) as r: data=json.load(r)
   duration=round(time.monotonic()-started,2);response=data.get('response','')
   with tempfile.TemporaryDirectory() as directory:
    path=pathlib.Path(directory)
    (path/'solution.py').write_text(response,encoding='utf8')
    (path/'check.py').write_text('from solution import *\n'+tests+'\n',encoding='utf8')
    cmd=['docker','run','--rm','--network','none','--memory','512m','--cpus','1','--pids-limit','64','--read-only','--security-opt','no-new-privileges','-v',str(path.resolve())+':/work:ro','-w','/work','python:3.12-slim','python','-B','check.py']
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
    passed=r.returncode==0;detail=(r.stderr or r.stdout)[-500:]
  except Exception as e: detail=repr(e)
  blob=response.encode('utf8');(out/(key+'.txt')).write_bytes(blob)
  rows.append({'task':key,'pass':passed,'seconds':duration,'sha256':hashlib.sha256(blob).hexdigest(),'detail':detail})
  print(a.model,key,'PASS' if passed else 'FAIL',flush=True)
 result={'model':a.model,'suite':'cpu-screen-v1','passed':sum(x['pass'] for x in rows),'total':len(rows),'tasks':rows}
 (out/'score.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
 print(json.dumps({'model':a.model,'passed':result['passed'],'total':result['total']}))
if __name__=='__main__':main()
