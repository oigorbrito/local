"""LOCAL-12: independent, non-executing semantic checker for the fixed LOCAL-11 fixture.

Never executes generated Python or imports candidate modules. Restricts AST to a tiny
whitelist and interprets only the pure sum(items)+integer expression. This is a
functional *fixture* oracle, not SWE-bench and not general Python test execution.
"""
import argparse
import ast
import hashlib
import json
import pathlib

CASES = [([], 1), ([1], 2), ([2, 3], 6), ([-4, 4, 5], 6)]


def evaluate_fixture(content: str):
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {"status": "SYNTAX_INVALID", "passed": 0, "total": len(CASES)}
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        return {"status": "UNSUPPORTED_AST", "passed": 0, "total": len(CASES)}
    fn = tree.body[0]
    args = fn.args
    if (fn.name != "calculate_total" or len(args.posonlyargs) != 0 or
        len(args.args) != 1 or args.args[0].arg != "items" or
        args.vararg or args.kwarg or args.kwonlyargs or args.defaults or
        args.kw_defaults or fn.decorator_list or
        len(fn.body) != 1 or not isinstance(fn.body[0], ast.Return)):
        return {"status": "UNSUPPORTED_AST", "passed": 0, "total": len(CASES)}

    def interpret(node, items):
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return interpret(node.left, items) + interpret(node.right, items)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "sum" and len(node.args) == 1 and
            not node.keywords and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "items"):
            return sum(items)
        raise ValueError("UNSUPPORTED_AST")

    try:
        got = [interpret(fn.body[0].value, xs) for xs, _ in CASES]
    except (ValueError, TypeError):
        return {"status": "UNSUPPORTED_AST", "passed": 0, "total": len(CASES)}
    passed = sum(type(actual) is int and actual == expected
                 for actual, (_, expected) in zip(got, CASES))
    return {"status": "FIXTURE_PASS" if passed == len(CASES) else "FIXTURE_FAIL",
            "passed": passed, "total": len(CASES),
            "expected": [expected for _, expected in CASES], "actual": got}


def grade_response_file(path):
    data = pathlib.Path(path).read_bytes()
    if len(data) > 256 * 1024:
        raise ValueError("RESPONSE_TOO_LARGE")
    obj = json.loads(data)
    if (not isinstance(obj, dict) or set(obj) != {"schema", "file", "content"}
        or type(obj.get("schema")) is not int or obj["schema"] != 1
        or obj["file"] != "calculator.py" or not isinstance(obj["content"], str)):
        raise ValueError("RESPONSE_CONTRACT_INVALID")
    result = evaluate_fixture(obj["content"])
    result.update(schema=1, gate="LOCAL-12",
                  response_sha256=hashlib.sha256(data).hexdigest(),
                  generated_code_executed=False,
                  general_issue_resolution="NOT_EVALUATED")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--response-json", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    result = grade_response_file(a.response_json)
    dest = pathlib.Path(a.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "passed": result["passed"],
                      "total": result["total"], "output": str(dest)}))
    return 0 if result["status"] == "FIXTURE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
