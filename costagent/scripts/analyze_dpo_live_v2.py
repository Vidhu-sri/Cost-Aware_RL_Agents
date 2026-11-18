import json,pathlib,collections,statistics,math,sys
import numpy as np
from scipy.stats import binomtest,wilcoxon
R=pathlib.Path(__file__).resolve().parents[2]/'results/dpo_live_v2';rng=np.random.default_rng(20261119)
rows={};turns={};snaps={};traces={}
for p in (R/'attempts').glob('*/*/done.json'):
 d=json.loads(p.read_text())
 if d.get('smoke'):continue
 key=(d['task_id'],d['arm']);rows[key]=d
 q=pathlib.Path(d['result_dir'])
 turns[key]=[json.loads(x) for x in (q/'turn_telemetry.jsonl').read_text().splitlines() if x]
 snaps[key]=[json.loads(x) for x in (q/'snapshot_manifest.jsonl').read_text().splitlines() if x] if (q/'snapshot_manifest.jsonl').exists() else []
 trace=q/'traces'/f'trace_{d["task_id"]}.json'
 traces[key]=json.loads(trace.read_text())['steps'] if trace.exists() else []
assert len(rows)==168
ids=sorted({k[0] for k in rows});assert len(ids)==84 and all((t,a) in rows for t in ids for a in ('A0','DPO'))
valid=lambda d: d['verification_status'] in ('passed','failed','no_patch')
paired=[t for t in ids if valid(rows[t,'A0']) and valid(rows[t,'DPO'])]
solve=lambda t,a: rows[t,a]['resolved'] is True
b=sum(solve(t,'A0') and not solve(t,'DPO') for t in paired);c=sum(solve(t,'DPO') and not solve(t,'A0') for t in paired)
mcn=min(1.,2*binomtest(min(b,c),b+c,p=.5,alternative='less').pvalue) if b+c else 1.
out={'n_attempts':168,'n_tasks':84,'interpretable_pairs':len(paired),'unknown_pairs':len(ids)-len(paired),'mcnemar':{'A0_only':b,'DPO_only':c,'p_exact_two_sided':mcn,'A0_only_ids':[t for t in paired if solve(t,'A0') and not solve(t,'DPO')],'DPO_only_ids':[t for t in paired if solve(t,'DPO') and not solve(t,'A0')]},'arms':{}}
for arm in ('A0','DPO'):
 d=[rows[t,arm] for t in ids];out['arms'][arm]={'passes':sum(x['resolved'] is True for x in d),'failed':sum(x['verification_status']=='failed' for x in d),'no_patch':sum(x['verification_status']=='no_patch' for x in d),'unknown':sum(x['resolved'] is None for x in d),'timeouts':sum(x['agent_timeout'] for x in d),'timeout_passes':sum(x['agent_timeout'] and x['resolved'] is True for x in d),'calls_total':sum(x['tool_calls'] for x in d),'calls_mean':statistics.mean(x['tool_calls'] for x in d),'tokens_total':sum(x['prompt_tokens']+x['completion_tokens'] for x in d),'tokens_mean':statistics.mean(x['prompt_tokens']+x['completion_tokens'] for x in d),'llm_total':sum(x['total_llm_calls'] for x in d),'wall_mean_s':statistics.mean(x['elapsed_controller_seconds'] for x in d if isinstance(x.get('elapsed_controller_seconds'),(int,float))),'cleanup_fail':sum(x['cleanup_ok'] is not True for x in d)}
 out['arms'][arm]['calls_per_solve']=out['arms'][arm]['calls_total']/out['arms'][arm]['passes']
 out['arms'][arm]['tokens_per_solve']=out['arms'][arm]['tokens_total']/out['arms'][arm]['passes']
for field in ('tool_calls','tokens'):
 a=np.array([rows[t,'A0']['tool_calls'] if field=='tool_calls' else rows[t,'A0']['prompt_tokens']+rows[t,'A0']['completion_tokens'] for t in ids],float)
 d=np.array([rows[t,'DPO']['tool_calls'] if field=='tool_calls' else rows[t,'DPO']['prompt_tokens']+rows[t,'DPO']['completion_tokens'] for t in ids],float)
 z=d-a;res=wilcoxon(z,zero_method='wilcox',alternative='two-sided')
 out[field+'_paired']={'p':float(res.pvalue),'statistic':float(res.statistic),'ties':int((z==0).sum()),'mean_diff':float(z.mean())}
 ix=rng.integers(0,len(ids),size=(20000,len(ids)))
 sa=np.array([solve(t,'A0') for t in ids]);sd=np.array([solve(t,'DPO') for t in ids]);na=sa[ix].sum(axis=1);nd=sd[ix].sum(axis=1)
 with np.errstate(divide='ignore',invalid='ignore'): diff=d[ix].sum(axis=1)/nd-a[ix].sum(axis=1)/na
 good=diff[np.isfinite(diff)];out[field+'_per_solve_bootstrap']={'undefined_draws':int(len(diff)-len(good)),'diff_CI':list(np.quantile(good,[.025,.975])) if len(good)>=.975*len(diff) else None}
