"""LOCAL-WINNER-03: independent baseline vs gold control in constrained Docker.

One frozen SWE-bench Lite/dev instance per run; never invokes any LLM.
Uses SWE-bench's public test-spec generator and grader, but NOT its
container-creation helper (which currently adds SYS_ADMIN). Gold and tests
stay evaluator-private. The host receives only hashed/sanitized results.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from qualify_static import official_rows, EXPECTED_DATASET_SHA256
from select_cases import freeze, extract, hash_bytes
from datasets import load_dataset
from swebench.harness.utils import make_test_spec
from swebench.harness.grading import get_eval_report
from swebench.image_builder.constants import CONTAINER_WORKDIR

PILOT = "pvlib__pvlib-python-1854"
ENRICHED_DATASET = "SWE-bench/SWE-bench_Lite"
ENRICHED_REVISION = "a0291d6d46bcfa739d77ca942e1ba16006ab7e46"
MAX_TEST_SECONDS = 240
IMAGE_WAIT_SECONDS = 600

def call(args, timeout=30):
    return subprocess.run(args,capture_output=True,text=True,timeout=timeout,
                          errors="replace",encoding="utf-8",check=False)

def docker_image(image):
    if not isinstance(image,str) or not image or "\n" in image:
        raise RuntimeError("INVALID_DOCKER_IMAGE_IDENTITY")
    test=call(["docker","image","inspect",image,"--format","{{.Id}}"])
    if test.returncode:
        fetch=call(["docker","pull",image],IMAGE_WAIT_SECONDS)
        if fetch.returncode:
            raise RuntimeError("DOCKER_IMAGE_PULL_FAILED")
        test=call(["docker","image","inspect",image,"--format","{{.Id}}"])
    if test.returncode or not test.stdout.strip().startswith("sha256:"):
        raise RuntimeError("DOCKER_IMAGE_DIGEST_UNAVAILABLE")
    return test.stdout.strip()

def docker_eval(spec, image_id, gold_patch, mode, scratch):
    if mode not in ("baseline","gold"):
        raise ValueError("INVALID_MODE")
    uid="65534:65534"
    shell=("set -e; cd "+CONTAINER_WORKDIR+"; "
           +("git apply --check /model.patch; git apply /model.patch; " if mode=="gold" else "")
           +"exec /bin/bash /eval.sh")
    args=["docker","create","--network","none","--cap-drop","ALL",
          "--security-opt","no-new-privileges","--pids-limit","128",
          "--cpus","2","--memory","3g","--user",uid,
          "--tmpfs","/tmp:rw,nosuid,nodev,size=256m",
          "--workdir",CONTAINER_WORKDIR,
          "--entrypoint","/bin/bash", image_id,"-lc",shell]
    result=call(args,60)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError("ISOLATED_CONTAINER_CREATION_FAILED")
    name=result.stdout.strip()
    temp=Path(scratch)
    evalsh=temp/("eval-"+mode+".sh")
    evalsh.write_text(spec.eval_script,encoding="utf-8")
    if gold_patch and mode=="gold":
        patch=temp/"private-gold.patch"
        patch.write_text(gold_patch,encoding="utf-8")
    try:
        steps=[["docker","cp",str(evalsh),name+":/eval.sh"]]
        if mode=="gold":
            steps.append(["docker","cp",str(patch),name+":/model.patch"])
        for cmd in steps:
            cp=call(cmd,60)
            if cp.returncode:
                raise RuntimeError("CONTAINER_STAGING_FAILED")
        # The command/test runner operates only inside the non-root,
        # no-network, cap-drop, resource-capped, throwaway container.
        start=time.monotonic()
        try:
            launch=call(["docker","start","--attach",name],MAX_TEST_SECONDS+20)
        except subprocess.TimeoutExpired:
            return {"mode":mode,"status":"TEST_TIMEOUT","seconds":round(time.monotonic()-start,2)}
        elapsed=round(time.monotonic()-start,2)
        output=launch.stdout+"\n"+launch.stderr
        private_log=temp/("private-"+mode+"-test.log")
        private_log.write_text(output,encoding="utf-8")
        out={"mode":mode,"status":"TEST_OUTPUT_CAPTURED",
             "docker_exit":launch.returncode,"seconds":elapsed,
             "test_log_sha256":hash_bytes(output.encode("utf-8"))}
        try:
            model_name=f"control-{mode}"
            pred={"instance_id":spec.instance_id,"model_name_or_path":model_name,
                  "model_patch":gold_patch if mode=="gold" else "NO_MODEL_PATCH_CONTROL"}
            graded=get_eval_report(spec,pred,str(private_log),True)[spec.instance_id]
            f2p=graded.get("tests_status",{}).get("FAIL_TO_PASS",{})
            p2p=graded.get("tests_status",{}).get("PASS_TO_PASS",{})
            out.update({
                "resolved":graded.get("resolved") is True,
                "tests_parsed":graded.get("patch_successfully_applied") is True,
                "f2p_passed":len(f2p.get("success",[])),
                "f2p_failed":len(f2p.get("failure",[])),
                "p2p_failed":len(p2p.get("failure",[])),
                "environment_failure":graded.get("infra_failure") is True})
            out["status"]="GRADED" if out["tests_parsed"] and not out["environment_failure"] else "UNPARSEABLE_OR_ENVIRONMENT"
        except (ValueError,KeyError,TypeError):
            out["status"]="OFFICIAL_GRADER_ERROR"
        return out
    finally:
        call(["docker","rm","--force",name],60)

def execute(case_id=PILOT):
    raw=official_rows()
    if hash_bytes(raw)!=EXPECTED_DATASET_SHA256:
        raise RuntimeError("DATASET_PIN_CHANGED")
    manifest,_=freeze(raw)
    if case_id not in {c["case_id"] for c in manifest["cases"]}:
        raise RuntimeError("CASE_NOT_IN_FROZEN_SET")
    original=next(x for x in extract(raw) if x["instance_id"]==case_id)
    # Original Princeton dataset has issue/gold/test fields but NOT current
    # harness metadata. Read only the enriched official SWE-bench dataset at
    # a fixed HuggingFace commit and verify matching issue/source/gold bytes.
    enriched=load_dataset(ENRICHED_DATASET,split="dev",revision=ENRICHED_REVISION)
    matches=[dict(x) for x in enriched if x["instance_id"]==case_id]
    if len(matches)!=1:
        raise RuntimeError("ENRICHED_INSTANCE_NOT_FOUND")
    row=matches[0]
    for field in ("repo","base_commit","patch","test_patch","problem_statement"):
        if row.get(field)!=original.get(field):
            raise RuntimeError("ENRICHED_DATASET_CONTENT_DIFFERS:"+field)
    required=("image","eval_script","log_parser","eval_type","FAIL_TO_PASS",
              "PASS_TO_PASS","version","repo","patch","test_patch")
    missing=[x for x in required if not row.get(x)]
    if missing:
        raise RuntimeError("OFFICIAL_DATASET_HARNESS_FIELDS_MISSING:" + ",".join(missing))
    if row.get("image_assets") and row["image_assets"] not in ("", "{}", {}):
        raise RuntimeError("MULTIMODAL_ASSETS_NOT_SUPPORTED_IN_PILOT")
    spec=make_test_spec(row)
    before=hash_bytes(row["patch"].encode("utf-8"))
    expected=next(x for x in manifest["cases"] if x["case_id"]==case_id)
    if before!=expected["gold_patch_sha256"]:
        raise RuntimeError("REFERENCE_PATCH_HASH_DRIFT")
    docker_status=call(["docker","info","--format","{{.ServerVersion}}"],20)
    if docker_status.returncode:
        raise RuntimeError("DOCKER_DAEMON_UNAVAILABLE")
    image_id=docker_image(spec.image)
    with tempfile.TemporaryDirectory(prefix="winner03-controls-") as td:
        base=docker_eval(spec,image_id,row["patch"],"baseline",td)
        # Do not spend another run if baseline could not even be parsed.
        if (base.get("status")!="GRADED" or base.get("f2p_failed",0)<1):
            return {"status":"BLOCKED_BASELINE_NOT_REPRODUCED", "case_id":case_id,
                    "image_id":image_id,"baseline":base,"gold":None}
        gold=docker_eval(spec,image_id,row["patch"],"gold",td)
    pass_gold=(gold.get("status")=="GRADED" and gold.get("resolved") is True and
               gold.get("f2p_failed")==0 and gold.get("p2p_failed")==0 and
               gold.get("f2p_passed")==len(spec.FAIL_TO_PASS))
    status="FUNCTIONAL_ORACLE_QUALIFIED" if pass_gold else "BLOCKED_GOLD_NOT_RESOLVED"
    return {"status":status,"case_id":case_id,"image_id":image_id,
            "enriched_dataset_revision":ENRICHED_REVISION,
            "baseline":base,"gold":gold,
            "f2p_expected":len(spec.FAIL_TO_PASS),"p2p_expected":len(spec.PASS_TO_PASS),
            "inference_calls":0,"host_code_execution":False,
            "model_saw_reference_patch":False,
            "note":"Gold control is never a model score; source code executed only in ephemeral Docker."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case-id",default=PILOT)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():
        p.error("output already exists")
    try:
        report=execute(a.case_id)
    except Exception as e:
        report={"status":"BLOCKED_HARNESS_OR_ENVIRONMENT",
                "case_id":a.case_id,"diagnostic":str(e)[:160],
                "inference_calls":0}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("GOLD_BASELINE_GATE",json.dumps(report,ensure_ascii=False),flush=True)
    return 0 if report["status"]=="FUNCTIONAL_ORACLE_QUALIFIED" else 2

if __name__=="__main__":
    sys.exit(main())
