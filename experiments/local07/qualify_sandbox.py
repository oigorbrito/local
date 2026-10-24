"""LOCAL-14 sandbox qualification. Explicit opt-in; no candidate patch execution.

Requires an existing digest-pinned image and a running Docker daemon.
Runs a fixed harmless Python probe in a constrained container and checks
its observable properties. Does not claim VM-grade isolation.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

IMAGE=re.compile(r"^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$")
PROBE="""import json,os,pathlib,socket
caps=pathlib.Path('/proc/self/status').read_text().splitlines()
cap=next((x.split(':',1)[1].strip() for x in caps if x.startswith('CapEff:')),'UNKNOWN')
status={'uid':os.getuid(),'cap_eff':cap,'root_writable':os.access('/',os.W_OK)}
try:
    socket.create_connection(('1.1.1.1',443),timeout=2)
    status['outbound_network']='CONNECTED'
except OSError:
    status['outbound_network']='BLOCKED'
print('LOCAL14_PROBE='+json.dumps(status,sort_keys=True))
"""

def qualify(image, output, runner=subprocess.run):
    if not IMAGE.fullmatch(image):
        raise ValueError("IMAGE_MUST_BE_PINNED_TO_SHA256")
    inspect=runner(["docker","image","inspect",image],capture_output=True,timeout=30)
    if inspect.returncode:
        raise RuntimeError("LOCAL_IMAGE_MISSING_OR_DOCKER_UNAVAILABLE")
    command=["docker","run","--rm","--pull","never","--network","none",
             "--read-only","--cap-drop","ALL","--security-opt","no-new-privileges",
             "--pids-limit","128","--memory","2g","--cpus","2",
             "--user","65534:65534","--tmpfs","/tmp:rw,nosuid,noexec,size=32m",
             image,"python","-c",PROBE]
    result=runner(command,capture_output=True,timeout=60)
    report={"schema":1,"gate":"LOCAL-14-SANDBOX","image":image,"probe_exit_code":result.returncode,
            "qualified":False,"untrusted_code_executed":False}
    if result.returncode==0:
        lines=[line for line in result.stdout.decode("utf-8","replace").splitlines()
               if line.startswith("LOCAL14_PROBE=")]
        if len(lines)==1:
            observed=json.loads(lines[0].split("=",1)[1])
            report["observed"]=observed
            report["qualified"]=(observed.get("uid")==65534 and
                observed.get("cap_eff")=="0000000000000000" and
                observed.get("root_writable") is False and
                observed.get("outbound_network")=="BLOCKED")
    pathlib.Path(output).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(output).write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return report

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--image",required=True)
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    try:
        r=qualify(args.image,args.output)
        print(json.dumps({"qualified":r["qualified"],"output":args.output}))
        sys.exit(0 if r["qualified"] else 1)
    except (RuntimeError,ValueError,subprocess.TimeoutExpired) as exc:
        print(type(exc).__name__+": "+str(exc),file=sys.stderr)
        sys.exit(2)
