"""LOCAL-18: bounded localized edits and legacy full-source replay.

External providers produce JSON {schema:1, file:<allowlisted>, content:<full Python source>}.
The bridge never evaluates the generated source in-process. It passes it to the
LOCAL-07 isolated patch validator. A file-backed adapter makes replay reproducible.
"""
import argparse
import json
import pathlib
import sys
from dataclasses import dataclass

from integrated_edit import assess
from retrieve_context import retrieve

MAX_RESPONSE_BYTES = 256 * 1024
MAX_SOURCE_CHARS = 160_000
MAX_ISSUE_CHARS = 32_000
MAX_EDIT_CHARS = 8192


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class Request:
    issue: str
    selected_files: tuple[str, ...]
    context: tuple[dict, ...]

    def to_json(self):
        return {"schema": 1, "issue": self.issue,
                "allowed_files": list(self.selected_files),
                "context": list(self.context),
                "output_contract": {"schema": 1, "file": "one of allowed_files",
                                    "content": "complete replacement Python source"}}


def prepare(repo, issue, *, max_chars=9000):
    if not isinstance(issue, str) or not issue.strip() or len(issue) > MAX_ISSUE_CHARS:
        raise ContractError("INVALID_ISSUE")
    r = retrieve(repo, issue, max_chars=max_chars)
    selected = tuple(r["selected_files"][:2])
    if not selected:
        raise ContractError("NO_RETRIEVED_FILES")
    return Request(issue, selected, tuple(x for x in r["results"] if x["path"] in selected))


def parse_response(payload, allowed_files):
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ContractError("RESPONSE_TOO_LARGE")
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as e:
        raise ContractError("INVALID_JSON") from e
    if isinstance(raw, dict) and raw.get("schema") == 2:
        if set(raw) != {"schema", "file", "old", "new"} or type(raw["schema"]) is not int:
            raise ContractError("SCHEMA_MISMATCH")
        if not isinstance(raw["file"], str) or raw["file"] not in allowed_files:
            raise ContractError("FILE_NOT_ALLOWED")
        if any(not isinstance(raw[k], str) for k in ("old", "new")):
            raise ContractError("INVALID_EDIT")
        if not raw["old"] or len(raw["old"]) > MAX_EDIT_CHARS or len(raw["new"]) > MAX_EDIT_CHARS:
            raise ContractError("INVALID_EDIT")
        return raw["file"], raw
    if not isinstance(raw, dict) or set(raw) != {"schema", "file", "content"} or type(raw["schema"]) is not int or raw["schema"] != 1:
        raise ContractError("SCHEMA_MISMATCH")
    if not isinstance(raw["file"], str) or raw["file"] not in allowed_files:
        raise ContractError("FILE_NOT_ALLOWED")
    if not isinstance(raw["content"], str) or len(raw["content"]) > MAX_SOURCE_CHARS:
        raise ContractError("INVALID_CONTENT")
    return raw["file"], raw["content"]


def replay(repo, issue, response_bytes):
    request = prepare(repo, issue)
    path, source = parse_response(response_bytes, request.selected_files)
    if isinstance(source, dict):
        root = pathlib.Path(repo).resolve()
        target = root.joinpath(*pathlib.PurePosixPath(path).parts)
        if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(root):
            raise ContractError("INVALID_TARGET")
        original = target.read_bytes()
        try:
            content = original.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractError("INVALID_SOURCE_ENCODING") from exc
        if content.count(source["old"]) != 1:
            raise ContractError("EDIT_ANCHOR_NOT_UNIQUE")
        source = content.replace(source["old"], source["new"], 1)
    report, patch = assess(repo, issue, path, source, max_files=2)
    return {"schema": 1, "status": report["result"],
            "request": request.to_json(), "validation": report}, patch


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--issue-json", required=True)
    p.add_argument("--response-json", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--patch", required=True)
    a = p.parse_args()
    issue_file = pathlib.Path(a.issue_json)
    issue = json.loads(issue_file.read_text(encoding="utf-8"))["problem_statement"]
    # Read a bounded response without loading arbitrarily large files.
    with pathlib.Path(a.response_json).open("rb") as f:
        response = f.read(MAX_RESPONSE_BYTES + 1)
    result, patch = replay(a.repo, issue, response)
    pathlib.Path(a.report).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pathlib.Path(a.patch).write_text(patch, encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "sha256": result["validation"]["patch_sha256"]}))


if __name__ == "__main__":
    main()
