import argparse,json,pathlib
def analyze(folder):
 rows=[]
 for path in sorted(pathlib.Path(folder).rglob("*.trace.json")):
  turns=json.loads(path.read_text(encoding="utf-8"))
  ops=[t.get("tool","invalid") for t in turns]
  errors=[str(t.get("result","")) for t in turns if str(t.get("result","")).startswith("ERROR:")]
  rows.append({"instance":path.name.removesuffix(".trace.json"),"calls":len(turns),"ops":ops,
   "read_calls":ops.count("read"),"search_calls":ops.count("search"),"edit_calls":ops.count("edit"),
   "errors":errors,"patch_exists":path.with_name(path.name.replace(".trace.json",".patch")).exists(),
   "premature_finish":bool(ops and ops[-1]=="finish" and not any(op in ("read","search") for op in ops))})
 return {"cases":rows,"totals":{"cases":len(rows),"patches":sum(r["patch_exists"] for r in rows),
  "cases_without_investigation":sum(r["read_calls"]+r["search_calls"]==0 for r in rows),
  "invalid_tool_responses":sum("invalid" in r["ops"] for r in rows),
  "failed_tool_calls":sum(len(r["errors"]) for r in rows)}}
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("folder");p.add_argument("--output",default="trace-report.json");a=p.parse_args()
 report=analyze(a.folder)
 pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(report["totals"]))
