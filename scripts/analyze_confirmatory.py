"""No interim analysis: require every preregistered slot before comparing arms."""
import csv,json,math,sys
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/confirmatory'
E=ROOT/'costagent/artifacts/mixed-temperature-v1/evaluation'
NBOOT=20000;SEED=20261116

def wilson(k,n):
 if not n:return None
 z=1.959963984540054;p=k/n;d=1+z*z/n
 return [(p+z*z/2/n-z*math.sqrt(p*(1-p)/n+z*z/4/n/n))/d,(p+z*z/2/n+z*math.sqrt(p*(1-p)/n+z*z/4/n/n))/d]

def mcnemar(a,b):
 left=sum(x is True and y is False for x,y in zip(a,b));right=sum(y is True and x is False for x,y in zip(a,b));n=left+right
 p=min(1.,2*sum(math.comb(n,k) for k in range(min(left,right)+1))/2**n) if n else 1.
 return {'paired_n':len(a),'baseline_only':left,'router_only':right,'exact_two_sided_p':p}

def trace_cost(path):
 if not Path(path).exists():return {'calls':None,'tokens':None,'llm_calls':None,'trace_missing':True}
 trace=json.loads(Path(path).read_text());calls=tokens=llm=0
 for step in trace['steps']:
  metrics=step.get('metrics') or {}
  tokens+=int(metrics.get('prompt_tokens') or 0)+int(metrics.get('completion_tokens') or 0)
  if step.get('source')=='agent':llm+=1
  for c in step.get('tool_calls') or []:calls+=c.get('function_name',c.get('name','')) not in {'get_status','submit_patch'}
 return {'calls':calls,'tokens':tokens,'llm_calls':llm,'trace_missing':False}

