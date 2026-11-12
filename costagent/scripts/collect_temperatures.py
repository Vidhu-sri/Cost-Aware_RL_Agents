"""Resume 5 Kaggle + 5 SWE tasks, four temperatures, owned local vLLM."""
import argparse,importlib.util,json,os,signal,subprocess,sys,time,uuid,fcntl,hashlib
from resource_retry import gpu_memory_failure
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PKG=ROOT/'costagent'
sys.path.insert(0,str(ROOT/'baseline-kit'))
from run_docker_agent_all import stop_server,gpu_free_mib
from run_docker_reference_batch import IMAGES

def read(p):return json.loads(p.read_text())
def save(p,x):
    t=p.with_suffix('.tmp');t.write_text(json.dumps(x,indent=2)+'\n');t.replace(p)
def module(path):
    spec=importlib.util.spec_from_file_location('swecollector',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--batch',type=Path,default=PKG/'artifacts/mixed-temperature-v1');ap.add_argument('--dry-run',action='store_true');args=ap.parse_args()
    batch=args.batch.resolve();plan=read(batch/'plan.json')
    assert len(plan['tasks'])==10 and plan['temperatures']==[.2,.5,.8,1.]
    for task in plan['tasks']:
        if task['spec']:assert Path(task['spec']).is_file(),task['spec']
    if args.dry_run:print(json.dumps(plan,indent=2));return
    import docker,psutil
    lock=(batch/'controller.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    save(batch/'controller.json',{'pid':os.getpid(),'started':time.time()})
    m=module(batch/'swe_worker.py')
    signal.signal(signal.SIGINT,m.stopped);signal.signal(signal.SIGTERM,m.stopped)
    state=read(batch/'manifest.json') if (batch/'manifest.json').exists() else {'attempts':[],'target_attempts':40,'plan':plan}
    default_host=os.environ.get('DOCKER_HOST') or subprocess.check_output(['docker','context','inspect','--format','{{.Endpoints.docker.Host}}'],text=True).strip()
    swe_host='unix:///tmp/gemma-swerebench-docker-1017/docker.sock'
    client_swe=docker.DockerClient(base_url=swe_host)
    client_k=docker.DockerClient(base_url=default_host)
    if client_swe.info()['DockerRootDir']!='/tmp/gemma-swerebench-docker-1017/data':raise RuntimeError('Wrong SWE Docker root')
    server=None;created=None;watcher=None;acquired=set(read(batch/'acquired_images.json')) if (batch/'acquired_images.json').exists() else set()
    started=time.time()
    os.environ['GEMMA_RESULTS_DATA_ROOT']=str(batch)
    os.environ['GEMMA_DOCKER_DATA_ROOT']='/tmp/gemma-swerebench-docker-1017/data'
    os.environ['VLLM_CACHE_ROOT']='/tmp/costagent-vllm-cache'
    os.environ['TORCHINDUCTOR_CACHE_DIR']='/tmp/costagent-inductor-cache'
    os.environ['TRITON_CACHE_DIR']='/tmp/costagent-triton-cache'
    save(batch/'status.json',{'stage':'starting_server','completed':len(state['attempts'])})
    try:
        while gpu_free_mib()<62000:
            save(batch/'status.json',{'stage':'waiting_for_gpu','completed':len(state['attempts'])})
            if m.STOP:raise RuntimeError('Interrupted')
            time.sleep(30)
        server,created=m.start_server(batch)
        m.wait_server(server,batch)
        watcher=subprocess.Popen([sys.executable,str(PKG/'scripts/log_gpu_pressure.py'),str(batch),str(os.getpid()),str(psutil.Process().create_time())],stdout=(batch/'watcher.log').open('a'),stderr=subprocess.STDOUT)
        for i,task in enumerate(plan['tasks']):
            tid=task['task_id'];taskdir=batch/'tasks'/tid;taskdir.mkdir(parents=True,exist_ok=True)
            if task['source']=='swe_rebench':
                os.environ['DOCKER_HOST']=swe_host
                os.environ['GEMMA_DOCKER_DATA_ROOT']='/tmp/gemma-swerebench-docker-1017/data'
                spec=read(Path(task['spec']));m.image_ready(spec,client_swe,batch,acquired)
            else:os.environ['DOCKER_HOST']=default_host
            for j,temp in enumerate(plan['temperatures']):
                if any(r['task_id']==tid and r['temperature']==temp for r in state['attempts']):continue
                if m.STOP or server.poll() is not None:raise RuntimeError('Interrupted or server exited')
                seed=plan['seed_base']+i*10+j;run='temp-'+uuid.uuid4().hex
                out=taskdir/f'temp-{temp}-seed-{seed}-{run[-6:]}'
                os.environ['COSTAGENT_TEMPERATURE']=str(temp)
                save(batch/'status.json',{'stage':'collecting','task':tid,'temperature':temp,'seed':seed,'completed':len(state['attempts'])})
                if task['source']=='swe_rebench':
                    ok=m.supervise(Path(task['spec']),out,run,seed,'attempt',client_swe)
                    if not ok:raise RuntimeError(f'Worker infrastructure failure: {out}')
                    outcome=read(out/'outcome.json');trace=out/'trace.json'
                else:
                    native=next(t for t in map(json.loads,(ROOT/'data/tasks.jsonl').read_text().splitlines()) if t['instance_id']==tid)
                    client_k.images.get(IMAGES[native['repo']])
                    env=os.environ.copy();env.update(COSTAGENT_SUBMISSION=str(ROOT/'data/sample_submission'),COSTAGENT_RESULT=str(out),PYTHONPATH=str(ROOT/'baseline-kit'))
                    cmd=[sys.executable,str(batch/'kaggle_worker.py'),'--mode','agent','--external-server','--task-id',tid,'--image',IMAGES[native['repo']],'--label',run,'--seed',str(seed),'--seconds','900']
                    with (taskdir/f'{run}.log').open('w') as log:
                        p=subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
                        signaled=False
                        while p.poll() is None:
                            if m.STOP and not signaled:
                                p.send_signal(signal.SIGINT);signaled=True
                            time.sleep(2)
                    if not (out/'outcome.json').exists():raise RuntimeError(f'Worker failed without outcome: {out}')
                    result=read(out/'outcome.json');trace=out/'traces'/f'trace_{tid}.json'
                    # The prior supervisor returns 1 for ordinary unsuccessful attempts too.
                    known=not result.get('verification_error') or result.get('agent_timeout')
                    outcome={'resolved':result['resolved'] if known else None,'agent':{'elapsed_seconds':result.get('duration_seconds')},'category':'resolved' if result['resolved'] else ('unresolved' if known else 'infrastructure_grading_error')}
                row={**outcome, 'task_id':tid, 'source':task['source'], 'temperature':temp, 'seed':seed, 'result_dir':str(out), 'trace_path':str(trace)}
                state['attempts'].append(row);state['updated']=time.time();save(batch/'manifest.json',state)
                print(json.dumps({'completed':len(state['attempts']),'task':tid,'temperature':temp,'resolved':row['resolved']}),flush=True)
            if task['source']=='swe_rebench':m.release_image(client_swe,spec['image_name'],acquired,batch)
        save(batch/'status.json',{'stage':'complete','completed':len(state['attempts'])})
    except BaseException as exc:
        marker=batch/'gpu_resource_stop.json'
        resource_stop=marker.exists() and read(marker).get('time',0)>=started
        server_log=batch/'vllm.log'
        memory_failure=(server is not None and server_log.exists() and gpu_memory_failure(server_log.read_text(errors='replace')[-100000:]))
        resource_stop=resource_stop or memory_failure or gpu_memory_failure(str(exc))
        if resource_stop:
            snapshot=subprocess.run(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv'],capture_output=True,text=True)
            with (batch/'resource_interruptions.jsonl').open('a') as f:
                f.write(json.dumps({'time':time.time(),'reason':read(marker) if marker.exists() and read(marker).get('time',0)>=started else {'error':str(exc),'gpu_memory_failure':memory_failure},'processes':snapshot.stdout,'stderr':snapshot.stderr})+'\n')
        save(batch/'status.json',{'stage':'retry_wait' if resource_stop else 'stopped','retryable':resource_stop,'completed':len(state['attempts']),'error':str(exc)})
        raise
    finally:
        if watcher:watcher.terminate();watcher.wait(timeout=15)
        if server:stop_server(server,created)

if __name__=='__main__':main()
