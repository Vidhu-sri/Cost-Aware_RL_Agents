#!/usr/bin/env python3
"""Iterated GRPO: sample with an external harness driver, score, update, checkpoint.

The sampler command is a JSON argv array. It receives --request PATH --output PATH.
It must serve the requested adapter and emit verified token-capture JSONL; ATIF alone
is insufficient. The driver interface is explicit because current runs lack responses.
"""
import argparse
from collections import defaultdict
import json
import random
import gc
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from costagent.datasets import allowed_tasks,load_dataset
from costagent.grpo import advantages,step_advantages,clipped_loss
from costagent.rewards import rewards
from costagent.traces import ARTIFACTS,write_json


def prepare(rows,reward,group_size,policy_hash):
    groups=defaultdict(list)
    for row in rows:
        if row['sampling_policy_sha256']!=policy_hash: raise ValueError('Stale/off-policy rollout')
        groups[(row['task_id'],row['group_id'])].append(row)
    prepared=[]; dropped=dict(incomplete=0,partial_kept=0,zero_variance=0)
    for group in groups.values():
        if len(group)>group_size: raise ValueError('Oversized GRPO group')
        if len(group)<group_size:
            if len(group)<4: dropped['incomplete']+=1;continue
            dropped['partial_kept']+=1
        values=[rewards(r['solved'],r['cost'],r['potentials'])[reward] for r in group]
        if reward=='R3_rtg': adv=step_advantages(values)
        else:
            a=advantages(values)
            if a is None: dropped['zero_variance']+=1;continue
            adv=[[value]*len(row['turns']) for row,value in zip(group,a)]
        if all(all(a is None for a in row) for row in adv): dropped['zero_variance']+=1;continue
        for row,aa in zip(group,adv):
            if len(row['turns']) != len(aa): raise ValueError('Turn/advantage alignment mismatch')
            for turn,a in zip(row['turns'],aa):
                if a is not None: prepared.append((turn,a))
    return prepared,dropped


def sample_tasks(pool, count, seed, iteration):
    return random.Random(seed+iteration).sample(sorted(pool),count)


