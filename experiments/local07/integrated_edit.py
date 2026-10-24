"""Offline integration: deterministic retrieval + allowlisted edits in disposable Git worktree.

Accepts externally supplied candidate edit (not gold patch); NEVER invokes an LLM.
No edits to the input repository, no tests or oracle material fed into retrieval.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import tempfile
import ast
from retrieve_context import retrieve


def git(repo, *args, input=None):
    r=subprocess.run(['git',*args],cwd=repo,input=input,text=True,capture_output=True,timeout=45)
    if r.returncode: raise RuntimeError(f'git {args[0]} failed: {r.stderr[:300]}')
    return r.stdout


def assess(repo, issue, replacement_path, candidate_source, max_chars=9000, max_files=2):
    repo=pathlib.Path(repo).resolve()
    if not (repo/'.git').exists(): raise ValueError('REQUIRES_GIT_CHECKOUT')
    if git(repo,'status','--porcelain').strip(): raise ValueError('DIRTY_SOURCE_REPOSITORY')
    baseline=git(repo,'rev-parse','HEAD').strip()
    outcome=retrieve(repo,issue,max_chars=max_chars)
    allowed=outcome['selected_files'][:max_files]
    name=pathlib.PurePosixPath(replacement_path)
    if name.as_posix()!=replacement_path or name.is_absolute() or '..' in name.parts or name.suffix!='.py' or replacement_path not in allowed:
        raise ValueError('EDIT_OUTSIDE_RETRIEVED_ALLOWLIST')
    if any(p.lower().startswith('test') for p in name.parts): raise ValueError('TEST_EDIT_FORBIDDEN')
    target=repo.joinpath(*name.parts)
    if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(repo):
        raise ValueError('INVALID_TARGET')
    ast.parse(candidate_source)
    if not candidate_source.endswith('\n'): candidate_source+='\n'
    original_sha=hashlib.sha256(target.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='local07-isolated-') as d:
        isolated=pathlib.Path(d)/'checkout'
        git(repo,'worktree','add','--detach',str(isolated),baseline)
        try:
            itarget=isolated.joinpath(*name.parts)
            if itarget.is_symlink() or not itarget.resolve().is_relative_to(isolated.resolve()):
                raise ValueError('ISOLATED_PATH_ESCAPE')
            # Git may materialize the same tracked blob with different LF/CRLF bytes
            # across worktrees on Windows. Check tracked identity and clean index/worktree,
            # not raw working-file equality.
            if git(isolated,'rev-parse','HEAD').strip() != baseline:
                raise ValueError('BASE_COMMIT_DRIFT')
            if git(isolated,'rev-parse',f'HEAD:{replacement_path}').strip() != git(repo,'rev-parse',f'HEAD:{replacement_path}').strip():
                raise ValueError('BASE_BLOB_DRIFT')
            if git(isolated,'status','--porcelain').strip():
                raise ValueError('ISOLATED_WORKTREE_DIRTY')
            itarget.write_bytes(candidate_source.encode('utf-8'))
            changed=git(isolated,'diff','--name-only').splitlines()
            if changed!=[replacement_path]: raise ValueError('DIFF_SCOPE_VIOLATION')
            git(isolated,'diff','--check')
            patch=git(isolated,'diff','--binary','--',replacement_path)
            if not patch: raise ValueError('NO_CHANGE')
            git(repo,'apply','--cached','--check','-',input=patch)
            report={'result':'PATCH_APPLICABLE_NOT_GRADED','commit':baseline,'selected_files':allowed,
                    'edited_file':replacement_path,'context_chars':outcome['context_chars'],
                    'source_sha256':original_sha,'patch_sha256':hashlib.sha256(patch.encode()).hexdigest(),
                    'patch_bytes':len(patch.encode())}
            return report,patch
        finally:
            git(repo,'worktree','remove','--force',str(isolated))


def main():
    ap=argparse.ArgumentParser()
    for flag in ('repo','issue-json','edit-file','candidate-file','report','patch'):
        ap.add_argument('--'+flag,required=True)
    a=ap.parse_args()
    issue=json.loads(pathlib.Path(a.issue_json).read_text(encoding='utf-8'))['problem_statement']
    candidate=pathlib.Path(a.candidate_file).read_text(encoding='utf-8')
    report,patch=assess(a.repo,issue,a.edit_file,candidate)
    pathlib.Path(a.patch).write_text(patch,encoding='utf-8',newline='\n')
    pathlib.Path(a.report).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))
if __name__=='__main__':main()
