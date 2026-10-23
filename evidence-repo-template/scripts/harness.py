#!/usr/bin/env python3
"""Minimal repository maturity/evidence harness.

This is a repository-specific adapter. It does not claim full OSPS/NIST/DORA
conformance. It checks only evidence that can be determined safely from local
repository state and labels platform-dependent controls UNKNOWN_EXTERNAL.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "policy" / "project-state.json"

PASS = "PASS"
GAP = "GAP"
UNKNOWN = "UNKNOWN_EXTERNAL"
NA = "NOT_APPLICABLE"
INFO = "INFO"
REASSESS = "MATURITY_REASSESSMENT_REQUIRED"

@dataclass
class Finding:
    status: str
    control: str
    message: str


def load_state(path: Path = STATE_FILE) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema_version": int,
        "product_stage": str,
        "osps_baseline_version": str,
        "osps_target_level": int,
        "project_kind": str,
        "maintainers_count": int,
        "consistent_users": str,
        "release": dict,
        "production_deployed": bool,
        "enforce_local_gaps": bool,
    }
    for key, typ in required.items():
        if key not in data or not isinstance(data[key], typ):
            raise ValueError(f"invalid project state: {key!r} missing or wrong type")
    if data["osps_target_level"] not in (1, 2, 3):
        raise ValueError("osps_target_level must be 1, 2, or 3")
    if data["osps_baseline_version"] != "2026.08.28":
        raise ValueError("template mappings are pinned to OSPS Baseline 2026.08.28")
    if data["consistent_users"] not in {"unknown", "none", "small", "large"}:
        raise ValueError("consistent_users must be unknown|none|small|large")
    return data


def git_tags(root: Path = ROOT) -> list[str]:
    try:
        cp = subprocess.run(
            ["git", "tag", "--list"], cwd=root, check=False,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
    except OSError:
        return []
    return [line.strip() for line in cp.stdout.splitlines() if line.strip()]


def has_release(state: dict, root: Path = ROOT) -> tuple[bool, str]:
    if state["release"].get("made") is True:
        return True, "policy/project-state.json declares a release"
    tags = git_tags(root)
    if tags:
        return True, f"Git tags observed: {', '.join(tags[:3])}"
    return False, "no declared release and no Git tags observed"


def contains_placeholder(path: Path, tokens=("TBD", "STATUS: NOT_RELEASED", "STATUS: NOT_APPLICABLE_UNTIL_FIRST_RELEASE")) -> bool:
    if not path.exists():
        return True
    text = path.read_text(encoding="utf-8", errors="replace")
    return any(t in text for t in tokens)


def source_files_present(root: Path = ROOT) -> bool:
    src = root / "src"
    if not src.exists():
        return False
    return any(p.is_file() and p.name != ".gitkeep" for p in src.rglob("*"))


def recognized_license(root: Path = ROOT) -> bool:
    return any((root / name).exists() for name in ("LICENSE", "COPYING", "LICENSES"))


def findings(state: dict, root: Path = ROOT) -> list[Finding]:
    f: list[Finding] = []
    level = state["osps_target_level"]
    released, release_evidence = has_release(state, root)

    # Local Level 1 evidence.
    f.append(Finding(PASS if (root/"CONTRIBUTING.md").exists() else GAP,
                     "OSPS-GV-03.01", "Contribution process is versioned." if (root/"CONTRIBUTING.md").exists() else "CONTRIBUTING.md is missing."))
    f.append(Finding(PASS if recognized_license(root) else GAP,
                     "OSPS-LE-03.01", "Recognized license location exists." if recognized_license(root) else "Select and commit the project license in a recognized location."))

    # Platform facts cannot be proved locally.
    for control, msg in [
        ("OSPS-AC-01.01", "MFA enforcement must be verified on the authoritative repository/platform."),
        ("OSPS-AC-02.01", "Collaborator least-privilege defaults must be verified on the platform."),
        ("OSPS-AC-03.01", "Primary-branch direct-commit protection must be verified via repository rules/branch protection."),
        ("OSPS-AC-03.02", "Primary-branch deletion protection must be verified on the platform."),
    ]:
        f.append(Finding(UNKNOWN, control, msg))

    # Implementation means a project test suite should no longer be just the template tests.
    if source_files_present(root):
        project_tests = [p for p in (root/"tests").glob("test_*.py") if p.name != "test_harness.py"]
        f.append(Finding(PASS if project_tests else GAP, "DORA-CI-ADAPTER",
                         "Project-specific tests found." if project_tests else "Implementation exists but only harness tests were found; add project-specific automated tests."))
    else:
        f.append(Finding(NA, "DORA-CI-ADAPTER", "No project implementation observed yet."))

    # Release-conditioned documentation.
    f.append(Finding(INFO, "RELEASE-TRIGGER", release_evidence))
    release_doc = root/"docs"/"RELEASE.md"
    readme = root/"README.md"
    if released:
        basic_usage_ok = readme.exists() and "STATUS: NOT_RELEASED" not in readme.read_text(encoding="utf-8", errors="replace")
        f.append(Finding(PASS if basic_usage_ok else GAP, "OSPS-DO-01.01", "Basic user guidance updated." if basic_usage_ok else "First release observed: replace bootstrap usage placeholder with real basic user guidance."))
        f.append(Finding(PASS if not contains_placeholder(release_doc) else GAP, "RELEASE-DOC-ADAPTER", "Release documentation placeholders cleared." if not contains_placeholder(release_doc) else "First release observed: complete docs/RELEASE.md for applicable release-conditioned controls."))
    else:
        f.append(Finding(NA, "OSPS-DO-01.01", "Applies when the project has made a release."))
        f.append(Finding(NA, "RELEASE-DOC-ADAPTER", "Release-conditioned documentation not activated."))

    # Level 2/3 local checks.
    if level >= 2:
        workflow = root/".github"/"workflows"/"verify.yml"
        f.append(Finding(PASS if workflow.exists() else GAP, "OSPS-QA-06.01", "CI verification workflow exists; hosted execution must still be observed." if workflow.exists() else "Level 2 target requires an automated test suite in CI before acceptance."))
        security = (root/"SECURITY.md").read_text(encoding="utf-8", errors="replace") if (root/"SECURITY.md").exists() else ""
        f.append(Finding(GAP if "PRIVATE_REPORTING_CHANNEL_NOT_CONFIGURED" in security else PASS,
                         "OSPS-VM-03.01", "Configure a real private vulnerability-reporting channel." if "PRIVATE_REPORTING_CHANNEL_NOT_CONFIGURED" in security else "Private vulnerability-reporting procedure is documented."))
    else:
        f.append(Finding(NA, "OSPS-QA-06.01", "Local adapter activates this check at OSPS target Level 2+."))
        f.append(Finding(NA, "OSPS-VM-03.01", "Control applies to OSPS Level 2+."))

    if level >= 3:
        testing = (root/"docs"/"TESTING.md").read_text(encoding="utf-8", errors="replace") if (root/"docs"/"TESTING.md").exists() else ""
        f.append(Finding(PASS if "Canonical local verification" in testing else GAP,
                         "OSPS-QA-06.02", "Test execution documentation found." if "Canonical local verification" in testing else "Document when and how tests run."))
        f.append(Finding(UNKNOWN, "OSPS-VM-05.*", "Level 3 SCA policy/enforcement requires technology-specific configuration and hosted evidence."))
        f.append(Finding(UNKNOWN, "OSPS-VM-06.*", "Level 3 SAST policy/enforcement requires technology-specific configuration and hosted evidence."))
        if released:
            f.append(Finding(UNKNOWN, "OSPS-QA-02.02", "For compiled released assets, verify that an SBOM is produced and delivered."))
        else:
            f.append(Finding(NA, "OSPS-QA-02.02", "SBOM release condition not activated."))
    else:
        f.append(Finding(NA, "OSPS-QA-06.02", "Control applies to OSPS Level 3."))

    # Maturity reassessment signal; never auto-promotes.
    if state["project_kind"] == "code" and state["maintainers_count"] >= 2 and state["consistent_users"] in {"small", "large"} and level < 2:
        f.append(Finding(REASSESS, "OSPS-MATURITY", "Recorded facts now match the OSPS Level 2 audience description; reassess target level rather than auto-promoting."))
    if state["project_kind"] == "code" and state["consistent_users"] == "large" and level < 3:
        f.append(Finding(REASSESS, "OSPS-MATURITY", "Recorded user population is 'large'; reassess Level 3 applicability rather than auto-promoting."))

    f.append(Finding(INFO, "PRODUCT-STAGE", f"product_stage={state['product_stage']} is descriptive only and has no normative effect."))
    return f


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="return non-zero when applicable local GAPs exist")
    args = ap.parse_args(argv)
    try:
        state = load_state()
    except Exception as exc:
        print(f"GAP STATE {exc}")
        return 2

    fs = findings(state)
    print(f"OSPS_BASELINE={state['osps_baseline_version']}")
    print(f"OSPS_TARGET_LEVEL={state['osps_target_level']}")
    print(f"PRODUCT_STAGE={state['product_stage']} (non-normative)")
    print("---")
    for x in fs:
        print(f"{x.status:30} {x.control:20} {x.message}")

    gaps = [x for x in fs if x.status == GAP]
    reassess = [x for x in fs if x.status == REASSESS]
    print("---")
    print(f"LOCAL_GAPS={len(gaps)}")
    print(f"MATURITY_REASSESSMENT_SIGNALS={len(reassess)}")
    if not state["enforce_local_gaps"]:
        print("ENFORCEMENT=REPORT_ONLY (set policy/project-state.json enforce_local_gaps=true when bootstrap gates are ready)")
    else:
        print("ENFORCEMENT=ENABLED")

    if (args.strict or state["enforce_local_gaps"]) and gaps:
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
