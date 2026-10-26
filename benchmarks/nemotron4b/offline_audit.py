#!/usr/bin/env python3
"""Reproduce LOCAL-09 rejected edits using preserved responses; never call Ollama."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import traceback

TASK = (
    "Fix guard.py read_text_under_root(root, relative_path): allow files "
    "inside root, but reject absolute paths, ../ traversal and symbolic links "
    "that resolve outside root with ValueError or PermissionError. "
    "Do not modify tests. Run tests to check your fix."
)


def run(argv, cwd=None, timeout=35, input_bytes=None):
    try:
        p = subprocess.run(argv, cwd=cwd, input=input_bytes,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout)
        return {"exit_code": p.returncode,
                "stdout": p.stdout.decode('utf-8', 'replace'),
                "stderr": p.stderr.decode('utf-8', 'replace')}
    except subprocess.TimeoutExpired as e:
        return {"exit_code": None,
                "stdout": (e.stdout or b'').decode('utf-8', 'replace'),
                "stderr": (e.stderr or b'').decode('utf-8', 'replace'),
                "timed_out": True}


def fixture_checkout(fixture, dest):
    shutil.copytree(fixture, dest)
    for cmd in (['git', 'init', '-q'],
                ['git', 'config', 'user.name', 'Fixture'],
                ['git', 'config', 'user.email', 'fixture@example.invalid'],
                ['git', 'add', '.'], ['git', 'commit', '-qm', 'fixture']):
        result = run(cmd, cwd=dest)
        if result['exit_code'] != 0:
            raise RuntimeError('fixture Git initialization failed: ' + result['stderr'])
    return dest


def raw_match(evidence, response_bytes, phase):
    metrics_file = evidence / 'relay-request-metrics.jsonl'
    if not metrics_file.is_file():
        return 'METRICS_MISSING'
    records = [json.loads(line) for line in metrics_file.read_text(encoding='utf8').splitlines()
               if line.strip()]
    records = [r for r in records if r.get('phase') == phase and
               r.get('raw_response') and r.get('path', '/api/generate') == '/api/generate']
    if len(records) != 1:
        return 'RAW_RESPONSE_COUNT_' + str(len(records))
    r = records[0]['raw_response']
    relative = r.get('relative_path', '')
    path = (evidence / relative).resolve()
    if not path.is_relative_to(evidence.resolve()) or not path.is_file():
        return 'RAW_PATH_INVALID'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != r.get('sha256'):
        return 'RAW_SHA256_MISMATCH'
    try:
        inner = json.loads(raw)['response'].encode('utf8')
    except (ValueError, KeyError, TypeError, AttributeError):
        return 'RAW_OUTER_JSON_INVALID'
    return 'MATCH' if inner == response_bytes else 'INNER_RESPONSE_MISMATCH'


def audit_trial(evidence, output, fixture, adapter, phase='r01-local09'):
    candidate = evidence / phase / 'model-response.json'
    result = {'evidence': evidence.name, 'phase': phase,
              'model_response_present': candidate.is_file()}
    if not candidate.is_file():
        return result
    if candidate.stat().st_size > 256 * 1024:
        result['status'] = 'RESPONSE_TOO_LARGE'
        return result
    raw_bytes = candidate.read_bytes()
    result['response_sha256'] = hashlib.sha256(raw_bytes).hexdigest()
    result['raw_response_link'] = raw_match(evidence, raw_bytes, phase)
    if result['raw_response_link'] != 'MATCH':
        result['status'] = 'RAW_RESPONSE_NOT_VERIFIED'
        return result
    try:
        data = json.loads(raw_bytes)
        if not isinstance(data, dict) or set(data) != {'schema', 'file', 'content'} \
                or type(data['schema']) is not int or data['schema'] != 1 \
                or data['file'] != 'guard.py' or not isinstance(data['content'], str):
            result['status'] = 'UNEXPECTED_CONTRACT'
            return result
        ast.parse(data['content'])
        content = data['content'] if data['content'].endswith('\n') else data['content'] + '\n'
    except (ValueError, SyntaxError, UnicodeError, TypeError, KeyError) as e:
        result['status'] = 'INVALID_CANDIDATE'
        result['error'] = str(e)[:1000]
        return result
    result['candidate_sha256'] = hashlib.sha256(content.encode('utf8')).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    # Recreate the production replay against a pristine copy.
    with tempfile.TemporaryDirectory(prefix='local27-forensic-') as tmp:
        replay_repo = fixture_checkout(fixture, Path(tmp) / 'replay')
        sys.path.insert(0, str(adapter))
        from executor_bridge import replay
        try:
            replay_report, original_patch = replay(replay_repo, TASK, raw_bytes)
            result['replay'] = {'status': 'ACCEPTED', 'report': replay_report,
                                'patch_sha256': hashlib.sha256(original_patch.encode()).hexdigest()}
            (output / 'replay.patch').write_text(original_patch, encoding='utf8')
        except Exception as exc:
            result['replay'] = {'status': 'REJECTED', 'error_type': type(exc).__name__,
                                'error': str(exc)[:2000]}
            patch_bytes = getattr(exc, 'patch_bytes', None)
            if isinstance(patch_bytes, bytes):
                (output / 'rejected-validator.patch').write_bytes(patch_bytes)
                index_check = run(['git', 'apply', '--cached', '--check', '-'],
                                  cwd=replay_repo, input_bytes=patch_bytes)
                result['replay']['rejected_patch'] = {
                    'sha256': hashlib.sha256(patch_bytes).hexdigest(),
                    'bytes': len(patch_bytes),
                    'index_recheck_exit': index_check['exit_code'],
                    'index_recheck_error': index_check['stderr'][:1000],
                }
            (output / 'replay-trace.log').write_text(traceback.format_exc(), encoding='utf8')
        # Independent evaluation only, not a bypass of production validation.
        direct_repo = fixture_checkout(fixture, Path(tmp) / 'direct')
        (direct_repo / 'guard.py').write_bytes(content.encode('utf8'))
        diff = run(['git', 'diff', '--binary', 'HEAD', '--'], cwd=direct_repo)
        if diff['exit_code'] != 0:
            raise RuntimeError('Git diff failed: ' + diff['stderr'])
        patch_bytes = diff['stdout'].encode('utf8')
        (output / 'candidate.patch').write_bytes(patch_bytes)
        index_check = run(['git', 'apply', '--cached', '--check', '-'],
                          cwd=direct_repo, input_bytes=patch_bytes)
        independent = run([sys.executable, '-B', '-m', 'unittest', 'discover',
                           '-s', 'tests', '-v'], cwd=direct_repo)
        (output / 'independent-tests.log').write_text(
            independent['stdout'] + independent['stderr'], encoding='utf8')
        result['direct'] = {
            'patch_sha256': hashlib.sha256(patch_bytes).hexdigest(),
            'patch_bytes': len(patch_bytes),
            'index_check_exit': index_check['exit_code'],
            'index_check_stderr': index_check['stderr'][:1000],
            'tests_exit': independent['exit_code'],
            'tests_timed_out': independent.get('timed_out', False),
            'functional_passed': bool(patch_bytes) and index_check['exit_code'] == 0
                                 and independent['exit_code'] == 0,
        }
    result['diagnosis'] = (
        'ORIGINAL_VALIDATOR_REJECTS_FUNCTIONAL_CANDIDATE'
        if result['replay']['status'] == 'REJECTED' and result['direct']['functional_passed']
        else 'VALIDATOR_ACCEPTED_FUNCTIONAL_CANDIDATE'
        if result['replay']['status'] == 'ACCEPTED' and result['direct']['functional_passed']
        else 'CANDIDATE_DID_NOT_PASS_INDEPENDENT_TESTS'
        if not result['direct']['functional_passed'] else 'REQUIRES_REVIEW'
    )
    result['status'] = 'AUDITED'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, action='append', required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--adapter', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('output directory must be empty')
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for evidence in args.evidence:
        if not (evidence / 'report.json').is_file():
            raise ValueError('Missing report.json: ' + str(evidence))
        row = audit_trial(evidence, args.output / evidence.name,
                          args.fixture, args.adapter)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    report = {'schema': 1, 'mode': 'OFFLINE_NO_OLLAMA', 'trials': rows}
    (args.output / 'offline-audit.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    return 0 if all(r.get('status') == 'AUDITED' for r in rows) else 1


if __name__ == '__main__':
    sys.exit(main())
