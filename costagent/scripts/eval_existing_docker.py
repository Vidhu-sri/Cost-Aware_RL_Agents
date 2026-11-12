"""Run the prior bounded Docker evaluator with a specified submission."""
import argparse,json,os,subprocess,sys,time,uuid
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--submission',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
p.add_argument('--task-list',type=Path);p.add_argument('--seed',type=int,default=42);p.add_argument('--temperature',type=float,default=.2)
a=p.parse_args();root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'baseline-kit'))
from run_docker_reference_batch import IMAGES
sys.path.insert(0,str(root/'costagent'))
from costagent.eval_status import interpret_outcome
import docker
os.environ.setdefault('DOCKER_HOST',subprocess.check_output(['docker','context','inspect','--format','{{.Endpoints.docker.Host}}'],text=True).strip())
client=docker.from_env()
tasks=[json.loads(x) for x in (root/'data/tasks.jsonl').read_text().splitlines()]
if a.task_list:
 selected=set(json.loads(a.task_list.read_text()));tasks=[t for t in tasks if t['instance_id'] in selected]
 if len(tasks)!=len(selected):raise ValueError('Unknown evaluation task')
for image in set(IMAGES.values()):client.images.get(image) # Never silently pull or switch daemon.
a.out.mkdir(parents=True,exist_ok=True)
(a.out/'traces').mkdir(exist_ok=True);(a.out/'patches').mkdir(exist_ok=True)
def progress(event,**fields):
 with (a.out/'progress.jsonl').open('a') as stream:
  stream.write(json.dumps({'time':time.time(),'event':event,**fields})+'\n')
  stream.flush();os.fsync(stream.fileno())
for task in tasks:
 tid=task['instance_id'];out=a.out/'tasks'/tid
 if (out/'outcome.json').exists():continue
 if out.exists():raise RuntimeError(f'Incomplete previous evaluation preserved: {out}')
 env=os.environ.copy();env['COSTAGENT_SUBMISSION']=str(a.submission.resolve());env['COSTAGENT_RESULT']=str(out.resolve())
 env['PYTHONPATH']=str(root/'baseline-kit');env['COSTAGENT_TEMPERATURE']=str(a.temperature)
 cmd=[sys.executable,str(Path(__file__).with_name('docker_eval_worker.py')),'--mode','agent','--external-server','--task-id',tid,'--image',IMAGES[task['repo']],'--label','costagent-'+uuid.uuid4().hex[:12],'--seed',str(a.seed),'--seconds','900']
 progress('task_started',task_id=tid,image=IMAGES[task['repo']])
 result=subprocess.run(cmd,env=env)
 if not (out/'outcome.json').exists():
  progress('task_infrastructure_error',task_id=tid,worker_returncode=result.returncode,result_dir=str(out))
  raise RuntimeError(f'Infrastructure failure without outcome: {out}, code={result.returncode}')
 monitor_path=out/'monitor.json'
 if not monitor_path.exists():raise RuntimeError(f'Missing cleanup monitor: {out}')
 monitor=json.loads(monitor_path.read_text())
 resolved,verification_status=interpret_outcome(json.loads((out/'outcome.json').read_text()),monitor,result.returncode)
 if env.get('COSTAGENT_ROUTER'):
  decisions=out/'router_decisions.jsonl'
  valid_responses=[]
  for response_file in out.glob('model_response_*.bin'):
   try: response_body=json.loads(response_file.read_bytes())
   except (ValueError,UnicodeError): continue
   if response_body.get('choices'): valid_responses.append(response_file)
  if not decisions.exists() or not decisions.stat().st_size or not valid_responses:
   progress('router_integration_error',task_id=tid,valid_responses=len(valid_responses))
   raise RuntimeError(f'Router did not complete a model request; stopping: {out}')
 progress('task_terminal',task_id=tid,resolved=resolved,verification_status=verification_status,
          worker_returncode=result.returncode,remaining_owned_ids=monitor.get('remaining_owned_ids'))
 # Preserve the evaluator's native results, expose the same layout to the parser.
 for src in out.glob('traces/trace_*.json'):
  target=a.out/'traces'/src.name
  if not target.exists():target.symlink_to(src.resolve())
 for src in out.glob('patches/*.patch'):
  target=a.out/'patches'/src.name
  if not target.exists():target.symlink_to(src.resolve())
 records=[]
 for f in sorted((a.out/'tasks').glob('*/task_results.jsonl')):records.extend(f.read_text().splitlines())
 (a.out/'task_results.jsonl').write_text('\n'.join(records)+'\n')

# Build the manifest from all completed tasks, including resumed tasks.
rows=[]
for task in tasks:
 out=a.out/'tasks'/task['instance_id']
 if not (out/'outcome.json').exists():continue
 result=json.loads((out/'outcome.json').read_text())
 monitor=json.loads((out/'monitor.json').read_text())
 resolved,verification_status=interpret_outcome(result,monitor,monitor.get('worker_exit_code'))
 import yaml
 effective=json.loads((out/'effective_settings.json').read_text())['local_evaluation']
 sampling=yaml.safe_load((out/'agent_snapshot/configs/sampling.yaml').read_text())
 (out/'settings.json').write_text(json.dumps(dict(agent_minutes=5,tool_calls=100,turns=effective.get('max_turns'),command_timeout_seconds=effective['timeout_seconds'],image=IMAGES[task['repo']],sampling=sampling)))
 rows.append(dict(task_id=task['instance_id'],seed=a.seed,result_dir=str(out.resolve()),trace_path=str((out/'traces'/f"trace_{task['instance_id']}.json").resolve()),resolved=resolved,verification_status=verification_status,agent_timeout=result.get('agent_timeout'),patch_bytes=result.get('patch_bytes'),test_exit_code=result.get('test_exit_code'),verification_error=result.get('verification_error'),base_commit=task['base_commit'],agent={'elapsed_seconds':result.get('duration_seconds')},settings={'temperature':a.temperature,'seed':a.seed,'agent_minutes':5,'tool_calls':100,'image':IMAGES[task['repo']]}))
(a.out/'manifest.json').write_text(json.dumps({'attempts':rows},indent=2)+'\n')
