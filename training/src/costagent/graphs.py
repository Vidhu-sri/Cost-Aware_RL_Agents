"""AST code graphs and gold-patch potentials for R3 training (not a GNN)."""
import argparse
import ast
from collections import defaultdict, deque
from pathlib import Path
import subprocess
from .traces import write_json


def build_graph(snapshot):
    root=Path(snapshot).resolve(); nodes=[]; edges=[]; trees={}; modules={}
    def edge(a,b,kind): edges.append(dict(source=a,target=b,type=kind,key=len(edges)))
    for path in sorted(root.rglob('*.py')):
        if path.is_symlink() or not path.resolve().is_relative_to(root): continue
        rel=path.relative_to(root).as_posix()
        if any(p.startswith('.') for p in path.relative_to(root).parts): continue
        source=path.read_text(encoding='utf-8-sig')
        try: tree=ast.parse(source)
        except SyntaxError as exc: raise ValueError(f'Cannot parse base file {rel}: {exc}') from exc
        module=rel[:-3].replace('/','.')
        modules[module]=module; trees[module]=tree
        nodes.append(dict(id=module,name=module,text=source,file=rel,start=1,end=max(1,len(source.splitlines())),kind='module'))
        def visit(node,parent):
            for child in ast.iter_child_nodes(node):
                if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                    ident=parent+'.'+child.name
                    nodes.append(dict(id=ident,name=ident,text=ast.get_source_segment(source,child) or '',file=rel,
                                      start=min([child.lineno]+[d.lineno for d in child.decorator_list]),end=child.end_lineno,
                                      kind='class' if isinstance(child,ast.ClassDef) else 'function'))
                    edge(ident,parent,'DEFINED_IN'); visit(child,ident)
                else: visit(child,parent)
        visit(tree,module)
    ids={n['id'] for n in nodes}
    if len(ids)!=len(nodes): raise ValueError('Duplicate AST qualified names; cannot map unambiguously')
    for module,tree in trees.items():
        file_nodes=[n for n in nodes if n['file']==module.replace('.','/')+'.py']
        for item in ast.walk(tree):
            if not hasattr(item,'lineno'): continue
            owners=[n for n in file_nodes if n['start']<=item.lineno<=n['end']]
            owner=min(owners,key=lambda n:n['end']-n['start'])['id'] if owners else module
            if isinstance(item,ast.Call):
                name=ast.unparse(item.func)
                candidates=[owner.rsplit('.',1)[0]+'.'+name,module+'.'+name,name]
                target=next((v for v in candidates if v in ids),None)
                if target: edge(owner,target,'CALLS')
            elif isinstance(item,(ast.Import,ast.ImportFrom)):
                names=[a.name for a in item.names] if isinstance(item,ast.Import) else [item.module or '']
                for name in names:
                    if name in modules: edge(module,name,'IMPORTS')
    return dict(directed=True,multigraph=True,graph={'repo_name':root.name},nodes=nodes,edges=edges)


def resolve(graph,query):
    ids=sorted(n['id'] for n in graph['nodes'])
    for matches in ([n for n in ids if n==query], [n for n in ids if n.endswith(query)],
                    [n for n in ids if n.lower()==query.lower()], [n for n in ids if query.lower() in n.lower()]):
        if matches: return matches
    return []


def range_symbols(graph,path,start,end):
    path=path.removeprefix('/workspace/').removeprefix('./')
    candidates=[n for n in graph['nodes'] if n.get('file')==path]
    result={n['id'] for n in candidates if n['kind']=='module'}
    for n in candidates:
        if n['start']<=end and start<=n['end']: result.add(n['id'])
    return result


def gold_symbols(patch,graph):
    from unidiff import PatchSet
    result=set()
    for file in PatchSet(patch):
        # New files have no pre-patch symbol. No test-patch substitution.
        if file.is_added_file: continue
        path=file.source_file.removeprefix('a/')
        candidates=[n for n in graph['nodes'] if n.get('file')==path]
        result.update(n['id'] for n in candidates if n['kind']=='module')
        for hunk in file:
            cursor=hunk.source_start
            for line in hunk:
                if line.is_added or line.is_removed:
                    enclosing=[n for n in candidates if n['start']<=max(cursor,1)<=n['end']]
                    if enclosing: result.add(min(enclosing,key=lambda n:n['end']-n['start'])['id'])
                if not line.is_added: cursor+=1
    return result


def relevance(graph,gold,gamma_g=.5):
    if not 0<gamma_g<=1: raise ValueError('Invalid graph discount')
    ids={n['id'] for n in graph['nodes']}
    if not gold or not set(gold)<=ids: raise ValueError('Missing/unresolved gold symbols')
    adj=defaultdict(set)
    for e in graph['edges']:
        adj[e['source']].add(e['target']); adj[e['target']].add(e['source'])
    distances={g:0 for g in gold}; queue=deque(sorted(gold))
    while queue:
        node=queue.popleft()
        for neighbor in sorted(adj[node]):
            if neighbor not in distances:
                distances[neighbor]=distances[node]+1;queue.append(neighbor)
    return {n:gamma_g**distances[n] if n in distances else 0. for n in sorted(ids)}


def potentials(touched, scores):
    result=[0.]
    for symbols in touched: result.append(max([result[-1]]+[scores.get(s,0.) for s in symbols]))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',required=True,type=Path);p.add_argument('--base-commit',required=True)
    p.add_argument('--gold-patch',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--dry-run',action='store_true');args=p.parse_args()
    commit=subprocess.check_output(['git','-C',str(args.snapshot),'rev-parse','HEAD'],text=True).strip()
    expected=subprocess.check_output(['git','-C',str(args.snapshot),'rev-parse',args.base_commit+'^{commit}'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(args.snapshot),'status','--porcelain','--untracked-files=all'],text=True)
    if commit!=expected or dirty: raise ValueError('Snapshot must be clean at base_commit')
    graph=build_graph(args.snapshot); gold=gold_symbols(args.gold_patch.read_text(),graph)
    result=dict(graph=graph,gold=sorted(gold),relevance=relevance(graph,gold),base_commit=commit)
    write_json(args.output,result)
    print({'nodes':len(graph['nodes']),'edges':len(graph['edges']),'gold':len(gold),'dry_run':args.dry_run})

if __name__=='__main__': main()
