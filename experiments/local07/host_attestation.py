"""LOCAL-15: host isolation preflight, observational and fail-closed.

Does not execute model code, Docker, or network requests. The runner must be
explicitly attested as disposable, credential-free and dedicated by operator.
Self-attestation is not proof of hypervisor isolation.
"""
import argparse
import json
import pathlib
import platform
import re
import sys

DIGEST = re.compile(r"^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$")
FIELDS = {"schema", "host_kind", "ephemeral", "dedicated", "no_credentials",
          "no_personal_mounts", "disposal_verified", "container_image", "operator_approved"}

def evaluate(attestation, *, observed_os):
    if not isinstance(attestation, dict) or set(attestation) != FIELDS or attestation["schema"] != 1:
        raise ValueError("ATTESTATION_SCHEMA_INVALID")
    checks = {
        key: attestation[key] is True
        for key in ("ephemeral", "dedicated", "no_credentials",
                    "no_personal_mounts", "disposal_verified", "operator_approved")
    }
    checks["guest_linux"] = observed_os == "Linux"
    checks["vm_or_ephemeral_runner"] = attestation["host_kind"] in {"disposable_vm", "ephemeral_ci_runner"}
    checks["digest_pinned_image"] = isinstance(attestation["container_image"], str) and bool(
        DIGEST.fullmatch(attestation["container_image"]))
    return {
        "schema": 1, "gate": "LOCAL-15", "status": "ATTESTATION_COMPLETE_UNVERIFIED" if all(checks.values()) else "BLOCKED",
        "checks": checks, "host_observed_os": observed_os,
        "isolation_technically_verified": False,
        "untrusted_execution_authorized": False,
        "reason": "Declarative attestation alone cannot verify credential absence, VM isolation or destruction."
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--attestation", required=True)
    p.add_argument("--output", required=True)
    a=p.parse_args()
    path=pathlib.Path(a.attestation)
    if path.stat().st_size > 8192:
        raise ValueError("ATTESTATION_TOO_LARGE")
    data=json.loads(path.read_text(encoding="utf-8"))
    report=evaluate(data,observed_os=platform.system())
    target=pathlib.Path(a.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"untrusted_execution_authorized":False,
                      "report":str(target)}))
    return 0 if report["status"]=="ATTESTATION_COMPLETE_UNVERIFIED" else 1

if __name__=="__main__":
    sys.exit(main())
