"""Serve an owned checkpoint and run a frozen evaluation split sequentially."""
import argparse,json,os,signal,socket,subprocess,sys,time,urllib.request
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[2];PKG=ROOT/'costagent';sys.path.insert(0,str(ROOT/'baseline-kit'))
from run_docker_agent_all import stop_server,gpu_free_mib
p=argparse.ArgumentParser();p.add_argument('--adapter',type=Path);p.add_argument('--arm',required=True);p.add_argument('--split',choices=['dev','test'],required=True)
p.add_argument('--submission',type=Path,default=ROOT/'data/sample_submission')
p.add_argument('--seeds',type=int,nargs='+',help='Explicit local evaluation seeds (default: dev 42; test 42,43)')
a=p.parse_args()
base=PKG/'artifacts/mixed-temperature-v1/evaluation';seeds=a.seeds if a.seeds is not None else ([42] if a.split=='dev' else [42,43])
if len(seeds)!=len(set(seeds)):p.error('Duplicate seeds are not allowed')
if not (a.submission/'agent.yaml').is_file():p.error(f'Missing submission agent.yaml: {a.submission}')
if a.adapter and not all((a.adapter/f).is_file() for f in ('adapter_config.json','adapter_model.safetensors')):
 p.error(f'Incomplete adapter: {a.adapter}')
server=None;created=None
try:
 started=time.time()
 while gpu_free_mib()<62000:
  if time.time()-started>48*3600:raise RuntimeError('GPU wait expired')
  time.sleep(30)
 with socket.socket() as s:
  if s.connect_ex(('127.0.0.1',8001))==0:raise RuntimeError('Port occupied by another server')
 env=os.environ.copy()
 if a.adapter:env['MAIN_ADAPTER']=str(a.adapter.resolve())
 with (base/f'{a.arm}-{a.split}-vllm.log').open('a') as log:server=subprocess.Popen(['bash',str(PKG/'scripts/serve_local.sh')],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 created=psutil.Process(server.pid).create_time()
 for _ in range(120):
  if server.poll() is not None:raise RuntimeError('vLLM exited; inspect log')
  try:
   with urllib.request.urlopen('http://127.0.0.1:8001/v1/models',timeout=2) as r:json.load(r)
   break
  except Exception:time.sleep(5)
 else:raise RuntimeError('vLLM readiness timeout')
 # A model-list response alone does not prove that the LoRA adapters can
 # generate. Fail before any task container is created if one is broken.
 probe=base/f'{a.arm}-{a.split}-model-probe.json'
 subprocess.run([sys.executable,str(ROOT/'baseline-kit/probe_models.py'),
                 '--output',str(probe)],check=True,timeout=390)
 for seed in seeds:
  out=base/f'{a.arm}-{a.split}-seed-{seed}'
  subprocess.run([sys.executable,str(PKG/'scripts/eval_existing_docker.py'),'--submission',str(a.submission),'--out',str(out),'--task-list',str(base/f'{a.split}_tasks.json'),'--seed',str(seed)],check=True)
 merged={'attempts':[],'arm':a.arm,'adapter':str(a.adapter) if a.adapter else 'original sample submission','submission':str(a.submission),'split':a.split,'seeds':seeds}
 for seed in seeds:merged['attempts']+=json.loads((base/f'{a.arm}-{a.split}-seed-{seed}'/'manifest.json').read_text())['attempts']
 (base/f'{a.arm}-{a.split}-manifest.json').write_text(json.dumps(merged,indent=2)+'\n')
finally:
 if server:stop_server(server,created)
