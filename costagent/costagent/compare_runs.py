"""Paired evaluation of indexed Docker/ATIF runs; no model or GPU required."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import posixpath
import random
from statistics import mean

ARTIFACTS = Path(__file__).resolve().parents[1] / 'artifacts'
def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2)+'\n')
def load_run(index, source):
    result=[]
    for entry in json.loads(Path(index).read_text())['attempts']:
        trace=json.loads(Path(entry['trace_path']).read_text())
        result.append(dict(task_id=entry['task_id'],seed=entry['seed'],solved=entry['resolved'],steps=trace['steps'],final_metrics=trace['final_metrics'],rollout_id=entry['result_dir'],base_commit=entry['base_commit'],wall_s=entry['agent']['elapsed_seconds']))
    return result

METRICS = ('solve_rate', 'generated_tokens', 'prompt_tokens', 'cached_prompt_tokens',
           'total_model_tokens', 'agent_wall_seconds', 'tool_calls', 'charged_tool_calls',
           'read_file_calls', 'unique_explicit_files_read', 'unique_explicit_files_touched',
           'shell_calls', 'observation_text_tokens')
BUDGET_KEYS = ('agent_minutes','tool_calls','turns','command_timeout_seconds','outer_deadline_seconds','sampling','image')

def configuration(directory):
    p = Path(directory)/'settings.json'
    if not p.exists(): return None
    data = json.loads(p.read_text())
    result = {k:data.get(k) for k in BUDGET_KEYS}
    result['sampling'] = {k:v for k,v in (result['sampling'] or {}).items() if k != 'seed'}
    return result

def metrics(row, tokenizer=None):
    calls = [c for s in row['steps'] for c in s.get('tool_calls', [])]
    reads, touched = set(), set()
    for c in calls:
        name, args = c['function_name'], c['arguments']
        # Shell commands may read arbitrary files; do not pretend to recover them.
        if name in {'read_file','edit_file','write_file'}:
            path = args.get('filepath', args.get('file_path', args.get('path')))
            if isinstance(path,str):
                path = posixpath.normpath(path)
                touched.add(path)
                if name == 'read_file': reads.add(path)
    fm = row['final_metrics']
    obs = [s['observation'].get('content') for s in row['steps'] if s.get('observation')]
    observation_tokens = (sum(len(tokenizer.encode(x, add_special_tokens=False)) for x in obs)
                          if tokenizer is not None and all(isinstance(x,str) for x in obs) else None)
    return dict(task_id=row['task_id'],seed=row['seed'],rollout_id=row['rollout_id'],
                base_commit=row['base_commit'],configuration=configuration(row['rollout_id']),
                solve_rate=int(row['solved']) if row['solved'] is not None else None,
                generated_tokens=fm.get('total_completion_tokens'),prompt_tokens=fm.get('total_prompt_tokens'),
                cached_prompt_tokens=fm.get('total_cached_tokens'),total_model_tokens=fm.get('total_tokens'),
                agent_wall_seconds=row['wall_s'],tool_calls=len(calls),
                charged_tool_calls=sum(c['function_name'] not in {'submit_patch','get_status'} for c in calls),
                read_file_calls=sum(c['function_name']=='read_file' for c in calls),
                unique_explicit_files_read=len(reads),unique_explicit_files_touched=len(touched),
                shell_calls=sum(c['function_name']=='run_command' for c in calls),
                observation_text_tokens=observation_tokens)

def summarize(rows):
    return {'rollouts':len(rows),'tasks':len({r['task_id'] for r in rows}),
            'unknown_outcomes':sum(r['solve_rate'] is None for r in rows),
            'metrics':{k:{'mean':mean(v) if v else None,'available':len(v)}
                       for k in METRICS for v in [[r[k] for r in rows if r[k] is not None]]}}

def keyed(rows):
    result = {}
    for r in rows:
        key = (r['task_id'],r['seed'])
        if key in result: raise ValueError(f'Duplicate task/seed {key}; choose one indexed attempt per seed')
        if key[1] is None: raise ValueError('Paired comparison requires recorded seeds')
        result[key] = r
    return result

def compare(base, candidate, bootstrap=2000, seed=42, exploratory=False):
    a,b = keyed(base),keyed(candidate)
    common=sorted(a.keys() & b.keys())
    if not common: raise ValueError('No matching task/seed pairs; collect matched evaluation runs')
    mismatches=[]
    for key in common:
        x,y=a[key],b[key]
        if (not x['base_commit'] or not y['base_commit'] or x['base_commit']!=y['base_commit']
            or x['configuration'] is None or y['configuration'] is None
            or x['configuration']!=y['configuration']): mismatches.append(list(key))
    if mismatches and not exploratory:
        raise ValueError('Missing/mismatched task commits or evaluation budgets; use --exploratory only for descriptive comparison')
    known=[key for key in common if a[key]['solve_rate'] is not None and b[key]['solve_rate'] is not None]
    output={'matched_pairs':len(common),'known_outcome_pairs':len(known),
            'baseline_only_pairs':len(a.keys()-b.keys()),'candidate_only_pairs':len(b.keys()-a.keys()),
            'configuration_mismatches':mismatches,'exploratory':exploratory,'cohorts':{}}
    for cohort,keys in [('all_graded_pairs',known),('both_solved_pairs',[k for k in known if a[k]['solve_rate']==b[k]['solve_rate']==1])]:
        results={}
        for metric in METRICS:
            groups=defaultdict(list)
            for key in keys:
                x,y=a[key][metric],b[key][metric]
                if x is not None and y is not None: groups[key[0]].append((x,y))
            task_means=[(mean(x for x,y in vals),mean(y for x,y in vals)) for vals in groups.values()]
            if not task_means:
                results[metric]={'tasks':0,'pairs':0};continue
            am,bm=mean(x for x,y in task_means),mean(y for x,y in task_means)
            deltas=[y-x for x,y in task_means]
            rng=random.Random(seed)
            samples=sorted(mean(rng.choices(deltas,k=len(deltas))) for _ in range(bootstrap))
            ci=[samples[int(.025*(bootstrap-1))],samples[int(.975*(bootstrap-1))]] if len(deltas)>1 else None
            results[metric]={'tasks':len(groups),'pairs':sum(map(len,groups.values())),
                             'baseline_mean':am,'candidate_mean':bm,'delta':bm-am,
                             'change_percent':100*(bm-am)/am if am else None,
                             'delta_ci95':ci}
        output['cohorts'][cohort]=results
    return output

def markdown(report):
    lines=['# Rollout comparison','',
           'Negative cost deltas favor the candidate; positive solve-rate deltas favor it.',
           'Paired estimates weight tasks equally. Confidence intervals bootstrap tasks, keeping seeds grouped.',
           'These intervals describe evaluation-task variation, not training-seed variation.','']
    for name,summary in report['arms'].items():
        lines.append(f"- {name}: {summary['rollouts']} rollouts, {summary['tasks']} tasks, {summary['unknown_outcomes']} unknown outcomes.")
    lines.extend(['', '## Per-arm descriptive metrics', '', '| Arm | Metric | Mean | Available rollouts |', '|---|---|---:|---:|'])
    for name, summary in report['arms'].items():
        for metric, value in summary['metrics'].items():
            value_text = 'N/A' if value['mean'] is None else f"{value['mean']:.3f}"
            lines.append(f"| {name} | {metric} | {value_text} | {value['available']} |")
    for name,c in report['comparisons'].items():
        lines.extend(['',f'## {name} versus {report["baseline"]}', '',
                      f"Matched pairs: {c['matched_pairs']}; pairs with known outcomes: {c['known_outcome_pairs']}. Exploratory: {c['exploratory']}."])
        for cohort,ms in c['cohorts'].items():
            lines.extend(['',f'### {cohort}','', '| Metric | Baseline | Candidate | Change % | Delta 95% CI | Tasks / pairs |', '|---|---:|---:|---:|---|---|'])
            for metric,v in ms.items():
                if not v['tasks']: continue
                pct='N/A' if v['change_percent'] is None else f"{v['change_percent']:.2f}"
                lines.append(f"| {metric} | {v['baseline_mean']:.3f} | {v['candidate_mean']:.3f} | {pct} | {v['delta_ci95']} | {v['tasks']} / {v['pairs']} |")
    lines.extend(['','## Measurement limits','']+['- '+x for x in report['limitations']])
    return '\n'.join(lines)+'\n'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arm',action='append',required=True,help='NAME=manifest.json (repeat for each arm)')
    p.add_argument('--baseline',required=True)
    p.add_argument('--source',choices=['swe_rebench','kaggle_dev'],default='swe_rebench')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--bootstrap',type=int,default=2000)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--exploratory',action='store_true')
    p.add_argument('--tokenizer',type=Path,help='Optional LOCAL tokenizer to count serialized observation text')
    args=p.parse_args()
    if args.bootstrap<100:p.error('--bootstrap must be >=100')
    if not args.output.resolve().is_relative_to(ARTIFACTS.resolve()):p.error('Output must be under artifacts/')
    tokenizer=None
    if args.tokenizer:
        from transformers import AutoTokenizer
        tokenizer=AutoTokenizer.from_pretrained(args.tokenizer,local_files_only=True)
    arms={};inputs={}
    for item in args.arm:
        name,path=item.split('=',1)
        if name in arms:p.error('Duplicate arm name')
        inputs[name]=str(Path(path).resolve())
        arms[name]=[metrics(r,tokenizer) for r in load_run(Path(path),args.source)]
    if args.baseline not in arms:p.error('Baseline must name an --arm')
    report={'baseline':args.baseline,'inputs':inputs,'arms':{n:summarize(r) for n,r in arms.items()},
            'comparisons':{n:compare(arms[args.baseline],r,args.bootstrap,args.seed,args.exploratory)
                           for n,r in arms.items() if n!=args.baseline},
            'limitations':[
                'No training/evaluation split provenance is inferred; exclude training tasks from evaluation.',
                'Unknown grading outcomes are reported and excluded from paired estimates, never treated as failures.',
                'Prompt tokens include repeated context. Total model tokens = prompt + generated; not unique observed tokens.',
                'Observation text tokens, if requested, tokenize serialized trace observations; not exact model-visible observation tokens.',
                'File counts cover explicit read_file/edit_file/write_file arguments only; shell access and path aliases are not resolved.',
                'Agent wall time excludes grading and server startup; shared GPU contention affects latency. No model-only latency claim.',
                'All-graded and both-solved comparisons are reported separately to expose cheaper failures and success-selection effects.',
                'Matched seeds, task commits and recorded budgets are checked; hardware, model provenance and hidden harness differences require review.'
            ]}
    args.output.mkdir(parents=True,exist_ok=True)
    write_json(args.output/'comparison.json',report)
    (args.output/'report.md').write_text(markdown(report))
    with (args.output/'rollouts.csv').open('w',newline='') as f:
        fields=['arm','task_id','seed','rollout_id']+list(METRICS)
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader()
        for name,rows in arms.items():
            for row in rows:writer.writerow(dict(arm=name,**row))
    print(args.output/'report.md')

if __name__=='__main__':main()
