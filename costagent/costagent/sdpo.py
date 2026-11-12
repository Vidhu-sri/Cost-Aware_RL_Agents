"""Offline cost-aware contrastive self-distillation (experimental SDPO-inspired arm).

A fixed teacher scores the same stored assistant tokens under good/bad feedback.
This is not standard online SDPO, a calibrated reward model, or a telescoping proof.
"""
import argparse,hashlib,json
from collections import defaultdict
from pathlib import Path
import torch
from .costs import counts,calibrate,cost


def contrast_targets(rewards, contrasts, k1=10., k2=1., clip=1., lam=.5):
    if not (0<=lam<1 and clip>0 and k1>0 and k2>=0):raise ValueError('Invalid contrast settings')
    if 2*k2*clip >= k1*(1-lam):raise ValueError('Contrast can reverse success/failure ordering: require 2*k2*clip < k1*(1-lam)')
    d=torch.as_tensor(contrasts,dtype=rewards.dtype,device=rewards.device)
    if not torch.isfinite(d).all() or not torch.isfinite(rewards).all():raise ValueError('Nonfinite scores')
    return torch.softmax(k1*rewards+k2*d.clamp(-clip,clip),dim=0)


def action_feedback(row):
    actions=[];seen=set()
    for turn in row['turns']:
        for call in turn.get('calls',[]):
            text=call['name']+' '+json.dumps(call['args'],sort_keys=True)
            repeat=' [REPEATED IDENTICAL CALL]' if text in seen else ''
            seen.add(text);actions.append(text[:240]+repeat)
    return '\n'.join(actions)[:4000]


def failure_feedback(row):
    evidence=[]
    for turn in row['turns']:
        for result in turn.get('results',[]):
            text=result.get('content','')
            if any(word in text.lower() for word in ('fail','error','traceback','exception')):evidence.append(text[:700])
    return '\n'.join(evidence)[:3000] or 'No detailed failure output was captured; final rollout was not successful.'


def feedback(rows,gold=None):
    successes=sorted([r for r in rows if r['solved']],key=lambda r:(r['cost'],r['rollout_id']))
    failures=[r for r in rows if not r['solved']]
    if successes:
        positive='Verified successful attempt (lowest recorded cost):\n'+action_feedback(successes[0])
        if failures:
            return positive,'Unsuccessful attempt:\n'+action_feedback(failures[0])+'\nObserved failure output:\n'+failure_feedback(failures[0]),'mixed'
        return positive,'Verified successful but highest-cost attempt; contrast efficiency only:\n'+action_feedback(successes[-1]),'all_success'
    if not gold:raise ValueError('All-failure group requires an authorized training reference patch')
    positive='Privileged reference patch for this TRAINING task; teacher only:\n'+gold[:6000]
    negative='Observed unsuccessful attempts:\n'+'\n'.join(action_feedback(r)+'\n'+failure_feedback(r) for r in rows)
    return positive,negative[:6000],'all_failure'


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

def aligned_views(tok,row,positive,negative,max_len):
    """Jointly truncate complete exchanges; all views score identical target tokens."""
    from .chat import blocks,_render
    head,history=blocks(row)
    result=[[],[],[]]
    for i,(turn,messages) in enumerate(history):
        if turn is None:continue
        for start in range(i+1):
            retained=[m for _,ms in history[start:i] for m in ms]
            examples=[]
            for feedback_text in (None,positive,negative):
                header=[dict(m) for m in head]
                if feedback_text is not None:
                    extra="\n\nTeacher-only retrospective feedback:\n"+feedback_text
                    if header and header[0]['role']=='system':header[0]['content']+=extra
                    else:header.insert(0,{'role':'system','content':extra})
                context=header+retained
                prefix=_render(tok,context,True);full=_render(tok,context+[messages[0]],False)
                if not full.startswith(prefix):
                    # Gemma merges adjacent assistant messages. In that case
                    # the existing rendered context is the continuation prefix.
                    if not context or context[-1]['role']!='assistant':return None
                    prefix=_render(tok,context,False)
                    if not full.startswith(prefix):return None
                pids=tok(prefix,add_special_tokens=False)['input_ids']
                ids=tok(full,add_special_tokens=False)['input_ids']
                if ids[:len(pids)]!=pids or len(ids)==len(pids):return None
                examples.append(dict(input_ids=ids,mask=[0]*len(pids)+[1]*(len(ids)-len(pids)),n_assistant=len(ids)-len(pids),approx=True,turn=i,dropped_blocks=start))
            if max(len(e['input_ids']) for e in examples)>max_len:continue
            targets=[[t for t,m in zip(e['input_ids'],e['mask']) if m] for e in examples]
            if targets[0]!=targets[1] or targets[0]!=targets[2]:return None
            for dest,example in zip(result,examples):dest.append(example)
            break
        else:return None
    return result


