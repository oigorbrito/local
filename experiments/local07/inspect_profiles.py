"""Read-only, bounded Ollama native profile audit; never modifies any model."""
import argparse
import hashlib
import http.client
import json
import pathlib
import re
import sys

from windows_preflight import ollama_get, PreflightFailure

from executor_bridge import ContractError
from model_profiles import PROFILES, select_profile

MAX_SHOW_BYTES = 1024 * 1024
MODEL_DIGEST = re.compile(r"^[0-9a-f]{64}$")

def digest(value):
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def inspect(name, *, host="127.0.0.1", port=11434, timeout=20):
    profile = select_profile(name)
    if host != "127.0.0.1" or type(port) is not int or not 1 <= port <= 65535:
        raise ContractError("ONLY_LOOPBACK_OLLAMA_ALLOWED")
    if type(timeout) is not int or not 1 <= timeout <= 60:
        raise ContractError("INVALID_TIMEOUT")
    # Ollama's /api/tags digest identifies the actual installed model manifest.
    # /api/show alone does not reliably include an installed-model digest.
    try:
        tags = ollama_get("/api/tags", host=host, port=port,
                          timeout=timeout, transport=http.client.HTTPConnection)
    except PreflightFailure as exc:
        raise ContractError("OLLAMA_TAGS_INVALID") from exc
    inventory = tags.get("models")
    if not isinstance(inventory, list):
        raise ContractError("OLLAMA_TAGS_INVALID")
    selected = [m for m in inventory if isinstance(m, dict)
                and m.get("name") == profile.base_model]
    if len(selected) != 1 or not isinstance(selected[0].get("digest"), str):
        raise ContractError("OLLAMA_MODEL_NOT_IN_INVENTORY")
    model_digest = selected[0]["digest"].lower()
    if not MODEL_DIGEST.fullmatch(model_digest):
        raise ContractError("OLLAMA_MODEL_DIGEST_INVALID")
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request(
            "POST", "/api/show", body=json.dumps({"model": profile.base_model}),
            headers={"Content-Type": "application/json"}
        )
        response = conn.getresponse()
        if response.status != 200:
            raise ContractError("OLLAMA_SHOW_HTTP_" + str(response.status))
        length = response.getheader("Content-Length")
        if length is not None:
            try:
                if int(length) > MAX_SHOW_BYTES:
                    raise ContractError("OLLAMA_SHOW_TOO_LARGE")
            except ValueError as exc:
                raise ContractError("OLLAMA_SHOW_INVALID_LENGTH") from exc
        blob = response.read(MAX_SHOW_BYTES + 1)
        if len(blob) > MAX_SHOW_BYTES:
            raise ContractError("OLLAMA_SHOW_TOO_LARGE")
    finally:
        conn.close()
    try:
        data = json.loads(blob.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("OLLAMA_SHOW_INVALID_JSON") from exc
    if not isinstance(data, dict):
        raise ContractError("OLLAMA_SHOW_INVALID_RESPONSE")
    native = {}
    for field in ("modelfile", "template", "parameters"):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            raise ContractError("OLLAMA_SHOW_INVALID_" + field.upper())
        native[field + "_sha256"] = digest(value)
        native[field + "_present"] = bool(value)
    if not native["modelfile_present"] and not native["template_present"]:
        raise ContractError("OLLAMA_SHOW_NO_NATIVE_DEFINITION")
    details = data.get("details")
    if not isinstance(details, dict):
        details = {}
    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list) or any(not isinstance(x, str) for x in capabilities):
        capabilities = []
    return {
        "inspection_schema": 1, "status": "INSPECTED_NOT_GRADED",
        "profile": profile.name, "profile_version": profile.version,
        "profile_fingerprint_sha256": profile.fingerprint,
        "native_model": profile.base_model,
        "native_model_digest_sha256": model_digest,
        "native": native,
        "details": {k: details.get(k) for k in
                    ("family", "parameter_size", "quantization_level", "format")},
        "declared_capabilities": sorted(set(capabilities))
    }

def main():
    p = argparse.ArgumentParser(description="Read native Ollama metadata (no inference or mutation)")
    p.add_argument("--profile", choices=tuple(PROFILES), default=None)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    results = {}
    for name in ([args.profile] if args.profile else PROFILES):
        try:
            results[name] = inspect(name)
        except (ContractError, OSError) as exc:
            # Never include host body, native Modelfile or HTTP error payloads.
            results[name] = {"profile": name, "status": "BLOCKED",
                             "reason": str(exc) if isinstance(exc, ContractError) else "OLLAMA_UNREACHABLE"}
    ok = all(item["status"] == "INSPECTED_NOT_GRADED" for item in results.values())
    report = {"schema": 1, "complete": ok, "results": results}
    pathlib.Path(args.output).write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"complete": ok, "profiles": list(results), "output": args.output}))
    if not ok:
        sys.exit(2)

if __name__ == "__main__":
    main()
