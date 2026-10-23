import argparse,json,pathlib,collections
def main():
 p=argparse.ArgumentParser();p.add_argument("report");p.add_argument("--out",default="per-issue-gate.json");a=p.parse_args()
 data=json.loads(pathlib.Path(a.report).read_text(encoding="utf8"))
 cases=data["cases"]
 if len(cases)!=3 or len({x["instance_id"] for x in cases})!=3:raise SystemExit("Expected three unique instances")
 entries=[]
 for x in cases:
  f=x["fail_to_pass_failed"];r=x["pass_to_pass_failed"]
  entries.append({"instance_id":x["instance_id"],"patch_applied":x["applied"],
   "resolved":x["resolved"],"failing_target_tests":len(f),"regressed_existing_tests":len(r),
   "target_test_names":f,"regression_test_names":r,
   "accept":bool(x["applied"] and x["resolved"] and not f and not r)})
 out={"contract":"real-issue-functional-gate-v1","source_run":40014441296,"cases":entries,
      "all_patches_pass":all(x["accept"] for x in entries),
      "totals":{"applied":sum(x["patch_applied"] for x in entries),"resolved":sum(x["resolved"] for x in entries),
                "target_failures":sum(x["failing_target_tests"] for x in entries),
                "regressions":sum(x["regressed_existing_tests"] for x in entries)}}
 pathlib.Path(a.out).write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
 print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
