#!/usr/bin/env python3
"""Sequential, outcome-blind orchestration around unchanged pilot execution code."""
import argparse, fcntl, hashlib, importlib.metadata as md, json, os, signal, socket
import subprocess, sys, time, traceback, urllib.request
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[1];PKG=ROOT/'costagent';OUT=ROOT/'results/confirmatory'
sys.path[:0]=[str(ROOT/'baseline-kit'),str(PKG)]
from run_docker_agent_all import gpu_free_mib,resource_concern,stop_server
from run_docker import owned_containers,clean_owned
from costagent.eval_status import interpret_outcome
from prepare_confirmatory import sha
STOP=False
class HardStop(RuntimeError):pass
class InfraCrash(RuntimeError):pass

def signal_stop(*_):
 global STOP;STOP=True

def atomic(path,obj):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(obj,indent=2)+'\n');os.replace(tmp,path)

def event(name,**kw):
 row={'time':time.time(),'event':name,**kw};OUT.mkdir(parents=True,exist_ok=True)
 with (OUT/'progress.jsonl').open('a') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())
 print(json.dumps(row),flush=True)

def terminal(path):
 return (path/'outcome.json').exists() or (path/'terminal_unknown.json').exists()

def retry_allowed(path):
 if terminal(path):return False
 f=path/'infrastructure_failure.json'
 return f.exists() and json.loads(f.read_text())['kind'] in ['vllm_crash','gpu_crash','docker_crash']

def stop_child(proc):
 if proc is None or proc.poll() is not None:return
 for sig,wait in [(signal.SIGINT,45),(signal.SIGTERM,15),(signal.SIGKILL,10)]:
  if proc.poll() is not None:return
  os.killpg(proc.pid,sig)
  try:proc.wait(timeout=wait)
  except subprocess.TimeoutExpired:continue
 if proc.poll() is None:raise HardStop('Owned worker did not stop')

def frozen_check(plan,full=True):
 for name,h in plan['files'].items():
  p=Path(name);p=p if p.is_absolute() else ROOT/p
  if full or p.suffix in ['.py','.sh','.yaml','.json']:
   if sha(p)!=h:raise HardStop(f'Frozen file drift: {p}')
 for name,v in plan['packages'].items():
  if md.version(name)!=v:raise HardStop(f'Package version drift: {name}')
 commit=(OUT/'prereg_commit.txt').read_text().strip()
 for name in ['prereg/CONFIRMATORY.md','prereg/frozen.json','scripts/confirmatory.py','scripts/run_confirmatory.sh','scripts/analyze_confirmatory.py']:
  saved=subprocess.check_output(['git','show',f'{commit}:{name}'],cwd=ROOT)
  if saved!=(ROOT/name).read_bytes():raise HardStop(f'Committed configuration drift: {name}')

def port_open():
 with socket.socket() as s:return s.connect_ex(('127.0.0.1',8001))==0

def arm_env(arm):
 env=os.environ.copy()
 for name in ['MAIN_ADAPTER','COSTAGENT_METHOD_ROUTER','COSTAGENT_ROUTER','COSTAGENT_ROUTER_SOURCE','COSTAGENT_SUBMISSION','COSTAGENT_RESULT','COSTAGENT_TEMPERATURE']:
  env.pop(name,None)
 if arm=='router':
  env.update(MAIN_ADAPTER=str(PKG/'artifacts/mixed-temperature-v1/dpo/epoch-005'),COSTAGENT_ROUTER='method-v1',COSTAGENT_METHOD_ROUTER='1',COSTAGENT_ROUTER_SOURCE=str(PKG/'scripts/method_router.py'))
 return env

