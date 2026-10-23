"""Deterministic two-stage Python source retriever; no model or gold patch access.

Input: issue text and source snapshot. Output: ranked, bounded source snippets.
All scoring uses issue text, file path and source definitions only.
"""
import argparse
import ast
import json
import pathlib
import re
from collections import Counter

STOP = {'this','that','with','from','have','when','given','like','error','type','field','fields','index','value','data','self','return','class','line','file','python','test','code','function','using','into','after','before','should','cannot','works','version','above','below','none','true','false'}
FILE_RE = re.compile(r'(?:[\\/]|\b)([a-zA-Z_]\w*\.py)\b')
TRACE_RE = re.compile(r'File\s+["\']([^"\']+\.py)["\'],\s*line\s+(\d+)')
QUALIFIED_RE = re.compile(r'\b(?:[A-Za-z_]\w*\.)+([A-Za-z_]\w*)\b')
WORD_RE = re.compile(r'[A-Za-z_][A-Za-z_0-9]{3,}')

def words(text):
    return {x.lower() for x in WORD_RE.findall(text) if x.lower() not in STOP}

def spans(source):
    try: tree=ast.parse(source)
    except (SyntaxError,ValueError): return []
    result=[]
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            result.append((node.name,node.lineno,getattr(node,'end_lineno',node.lineno)))
    return result

def retrieve(root, issue, max_chars=9000, top_k=8):
    root=pathlib.Path(root)
    traceback_files={pathlib.PurePath(p).name.lower() for p,_ in TRACE_RE.findall(issue)}
    mentioned={x.lower() for x in FILE_RE.findall(issue)}
    issue_tokens=words(issue)
    symbols={x.lower() for x in QUALIFIED_RE.findall(issue)}
    ranked=[]
    for path in sorted(root.rglob('*.py')):
        relative=path.relative_to(root).as_posix()
        if any(p in {'tests','test','docs','examples','.venv','site-packages','__pycache__'} for p in path.parts): continue
        if path.name.startswith('test_') or '/test_' in relative: continue
        try: content=path.read_text(encoding='utf8')
        except (OSError,UnicodeError): continue
        if len(content)>400000: continue
        defs=spans(content)
        names={name.lower() for name,_,_ in defs}
        score=0
        tags=[]
        if path.name.lower() in traceback_files:
            score+=90;tags.append('traceback_filename')
        if path.name.lower() in mentioned:
            score+=55;tags.append('mentioned_filename')
        hit_names=names & (symbols|issue_tokens)
        if hit_names:
            score+=min(60,15*len(hit_names));tags.append('matching_definitions')
        pathhits=issue_tokens & words(relative)
        if pathhits:
            score+=min(20,8*len(pathhits));tags.append('path_terms')
        if score<=0:continue
        lines=content.splitlines()
        anchors=[]
        for name,start,end in defs:
            if name.lower() in (symbols|issue_tokens): anchors.append((start,end,'symbol:'+name))
        if path.name.lower() in traceback_files:
            for f,line in TRACE_RE.findall(issue):
                if pathlib.PurePath(f).name.lower()==path.name.lower():
                    n=int(line)
                    if n<=len(lines):anchors.append((n,n,'traceback_line'))
        if not anchors:anchors=[(1,min(len(lines),30),'header')]
        ranked.append(dict(path=relative,score=score,tags=tags,lines=lines,anchors=anchors))
    ranked.sort(key=lambda x:(-x['score'],x['path']))
    total=0; selected=[]
    for item in ranked[:top_k]:
        fragments=[];used=[]
        for start,end,why in item['anchors'][:5]:
            lo=max(1,start-6);hi=min(len(item['lines']),max(end,start)+8)
            if any(not (hi<a or lo>b) for a,b in used):continue
            chunk='\n'.join(f'{i}: {item["lines"][i-1]}' for i in range(lo,hi+1))
            if total+len(chunk)+len(item['path'])+40>max_chars:continue
            fragments.append({'line_start':lo,'line_end':hi,'reason':why,'text':chunk})
            used.append((lo,hi));total+=len(chunk)+len(item['path'])+40
        if fragments:selected.append({'path':item['path'],'score':item['score'],'signals':item['tags'],'fragments':fragments})
    return {'selected_files':[s['path'] for s in selected],'context_chars':total,'results':selected}

def main():
    a=argparse.ArgumentParser();a.add_argument('--repo',required=True);a.add_argument('--issue-json',required=True);a.add_argument('--output',required=True);a.add_argument('--max-chars',type=int,default=9000);args=a.parse_args()
    issue=json.loads(pathlib.Path(args.issue_json).read_text(encoding='utf8'))['problem_statement']
    result=retrieve(args.repo,issue,args.max_chars)
    pathlib.Path(args.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps({'selected_files':result['selected_files'],'context_chars':result['context_chars']}))
if __name__=='__main__':main()
