"""LOCAL-17: bounded AST *simulation* of a preregistered real bug.

Does not import, compile, eval, exec, or invoke any model-produced source.
Implements a deliberately small, documented subset of Path/if/raise/return,
using a deterministic fake filesystem. Unsupported candidates are INCONCLUSIVE,
not counted as solved. A passing simulation is NOT real issue resolution.
"""
import argparse
import ast
import hashlib
import json
import pathlib
import re
import sys

from executor_bridge import ContractError, MAX_RESPONSE_BYTES, parse_response
from local16_workflow import check as check_session, load as load_session, read_bounded
from local17_real_issue_trial import (
    CASE_ID, DESCRIPTION, PINNED_COMMIT, PROFILE, TARGET_PATH,
    verify_pinned_source,
)
from model_profiles import PROFILES

ORACLE_VERSION = 1
MAX_NODES = 1200
MAX_STEPS = 250
REPORT_STATUS = "STATIC_BEHAVIOR_CASES_PASS_NOT_RESOLVED"
ERROR_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,100}$")


class Unsupported(Exception):
    pass


class RaisedContract(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class FakePath:
    """A tiny symbolic model: resolve() dereferences symlinks before checks."""
    __slots__ = ("inside", "link", "missing")

    def __init__(self, *, inside=False, link=False, missing=False):
        self.inside = inside
        self.link = link
        self.missing = missing

    def resolve(self):
        return FakePath(inside=self.inside, link=False, missing=self.missing)

    def is_symlink(self):
        return self.link

    def is_relative_to(self, other):
        if not isinstance(other, FakePath):
            raise Unsupported("INVALID_SYMBOLIC_ROOT")
        return self.inside

    def __bool__(self):
        return True


class ModulePath:
    __slots__ = ()

    @staticmethod
    def Path(value):
        if type(value) is not FakePath:
            raise Unsupported("INVALID_PATH_CONSTRUCTION")
        return value


def method_call(node, values):
    if node.keywords:
        raise Unsupported("KEYWORD_CALL_UNSUPPORTED")
    if not isinstance(node.func, ast.Attribute) or node.func.attr.startswith("_"):
        raise Unsupported("CALL_NOT_ALLOWED")
    obj = expression(node.func.value, values)
    name = node.func.attr
    if obj is ModulePath and name == "Path" and len(node.args) == 1:
        return ModulePath.Path(expression(node.args[0], values))
    if type(obj) is FakePath:
        if name == "resolve" and not node.args:
            return obj.resolve()
        if name == "is_symlink" and not node.args:
            return obj.is_symlink()
        if name == "is_relative_to" and len(node.args) == 1:
            return obj.is_relative_to(expression(node.args[0], values))
    raise Unsupported("CALL_NOT_ALLOWED")


def expression(node, values):
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise Unsupported("UNBOUND_NAME")
        return values[node.id]
    if isinstance(node, ast.Constant) and type(node.value) in (str, bool):
        return node.value
    if isinstance(node, ast.Call):
        return method_call(node, values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not expression(node.operand, values)
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        if isinstance(node.op, ast.And):
            return all(bool(expression(x, values)) for x in node.values)
        return any(bool(expression(x, values)) for x in node.values)
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        if not isinstance(node.ops[0], (ast.Is, ast.IsNot, ast.Eq, ast.NotEq)):
            raise Unsupported("COMPARISON_NOT_ALLOWED")
        left = expression(node.left, values)
        right = expression(node.comparators[0], values)
        if type(left) not in (str, bool) or type(right) not in (str, bool):
            raise Unsupported("COMPARISON_NOT_ALLOWED")
        equal = left == right
        return equal if isinstance(node.ops[0], (ast.Is, ast.Eq)) else not equal
    raise Unsupported("EXPRESSION_NOT_ALLOWED")


def statements(nodes, values, budget):
    for stmt in nodes:
        budget[0] += 1
        if budget[0] > MAX_STEPS:
            raise Unsupported("STEP_BUDGET_EXCEEDED")
        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                raise Unsupported("ASSIGNMENT_NOT_ALLOWED")
            name = stmt.targets[0].id
            if name in {"path", "root", "pathlib", "Path", "ContractError"}:
                raise Unsupported("RESERVED_NAME_ASSIGNMENT")
            values[name] = expression(stmt.value, values)
        elif isinstance(stmt, ast.If):
            body = stmt.body if expression(stmt.test, values) else stmt.orelse
            outcome = statements(body, values, budget)
            if outcome is not None:
                return outcome
        elif isinstance(stmt, ast.Raise):
            call = stmt.exc
            if (not isinstance(call, ast.Call) or
                not isinstance(call.func, ast.Name) or
                call.func.id != "ContractError" or
                len(call.args) != 1 or call.keywords or stmt.cause is not None):
                raise Unsupported("RAISE_NOT_ALLOWED")
            code = expression(call.args[0], values)
            if not isinstance(code, str) or not ERROR_RE.fullmatch(code):
                raise Unsupported("RAISE_CODE_INVALID")
            raise RaisedContract(code)
        elif isinstance(stmt, ast.Return):
            return ("returned", expression(stmt.value, values))
        elif isinstance(stmt, ast.Pass):
            continue
        else:
            raise Unsupported("STATEMENT_NOT_ALLOWED")
    return None


def target_function(source):
    if not isinstance(source, str) or len(source) > 160000:
        raise Unsupported("SOURCE_SIZE_INVALID")
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        raise Unsupported("INVALID_PYTHON_SYNTAX") from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES * 100:
        raise Unsupported("AST_TOO_LARGE")
    matches = [x for x in tree.body if isinstance(x, ast.FunctionDef)
               and x.name == "_external_path"]
    if len(matches) != 1:
        raise Unsupported("TARGET_FUNCTION_MISSING_OR_AMBIGUOUS")
    fn = matches[0]
    if (len(fn.args.args) != 2 or [a.arg for a in fn.args.args] != ["path", "root"]
            or fn.args.posonlyargs or fn.args.kwonlyargs or
            fn.args.vararg or fn.args.kwarg or fn.args.defaults or fn.decorator_list):
        raise Unsupported("FUNCTION_SIGNATURE_UNSUPPORTED")
    if sum(1 for _ in ast.walk(fn)) > MAX_NODES:
        raise Unsupported("TARGET_AST_TOO_LARGE")
    return tree, fn


def normalize_outside(tree):
    return [ast.dump(x, include_attributes=False) for x in tree.body
            if not (isinstance(x, ast.FunctionDef) and x.name == "_external_path")]


def assess_source(candidate_source, original_source):
    try:
        tree, target = target_function(candidate_source)
        original_tree, original_target = target_function(original_source)
        if normalize_outside(tree) != normalize_outside(original_tree):
            raise Unsupported("OUTSIDE_TARGET_AST_CHANGED")
        if (ast.dump(target.args, include_attributes=False)
                != ast.dump(original_target.args, include_attributes=False)):
            raise Unsupported("FUNCTION_SIGNATURE_CHANGED")
    except Unsupported as exc:
        return {"status": "STATIC_ORACLE_INCONCLUSIVE",
                "reason": str(exc), "passed": 0, "total": 4,
                "candidate_executed": False}

    cases = (
        ("external_symlink_rejected", FakePath(link=True), "EVIDENCE_SYMLINK_FORBIDDEN"),
        ("external_file_accepted", FakePath(), "EXTERNAL_PATH"),
        ("inside_file_rejected", FakePath(inside=True), "EVIDENCE_INSIDE_SOURCE_REPOSITORY"),
        ("missing_external_path_preserved", FakePath(missing=True), "EXTERNAL_PATH"),
    )
    results = {}
    for name, source_path, expected in cases:
        values = {"path": source_path, "root": FakePath(inside=True),
                  "pathlib": ModulePath, "Path": ModulePath.Path}
        try:
            outcome = statements(target.body, values, [0])
            if (isinstance(outcome, tuple) and outcome[0] == "returned"
                    and type(outcome[1]) is FakePath and
                    not outcome[1].inside and not outcome[1].link):
                observed = "EXTERNAL_PATH"
            else:
                observed = "WRONG_RETURN"
        except RaisedContract as exc:
            observed = exc.code
        except Unsupported as exc:
            return {"status": "STATIC_ORACLE_INCONCLUSIVE",
                    "reason": str(exc), "passed": 0, "total": len(cases),
                    "candidate_executed": False}
        results[name] = {"passed": observed == expected,
                         "observed": observed, "expected": expected}
    passed = sum(x["passed"] for x in results.values())
    return {"status": REPORT_STATUS if passed == len(cases) else "STATIC_BEHAVIOR_FAIL",
            "passed": passed, "total": len(cases), "cases": results,
            "candidate_executed": False}


def evaluate_session(session):
    # Full provenance + the reviewed patch gate come before the static oracle.
    reviewed = check_session(session)
    path, root, manifest, issue, request = load_session(session)
    if (manifest["source_commit"] != PINNED_COMMIT
            or issue["problem_statement"] != DESCRIPTION
            or manifest["profile"] != PROFILES[PROFILE].manifest()
            or TARGET_PATH not in request["allowed_files"]
            or reviewed["path"] != TARGET_PATH):
        raise ContractError("LOCAL17_CASE_PROVENANCE_MISMATCH")
    verify_pinned_source(root)
    blob = read_bounded(path / "response.json", MAX_RESPONSE_BYTES)
    target, candidate = parse_response(blob, request["allowed_files"])
    if target != TARGET_PATH:
        raise ContractError("LOCAL17_CANDIDATE_SCOPE_MISMATCH")
    baseline = root.joinpath(*pathlib.PurePosixPath(TARGET_PATH).parts).read_text(
        encoding="utf-8"
    )
    verdict = assess_source(candidate, baseline)
    return {
        "schema": ORACLE_VERSION, "gate": "LOCAL-17-STATIC-ORACLE",
        "case_id": CASE_ID, "base_commit": PINNED_COMMIT,
        "source_path": TARGET_PATH,
        "profile": PROFILE,
        "generation_mode": json.loads(read_bounded(path / "report.json"))["execution"]["mode"],
        "patch_sha256": reviewed["patch_sha256"],
        "response_sha256": hashlib.sha256(blob).hexdigest(),
        "patch_review_status": reviewed["status"],
        **verdict,
        "functional_execution": "NOT_RUN",
        "issue_resolved": "NOT_EVALUATED",
        "host_candidate_code_executed": False,
        "official_benchmark": "NOT_EVALUATED"
    }


def main():
    parser = argparse.ArgumentParser(description="LOCAL-17 finite static AST simulation, no candidate execution")
    parser.add_argument("--session", required=True)
    parser.add_argument("--output", help="Optional new JSON report; refuses overwrite")
    args = parser.parse_args()
    try:
        result = evaluate_session(args.session)
        if args.output:
            path = pathlib.Path(args.output)
            if path.exists() or path.is_symlink() or not path.parent.is_dir():
                raise ContractError("ORACLE_OUTPUT_COLLISION")
            with path.open("xb") as stream:
                stream.write((json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == REPORT_STATUS else 2
    except (ContractError, Unsupported, OSError, ValueError, KeyError,
            UnicodeError, json.JSONDecodeError) as exc:
        code = str(exc)
        if not ERROR_RE.fullmatch(code):
            code = "STATIC_ORACLE_INFRA_FAILURE"
        print(json.dumps({"status": "BLOCKED", "reason": code,
                          "issue_resolved": "NOT_EVALUATED"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
