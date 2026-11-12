"""Select authorized tasks and keep only compatible sibling groups."""
import hashlib,json
from pathlib import Path
from costagent.traces import load_run,kaggle_ids
ROOT=Path(__file__).resolve().parents[2];PKG=ROOT/'costagent';BATCH=PKG/'artifacts/mixed-temperature-v1'
plan=json.loads((BATCH/'plan.json').read_text());selected={x['task_id'] for x in plan['tasks']}
kid=kaggle_ids(ROOT/'data/tasks.jsonl')
rows=[]
for path in [ROOT/'swe-rebench-work/results/gemma100-v2-20261021',ROOT/'baseline-kit/results/docker-gemma129-20261017b-agent-batch',BATCH]:
 rows += [r for r in load_run(path,kid) if r['task_id'] in selected]
metadata={}
for f in (ROOT/'data/tasks.jsonl').read_text().splitlines():
 t=json.loads(f);metadata[t['instance_id']]=t
for task in plan['tasks']:
 if task['spec']:metadata[task['task_id']]=json.loads(Path(task['spec']).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
kept=[];excluded=[]
for row in rows:
 trace=Path(row['rollout_id']);directory=trace.parent if trace.name=='trace.json' else trace.parent.parent
 settings=directory/'settings.json';effective=directory/'effective_settings.json'
 if settings.exists():
  cfg=json.loads(settings.read_text());budget={k:cfg.get(k) for k in ['agent_minutes','tool_calls','turns','command_timeout_seconds']};sampling=cfg['sampling']
 elif effective.exists():
  cfg=json.loads(effective.read_text());e=cfg['local_evaluation'];budget={'agent_minutes':e['max_time_minutes'],'tool_calls':e['max_tool_calls'],'turns':e.get('max_turns'),'command_timeout_seconds':e['timeout_seconds']}
  import yaml
  sampling=yaml.safe_load((directory/'agent_snapshot/configs/sampling.yaml').read_text())
 else:excluded.append({'rollout':str(trace),'reason':'missing settings'});continue
 hashes={}
 for name in ['main_lora','tool_lora']:
  folder=directory/'agent_snapshot/adapters'/name
  for filename in ['adapter_config.json','adapter_model.safetensors']:
   f=folder/filename
   if f.exists():hashes[f'{name}/{filename}']=sha(f)
 if len(hashes)!=4:excluded.append({'rollout':str(trace),'reason':'missing adapter provenance'});continue
 task=metadata[row['task_id']]
 compat=dict(system=row['system'],issue=row['first_user'],repo=task['repo'],base_commit=task['base_commit'],budget=budget,sampling={k:v for k,v in sampling.items() if k not in ['temperature','seed']},adapter_hashes=hashes)
 row['compatibility_sha256']=hashlib.sha256(json.dumps(compat,sort_keys=True).encode()).hexdigest()
 kept.append(row)
(BATCH/'trajectories.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in kept))
(BATCH/'compatibility_report.json').write_text(json.dumps({'kept':len(kept),'excluded':excluded},indent=2)+'\n')
print('Compatible-metadata trajectories:',len(kept),'excluded:',len(excluded))
