"""Inspect native Ollama definitions without changing installed models."""
import argparse
import http.client
import json
import pathlib
from model_profiles import PROFILES

def inspect(name):
    model = PROFILES[name].base_model
    conn = http.client.HTTPConnection("127.0.0.1", 11434, timeout=20)
    try:
        conn.request("POST", "/api/show", body=json.dumps({"model": model}), headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            raise RuntimeError("OLLAMA_SHOW_HTTP_" + str(response.status))
        blob = response.read(1024 * 1024 + 1)
        if len(blob) > 1024 * 1024:
            raise ValueError("OLLAMA_SHOW_TOO_LARGE")
    finally:
        conn.close()
    data = json.loads(blob.decode("utf-8"))
    return {"profile": name, "model": model, "modelfile": data.get("modelfile"),
            "template": data.get("template"), "parameters": data.get("parameters"),
            "model_info": data.get("model_info")}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    args = p.parse_args()
    result = {name: inspect(name) for name in PROFILES}
    pathlib.Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"inspected": list(result), "output": args.output}))

if __name__ == "__main__":
    main()
