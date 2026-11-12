#!/usr/bin/env python3
"""Trajectory-pair DPO with RFT reference and assistant-only NLL anchor."""
import argparse
from collections import Counter
import json
import random
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from costagent.datasets import allowed_tasks, load_dataset
from costagent.traces import ARTIFACTS, write_json


def plan(args):
    rows=load_dataset(args.dataset,'dpo',allowed_tasks()) if args.dataset else []
    config=dict(method='cheap_trajectory_pair_DPO',examples=len(rows),types=dict(Counter(r['type'] for r in rows)),
                beta=.1,nll_alpha=0.0 if args.no_nll else 1.0,seed=args.seed,rank=16,
                learning_rate=args.learning_rate,grad_accum=args.grad_accum,epochs=args.epochs,
                max_length=32768,reference=args.rft_adapter,assistant_only=True,
                blockers=[] if rows else ['No verified tokenized sibling-pair dataset; see artifacts/QUESTIONS.md'])
    write_json(ARTIFACTS/'dpo_plan.json',config)
    return rows,config


def reference_scores(model, pair):
    import torch
    from costagent.train import logps
    model.set_adapter('reference')
    with torch.no_grad():
        scores = {side: sum(float(logps(model, turn)[0][logps_mask(turn)].sum())
                           for turn in pair[side + '_turns'])
                  for side in ('chosen', 'rejected')}
    model.set_adapter('policy')
    return scores


def logps_mask(turn):
    # Python indices also work when likelihoods live on a CUDA device.
    return [i for i, value in enumerate(turn['assistant_mask'][1:]) if value]


def dpo_pair_step(model, pair, reference, beta=.1, alpha=1., scale=1.):
    """Exact pair gradient, retaining at most one turn's activation graph."""
    import torch
    from costagent.train import logps
    model.set_adapter('policy')
    scores = {}
    with torch.no_grad():
        for side in ('chosen', 'rejected'):
            scores[side] = sum(float(logps(model, turn)[0][logps_mask(turn)].sum())
                               for turn in pair[side + '_turns'])
    count = sum(sum(t['assistant_mask'][1:]) for t in pair['chosen_turns'])
    margin = torch.tensor((scores['chosen'] - scores['rejected']) -
                          (reference['chosen'] - reference['rejected']), dtype=torch.float64)
    g = float(-beta * torch.sigmoid(-beta * margin))
    for side, weight in (('chosen', g - alpha/count), ('rejected', -g)):
        for turn in pair[side + '_turns']:
            lp, mask = logps(model, turn)
            (scale * weight * lp[mask].sum()).backward()
            del lp, mask
    return float(-torch.nn.functional.logsigmoid(beta * margin) - alpha*scores['chosen']/count)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path);p.add_argument('--model');p.add_argument('--rft-adapter')
    p.add_argument('--output',type=Path,default=ARTIFACTS/'dpo');p.add_argument('--dry-run',action='store_true')
    p.add_argument('--no-nll',action='store_true');p.add_argument('--qlora',action='store_true')
    p.add_argument('--learning-rate',type=float,default=1e-5)
    p.add_argument('--grad-accum',type=int,default=8)
    p.add_argument('--epochs',type=int,default=1);p.add_argument('--seed',type=int,default=42)
    args=p.parse_args()
    if args.epochs < 1 or args.grad_accum < 1 or args.learning_rate <= 0: p.error("Invalid training hyperparameters")
    args.output=args.output.resolve()
    if not args.output.is_relative_to(ARTIFACTS.resolve()): p.error('Output must be under artifacts/')
    rows,config=plan(args)
    if args.dry_run: print(json.dumps(config,indent=2));return
    if not rows or not args.model or not args.rft_adapter: p.error('Training needs --dataset, --model and --rft-adapter')
    from costagent.train import load_model, logps, save_adapter, require_train_env
    require_train_env()
    from transformers import set_seed
    set_seed(args.seed)
    model,tokenizer=load_model(args.model,args.rft_adapter,args.qlora)
    import torch
    model.train()  # load_model disables dropout, including LoRA dropout.
    references=[reference_scores(model,pair) for pair in rows]
    model.set_adapter('policy')
    optimizer=torch.optim.AdamW([v for v in model.parameters() if v.requires_grad],lr=args.learning_rate)
    for epoch in range(args.epochs):
        order=list(range(len(rows)));random.Random(args.seed+epoch).shuffle(order)
        for offset in range(0,len(order),args.grad_accum):
            batch=order[offset:offset+args.grad_accum]
            optimizer.zero_grad(set_to_none=True)
            losses=[dpo_pair_step(model,rows[i],references[i],alpha=0. if args.no_nll else 1.,
                                  scale=1/len(batch)) for i in batch]
            torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
            optimizer.step()
            print(json.dumps(dict(epoch=epoch,loss=sum(losses)/len(losses))),flush=True)
    saved=save_adapter(model,tokenizer,args.output)
    write_json(ARTIFACTS/'dpo_transfer_pending.json',{'adapter':str(saved),'status':'requires vLLM transfer check'})
    print(f'Saved {saved}. Run scripts/check_adapter.py in the serving environment before evaluation.')

if __name__=='__main__':main()