# process features
features={}
for key,d in rows.items():
 tt=turns[key];gen=[x.get('generation_wall_seconds') for x in tt if isinstance(x.get('generation_wall_seconds'),(int,float)) and x['generation_wall_seconds']>0]
 calls=[]
 for step in traces[key]:
  if step.get('source')=='agent':calls.extend(step.get('tool_calls') or [])
 actions=[x.get('function_name') for x in calls]
 features[key]={'mean_gen_s':statistics.mean(gen) if gen else None,'edits':sum(n in ('edit_file','write_file') for n in actions),'actions':len(actions),'edit_share':sum(n in ('edit_file','write_file') for n in actions)/len(actions) if actions else 0,'explicit_submit':any(n=='submit_patch' for n in actions),'turns':len(tt),'gen_n':len(gen),'load_running_mean':statistics.mean(x.get('running_requests') or 0 for x in tt) if tt else None,'load_waiting_mean':statistics.mean(x.get('waiting_requests') or 0 for x in tt) if tt else None}
for arm in ('A0','DPO'):
 fs=[features[t,arm] for t in ids];out['arms'][arm].update({'explicit_submit':sum(x['explicit_submit'] for x in fs),'edit_actions':sum(x['edits'] for x in fs),'all_actions':sum(x['actions'] for x in fs),'edit_share_pooled':sum(x['edits'] for x in fs)/sum(x['actions'] for x in fs),'mean_gen_s_per_turn':statistics.mean(x['mean_gen_s'] for x in fs if x['mean_gen_s']),'turns_mean':statistics.mean(x['turns'] for x in fs)})
# H1-3 paired task permutation and bootstrap
for label,values,direction in [('H1_gen_s',[math.log(features[t,'DPO']['mean_gen_s']/features[t,'A0']['mean_gen_s']) for t in ids],-1),('H2_calls',[math.log(rows[t,'DPO']['tool_calls']/rows[t,'A0']['tool_calls']) for t in ids],1),('H3_edit_share',[features[t,'DPO']['edit_share']-features[t,'A0']['edit_share'] for t in ids],1)]:
 v=np.array(values);obs=v.mean();ix=rng.integers(0,len(v),size=(20000,len(v)));boot=v[ix].mean(axis=1);signs=rng.choice([-1,1],size=(20000,len(v)));null=(v*signs).mean(axis=1);p=(1+sum(direction*null>=direction*obs))/(20001)
 ci=np.quantile(boot,[.025,.975]);out[label]={'estimate':float(math.exp(obs) if label!='H3_edit_share' else obs),'ci':list(np.exp(ci) if label!='H3_edit_share' else ci),'p_one_sided':float(p)}
suba=[features[t,'A0']['explicit_submit'] for t in ids];subd=[features[t,'DPO']['explicit_submit'] for t in ids];hb=sum(a and not d for a,d in zip(suba,subd));hc=sum(d and not a for a,d in zip(suba,subd));out['H4_submit']={'A0_only':hb,'DPO_only':hc,'p_one_sided':binomtest(hc,hb+hc,p=.5,alternative='greater').pvalue if hb+hc else 1.}
pvals=[out['H1_gen_s']['p_one_sided'],out['H2_calls']['p_one_sided'],out['H3_edit_share']['p_one_sided'],out['H4_submit']['p_one_sided']];order=np.argsort(pvals);adj=[0.]*4;mx=0
for k,i in enumerate(order):mx=max(mx,min(1.,pvals[i]*(4-k)));adj[i]=mx
out['holm_adjusted']={k:adj[i] for i,k in enumerate(('H1_gen_s','H2_calls','H3_edit_share','H4_submit'))}
# snapshot found/lost, only valid failed outcomes; dedupe by task and sha but propagate to both arms if same diff
vr={}
for line in (R/'snapshot_verification.jsonl').read_text().splitlines():
 if line:
  x=json.loads(line);vr[x['task_id'],x['patch_sha256']]=x
for arm in ('A0','DPO'):
 failed=[t for t in ids if rows[t,arm]['verification_status'] in ('failed','no_patch')]
 found=[];unknown=[]
 for t in failed:
  ss=snaps[t,arm]; grades=[vr.get((t,x.get('patch_sha256'))) for x in ss if x.get('status')=='ok']
  if any(g and g.get('status')=='complete' and g.get('resolved') is True for g in grades):found.append(t)
  if any(g is None or g.get('status')!='complete' for g in grades):unknown.append(t)
 out['arms'][arm]['failed_attempts_for_found_lost']=len(failed);out['arms'][arm]['found_then_lost']=found;out['arms'][arm]['snapshot_unknown_attempts']=unknown
out['snapshot_verifications']={'unique':len(vr),'status':dict(collections.Counter(x['status'] for x in vr.values())),'passes':sum(x.get('resolved') is True for x in vr.values())}
path=R/'analysis_summary.json';path.write_text(json.dumps(out,indent=2,default=float)+'\n');print(json.dumps(out,indent=2,default=float))
