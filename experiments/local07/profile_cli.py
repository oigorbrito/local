"""Explicit profile CLI using the existing LOCAL-09 and LOCAL-07 pipeline."""
import argparse
import json
import pathlib
from model_profiles import PROFILES, select_profile
from executor_bridge import prepare, replay
from ollama_adapter import generate

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true")
    p.add_argument("--profile", choices=tuple(PROFILES))
    for key in ("repo", "issue-json", "report", "patch"):
        p.add_argument("--" + key)
    p.add_argument("--timeout", type=int, default=180)
    args = p.parse_args()
    if args.list:
        print(json.dumps({k: vars(v) for k, v in PROFILES.items()}, indent=2))
        return
    if not args.profile or not all((args.repo, args.issue_json, args.report, args.patch)):
        p.error("Specify --profile, --repo, --issue-json, --report and --patch")
    if not 1 <= args.timeout <= 420:
        p.error("timeout must be between 1 and 420 seconds")
    profile = select_profile(args.profile)
    issue = json.loads(pathlib.Path(args.issue_json).read_text(encoding="utf-8"))["problem_statement"]
    request = prepare(args.repo, issue)
    payload = generate(request, profile.base_model, timeout=args.timeout)
    report, patch = replay(args.repo, issue, payload)
    report["profile"] = profile.name
    report["base_model"] = profile.base_model
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    pathlib.Path(args.patch).write_text(patch, encoding="utf-8", newline="\n")
    print(json.dumps({"profile": profile.name, "status": report["status"]}))

if __name__ == "__main__":
    main()
