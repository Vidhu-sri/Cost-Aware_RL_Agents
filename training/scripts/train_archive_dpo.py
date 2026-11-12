#!/usr/bin/env python3
"""DPO on compatible archived rollouts; fixed SFT reference, two-pass gradient."""
import argparse
import json
import os
from pathlib import Path
import random
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from costagent.traces import ROOT,ARTIFACTS,write_json
from costagent.train import fingerprint


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,default=ARTIFACTS/'archive-dpo-v1/dataset.json')
    p.add_argument('--output',type=Path,default=ARTIFACTS/'archive-dpo-v1')
    p.add_argument('--model',default=str(ROOT/'gemma-4-31b-it-qat-w4a16-ct'))
    p.add_argument('--reference',type=Path,default=ARTIFACTS/'resolved-sft/adapter')
    p.add_argument('--learning-rate',type=float,default=1e-5)
    p.add_argument('--epochs',type=int,default=1)
    p.add_argument('--through-epoch',type=int,help='Stop at this epoch boundary without changing the full-run signature')
    p.add_argument('--compact-checkpoints',action='store_true',help='Retain epoch checkpoints and the latest pair checkpoint')
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--no-nll',action='store_true');p.add_argument('--resume',action='store_true')
    p.add_argument('--dry-run',action='store_true')
    a=p.parse_args();a.output=a.output.resolve()
    allowed_roots=[ARTIFACTS.resolve()]
    if os.environ.get('GEMMA_DPO_OUTPUT_ROOT'):
        allowed_roots.append(Path(os.environ['GEMMA_DPO_OUTPUT_ROOT']).resolve())
    if not any(a.output.is_relative_to(root) for root in allowed_roots):
        p.error('Output must be under artifacts/ or the explicit GEMMA_DPO_OUTPUT_ROOT')
    if a.learning_rate<=0 or a.epochs<1:p.error('Invalid training settings')
    through=a.through_epoch or a.epochs
    if not 1<=through<=a.epochs:p.error('Invalid epoch boundary')
    import hashlib
    data=json.loads(a.dataset.read_text());pairs=data['pairs'];rollouts=data['rollouts']
    if not pairs:raise ValueError('No compatible encoded preference pairs; see dataset report')
    for pair in pairs:
        c,r=(rollouts[pair[side]] for side in ('chosen','rejected'))
        for key in ('task_id','prompt_sha256','environment_sha256'):
            if c[key]!=r[key]:raise ValueError('Mismatched preference pair: '+key)
        if not c['solved']:raise ValueError('Chosen rollout is not solved')
        if r['solved'] and c['calls']>=r['calls']:raise ValueError('Invalid efficiency preference')
        for row in (c,r):
            for turn in row['turns']:
                if len(turn['input_ids'])!=len(turn['assistant_mask']) or turn['assistant_mask'][0] or not any(turn['assistant_mask'][1:]):
                    raise ValueError('Invalid training mask')
    signature=dict(dataset_sha256=hashlib.sha256(a.dataset.read_bytes()).hexdigest(),reference_sha256=fingerprint(a.reference),
        model=a.model,learning_rate=a.learning_rate,epochs=a.epochs,seed=a.seed,compact_checkpoints=a.compact_checkpoints,alpha=0. if a.no_nll else 1.,beta=.1)
    plan=dict(signature=signature,data=data['report'])
    write_json(a.output/'plan.json',plan);print(json.dumps(plan),flush=True)
    if a.dry_run:return
    from costagent.train import require_train_env
    require_train_env()
    import torch
    if not torch.cuda.is_available():raise RuntimeError('GPU must be accessible from the host terminal')
    from transformers import set_seed
    from costagent.archive_dpo_train import load_model,trajectory_score,pair_step
    set_seed(a.seed)
    state_path=a.output/'state.json';state=None;start=0
    if state_path.exists():
        if not a.resume:raise ValueError('Checkpoint exists: use --resume')
        state=json.loads(state_path.read_text())
        if state['signature']!=signature:raise ValueError('Resume configuration differs')
        start=state['next_pair']
    elif a.resume:raise ValueError('No saved DPO state')
    model=load_model(a.model,a.reference,state['adapter'] if state else None)
    progress=lambda event: print(json.dumps(event),flush=True)
    reference_path=a.output/'reference_scores.json'
    if reference_path.exists():
        cached=json.loads(reference_path.read_text())
        if cached['signature']!=signature:raise ValueError('Reference cache signature differs')
        reference=cached['scores']
    else:
        reference={};model.set_adapter('reference')
        for key,row in rollouts.items():
            reference[key]=trajectory_score(model,row,progress)
            print(json.dumps(dict(event='reference_scored',rollout=key,turns=len(row['turns']))),flush=True)
        write_json(reference_path,dict(signature=signature,scores=reference))
    model.set_adapter('policy')
    optimizer=torch.optim.AdamW([v for v in model.parameters() if v.requires_grad],lr=a.learning_rate,foreach=False)
    if state:optimizer.load_state_dict(torch.load(state['optimizer'],map_location=model.get_input_embeddings().weight.device,weights_only=True))
    order=[]
    for epoch in range(a.epochs):
        indices=list(range(len(pairs)));random.Random(a.seed+epoch).shuffle(indices)
        order.extend((epoch,i) for i in indices)
    began=time.time()
    for j in range(start,min(len(order),through*len(pairs))):
        epoch,i=order[j];pair=pairs[i]
        print(json.dumps(dict(event='pair_start',step=j+1,task=pair['task_id'],type=pair['type'])),flush=True)
        optimizer.zero_grad(set_to_none=True)
        metrics=pair_step(model,rollouts[pair['chosen']],rollouts[pair['rejected']],reference,alpha=signature['alpha'],progress=progress)
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.,error_if_nonfinite=True);optimizer.step()
        metrics.update(step=j+1,epoch=epoch,pair=i,elapsed_s=time.time()-began,peak_gib=torch.cuda.max_memory_allocated()/2**30)
        print(json.dumps(metrics),flush=True);write_json(a.output/'latest_metrics.json',metrics)
        checkpoint=a.output/f'checkpoint-{j+1}';checkpoint.mkdir(exist_ok=True)
        model.save_pretrained(checkpoint,selected_adapters=['policy'],safe_serialization=True)
        torch.save(optimizer.state_dict(),checkpoint/'optimizer.pt')
        next_state=dict(next_pair=j+1,adapter=str(checkpoint/'policy'),optimizer=str(checkpoint/'optimizer.pt'),signature=signature)
        temp=state_path.with_suffix('.tmp');write_json(temp,next_state);temp.replace(state_path)
        if a.compact_checkpoints and j>0 and j%len(pairs)!=0:
            import shutil
            previous=a.output/f'checkpoint-{j}'
            if previous.is_dir() and not previous.is_symlink():shutil.rmtree(previous)
        if (j+1)%len(pairs)==0:
            from costagent.dpo_monitor import training_metrics
            scores={key:trajectory_score(model,row,progress) for key,row in rollouts.items()}
            summary=training_metrics(scores,reference,pairs,rollouts,alpha=signature['alpha'])
            summary.update(epoch=epoch+1,step=j+1,adapter=str(checkpoint/'policy'))
            write_json(a.output/f'epoch-{epoch+1}-training-metrics.json',summary)
            print(json.dumps(summary),flush=True)
    if through<a.epochs:return
    final=a.output/'adapter';model.save_pretrained(final,selected_adapters=['policy'],safe_serialization=True)
    write_json(a.output/'complete.json',dict(steps=len(order),adapter=str(final/'policy'),method=data['report']['method'],
        pairs=len(pairs),tasks=data['report']['tasks'],evaluated=False))

if __name__=='__main__':main()
