"""Reconstructed offline imitation data, explicitly including user-authorized Kaggle.

These examples do not assert exact historical token capture or on-policy validity.
"""
import copy
import hashlib
import json
from collections import Counter
from .traces import TRAIN, EVAL, load_run, write_json


def demonstrations(row, tools):
    if row['solved'] is not True:
        return
    # Structured SWE request histories preserve real messages, tools and compaction.
    if row['requests']:
        seen=set()
        for request in row['requests']:
            body=request['body'];messages=body['messages']
            for i,m in enumerate(messages):
                if m['role']!='assistant' or not (m.get('content') or m.get('tool_calls')):
                    continue
                item=dict(messages=copy.deepcopy(messages[:i]),completion=copy.deepcopy(m),
                          tools=body.get('tools',tools),reconstruction='request_history')
                key=json.dumps(item,sort_keys=True)
                if key in seen: continue
                seen.add(key)
                yield item
        return
    # Kaggle: reconstruct observed single-call turns. Ambiguous observations end
    # the usable prefix; never invent a missing tool result or pair it by position.
    history=[]
    for s in row['steps']:
        if s['source'] in ('system','user'):
            if s.get('message'): history.append(dict(role=s['source'],content=s['message']))
            continue
        calls=s.get('tool_calls',[])
        if len(calls)>1: break
        message=dict(role='assistant',content=s.get('message',''))
        if calls:
            message['tool_calls']=[dict(id=c['tool_call_id'],type='function',function=dict(name=c['function_name'],arguments=c['arguments'])) for c in calls]
            message['reasoning']=message.pop('content');message['content']=''
        if not calls and not message['content']: continue
        yield dict(messages=copy.deepcopy(history),completion=message,tools=tools,reconstruction='atif_imitation')
        history.append(message)
        if calls:
            observation=s.get('observation')
            if not observation: break
            history.append(dict(role='tool',tool_call_id=calls[0]['tool_call_id'],name=calls[0]['function_name'],content=observation['content']))


def encode(tokenizer, item, max_length):
    kwargs=dict(tools=item['tools'],tokenize=False,enable_thinking=True)
    prefix=tokenizer.apply_chat_template(item['messages'],add_generation_prompt=True,**kwargs)
    full=tokenizer.apply_chat_template(item['messages']+[item['completion']],add_generation_prompt=False,**kwargs)
    if not full.startswith(prefix): return None,'template_prefix'
    ids=tokenizer.encode(full,add_special_tokens=False)
    if len(ids)>max_length: return None,'overlength'
    p=tokenizer.encode(prefix,add_special_tokens=False)
    if ids[:len(p)]!=p: return None,'token_boundary'
    if len(ids)<=len(p): return None,'empty_target'
    return dict(input_ids=ids,assistant_mask=[0]*len(p)+[1]*(len(ids)-len(p))),None


def build(tokenizer, output, max_length=8192):
    swe=load_run(TRAIN,'swe_rebench');kaggle=load_run(EVAL,'kaggle_dev')
    tools=next(r['requests'][0]['body']['tools'] for r in swe if r['requests'])
    counts=Counter();seen=set();rollouts=set();tasks=set()
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w') as f:
        for row in swe+kaggle:
            if row['solved'] is not True: continue
            counts[row['source']+'_resolved_rollouts']+=1
            for item in demonstrations(row,tools):
                encoded,reason=encode(tokenizer,item,max_length)
                if reason: counts['skipped_'+reason]+=1;continue
                key=hashlib.sha256(json.dumps(encoded,sort_keys=True).encode()).hexdigest()
                if key in seen: counts['duplicates']+=1;continue
                seen.add(key);rollouts.add(row['rollout_id']);tasks.add((row['source'],row['task_id']))
                encoded.update(source=row['source'],task_id=row['task_id'],trace_path=row['trace_path'],
                               reconstruction=item['reconstruction'],exact_capture=False,solved=True)
                f.write(json.dumps(encoded)+'\n')
                counts[row['source']+'_examples']+=1
                counts['assistant_tokens']+=sum(encoded['assistant_mask'])
    report=dict(counts=counts,examples=len(seen),included_rollouts=len(rollouts),included_tasks=len(tasks),
                max_length=max_length,kaggle_used_for_training=True,held_out_kaggle=False,
                method='resolved_rollout_SFT',exact_historical_capture=False)
    write_json(output.with_suffix('.report.json'),report)
    return report