def prepare(args):
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(args.model,local_files_only=True)
    rows=[json.loads(x) for x in Path(args.trajectories).read_text().splitlines() if x.strip()]
    allowed=set(json.loads(Path(args.training_tasks).read_text()))
    if any(r['task_id'] not in allowed for r in rows):raise ValueError('Non-training task in teacher dataset')
    gold=json.loads(Path(args.gold_json).read_text()) if args.gold_json else {}
    for r in rows:r['counts']=counts(r)
    cal=calibrate(rows)
    groups=defaultdict(list)
    for r in rows:
        if not r.get('compatibility_sha256'):raise ValueError('Missing verified compatibility grouping')
        r['cost']=cost(r['counts'],r['task_id'],cal)
        groups[(r['task_id'],r['compatibility_sha256'])].append(r)
    output=[];skips=[]
    for (tid,compat),rs in groups.items():
        if len(rs)<2:continue
        try:pos,neg,kind=feedback(rs,gold.get(tid))
        except ValueError as e:skips.append({'task':tid,'reason':str(e)});continue
        cs=[]
        for r in rs:
            sets = aligned_views(tok,r,pos,neg,args.max_len)
            if sets is None:
                skips.append({'rollout':r['rollout_id'],'reason':'cannot encode aligned teacher/student views'});continue
            clean,plus,minus=sets
            ok=bool(clean)
            if not ok:skips.append({'rollout':r['rollout_id'],'reason':'cannot align full trajectory targets/history within context budget'});continue
            cs.append(dict(rollout_id=r['rollout_id'],task_id=tid,solved=r['solved'],cost=r['cost'],all_turns=clean,teacher_plus=plus,teacher_minus=minus))
        # Never silently change the group outcome class after encoding.
        if len(cs)!=len(rs):skips.append({'task':tid,'reason':'whole group excluded after candidate alignment failure'});continue
        output.append(dict(task_id=tid,kind=kind,compatibility_sha256=compat,candidates=cs))
    dest=Path(args.output);dest.mkdir(parents=True,exist_ok=True)
    torch.save(output,dest/'teacher_inputs.pt')
    coverage={kind:sum(g['kind']==kind for g in output) for kind in ('mixed','all_success','all_failure')}
    (dest/'prepare_report.json').write_text(json.dumps({'groups':len(output),'group_kinds':coverage,'candidates':sum(len(g['candidates']) for g in output),'input_trajectories':len(rows),'skips':skips,'training_tasks':sorted(allowed),'approximate_contexts':True,'cost_tokens':'prompt+completion proxy, not generated+observation','teacher_feedback_only':True},indent=2)+'\n')
    print('Prepared groups:',len(output),'skips:',len(skips))


@torch.no_grad()
def token_scores(model,example):
    from .modeling import _parts,_chunk_lp
    device=model.get_input_embeddings().weight.device
    ids=torch.tensor(example['input_ids'],device=device)[None]
    mask=torch.tensor(example['mask'],device=device,dtype=torch.bool)
    decoder,head,cap=_parts(model)
    with torch.autocast(device_type=device.type,dtype=torch.bfloat16,enabled=device.type=='cuda'):
        hidden=decoder(input_ids=ids,use_cache=False).last_hidden_state[0]
        positions=torch.where(mask[1:])[0]
        chunks=[_chunk_lp(head,cap,hidden[p],ids[0,p+1]).cpu() for p in positions.split(64)]
    return torch.cat(chunks) if chunks else torch.empty(0)