class Runner:
 def __init__(self,plan):
  import docker
  os.environ.setdefault('DOCKER_HOST',subprocess.check_output(['docker','context','inspect','--format','{{.Endpoints.docker.Host}}'],text=True).strip())
  self.client=docker.from_env(timeout=10);self.plan=plan;self.server=None;self.created=None;self.arm=None;self.active=None;self.current=None;self.last_progress=0
 def check(self):
  if STOP:raise HardStop('Interruption requested')
  concern=resource_concern()
  if concern:raise HardStop(concern)
  if time.time()-self.last_progress>=1800:
   event('progress_check',completed=len(list(OUT.glob('*/done/*.json'))),total=168,current=str(self.current) if self.current else None,disk_free_gib=__import__('shutil').disk_usage(ROOT).free/1024**3)
   self.last_progress=time.time()
 def cleanup_containers(self,path):
  if not path or not (path/'run_manifest.json').exists():return
  run=json.loads((path/'run_manifest.json').read_text());rid=run['run_id']
  removed=clean_owned(self.client,rid)
  remaining=[c.id for c in owned_containers(self.client,rid)]
  atomic(path/'outer_cleanup.json',{'run_id':rid,'removed':removed,'remaining':remaining,'time':time.time()})
  if remaining:raise HardStop(f'Cleanup failure {rid}: {remaining}')
 def shutdown_server(self):
  if self.server is None:return
  record=stop_server(self.server,self.created);event('server_cleanup',**record)
  self.server=None;self.arm=None
  if not record['process_exited'] or not record['port_8001_closed']:raise HardStop('Server cleanup failed')
 def ensure_server(self,arm):
  if self.server and self.arm==arm and self.server.poll() is None:return
  self.shutdown_server();self.check()
  if gpu_free_mib()<62000:raise HardStop('GPU unavailable: less than62000MiB free before startup')
  if port_open():raise HardStop('Port8001 occupied; will not claim ownership')
  label=f'{time.time_ns()}-{arm}';serverdir=OUT/'servers'/label;serverdir.mkdir(parents=True)
  env=arm_env(arm)
  with (serverdir/'vllm.log').open('w') as log:
   self.server=subprocess.Popen(['bash',str(PKG/'scripts/serve_local.sh')],cwd=PKG,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  self.created=psutil.Process(self.server.pid).create_time();self.arm=arm
  record={'pid':self.server.pid,'create_time':self.created,'pgid':os.getpgid(self.server.pid),'arm':arm,'directory':str(serverdir)}
  atomic(serverdir/'ownership.json',record);atomic(OUT/'active_server.json',record);event('server_starting',**record)
  deadline=time.monotonic()+1200
  while True:
   self.check()
   if self.server.poll() is not None:raise InfraCrash(f'vLLM startup exited {self.server.returncode}; {serverdir}/vllm.log')
   if time.monotonic()>deadline:raise HardStop('vLLM startup deadline1200s')
   try:
    with urllib.request.urlopen('http://127.0.0.1:8001/v1/models',timeout=2) as r:served=json.load(r)
    break
   except (OSError,ValueError):time.sleep(3)
  # Same original adapter probes and extra method probes as pilot.
  with (serverdir/'probe.log').open('w') as log:
   subprocess.run([sys.executable,str(ROOT/'baseline-kit/probe_models.py'),'--output',str(serverdir/'probe.json')],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=390)
  expected={'main_lora':PKG/'artifacts/mixed-temperature-v1/dpo/epoch-005' if arm=='router' else ROOT/'data/sample_submission/adapters/main_lora','tool_lora':ROOT/'data/sample_submission/adapters/tool_lora'}
  if arm=='router':expected.update(rft_lora=PKG/'artifacts/adapters/A2',dpo_lora=PKG/'artifacts/mixed-temperature-v1/dpo/epoch-005',sdpo_lora=PKG/'artifacts/mixed-temperature-v1/sdpo/contrast/epoch-005')
  models={x['id']:x for x in served['data']}
  for name,path in expected.items():
   if name not in models or Path(models[name]['root']).resolve()!=path.resolve():raise HardStop(f'Wrong adapter mapping {name}')
   if name in ['rft_lora','dpo_lora','sdpo_lora']:
    body={'model':name,'messages':[{'role':'user','content':'Reply OK.'}],'max_tokens':16,'temperature':0,'chat_template_kwargs':{'enable_thinking':False}}
    request=urllib.request.Request('http://127.0.0.1:8001/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=90) as response:result=json.load(response)
    if not result.get('choices'):raise HardStop(f'No adapter response {name}')
    atomic(serverdir/f'{name}-probe.json',result)
  event('server_ready',arm=arm,pid=self.server.pid)
 def result(self,arm,tid,path):
  self.cleanup_containers(path)
  if (path/'terminal_unknown.json').exists():return json.loads((path/'terminal_unknown.json').read_text())
  outcome=json.loads((path/'outcome.json').read_text());mp=path/'monitor.json'
  monitor=json.loads(mp.read_text()) if mp.exists() else {}
  resolved,status=interpret_outcome(outcome,monitor,monitor.get('worker_exit_code'))
  samples=monitor.get('samples',[])
  monitored=bool(monitor.get('monitor_started_at') and monitor.get('worker_started_at') and monitor['monitor_started_at']<=monitor['worker_started_at'] and any(x.get('host_pid') for x in samples))
  peak=max((x.get('observed_pid_namespace_rss_bytes') or 0 for x in samples),default=0)
  trace=path/'traces'/f'trace_{tid}.json'
  row={'arm':arm,'task_id':tid,'result_dir':str(path),'resolved':resolved,'verification_status':status,'agent_timeout':bool(outcome.get('agent_timeout')),'patch_bytes':outcome.get('patch_bytes'),'test_exit_code':outcome.get('test_exit_code'),'trace_path':str(trace),'cleanup_ok':not monitor.get('remaining_owned_ids'),'monitor_ok':monitored,'peak_observed_container_rss_bytes':peak,'agent_error':outcome.get('agent_error'),'time':time.time()}
  if (path/'effective_settings.json').exists():
   effective=json.loads((path/'effective_settings.json').read_text());expected=self.plan['effective_settings']
   for k in ['local_evaluation','sampling_seed','effective_sampling_sha256','agent_sha256','packages','model_config_sha256','model_source_sha256']:
    if effective[k]!=expected[k]:row['configuration_error']=k
  return row
 def attempt(self,arm,tid,path):
  # Terminal records ALWAYS win over retry status, including crashes after grading.
  if terminal(path):return self.result(arm,tid,path)
  if path.exists():raise HardStop(f'Incomplete slot preserved; requires qualifying infrastructure evidence: {path}')
  frozen_check(self.plan,full=False);self.check();self.ensure_server(arm)
  attempt_root=path.parents[2];attempt_root.mkdir(parents=True,exist_ok=True)
  tasklist=attempt_root/'task.json';atomic(tasklist,[tid]);out=attempt_root/'evaluation'
  env=arm_env(arm)
  command=[sys.executable,'-u',str(PKG/'scripts/eval_existing_docker.py'),'--submission',str(ROOT/'data/sample_submission'),'--out',str(out),'--task-list',str(tasklist),'--seed','42','--temperature','0.2']
  self.current=path
  event('attempt_started',arm=arm,task_id=tid,result_dir=str(path))
  first_request=False;watchdog=time.monotonic()+960;crash=None;reason=None
  with (attempt_root/'controller.log').open('w') as log:
   self.active=subprocess.Popen(command,cwd=PKG,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   atomic(attempt_root/'ownership.json',{'pid':self.active.pid,'create_time':psutil.Process(self.active.pid).create_time(),'pgid':self.active.pid,'arm':arm,'task_id':tid})
   try:
    while self.active.poll() is None:
     self.check()
     if self.server.poll() is not None:crash='vllm_crash';raise InfraCrash(f'Owned vLLM exited {self.server.returncode}')
     try:self.client.ping()
     except Exception as exc:crash='docker_crash';raise InfraCrash(str(exc)) from exc
     if not first_request and path.exists() and (path/'model_requests.jsonl').exists():
      first_request=True;event('first_model_request',arm=arm,task_id=tid)
     if time.monotonic()>watchdog:reason='outer_watchdog';break
     time.sleep(5)
   except BaseException as exc:
    reason=f'{type(exc).__name__}: {exc}'
    if crash is None and 'NVIDIA' in str(exc):crash='gpu_crash'
   finally:stop_child(self.active)
  rc=self.active.returncode;self.active=None;self.cleanup_containers(path)
  if not terminal(path):
   monitor=json.loads((path/'monitor.json').read_text()) if (path/'monitor.json').exists() else {}
   if monitor.get('timed_out') or reason=='outer_watchdog':
    atomic(path/'terminal_unknown.json',{'arm':arm,'task_id':tid,'result_dir':str(path),'resolved':None,'verification_status':'supervisor_incomplete','agent_timeout':True,'patch_bytes':None,'test_exit_code':None,'trace_path':str(path/'traces'/f'trace_{tid}.json'),'cleanup_ok':True,'monitor_ok':bool(monitor),'agent_error':'Outer deadline; no terminal agent record','time':time.time()})
   elif crash:
    atomic(path/'infrastructure_failure.json',{'kind':crash,'reason':reason,'worker_returncode':rc,'time':time.time()});raise InfraCrash(reason)
   else:raise HardStop(f'No terminal record; not eligible for automatic replacement: {path}; rc={rc}; {reason}')
  row=self.result(arm,tid,path)
  if reason:row['execution_anomaly']=reason
  return row
 def run_slot(self,arm,tid,smoke=False):
  base=(OUT/'smoke'/arm if smoke else OUT/arm)
  done=base/'done'/f'{tid}.json'
  if done.exists():
   row=json.loads(done.read_text())
   if not row.get('cleanup_ok') or not row.get('monitor_ok') or row.get('configuration_error'):raise HardStop(f'Prior terminal safety failure: {done}')
   return
  for attempt in [0,1]:
   path=base/tid/f'attempt-{attempt}'/'evaluation/tasks'/tid
   if attempt==0 and retry_allowed(path):continue
   if attempt==1:
    prior=base/tid/'attempt-0/evaluation/tasks'/tid
    if not retry_allowed(prior):raise HardStop('Replacement has no qualifying evidence')
    marker=base/tid/'replacement.json'
    if not marker.exists():
     atomic(marker,{'original':str(prior),'replacement':str(path),'time':time.time(),'cause':json.loads((prior/'infrastructure_failure.json').read_text())})
     event('replacement',arm=arm,task_id=tid,record=str(marker))
   try:row=self.attempt(arm,tid,path)
   except InfraCrash as exc:
    event('infrastructure_failure',arm=arm,task_id=tid,attempt=attempt,reason=str(exc))
    self.shutdown_server()
    if attempt==0 and retry_allowed(path):continue
    raise
   atomic(done,row)
   event('attempt_checkpointed',arm=arm,task_id=tid,smoke=smoke,completed=len(list(OUT.glob('*/done/*.json'))),total=168)
   if row.get('configuration_error'):raise HardStop(f'Pilot setting mismatch: {row["configuration_error"]}')
   if not row['cleanup_ok'] or not row['monitor_ok']:raise HardStop(f'Monitor/cleanup failure: {path}')
   if row.get('peak_observed_container_rss_bytes',0)>12*1024**3:raise HardStop('Observed container RSS exceeded12GiB')
   if row.get('execution_anomaly'):raise HardStop(row['execution_anomaly'])
   if smoke:
    responses=[]
    for f in path.glob('model_response_*.bin'):
     try:responses.append(json.loads(f.read_bytes()))
     except (ValueError,UnicodeError):pass
    if not Path(row['trace_path']).exists() or not any(x.get('choices') for x in responses):raise HardStop('Smoke has no trace/valid model response')
   self.current=None;return

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--dry-run',action='store_true');args=parser.parse_args()
 plan=json.loads((ROOT/'prereg/frozen.json').read_text())
 if args.dry_run:
  print(json.dumps({'tasks':len(plan['tasks']),'attempts':sum(len(x['arms']) for x in plan['order']),'first':plan['order'][0],'phase2_enabled':False}));return
 OUT.mkdir(parents=True,exist_ok=True)
 lock=(OUT/'runner.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,signal_stop)
 atomic(OUT/'supervisor.json',{'pid':os.getpid(),'create_time':psutil.Process().create_time(),'started':time.time()})
 frozen_check(plan);r=Runner(plan)
 try:
  for image,ident in plan['images'].items():
   if r.client.images.get(image).id!=ident:raise HardStop(f'Image identity changed: {image}')
  # Refuse any still-live old batch worker; no blind PID killing on resume.
  for p in OUT.glob('**/ownership.json'):
   old=json.loads(p.read_text())
   try:live=psutil.Process(old['pid']).create_time()==old['create_time']
   except psutil.Error:live=False
   if live:raise HardStop(f'Previous owned process still alive; inspect before resumption: {p}')
  for arm in ['A0','router']:r.run_slot(arm,plan['smoke_task'],smoke=True)
  event('smokes_complete',excluded_from_confirmatory=True)
  for row in plan['order']:
   for arm in row['arms']:r.run_slot(arm,row['task_id'])
  r.shutdown_server()
  subprocess.run([sys.executable,str(ROOT/'scripts/analyze_confirmatory.py')],check=True)
  atomic(OUT/'state.json',{'state':'complete','completed':168,'phase2':'requires user confirmation'})
  event('phase1_complete',completed=168,total=168)
 except BaseException as exc:
  atomic(OUT/'state.json',{'state':'stopped','reason':f'{type(exc).__name__}: {exc}','completed':len(list(OUT.glob('*/done/*.json')))})
  event('stopped',reason=f'{type(exc).__name__}: {exc}',completed=len(list(OUT.glob('*/done/*.json'))));traceback.print_exc();raise
 finally:
  try:stop_child(r.active);r.cleanup_containers(r.current)
  finally:r.shutdown_server()
if __name__=='__main__':main()
