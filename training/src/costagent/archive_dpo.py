"""Offline tool-action trajectory DPO from graded, compatible archived rollouts.

User explicitly authorized Kaggle training. These are reconstructed per-turn
contexts, not exact historical token captures or Q-estimated step-level pairs.
"""
import argparse
from collections import Counter,defaultdict
from itertools import combinations
import hashlib
import json
from pathlib import Path
from .traces import ROOT,ARTIFACTS,TRAIN,load_run,load_trace,write_json
from .resolved_sft import demonstrations
from .curated_sft import bounded_encode


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def compatible_key(row):
    return (row['task_id'],row['prompt_sha256'],row['environment_sha256'])


def select_pairs(rows):
    groups=defaultdict(list);pairs=[]
    for row in rows:groups[compatible_key(row)].append(row)
    for group in groups.values():
        for a,b in combinations(group,2):
            if a['solved'] and b['solved']:
                chosen,rejected=sorted((a,b),key=lambda r:r['calls'])
                if (rejected['calls']-chosen['calls'])/max(rejected['calls'],1)<.1:continue
                kind='efficiency_calls_proxy'
            elif a['solved'] != b['solved']:
                chosen,rejected=(a,b) if a['solved'] else (b,a)
                kind='success_over_budget_timeout' if rejected['timeout'] else 'competence'
            else:continue
            pairs.append(dict(task_id=chosen['task_id'],chosen=chosen['id'],rejected=rejected['id'],
                type=kind,shared_prefix_sha256=chosen['prompt_sha256'],delta_calls=rejected['calls']-chosen['calls']))
    return pairs


def discover():
    rows=[];excluded=Counter()
    for outcome_path in sorted((ROOT/'baseline-kit/results').glob('*/outcome.json')):
        directory=outcome_path.parent
        try:
            outcome=json.loads(outcome_path.read_text())
            manifest=json.loads((directory/'run_manifest.json').read_text())
            settings=json.loads((directory/'effective_settings.json').read_text())
            results=[json.loads(l) for l in (directory/'task_results.jsonl').read_text().splitlines() if l.strip()]
        except (FileNotFoundError,ValueError):excluded['missing_metadata']+=1;continue
        if manifest.get('mode')!='agent' or len(results)!=1:excluded['non_agent_or_ambiguous_task']+=1;continue
        result=results[0];task=result['instance_id'];solved=outcome.get('resolved')
        timeout=bool(outcome.get('agent_timeout'))
        if type(solved) is not bool or solved!=result.get('resolved'):excluded['unknown_or_conflicting_outcome']+=1;continue
        if solved:
            valid=outcome.get('test_exit_code')==0 and not result.get('error') and outcome.get('patch_bytes',0)>0
        else:
            # Do not treat infrastructure exceptions as preference labels.
            valid=(timeout and not outcome.get('patch_bytes') and
                   str(result.get('error','')).startswith('Agent exceeded session timeout')) or (
                   result.get('error') is None and outcome.get('test_exit_code')==1)
        if not valid:excluded['untrusted_outcome']+=1;continue
        trace_path=directory/'traces'/f'trace_{task}.json'
        if not trace_path.exists():excluded['missing_trace']+=1;continue
        trace=load_trace(trace_path)
        initial=[]
        for step in trace['steps']:
            if step['source']=='agent':break
            if step.get('message'):initial.append(dict(role=step['source'],content=step['message']))
        keys=('image_id','snapshot_sha256','tasks_sha256')
        if any(not manifest.get(k) for k in keys):excluded['missing_environment_provenance']+=1;continue
        environment={k:manifest[k] for k in keys}
        environment.update(budget=settings['local_evaluation'],model=settings['model_config_sha256'],
                           policy=settings['agent_sha256'].get('adapters/main_lora/adapter_model.safetensors'))
        rows.append(dict(id=directory.name,task_id=task,source='kaggle_dev',solved=solved,timeout=timeout,
            calls=outcome['tool_calls'],prompt_sha256=digest(initial),environment_sha256=digest(environment),
            trace_path=str(trace_path),steps=trace['steps'],requests=[],outcome_path=str(outcome_path)))
    return rows,excluded


def build(tokenizer,output,max_length=8192):
    rows,excluded=discover();raw_pairs=select_pairs(rows)
    used={p[side] for p in raw_pairs for side in ('chosen','rejected')}
    tools=next(r['requests'][0]['body']['tools'] for r in load_run(TRAIN,'swe_rebench') if r['requests'])
    encoded={};rejected={};coverage={}
    for row in rows:
        if row['id'] not in used:continue
        turns=[];dropped=0
        expected=sum(bool(s.get('tool_calls')) for s in row['steps'])
        # The renderer is label-independent. Never change the recorded label.
        for item in demonstrations(dict(row,solved=True),tools):
            if not item['completion'].get('tool_calls'):continue
            turn,removed,reason=bounded_encode(tokenizer,item,max_length)
            if reason:rejected[row['id']]=reason;break
            turn['context_blocks_removed']=removed;turns.append(turn);dropped+=bool(removed)
        if len(turns)!=expected:
            rejected.setdefault(row['id'],'incomplete_tool_trajectory');continue
        if row['id'] in rejected:continue
        encoded[row['id']]=dict(id=row['id'],task_id=row['task_id'],solved=row['solved'],timeout=row['timeout'],
            calls=row['calls'],turns=turns,trace_path=row['trace_path'],outcome_path=row['outcome_path'],
            prompt_sha256=row['prompt_sha256'],environment_sha256=row['environment_sha256'])
        coverage[row['id']]=dict(turns=len(turns),context_shortened_turns=dropped)
    pairs=[p for p in raw_pairs if p['chosen'] in encoded and p['rejected'] in encoded]
    final_ids={p[side] for p in pairs for side in ('chosen','rejected')}
    report=dict(method='offline_tool_action_trajectory_DPO',pairs=len(pairs),tasks=sorted({p['task_id'] for p in pairs}),
                types=dict(Counter(p['type'] for p in pairs)),max_length=max_length,
                discovered_rollouts=len(rows),excluded=dict(excluded),rejected_encoding=rejected,coverage=coverage,
                exact_historical_capture=False,context='system + issue + most recent complete exchanges',
                efficiency_metric='tool_calls proxy; not calibrated blueprint C',
                reference='completed resolved-rollout SFT adapter; not R2-selected RFT',
                limitations=['one-task pairs do not support claims of generalization',
                             'only tool-action turns are scored; terminal narrative is excluded',
                             'contexts reconstructed from ATIF; older exchanges removed to fit',
                             'budget timeouts are operational failures, not completed failed test runs'])
    write_json(output,dict(report=report,pairs=pairs,rollouts={k:v for k,v in encoded.items() if k in final_ids}))
    write_json(output.with_suffix('.report.json'),report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ARTIFACTS/'archive-dpo-v1/dataset.json')
    p.add_argument('--max-length',type=int,default=8192)
    a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'gemma-4-31b-it-qat-w4a16-ct',local_files_only=True)
    print(json.dumps(build(tokenizer,a.output,a.max_length),indent=2),flush=True)

if __name__=='__main__':main()
