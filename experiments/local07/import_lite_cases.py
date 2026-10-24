"""Import selected SWE-bench Lite issues, keeping benchmark gold outside model inputs.

Explicit CLI only; dataset-server rows API. Never checks out or runs downloaded code.
"""
import argparse
import json
import pathlib
import re
import urllib.parse
import urllib.request

DATASET = "princeton-nlp/SWE-bench_Lite"
ALLOWED = {
    "marshmallow-code__marshmallow-1343",
    "marshmallow-code__marshmallow-1359",
    "pvlib__pvlib-python-1072",
}
API = "https://datasets-server.huggingface.co/rows"
PATCH_HEADER = re.compile(r"^diff --git a/([^\r\n]+) b/([^\r\n]+)$", re.MULTILINE)
SHA = re.compile(r"^[0-9a-f]{40}$")


def target_paths(patch):
    result = []
    for before, after in PATCH_HEADER.findall(patch):
        if before != after or not before.endswith(".py") or before.startswith("/") or ".." in pathlib.PurePosixPath(before).parts:
            raise ValueError("UNSAFE_REFERENCE_PATCH_PATH")
        if before not in result:
            result.append(before)
    if not result:
        raise ValueError("NO_TARGET_FILES")
    return result


def transform(row, expected_id):
    if row.get("instance_id") != expected_id:
        raise ValueError("INSTANCE_ID_MISMATCH")
    base = row.get("base_commit")
    statement = row.get("problem_statement")
    if not isinstance(base, str) or not SHA.fullmatch(base):
        raise ValueError("INVALID_BASE_COMMIT")
    if not isinstance(statement, str) or not statement.strip() or len(statement) > 32000:
        raise ValueError("INVALID_PROBLEM_STATEMENT")
    issue = {"schema": 1, "issue_id": expected_id, "base_commit": base, "problem_statement": statement}
    evaluator = {"schema": 1, "issue_id": expected_id, "target_files": target_paths(row.get("patch", ""))}
    return issue, evaluator


def get_rows(split):
    query = urllib.parse.urlencode({"dataset": DATASET, "config": "default", "split": split,
                                    "offset": 0, "length": 100})
    request = urllib.request.Request(API + "?" + query, headers={"User-Agent": "local13-repro/1"})
    with urllib.request.urlopen(request, timeout=35) as response:
        payload = response.read(4_000_000 + 1)
    if len(payload) > 4_000_000:
        raise ValueError("DATASET_RESPONSE_TOO_LARGE")
    data = json.loads(payload)
    if not isinstance(data.get("num_rows_total"), int) or not isinstance(data.get("rows"), list):
        raise ValueError("DATASET_RESPONSE_INVALID")
    return data


def fetch_selected():
    found = {}
    for split in ("dev", "test"):
        offset = 0
        while True:
            query = urllib.parse.urlencode({"dataset": DATASET, "config": "default",
                                            "split": split, "offset": offset, "length": 100})
            req = urllib.request.Request(API + "?" + query, headers={"User-Agent": "local13-repro/1"})
            with urllib.request.urlopen(req, timeout=35) as response:
                raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise ValueError("DATASET_RESPONSE_TOO_LARGE")
            data = json.loads(raw)
            rows = data.get("rows")
            total = data.get("num_rows_total")
            if not isinstance(rows, list) or not isinstance(total, int) or total < 0 or total > 5000:
                raise ValueError("DATASET_RESPONSE_INVALID")
            for item in rows:
                row = item.get("row", {})
                ident = row.get("instance_id")
                if ident in ALLOWED:
                    if ident in found:
                        raise ValueError("DUPLICATE_INSTANCE")
                    found[ident] = (split, *transform(row, ident))
            offset += len(rows)
            if offset >= total:
                break
            if not rows:
                raise ValueError("DATASET_EMPTY_PAGE")
        if len(found) == len(ALLOWED):
            break
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    root = pathlib.Path(args.output_dir).resolve()
    if root.exists() and any(root.iterdir()):
        parser.error("output-dir must be absent or empty (fail-closed, no overwrite)")
    found = fetch_selected()
    if set(found) != ALLOWED:
        raise ValueError("DATASET_INCOMPLETE: " + ",".join(sorted(ALLOWED - set(found))))
    root.mkdir(parents=True, exist_ok=True)
    summary = {"schema": 1, "dataset": DATASET, "cases": []}
    for ident in sorted(found):
        split, issue, evaluator = found[ident]
        folder = root / ident
        folder.mkdir()
        (folder / "issue.json").write_text(json.dumps(issue, indent=2) + "\n", encoding="utf-8")
        (folder / "evaluator.json").write_text(json.dumps(evaluator, indent=2) + "\n", encoding="utf-8")
        summary["cases"].append({"id": ident, "split": split, "base_commit": issue["base_commit"]})
    (root / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
