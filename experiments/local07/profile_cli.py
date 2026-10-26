"""LOCAL-16: reproducible local model invocation and non-executing patch output.

No generated source is run or applied to the input checkout. Existing LOCAL-07
worktree patch gate remains the sole patch validator.
"""
import argparse
import json
import pathlib
import hashlib

from executor_bridge import MAX_RESPONSE_BYTES, ContractError, prepare, replay
from integrated_edit import git
from model_profiles import PROFILES, select_profile
from ollama_adapter import generate

def provenance(repo):
    root = pathlib.Path(repo).resolve()
    if not (root / ".git").exists():
        raise ContractError("REQUIRES_GIT_CHECKOUT")
    if git(root, "status", "--porcelain").strip():
        raise ContractError("DIRTY_SOURCE_REPOSITORY")
    return git(root, "rev-parse", "HEAD").strip()

def distinct_output_paths(inputs, outputs):
    normalized = [pathlib.Path(x).resolve() for x in (*inputs, *outputs) if x is not None]
    if len(normalized) != len(set(normalized)):
        raise ContractError("INPUT_OUTPUT_PATH_COLLISION")

def guard_output_locations(repo, outputs):
    """Never clobber saved evidence or write results into the source repository."""
    root = pathlib.Path(repo).resolve()
    for output in outputs:
        if output is None:
            continue
        path = pathlib.Path(output)
        resolved = path.resolve()
        if resolved.is_relative_to(root):
            raise ContractError("OUTPUT_INSIDE_SOURCE_REPOSITORY")
        if path.is_symlink() or path.exists():
            raise ContractError("OUTPUT_ALREADY_EXISTS")
        if not resolved.parent.is_dir():
            raise ContractError("OUTPUT_DIRECTORY_MISSING")


def save_outputs(payloads):
    """Create outputs exclusively; roll back this invocation's partial writes."""
    created = []
    try:
        for path, body in payloads:
            destination = pathlib.Path(path)
            with destination.open("xb") as stream:
                created.append(destination)
                stream.write(body)
                stream.flush()
    except BaseException:
        for destination in created:
            destination.unlink(missing_ok=True)
        raise


def run(repo, issue_json, profile_name, report_path, patch_path, *,
        timeout=180, offline_response_json=None, response_json_path=None,
        stage_callback=None):
    def stage(value):
        if stage_callback is not None:
            stage_callback(value)
    stage('PREPARATION')
    if type(timeout) is not int or not 1 <= timeout <= 420:
        raise ContractError("INVALID_TIMEOUT")
    profile = select_profile(profile_name)
    distinct_output_paths(
        [issue_json, offline_response_json],
        [report_path, patch_path, response_json_path]
    )
    guard_output_locations(repo, [report_path, patch_path, response_json_path])
    before = provenance(repo)
    issue = json.loads(pathlib.Path(issue_json).read_text(encoding="utf-8"))["problem_statement"]
    request = prepare(repo, issue, output_schema=profile.output_schema)

    def preserve_response(payload):
        """Persist bounded returned bytes before source and patch validation."""
        if response_json_path is not None:
            if len(payload) > MAX_RESPONSE_BYTES:
                raise ContractError("RESPONSE_TOO_LARGE")
            save_outputs([(response_json_path, payload)])

    if offline_response_json is None:
        stage('MODEL_REQUEST_OR_RESPONSE')
        payload = generate(
            request, profile.base_model, timeout=timeout,
            system=profile.system, options=profile.options
        )
        mode = "local_inference"
    else:
        with pathlib.Path(offline_response_json).open("rb") as stream:
            payload = stream.read(MAX_RESPONSE_BYTES + 1)
        mode = "offline_replay"
    # Record the returned reply before the source and patch validation gates.
    # Never overwrite a response already saved in this session.
    if response_json_path is not None and not pathlib.Path(response_json_path).is_file():
        preserve_response(payload)
    stage('RESPONSE_VALIDATION')
    if before != provenance(repo):
        raise ContractError("SOURCE_CHANGED_DURING_GENERATION")
    validation, patch = replay(repo, issue, payload,
                               output_schema=profile.output_schema)
    validation["execution"] = {
        "mode": mode, "model_invoked": mode == "local_inference",
        "selected_profile": profile.manifest(),
        "system_policy_sha256": profile.fingerprint,
        "response_sha256": hashlib.sha256(payload).hexdigest()
    }
    artifacts = [
        (patch_path, patch.encode("utf-8")),
        (report_path, (json.dumps(validation, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    ]
    stage('PERSISTENCE')
    save_outputs(artifacts)
    return validation

def main():
    p = argparse.ArgumentParser(description="LOCAL-16: explicit, constrained local editor")
    p.add_argument("--list", action="store_true")
    p.add_argument("--profile", choices=tuple(PROFILES))
    for name in ("repo", "issue-json", "report", "patch"):
        p.add_argument("--" + name)
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--offline-response-json", default=None,
                   help="Replay saved model JSON without contacting Ollama")
    p.add_argument("--response-json-path", default=None,
                   help="Store response only after valid patch output")
    args = p.parse_args()
    if args.list:
        print(json.dumps({name: p.manifest() for name, p in PROFILES.items()}, indent=2))
        return
    if not args.profile or not all((args.repo, args.issue_json, args.report, args.patch)):
        p.error("Specify --profile --repo --issue-json --report --patch")
    result = run(
        args.repo, args.issue_json, args.profile, args.report, args.patch,
        timeout=args.timeout, offline_response_json=args.offline_response_json,
        response_json_path=args.response_json_path
    )
    print(json.dumps({
        "status": result["status"], "mode": result["execution"]["mode"],
        "profile": args.profile,
        "patch_sha256": result["validation"]["patch_sha256"]
    }))

if __name__ == "__main__":
    main()
