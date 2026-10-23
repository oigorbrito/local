import json, pathlib, sys
root=pathlib.Path(sys.argv[1])
model=sys.argv[2]
out=pathlib.Path(sys.argv[3])
files=sorted(root.glob("*.patch"))
if not files: raise SystemExit("No generated patches; fail closed")
rows=[]
for f in files:
    patch=f.read_text(encoding="utf-8")
    if not patch.startswith("diff --git "): raise SystemExit("Not a git patch: "+f.name)
    rows.append({"instance_id":f.stem,"model_name_or_path":model,"model_patch":patch})
out.write_text("".join(json.dumps(x)+"\n" for x in rows),encoding="utf-8")
print("predictions:",len(rows),[x["instance_id"] for x in rows])
