import argparse,json,pathlib
def summarize(source):
 results=[]
 for path in sorted(pathlib.Path(source).glob("*.json")):
  obj=json.loads(path.read_text(encoding="utf-8"))
  for iid,record in obj.items():
   t=record["tests_status"]
   results.append({"instance_id":iid,"applied":bool(record.get("patch_successfully_applied")),
    "resolved":bool(record.get("resolved")),
    "fail_to_pass_failed":t.get("FAIL_TO_PASS",{}).get("failure",[]),
    "pass_to_pass_failed":t.get("PASS_TO_PASS",{}).get("failure",[]),
    "pass_to_pass_failed_count":len(t.get("PASS_TO_PASS",{}).get("failure",[]))})
 return results
def main():
 p=argparse.ArgumentParser();p.add_argument("folder");p.add_argument("--out",default="official-failure-analysis.json");a=p.parse_args()
 results=summarize(a.folder)
 if len(results)!=3:raise SystemExit("Expected exactly 3 official instance reports; got "+str(len(results)))
 outcome={"source":"official SWE-bench report, github actions 40014441296","cases":results,
 "totals":{"applied":sum(r["applied"] for r in results),"resolved":sum(r["resolved"] for r in results),
 "failing_fail_to_pass":sum(len(r["fail_to_pass_failed"]) for r in results),
 "regressing_pass_to_pass":sum(r["pass_to_pass_failed_count"] for r in results)}}
 pathlib.Path(a.out).write_text(json.dumps(outcome,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(outcome["totals"]))
if __name__=="__main__":main()