def audit_router(rows):
 audits=[]
 for r in rows:
  path=Path(r['result_dir'])/'router_decisions.jsonl'
  ds=[json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
  ds=[d for d in ds if not d.get('retry_same_request')]
  transitions=[d for d in ds if d['method']!=d['previous_method']]
  triggers=Counter(d['reason'] for d in transitions)
  sdpo=next((d['reason'] for d in transitions if d['method']=='sdpo'),None)
  audits.append({'task_id':r['task_id'],'resolved':r['resolved'],'final_adapter':ds[-1]['model'] if ds else None,'first_sdpo_trigger':sdpo,'transition_triggers':dict(triggers),'condition_true_requests':dict(Counter(k for d in ds for k,v in d['triggers'].items() if v)),'decisions':len(ds),'sticky_violation':any(d['previous_method']=='sdpo' and d['method']!='sdpo' for d in ds)})
 yields={}
 for trigger in ['budget_240s','repeat','successful_test','never_sdpo']:
  group=[a for a in audits if (a['first_sdpo_trigger'] or 'never_sdpo')==trigger]
  yields[trigger]={'tasks':len(group),'verified_passes':sum(r['resolved'] is True for r in group),'unknowns':sum(r['resolved'] is None for r in group)}
 return {'tasks':audits,'end_adapter_counts':dict(Counter(r['final_adapter'] for r in audits)),'transition_trigger_counts':dict(sum((Counter(r['transition_triggers']) for r in audits),Counter())),'yield_by_first_sdpo_trigger':yields}

def summary(rows):
 n=len(rows);k=sum(r['resolved'] is True for r in rows)
 out={'n':n,'verified_passes':k,'verified_yield':k/n if n else None,'wilson95':wilson(k,n),'timeouts':sum(bool(r.get('agent_timeout')) for r in rows),'no_patch':sum(r.get('patch_bytes')==0 for r in rows),'unknowns':sum(r['resolved'] is None for r in rows)}
 for metric in ['calls','tokens']:
  v=[r.get(metric) for r in rows];complete=all(x is not None for x in v)
  total=sum(v) if complete else None
  out[metric]={'total':total,'mean_per_task':total/n if complete and n else None,'per_solve':total/k if complete and k else None,'missing_cost_records':sum(x is None for x in v)}
 return out

def paired(rows):
 by={a:{r['task_id']:r for r in rows if r['arm']==a} for a in ['A0','router']}
 ids=sorted(t for t in by['A0'] if by['A0'][t]['resolved'] is not None and by['router'][t]['resolved'] is not None)
 a=[by['A0'][t] for t in ids];b=[by['router'][t] for t in ids]
 sa=np.array([r['resolved'] is True for r in a]);sb=np.array([r['resolved'] is True for r in b])
 out={**mcnemar([r['resolved'] for r in a],[r['resolved'] for r in b]),'included_ids':ids,'excluded_ids':sorted(set(by['A0'])-set(ids)),'bootstrap_seed':SEED,'resamples':NBOOT}
 if not ids:out['secondary']='No interpretable pairs';return out
 ix=np.random.default_rng(SEED).integers(len(ids),size=(NBOOT,len(ids)));da=sa[ix].sum(1);db=sb[ix].sum(1)
 invalid=(da==0)|(db==0);out['undefined_bootstrap_fraction']=float(invalid.mean())
 for metric in ['calls','tokens']:
  if any(r.get(metric) is None for r in a+b):out[metric]={'difference':None,'ci95':None,'reason':'Missing trace cost'};continue
  va=np.array([r[metric] for r in a]);vb=np.array([r[metric] for r in b])
  point=float(vb.sum()/sb.sum()-va.sum()/sa.sum()) if sa.sum() and sb.sum() else None
  if invalid.mean()>=.025:ci=None
  else:
   diffs=vb[ix[~invalid]].sum(1)/db[~invalid]-va[ix[~invalid]].sum(1)/da[~invalid];ci=np.quantile(diffs,[.025,.975]).tolist()
  out[metric]={'difference':point,'ci95':ci}
 return out

def table(summaries):
 lines=['| Arm | N | Passes | Yield [Wilson95%] | Mean calls | Mean tokens | Calls/solve | Tokens/solve | Timeouts | No patch | Unknown |','|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|']
 def fmt(v):return 'NA' if v is None else f'{v:,.2f}'
 for arm,s in summaries.items():
  ci=s['wilson95'];ci_text=f"{s['verified_yield']*100:.2f}% [{ci[0]*100:.2f}, {ci[1]*100:.2f}]"
  lines.append(f"| {arm} | {s['n']} | {s['verified_passes']} | {ci_text} | {fmt(s['calls']['mean_per_task'])} | {fmt(s['tokens']['mean_per_task'])} | {fmt(s['calls']['per_solve'])} | {fmt(s['tokens']['per_solve'])} | {s['timeouts']} | {s['no_patch']} | {s['unknowns']} |")
 return '\n'.join(lines)

def main():
 plan=json.loads((ROOT/'prereg/frozen.json').read_text());rows=[]
 for t in plan['tasks']:
  for arm in ['A0','router']:
   marker=OUT/arm/'done'/f'{t}.json'
   if not marker.exists():raise SystemExit(f'Analysis refused: missing terminal slot {arm}/{t}')
   row=json.loads(marker.read_text());assert row['task_id']==t and row['arm']==arm
   row.update(trace_cost(row['trace_path']));rows.append(row)
 assert len(rows)==168 and len({(r['arm'],r['task_id']) for r in rows})==168
 summaries={a:summary([r for r in rows if r['arm']==a]) for a in ['A0','router']};test=paired(rows)
 audit=audit_router([r for r in rows if r['arm']=='router'])
 pilot=json.loads((E/'method40-20261110-analysis/per_task.json').read_text());pooled=list(rows)
 for r in pilot:
  if r['arm'] in ['A0','Method router']:
   assert r['task_id'] not in plan['tasks']
   pooled.append({'arm':'A0' if r['arm']=='A0' else 'router','task_id':r['task_id'],'resolved':r['resolved'],'calls':r['billed_tool_calls_from_trace'],'tokens':r['total_tokens_from_trace'],'agent_timeout':r['timeout_flag'],'patch_bytes':r['patch_bytes']})
 pooled_summary={a:summary([r for r in pooled if r['arm']==a]) for a in ['A0','router']}
 assert all(s['n']==124 for s in pooled_summary.values())
 replacements=[{'file':str(p),**json.loads(p.read_text())} for p in OUT.glob('**/replacement.json')]
 progress=[json.loads(x) for x in (OUT/'progress.jsonl').read_text().splitlines()]
 anomalies=[x for x in progress if x['event'] in ['stopped','infrastructure_failure']]+[r for r in rows if r.get('agent_error') or r.get('configuration_error') or r['resolved'] is None]
 result={'prereg_commit':(OUT/'prereg_commit.txt').read_text().strip(),'deviations':[],'arms':summaries,'primary':test,'router_audit':audit,'pooled_descriptive':pooled_summary,'replacements':replacements,'anomalies':anomalies}
 if any(r.get('configuration_error') for r in rows):result['deviations'].append('Configuration mismatch; inspect rows')
 (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
 keys=sorted(set().union(*(r.keys() for r in rows)))
 with (OUT/'results.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
 primary=f"Exact two-sided McNemar: n={test['paired_n']}, baseline-only={test['baseline_only']}, router-only={test['router_only']}, p={test['exact_two_sided_p']:.6g}."
 text=f"# Confirmatory evaluation\n\nPreregistration commit: `{result['prereg_commit']}`.\n\nDeviations: {result['deviations'] or 'None recorded'}.\n\nAll168attempts completed. These84tasks are outside the matched pilot, but were previously covered by the129-task baseline;12also appeared in checkpoint-development evaluations. This is prospective replication, not untouched held-out validation.\n\n## Primary result\n\n{primary}\n\nAlpha=.05; one seed. Excluded uninterpretable pairs: {', '.join(test['excluded_ids']) or 'none'}.\n\n{table(summaries)}\n\nRatios use costs of all84attempts divided by verified passes; unknowns remain separate. A timeout may coexist with a verified pass. Failed/cancelled model requests may have unrecorded tokens.\n\n## Secondary descriptive paired differences\n\nRouter minus A0 on the interpretable paired set;20000paired task draws, seed20261116. No secondary significance claim.\n\n```json\n{json.dumps(test,indent=2)}\n```\n\n## Router audit\n\nTransitions exclude cached retries. Time/repeat/test select first SDPO takeover; exchange threshold counts transitions into DPO. Yield by first SDPO trigger is descriptive and not causal. Final adapter means last routed request.\n\n```json\n{json.dumps(audit,indent=2)}\n```\n\n## Pooled124-task comparison — DESCRIPTIVE\n\n{table(pooled_summary)}\n\n## Replacements and execution anomalies\n\n```json\n{json.dumps({'replacements':replacements,'anomalies':anomalies},indent=2)}\n```\n\nPhase2DPO has not been authorized or run.\n"
 (OUT/'REPORT.md').write_text(text);print(primary)
if __name__=='__main__':main()