def update_policy(model,prepared,epochs,batch_size,learning_rate,seed):
    import torch
    from costagent.train import logps
    old=[];refs=[]
    model.train()  # deterministic across scoring and update with dropout disabled
    with torch.no_grad():
        for turn,_ in prepared:
            model.set_adapter('policy');old.append(logps(model,turn)[0].cpu())
            model.set_adapter('reference');refs.append(logps(model,turn)[0].cpu())
    model.set_adapter('policy')
    optimizer=torch.optim.AdamW([v for v in model.parameters() if v.requires_grad],lr=learning_rate)
    metrics=[];steps=0
    for epoch in range(epochs):
        order=list(range(len(prepared)));random.Random(seed+epoch).shuffle(order)
        for offset in range(0,len(order),batch_size):
            batch=order[offset:offset+batch_size]
            total_tokens=sum(sum(prepared[i][0]['assistant_mask'][1:]) for i in batch)
            optimizer.zero_grad(set_to_none=True)
            for i in batch:
                turn,a=prepared[i]
                lp,mask=logps(model,turn)
                loss,metric=clipped_loss(lp,old[i].to(lp.device),refs[i].to(lp.device),a,mask)
                (loss*mask.sum()/total_tokens).backward();metrics.append(metric)
                del lp,mask,loss
            torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step();steps+=1
    return metrics,steps


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model');p.add_argument('--rft-adapter');p.add_argument('--sampler-command',type=Path)
    p.add_argument('--dataset',type=Path,help='Validate a captured group in dry-run mode')
    p.add_argument('--output',type=Path,default=ARTIFACTS/'grpo');p.add_argument('--dry-run',action='store_true')
    p.add_argument('--smoke',action='store_true');p.add_argument('--resume',action='store_true')
    p.add_argument('--reward',choices=['R1','R2','R3_traj','R3_rtg'],default='R2')
    p.add_argument('--iterations',type=int,default=5);p.add_argument('--group-size',type=int,default=16)
    p.add_argument('--tasks',type=int,default=4);p.add_argument('--epochs',type=int,choices=[1,2],default=1)
    p.add_argument('--minibatch-turns',type=int,default=8)
    p.add_argument('--learning-rate',type=float,default=1e-5)
    p.add_argument('--seed',type=int,default=42);p.add_argument('--qlora',action='store_true')
    args=p.parse_args()
    if args.smoke: args.iterations,args.tasks,args.group_size=5,4,4
    if args.minibatch_turns<1 or args.learning_rate<=0: p.error('Invalid optimizer settings')
    if min(args.tasks,args.iterations)<1 or args.group_size<2: p.error('Invalid iteration/task/group count')
    args.output=args.output.resolve()
    if not args.output.is_relative_to(ARTIFACTS.resolve()): p.error('Output must be under artifacts/')
    task_pool=sorted(allowed_tasks())
    if args.tasks>len(task_pool): p.error('Requested more tasks than available')
    rows=load_dataset(args.dataset,'grpo',set(task_pool)) if args.dataset else []
    config=dict(reward=args.reward,iterations=args.iterations,task_pool=task_pool,tasks_per_iteration=args.tasks,group_size=args.group_size,
                epochs=args.epochs,minibatch_turns=args.minibatch_turns,learning_rate=args.learning_rate,
                gpu_handoff='sequential_unload',epsilon=.2,beta=.04,seed=args.seed,reference=args.rft_adapter,
                model=args.model,qlora=args.qlora,validated_rollouts=len(rows),
                blockers=[] if args.sampler_command else ['Need a harness sampler with exact request/response capture'])
    if rows:
        prepared,dropped=prepare(rows,args.reward,args.group_size,rows[0]['sampling_policy_sha256'])
        config.update(update_turns=len(prepared),dropped_groups=dropped)
    write_json(ARTIFACTS/('graph_plan.json' if args.reward.startswith('R3') else 'grpo_plan.json'),config)
    if args.dry_run: print(json.dumps(config,indent=2));return
    if not args.model or not args.rft_adapter or not args.sampler_command:
        p.error('Training needs --model, --rft-adapter and --sampler-command')
    from costagent.train import load_model,logps,save_adapter,fingerprint,require_train_env
    require_train_env()
    from transformers import set_seed
    import torch
    set_seed(args.seed)
    command=json.loads(args.sampler_command.read_text())
    if not isinstance(command,list) or not command or not all(isinstance(x,str) for x in command):
        raise ValueError('Sampler command must be a nonempty JSON argv list')
    state_path=args.output/'state.json';start=0;current=Path(args.rft_adapter)
    signature={k:v for k,v in config.items() if k not in {'iterations','validated_rollouts','blockers'}}
    if state_path.exists():
        if not args.resume: raise ValueError('State exists; use --resume')
        state=json.loads(state_path.read_text())
        if state['config']!=signature: raise ValueError('Resume configuration changed')
        start=state['next_iteration'];current=Path(state['adapter'])
    elif args.resume: raise ValueError('No checkpoint to resume')
    for iteration in range(start,args.iterations):
        tasks=sample_tasks(task_pool,args.tasks,args.seed,iteration)
        directory=args.output/f'iteration-{iteration:04d}';dataset=directory/'rollouts.jsonl'
        policy_hash=fingerprint(current)
        request=dict(config,tasks=tasks,adapter=str(current.resolve()),sampling_policy_sha256=policy_hash,
                     seed=args.seed+iteration,iteration=iteration,output=str(dataset))
        request_path=directory/'request.json';write_json(request_path,request)
        subprocess.run(command+['--request',str(request_path),'--output',str(dataset)],check=True)
        rows=load_dataset(dataset,'grpo',set(tasks))
        missing_tasks=len(set(tasks)-{r['task_id'] for r in rows})
        prepared,dropped=prepare(rows,args.reward,args.group_size,policy_hash)
        if not prepared: raise ValueError('No usable groups after incomplete/zero-variance filtering')
        # The sampler must exit and terminate its vLLM workers before this load.
        model,tokenizer=load_model(args.model,args.rft_adapter,args.qlora)
        if current.resolve()!=Path(args.rft_adapter).resolve():
            model.delete_adapter('policy');model.load_adapter(current,adapter_name='policy',is_trainable=True)
            model.set_adapter('policy')
        for module in model.modules():
            if isinstance(module,torch.nn.Dropout): module.p=0.0
        metrics,optimizer_steps=update_policy(model,prepared,args.epochs,args.minibatch_turns,
                                              args.learning_rate,args.seed+iteration)
        current=save_adapter(model,tokenizer,directory/'adapter')
        del model,tokenizer,module
        gc.collect();torch.cuda.empty_cache()
        vals=[rewards(r['solved'],r['cost'],r['potentials'])[args.reward] for r in rows]
        vals=[sum(v)/len(v) if isinstance(v,list) else v for v in vals]
        summary=dict(iteration=iteration,reward_mean=sum(vals)/len(vals),solve_rate=sum(r['solved'] for r in rows)/len(rows),
                     mean_cost=sum(r['cost'] for r in rows)/len(rows),dropped_groups=dropped,missing_tasks=missing_tasks,optimizer_steps=optimizer_steps,tasks=tasks,
                     kl=sum(m['kl'] for m in metrics)/len(metrics),clip_fraction=sum(m['clip_fraction'] for m in metrics)/len(metrics))
        write_json(directory/'metrics.json',summary)
        # Commit checkpoint only after the adapter and metrics have been saved.
        tmp=state_path.with_suffix('.tmp');write_json(tmp,dict(next_iteration=iteration+1,adapter=str(current),config=signature))
        tmp.replace(state_path);print(json.dumps(summary),flush=True)
    print(f'Saved {current}; vLLM adapter transfer check still required.')

if __name__=='__main__':main()
