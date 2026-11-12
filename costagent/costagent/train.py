"""Training entry point.

  python -m costagent.train sft  --data artifacts/data/sft.pt    --model M --out artifacts/adapters/a2_rft
  python -m costagent.train pref --data artifacts/data/groups.pt --model M --out artifacts/adapters/a6b_k5 \
         --targets soft --kappa 5

pref implements THEORY.md sections 4-6: listwise loss over a task's rollouts with
targets softmax(R2/T), exact per-candidate coefficients, two-pass surrogate
gradients, stratified turn sampling (weights stored by the builder), NLL anchor.
Reference scores are cached; policy scores and exact coefficients are recomputed
for every group before its backward pass. Full encoded turns are required.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

import torch

from .listwise import coefficients, targets


def log(path: Path, **kv):
    kv["t"] = round(time.time(), 1)
    with open(path, "a") as f:
        f.write(json.dumps(kv) + "\n")
    print(json.dumps(kv), flush=True)


def make_opt(model, lr, total_steps):
    warmup = max(1, min(10, total_steps // 10))  # short runs must not spend their steps warming up
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=lr, betas=(0.9, 0.95), weight_decay=0.0)

    def lr_at(s):
        if s < warmup:
            return (s + 1) / warmup
        prog = (s - warmup) / max(1, total_steps - warmup)
        return 0.5 * (1 + math.cos(math.pi * min(1.0, prog)))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_at)
    return opt, sched, params


def check_frozen_base(model):
    bad = [n for n, p in model.named_parameters() if p.requires_grad and "lora_" not in n]
    assert not bad, f"non-LoRA params are trainable: {bad[:5]}"


def seq_logratio_full(model, cand, tok_examples):
    """Exact r = log P_pol - log P_ref over every turn (used by --rescore)."""
    from .modeling import turn_logprob
    pol = ref = 0.0
    with torch.no_grad():
        for e in tok_examples:
            lp, _ = turn_logprob(model, e["input_ids"], e["mask"])
            pol += float(lp)
            with model.disable_adapter():
                lr_, _ = turn_logprob(model, e["input_ids"], e["mask"])
            ref += float(lr_)
    return pol - ref


def epoch_checkpoint(args, model, mlog, epoch, step, **metrics):
    directory = Path(args.out) / f"epoch-{epoch:03d}"
    model.save_pretrained(directory, selected_adapters=["default"], safe_serialization=True)
    record = dict(event="epoch_end", epoch=epoch, step=step, checkpoint=str(directory), **metrics)
    (directory / "epoch_metrics.json").write_text(json.dumps(record, indent=2) + "\n")
    log(mlog, **record)


def run_sft(args, model, data, mlog):
    from .modeling import turn_logprob
    turns = [e for c in data for e in c["turns"]]
    rng = random.Random(args.seed)
    opt, sched, params = make_opt(model, args.lr, math.ceil(len(turns)/args.accum)*args.epochs)
    step = 0
    for ep in range(args.epochs):
        rng.shuffle(turns); started=time.time(); nll_sum=0.; tokens=0
        for offset in range(0,len(turns),args.accum):
            batch=turns[offset:offset+args.accum];opt.zero_grad(set_to_none=True)
            for e in batch:
                lp,n=turn_logprob(model,e["input_ids"],e["mask"])
                loss=-lp/max(n,1)
                if not torch.isfinite(loss):raise RuntimeError("Nonfinite SFT loss")
                (loss/len(batch)).backward()
                nll_sum-=float(lp.detach());tokens+=n
            gn=torch.nn.utils.clip_grad_norm_(params,1.,error_if_nonfinite=True)
            opt.step();sched.step();step+=1
            log(mlog,mode="sft",epoch=ep+1,step=step,loss=float(loss.detach()),grad_norm=float(gn),lr=sched.get_last_lr()[0])
        epoch_checkpoint(args,model,mlog,ep+1,step,mode="sft",nll_per_token=nll_sum/max(tokens,1),assistant_tokens=tokens,seconds=time.time()-started)


def full_turns(candidate):
    turns=candidate.get("all_turns")
    if not turns:raise ValueError("Exact preference training requires --all-turns data")
    return turns


def run_pref(args, model, data, mlog):
    """Exact two-pass listwise/DPO gradient, recomputed at every update group."""
    from .modeling import turn_logprob
    from .listwise import listwise_loss
    import contextlib
    @contextlib.contextmanager
    def reference():
        if args.adapter:
            model.set_adapter("reference")
            try:yield
            finally:model.set_adapter("default")
        else:
            with model.disable_adapter():yield
    def score(c):
        with torch.no_grad():
            vals=[turn_logprob(model,e["input_ids"],e["mask"])[0] for e in full_turns(c)]
            return sum(float(v) for v in vals)
    unique={c['rollout_id']:c for g in data for c in g['candidates']}
    # Reference is fixed: SFT adapter if supplied, otherwise the frozen base.
    with reference():refs={key:score(c) for key,c in unique.items()}
    for g in data:
        if not any(c['solved'] for c in g['candidates']) and not getattr(args,'teacher_contrast',False):raise ValueError('No successful candidate')
    lam=args.kappa*args.T
    if not 0<=lam<1:raise ValueError('kappa*T must be in [0,1)')
    opt,sched,params=make_opt(model,args.lr,math.ceil(len(data)/args.accum)*args.epochs)
    rng=random.Random(args.seed);step=0
    for ep in range(args.epochs):
        order=list(range(len(data)));rng.shuffle(order);started=time.time();losses=[];margins=[];accuracy=[];nlls=[]
        for offset in range(0,len(order),args.accum):
            batch=order[offset:offset+args.accum];opt.zero_grad(set_to_none=True)
            for gi in batch:
                g=data[gi];cs=g['candidates']
                policy=torch.tensor([score(c) for c in cs],dtype=torch.float64)
                ratios=policy-torch.tensor([refs[c['rollout_id']] for c in cs],dtype=torch.float64)
                rewards=torch.tensor([float(c['solved'])*(1-lam*c['cost']) for c in cs],dtype=torch.float64)
                if getattr(args,'teacher_contrast',False):
                    from .sdpo import contrast_targets
                    if any('teacher_plus' in c or 'teacher_minus' in c for c in cs):raise ValueError('Privileged teacher inputs in student data')
                    contrasts=[c['teacher_contrast'] for c in cs]
                    weight=args.contrast_weight
                    if args.no_efficiency_contrast and all(c['solved'] for c in cs):weight=0.
                    w=contrast_targets(rewards,contrasts,1/args.T,weight,args.contrast_clip,lam)
                else:w=targets(rewards,args.targets,args.T)
                best=int(w.argmax())
                group_alpha=args.alpha if any(c['solved'] for c in cs) else 0.
                n=sum(sum(e['mask'][1:]) for e in full_turns(cs[best]))
                if n<=0:raise ValueError('Empty chosen target')
                coef=coefficients(ratios,w,args.beta,group_alpha,n)
                objective=float(listwise_loss(ratios,w,args.beta)-group_alpha*policy[best]/n)
                if not math.isfinite(objective):raise RuntimeError('Nonfinite preference objective')
                losses.append(objective);nlls.append(float(-policy[best]/n))
                others=[float(ratios[j]) for j in range(len(cs)) if j!=best]
                margin=float(ratios[best])-max(others);margins.append(margin);accuracy.append(float(margin>0)+.5*float(margin==0))
                for c,weight in zip(cs,coef.tolist()):
                    for e in full_turns(c):
                        lp,_=turn_logprob(model,e['input_ids'],e['mask'])
                        (weight*lp/len(batch)).backward()
            gn=torch.nn.utils.clip_grad_norm_(params,1.,error_if_nonfinite=True)
            opt.step();sched.step();step+=1
            log(mlog,mode="pref",method="exact_two_pass",epoch=ep+1,step=step,loss=losses[-1],margin=margins[-1],chosen_nll=nlls[-1],grad_norm=float(gn),lr=sched.get_last_lr()[0])
        avg=lambda xs:sum(xs)/len(xs)
        epoch_checkpoint(args,model,mlog,ep+1,step,mode="pref",loss=avg(losses),margin=avg(margins),preference_accuracy=avg(accuracy),chosen_nll=avg(nlls),seconds=time.time()-started,metrics_scope="training groups measured before their updates; not held-out evaluation")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["sft", "pref"])
    ap.add_argument("--data", required=True)
    ap.add_argument("--model", required=True, help="trainable base weights (bf16 HF checkpoint)")
    ap.add_argument("--load", choices=["nf4", "bf16"], default="nf4")
    ap.add_argument("--adapter", default=None, help="start from an existing adapter (else zero-init LoRA)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--targets", choices=["soft", "hard"], default="soft")
    ap.add_argument("--kappa", type=float, default=5.0, help="lambda/T; 0 = cost-blind ablation")
    ap.add_argument("--T", type=float, default=0.1)
    ap.add_argument("--beta", type=float, default=0.1)
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--teacher-contrast", action="store_true", help="SDPO-inspired offline two-context listwise arm")
    ap.add_argument("--contrast-weight", type=float, default=1.)
    ap.add_argument("--contrast-clip", type=float, default=1.)
    ap.add_argument("--no-efficiency-contrast", action="store_true")
    ap.add_argument("--rescore", action="store_true")
    ap.add_argument("--probe-every", type=int, default=5)
    ap.add_argument("--displacement-tol", type=float, default=0.2)
    ap.add_argument("--max-items", type=int, default=0, help="debug: limit groups/trajectories")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if args.epochs < 1 or args.accum < 1: ap.error("epochs and accum must be positive")
    torch.manual_seed(args.seed)
    data = torch.load(args.data, weights_only=False)
    if args.max_items:
        data = data[:args.max_items]
    if not data:
        raise SystemExit(f"no training data in {args.data}")
    if args.teacher_contrast:
        from .sdpo import contrast_targets
        if args.mode!='pref' or args.T<=0 or not args.adapter:
            ap.error('teacher contrast requires pref mode, positive T, and a fixed reference adapter')
        contrast_targets(torch.zeros(2),[0.,0.],1/args.T,args.contrast_weight,args.contrast_clip,args.kappa*args.T)
        for group in data:
            if group.get('teacher_clip')!=args.contrast_clip:
                raise ValueError('Training contrast clip differs from teacher scoring clip')
            if len(group['candidates'])<2:
                raise ValueError('Contrast training requires at least two candidates')
            for c in group['candidates']:
                if 'teacher_plus' in c or 'teacher_minus' in c or not math.isfinite(c.get('teacher_contrast',float('nan'))):
                    raise ValueError('Expected clean student inputs with finite cached teacher scores')
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    mlog = out / "metrics.jsonl"
    log(mlog, start=vars(args), items=len(data))

    from .modeling import load
    model = load(args.model, args.load, lora_r=args.rank, lora_alpha=2 * args.rank, adapter=args.adapter)
    if args.mode == "pref" and args.adapter:
        model.load_adapter(args.adapter, adapter_name="reference", is_trainable=False, autocast_adapter_dtype=False)
        model.set_adapter("default")
    check_frozen_base(model)
    model.train()
    if args.mode == "sft":
        run_sft(args, model, data, mlog)
    else:
        run_pref(args, model, data, mlog)
    model.save_pretrained(out, selected_adapters=["default"], safe_serialization=True)
    log(mlog, done=True, saved=str(out))


if __name__ == "__main__":
    main()