def score(args):
    from .modeling import load
    inputs=Path(args.inputs);teacher=Path(args.teacher)
    signature=digest(dict(inputs_sha256=hashlib.sha256(inputs.read_bytes()).hexdigest(),teacher_sha256=hashlib.sha256((teacher/'adapter_model.safetensors').read_bytes()).hexdigest(),teacher_config=(teacher/'adapter_config.json').read_text(),model=str(Path(args.model).resolve()),model_config=(Path(args.model)/'config.json').read_text(),clip=args.clip))
    dest=Path(args.output);dest.mkdir(parents=True,exist_ok=True);cache=dest/'teacher_scores.json'
    saved=json.loads(cache.read_text()) if cache.exists() else {'signature':signature,'scores':{}}
    if saved['signature']!=signature:raise ValueError('Teacher cache signature mismatch')
    groups=torch.load(inputs,weights_only=False)
    if not groups:raise ValueError('No aligned groups to score')
    if args.clip<=0:raise ValueError('clip must be positive')
    if args.dry_run:
        print(json.dumps({'groups':len(groups),'teacher':str(teacher),'signature':signature,'teacher_passes_per_turn':2,'cached_candidates':len(saved['scores'])}));return
    if not torch.cuda.is_available():raise RuntimeError('Teacher scoring requires the GPU; no CPU fallback for 31B')
    model=load(args.model,'bf16',adapter=args.teacher,grad_ckpt=False)
    model.requires_grad_(False);model.eval()
    for group in groups:
        for c in group['candidates']:
            key=digest({'task':group['task_id'],'compatibility':group['compatibility_sha256'],'rollout':c['rollout_id']})
            if key not in saved['scores']:
                total=0.;raw=0.;n=0
                for plus,minus in zip(c['teacher_plus'],c['teacher_minus']):
                    delta=token_scores(model,plus)-token_scores(model,minus)
                    if not torch.isfinite(delta).all():raise ValueError('Nonfinite teacher contrast')
                    total+=float(delta.clamp(-args.clip,args.clip).sum());raw+=float(delta.sum());n+=delta.numel()
                if not n:raise ValueError('No teacher target tokens')
                saved['scores'][key]={'contrast':total/n,'unclipped_mean':raw/n,'tokens':n}
                temp=cache.with_suffix('.tmp');temp.write_text(json.dumps(saved,indent=2)+'\n');temp.replace(cache)
                print(json.dumps({'event':'teacher_candidate_scored','task':group['task_id'],'cached_candidates':len(saved['scores']),'tokens':n,'contrast':total/n}),flush=True)
            c['teacher_contrast']=saved['scores'][key]['contrast']
            # Privileged contexts never enter the student training file.
            del c['teacher_plus'];del c['teacher_minus']
        group['teacher_signature']=signature
        group['teacher_clip']=args.clip
    torch.save(groups,dest/'student_groups.pt')
    print('Scored groups:',len(groups),'cache:',cache)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='mode',required=True)
    a=sub.add_parser('prepare');a.add_argument('--trajectories',required=True);a.add_argument('--training-tasks',required=True);a.add_argument('--gold-json');a.add_argument('--max-len',type=int,default=8192)
    b=sub.add_parser('score');b.add_argument('--inputs',required=True);b.add_argument('--teacher',required=True);b.add_argument('--clip',type=float,default=1.);b.add_argument('--dry-run',action='store_true')
    for child in (a,b):child.add_argument('--model',required=True);child.add_argument('--output',required=True)
    args=p.parse_args();(prepare if args.mode=='prepare' else score)(args)

if __name__=='__main__':main()
