"""Descriptive CPU audit of existing pilot and training records only."""
import json,re,sys
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'costagent'),str(ROOT/'scripts')]
from costagent.traces import _norm_call
from costagent.costs import counts,cost,calibrate,TEST_RE,READ_CMD_RE
from analyze_confirmatory import audit_router
OUT=ROOT/'results/analysis';M=ROOT/'costagent/artifacts/mixed-temperature-v1';E=M/'evaluation'

def breakdown(parsed):
 counts_by=Counter();seen=defaultdict(list);last=None;dups=spin=reads=shells=0
 for turn in parsed['turns']:
  for call in turn.get('calls',[]):
   name=call['name'];a=call['args'] if isinstance(call['args'],dict) else {};fp=a.get('filepath')
   if name in ['edit_file','write_file']:
    counts_by['edit']+=1
    if fp:seen.pop(fp,None)
   elif name=='read_file':
    counts_by['read']+=1;reads+=1
    if fp:
     start=int(a.get('start_line') or 1);end=int(a.get('end_line') or start+149)
     dups+=any(start<=e and s<=end for s,e in seen[fp]);seen[fp].append((start,end))
   elif name in ['get_code_neighbors','get_code_subgraph','search_similar_code']:counts_by['graph']+=1
   elif name=='run_command':
    shells+=1;cmd=str(a.get('command',''));spin+=cmd==last
    counts_by['test' if TEST_RE.search(cmd) else ('read' if READ_CMD_RE.search(cmd) else 'shell')]+=1
   elif name in ['get_status','submit_patch']:counts_by['free']+=1
   else:counts_by['other']+=1
   last=str(a.get('command','')) if name=='run_command' else None
 return dict(counts_by),{'duplicate_read_file_calls':dups,'read_file_calls':reads,'repeated_commands':spin,'run_command_calls':shells}

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 training=[json.loads(x) for x in (M/'trajectories.jsonl').read_text().splitlines()];assert len(training)==50
 saved_cal=json.loads((M/'data/cost.json').read_text())
 for t in training:t['counts']=counts(t)
 calibration=calibrate(training)
 assert all(calibration[k]==saved_cal[k] for k in ['global','cmax','w'])
 groups=defaultdict(list)
 for t in training:
  c=cost(counts(t),t['task_id'],calibration)
  groups[t['task_id']].append({'success':bool(t['solved']),'cost':c,'ungated':float(t['solved'])-.5*c,'gated':float(t['solved'])*(1-.5*c),'rollout':t['rollout_id']})
 assert len(groups)==10 and all(len(v)==5 for v in groups.values())
 gate=[]
 for tid,rows in sorted(groups.items()):
  pairs=[(failure,success) for failure in rows if not failure['success'] for success in rows if success['success']]
  gate.append({'task_id':tid,'rollouts':len(rows),'successes':sum(r['success'] for r in rows),'failure_success_pairs':len(pairs),'ungated_failure_above_success':sum(f['ungated']>s['ungated'] for f,s in pairs),'gated_failure_above_success':sum(f['gated']>s['gated'] for f,s in pairs)})
 pilot=json.loads((E/'method40-20261110-analysis/per_task.json').read_text());pilot=[r for r in pilot if r['arm']!='Router'];assert len(pilot)==240
 actions=defaultdict(Counter);details=defaultdict(Counter);audits=[];taskrows=[]
 for r in pilot:
  raw=json.loads(Path(r['trace_path']).read_text())
  parsed={'turns':[{'calls':[_norm_call(c) for c in step.get('tool_calls',[])]} for step in raw['steps']]}
  b,d=breakdown(parsed);actions[r['arm']].update(b);details[r['arm']].update(d)
  assert sum(v for k,v in b.items() if k!='free')==r['billed_tool_calls_from_trace'],r['trace_path']
  taskrows.append({'arm':r['arm'],'task_id':r['task_id'],'actions':b,**d})
  if r['arm']=='Method router':audits.append({'task_id':r['task_id'],'resolved':r['resolved'],'result_dir':str(E/r['task_dir_relative'])})
 router=audit_router(audits)
 out={'gate_by_task':gate,'call_breakdown':dict(actions),'duplicate_counts':dict(details),'per_task':taskrows,'router_audit':router}
 (OUT/'additional.json').write_text(json.dumps(out,indent=2)+'\n')
 lines=['# Additional analyses of existing data only','','Calibration reconstructed with the original calibrate() from all50records; global medians, c_max and weights checked against saved cost.json (which omits per-task medians). Source:50training rollouts and240matched pilot attempts (A0,A1,A2,DPO,A9-contrast,final method router). The buggy controller pilot is excluded. No new task attempts.','','## Gate check','','With S∈{0,1}, C∈[0,1] and lambda=.5, ungated failure scores are[-.5,0], success scores[.5,1]; gated failure scores are0 and success scores[.5,1]. Therefore NEITHER score can rank a failure above a success. Zero violations here cannot demonstrate a competence-ranking advantage for gating. Gating removes cost distinctions among failures.','','| Task | Successes/5 | Failure–success pairs | Ungated violation | Gated violation |','|---|---:|---:|---:|---:|']
 for g in gate:lines.append(f"| {g['task_id']} | {g['successes']} | {g['failure_success_pairs']} | {g['ungated_failure_above_success']} | {g['gated_failure_above_success']} |")
 lines+=['','## Pilot action breakdown','','Exclusive buckets: test-regex run_command→test; recognized shell read→read; remaining run_command (including search/edit shell commands)→shell; explicit read_file→read, edit_file/write_file→edit, three graph tools→graph. get_status/submit_patch are free and shown separately. Other billed tools remain other. These are observable tool categories, not a perfect semantic classifier. Duplicate reads use explicit read_file overlapping line ranges with no intervening explicit edit of that path; shell reads/edits are not reconstructed. Repeated-command numerator requires consecutive identical run_command strings, without output-hash requirement. This is the existing cost-counter definition; router repeat trigger additionally requires matching output hash.','','| Arm | Read | Shell | Edit | Graph | Test | Other | Free | Duplicate read_file / read_file | Repeat / run_command |','|---|---:|---:|---:|---:|---:|---:|---:|---|---|']
 for arm in ['A0','A1','A2','DPO','A9-contrast','Method router']:
  c=actions[arm];d=details[arm]
  def frac(a,b):return f'{a}/{b} ({a/b:.2%})' if b else f'{a}/0 (undefined)'
  lines.append('| '+arm+' | '+' | '.join(str(c[k]) for k in ['read','shell','edit','graph','test','other','free'])+' | '+frac(d['duplicate_read_file_calls'],d['read_file_calls'])+' | '+frac(d['repeated_commands'],d['run_command_calls'])+' |')
 lines+=['','## Pilot method-router audit','','Final adapter is the last routed request. Trigger counts represent transitions (cached retries excluded); yield by firstSDPOtrigger is descriptive, not causal. Full per-task audit below.','','```json',json.dumps(router,indent=2),'```']
 (OUT/'ADDITIONAL.md').write_text('\n'.join(lines)+'\n')
 print(json.dumps({'training_rollouts':50,'pilot_attempts':240,'gate_failure_success_pairs':sum(g['failure_success_pairs'] for g in gate),'ungated_violations':sum(g['ungated_failure_above_success'] for g in gate),'gated_violations':sum(g['gated_failure_above_success'] for g in gate),'report':str(OUT/'ADDITIONAL.md')}))
if __name__=='__main__':main()
