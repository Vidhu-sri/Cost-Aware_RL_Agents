"""Preserve successful action coverage with explicit bounded-context reconstruction."""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
from .resolved_sft import demonstrations,encode
from .traces import ROOT,ARTIFACTS,TRAIN,EVAL,load_run,write_json


def history_blocks(messages):
    """Keep system/first issue; remove only complete assistant/tool exchanges."""
    first_user=next((i for i,m in enumerate(messages) if m['role']=='user'),None)
    if first_user is None: raise ValueError('Missing issue message')
    fixed=messages[:first_user+1];blocks=[]
    for message in messages[first_user+1:]:
        if message['role']=='assistant' or not blocks:
            blocks.append([])
        blocks[-1].append(message)
    return fixed,blocks


def bounded_encode(tokenizer,item,max_length):
    fixed,blocks=history_blocks(item['messages'])
    # First try the original rendering. If it does not fit, retain the most recent
    # complete exchanges; never cut a completion, system instruction, or issue.
    def attempt(dropped):
        candidate=dict(item,messages=fixed+[m for b in blocks[dropped:] for m in b])
        return encode(tokenizer,candidate,max_length)
    encoded,reason=attempt(0)
    if encoded is not None:return encoded,0,None
    if reason!='overlength':return None,0,reason
    if not blocks:return None,0,'issue_or_completion_overlength'
    best,reason=attempt(len(blocks))
    if best is None:return None,len(blocks),('issue_or_completion_overlength' if reason=='overlength' else reason)
    low,high=0,len(blocks)
    while high-low>1:
        mid=(low+high)//2
        encoded,reason=attempt(mid)
        if encoded is not None:high=mid;best=encoded
        elif reason=='overlength':low=mid
        else:return None,mid,reason
    return best,high,None


def build(tokenizer,output,max_length=4096):
    records=load_run(TRAIN,'swe_rebench')+load_run(EVAL,'kaggle_dev')
    tools=next(r['requests'][0]['body']['tools'] for r in records if r['requests'])
    counters=Counter();actions=Counter();seen=set();tasks=set()
    if output.exists():raise FileExistsError(f'Refusing to overwrite {output}')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w') as f:
        for row in records:
            for item in demonstrations(row,tools):
                # Copies prevent historical tool-call content being changed by tokenizers.
                encoded,dropped,reason=bounded_encode(tokenizer,copy.deepcopy(item),max_length)
                if reason:counters['skipped_'+reason]+=1;continue
                digest=hashlib.sha256(json.dumps(encoded,sort_keys=True).encode()).hexdigest()
                key=(row['source'],row['task_id'],digest)
                if key in seen:counters['duplicates']+=1;continue
                seen.add(key);tasks.add((row['source'],row['task_id']))
                calls=[c['function']['name'] for c in item['completion'].get('tool_calls',[])]
                actions.update(calls or ['text_only'])
                encoded.update(source=row['source'],task_id=row['task_id'],trace_path=row['trace_path'],
                    reconstruction=item['reconstruction'],exact_capture=False,solved=True,
                    dropped_history_blocks=dropped,actions=calls,
                    context_reconstruction='recent_complete_blocks' if dropped else 'logged_or_atif_prefix')
                f.write(json.dumps(encoded)+'\n')
                counters[row['source']+'_examples']+=1;counters['assistant_tokens']+=sum(encoded['assistant_mask'])
                if dropped:counters['context_shortened_examples']+=1
    report=dict(method='curated_resolved_rollout_SFT',examples=len(seen),included_tasks=len(tasks),
                counts=dict(counters),actions=dict(actions),max_length=max_length,
                exact_historical_capture=False,kaggle_used_for_training=True,
                caveat='Older context removed in complete blocks; not an on-policy token capture. No held-out evaluation claimed.')
    write_json(output.with_suffix('.report.json'),report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',default=str(ROOT/'gemma-4-31b-it-qat-w4a16-ct'))
    p.add_argument('--output',type=Path,default=ARTIFACTS/'curated-sft-v1/train.jsonl')
    p.add_argument('--max-length',type=int,default=4096)
    a=p.parse_args();a.output=a.output.resolve()
    if not a.output.is_relative_to(ARTIFACTS.resolve()):p.error('Output must be under artifacts/')
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(a.model,local_files_only=True)
    print(json.dumps(build(tokenizer,a.output,a.max_length),indent=2))

if __name__=='__main__':main()
