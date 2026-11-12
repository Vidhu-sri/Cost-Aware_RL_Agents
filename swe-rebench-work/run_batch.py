"""Sequential Gemma generation with pinned SWE-rebench V2 grading.

Generation is delegated to installed swegemma; grading uses the pinned publisher
parser/evaluator. Only container transport/provisioning is adapted locally.
"""
import argparse, asyncio, csv, hashlib, importlib.util, io, json, os
from pathlib import Path
import shlex, shutil, signal, socket, subprocess, sys, tarfile, time, uuid
from datetime import datetime, timezone
import urllib.request
import docker, psutil
ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent
KIT=PROJECT/'baseline-kit'
sys.path.insert(0,str(KIT))
from run_docker_agent_all import gpu_free_mib, stop_server
from swegemma.sandbox.docker import ContainerManager, ContainerConfig
LABEL='gemma.swerebench.batch'
REV='10483de0f50fe5da545942705a76c6150171af7f'
COMMIT='c71902a8cf8d2b725f63d51f199f4d3e56f68d2d'
FIRST_IMAGE='docker.io/swerebenchv2/wtforms-wtforms:614-848d28d'
STOP=False
for k,v in {'LITELLM_LOCAL_MODEL_COST_MAP':'True','OTEL_SDK_DISABLED':'true','LITELLM_TELEMETRY':'False','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'}.items(): os.environ[k]=v

def now(): return datetime.now(timezone.utc).isoformat()
def save(p,obj):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(obj,indent=2,default=str)+'\n');tmp.replace(p)
def append(p,obj):
    with Path(p).open('a') as f: f.write(json.dumps(obj,default=str)+'\n');f.flush()
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def stopped(signum,frame):
    global STOP
    STOP=True

def owned(client,run):
    # The worker can remove its container between Docker's list and inspect.
    # Docker SDK explicitly supports this race with ignore_removed.
    return client.containers.list(all=True,filters={'label':f'{LABEL}={run}'},ignore_removed=True)
def clean(client,run):
    ids=[]
    for c in owned(client,run):
        ids.append(c.id)
        try: c.remove(force=True)
        except docker.errors.NotFound: pass
    if owned(client,run): raise RuntimeError('owned-container cleanup failed: '+run)
    return ids

def publisher():
    path=ROOT/'publisher-harness/scripts/eval.py'
    spec=importlib.util.spec_from_file_location('publisher_eval',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def copy_text(container,name,text):
    raw=text.encode();stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as tar:
        entry=tarfile.TarInfo(name);entry.size=len(raw);entry.mode=0o600;tar.addfile(entry,io.BytesIO(raw))
    container.put_archive('/tmp',stream.getvalue())

class Manager(ContainerManager):
    def __init__(self,image,task,out,run,phase):
        super().__init__(ContainerConfig(image=image,timeout_seconds=60))
        self.task,self.out,self.run,self.phase=task,Path(out),run,phase
    def exec(self,cid,command,*,timeout=None):
        begin=now();result=super().exec(cid,command,timeout=timeout)
        append(self.out/'commands.jsonl',dict(time=begin,phase=self.phase,container_id=cid,command=command,stdout=result.stdout,stderr=result.stderr,exit_code=result.exit_code,status=result.status,duration_seconds=result.duration_seconds))
        return result
    def checked(self,cid,command,timeout=60):
        r=self.exec(cid,command,timeout=timeout)
        if r.exit_code: raise RuntimeError(f'container command failed ({r.exit_code}): {command}\n{r.stderr}\n{r.stdout}')
        return r
    def start(self):
        repo='/'+self.task['repo'].split('/')[1]
        c=self.client.containers.run(self.config.image,command=['sleep','infinity'],entrypoint='',detach=True,network_mode='none',working_dir=repo,environment={'PIP_CACHE_DIR':'/tmp/pip-cache','PYTHONPYCACHEPREFIX':'/tmp/pycache','XDG_CACHE_HOME':'/tmp/cache'},labels={LABEL:self.run,'gemma.swerebench.phase':self.phase})
        with self._lock:self._active_containers.add(c.id)
        append(self.out/'container_ids.jsonl',{'id':c.id,'phase':self.phase,'time':now()})
        c.reload();cfg=c.attrs['HostConfig']
        security={'id':c.id,'privileged':cfg['Privileged'],'network':cfg['NetworkMode'],'mounts':c.attrs.get('Mounts',[]),'binds':cfg.get('Binds'),'caps':cfg.get('CapAdd')}
        append(self.out/'security.jsonl',security)
        assert not security['privileged'] and security['network']=='none' and not security['mounts'] and not security['binds'] and not security['caps']
        base=self.checked(c.id,'git rev-parse HEAD').stdout.strip()
        if base!=self.task['base_commit']: raise RuntimeError(f'publisher image base mismatch {base}')
        if self.phase!='grading':
            # Remove all upstream Git objects before any agent tool or prompt.
            self.checked(c.id,'if test -e /workspace; then mv /workspace /tmp/publisher-original-workspace; fi; test ! -e /workspace && ln -s '+shlex.quote(repo)+' /workspace')
            self.checked(c.id,'git reset --hard '+shlex.quote(base)+' && rm -rf .git && git init -q && git config user.name Gemma && git config user.email gemma@localhost')
            self.checked(c.id,"mkdir -p .git/info && printf '__pycache__/\\n*.pyc\\n.pytest_cache/\\n*.egg-info/\\nbuild/\\ndist/\\n' >> .git/info/exclude && git add -A && git commit --allow-empty -qm baseline && git tag _swegemma_baseline")
            self.checked(c.id,'test "$(git rev-list --all --count)" = 1 && test -z "$(git remote)" && test -z "$(git status --porcelain)"')
        # Publisher images include older Python releases without the stdlib
        # importlib.metadata module. pip's JSON listing works across them.
        self.checked(c.id,'python --version && python -m pip list --format=json')
        return c.id
    def stop(self,cid):
        if self.phase=='agent':
            try:
                result=self.exec(cid,'git add -N . && git diff --binary _swegemma_baseline',timeout=15)
                (self.out/'working_tree.patch').write_text(result.stdout)
            except Exception as e: append(self.out/'errors.jsonl',{'capture_error':str(e)})
        return super().stop(cid)

def preflight(spec,out,run):
    m=Manager(spec['image_name'],spec,out,run,'preflight')
    try:
        cid=m.start()
        r=m.checked(cid,"printf 'LINE1\\nLINE2\\nLINE3\\n'");assert r.stdout=='LINE1\nLINE2\nLINE3\n'
        r=m.exec(cid,'sleep 3',timeout=1);assert r.exit_code==124
        r=m.exec(cid,"python -c 'import socket; s=socket.socket(); s.settimeout(1); s.connect((\"1.1.1.1\",443))'",timeout=5);assert r.exit_code!=0
        if spec['repo']=='wtforms/wtforms':
            r=m.checked(cid,"python -c 'import wtforms; print(wtforms.__file__)'")
            assert '/wtforms/' in r.stdout
        save(out/'preflight.json',{'passed':True,'time':now()})
    finally:m.cleanup_all()

def generate(spec,out,run,seed):
    from adk_submission import ModelRegistry
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.agents.context_cache_config import ContextCacheConfig
    from google.adk.apps._configs import EventsCompactionConfig
    from swegemma.config import EvalConfig
    from swegemma.models.task import Task
    from swegemma.harness import agent_runner
    from adk_eval_core.tracing import SessionTrace
    import yaml,litellm,httpx,importlib.metadata
    safe={k:spec[k] for k in ('instance_id','repo','base_commit','problem_statement')}
    save(out/'safe_task_input.json',safe)
    agentdir=out/'agent_snapshot';shutil.copytree(PROJECT/'data/sample_submission',agentdir)
    sample=agentdir/'configs/sampling.yaml';original=yaml.safe_load(sample.read_text())
    with sample.open('a') as f:f.write(f'\nseed: {seed}\n')
    save(out/'settings.json',{'agent_minutes':5,'tool_calls':100,'turns':50,'command_timeout_seconds':60,'outer_deadline_seconds':900,'seed':seed,'sampling':yaml.safe_load(sample.read_text()),'original_sampling':original,'image':spec['image_name'],'packages':{n:importlib.metadata.version(n) for n in ('swegemma','google-adk','adk-submission','litellm','vllm','torch','transformers')}})
    request_count=0
    original_send=httpx.AsyncClient.send
    async def logged_send(client,request,*args,**kwargs):
        nonlocal request_count
        if request.url.host=='127.0.0.1' and request.url.port==8001 and '/chat/completions' in request.url.path:
            request_count+=1;stamp=now()
            append(out/'model_requests.jsonl',{'timestamp':stamp,'number':request_count,'body':json.loads(request.content)})
            if request_count==1:
                save(out/'first_model_request.json',{'timestamp':stamp,'task':spec['instance_id'],'seed':seed})
                print(f'FIRST MODEL REQUEST SENT {stamp} task={spec["instance_id"]} seed={seed}',flush=True)
        return await original_send(client,request,*args,**kwargs)
    httpx.AsyncClient.send=logged_send
    class Trace(SessionTrace):
        def _add(self,entry):
            super()._add(entry)
            self.save(out/'trace.partial.tmp');(out/'trace.partial.tmp').replace(out/'trace.partial.json')
            save(out/'progress.json',{'elapsed':self.duration,'tool_calls':self.summarize()['tool_calls'],'llm_requests':request_count,'latest':entry.tool_name or entry.event_type,'time':now()})
    agent_runner.SessionTrace=Trace
    for name in ('setup_container_wheels','extract_snapshot','setup_git_exclude','install_editable_package','install_test_dependencies','setup_workspace_test_config','setup_baseline_commit'):
        setattr(agent_runner,name,lambda *a,**kw:None)
    litellm.drop_params=True;litellm.telemetry=False
    models=ModelRegistry();base='gemma-4-31b-it-qat-w4a16-ct'
    for alias,served in ((base,base),('adapter:main_lora','main_lora'),('adapter:tool_lora','tool_lora')):
        models.register(alias,LiteLlm(model='openai/'+served,api_base='http://127.0.0.1:8001/v1',api_key='EMPTY',num_retries=2))
    config=EvalConfig(tasks_path=out/'safe_task_input.json',snapshots_dir=out,results_dir=out,submission_dir=agentdir,models=models,image=spec['image_name'],sandbox='docker',graph_dir=str(out/'no_graph'),embeddings_dir=str(out/'no_embeddings'),concurrency=1,display_mode='quiet',timeout_seconds=60,max_time_minutes=5,max_tool_calls=100,max_turns=50,context_cache_config=ContextCacheConfig(min_tokens=2048,ttl_seconds=1800,cache_intervals=10),events_compaction_config=EventsCompactionConfig(compaction_interval=15,overlap_size=2,token_threshold=14336,event_retention_size=5))
    m=Manager(spec['image_name'],spec,out,run,'agent')
    try:
        patch,error,trace=asyncio.run(agent_runner.run_agent_sandbox(m,config,Task(**safe),out/'unused'))
        (out/'agent.patch').write_text(patch);trace.save(out/'trace.json')
        (out/'rollout.md').write_text(trace.to_markdown(max_thought_len=None,max_tool_args_len=None,max_tool_result_len=None,max_text_len=None,max_final_len=None,multiline_mode='code'))
        result={'agent_error':error,'agent_timeout':bool(error and 'timeout' in error.lower()),'patch_bytes':len(patch.encode()),'llm_requests':request_count,'tool_calls':trace.summarize()['tool_calls'],'tokens':trace.summarize(),'elapsed_seconds':trace.duration,'submission_seconds':next((e.elapsed for e in trace.entries if e.event_type=='tool_call' and e.tool_name=='submit_patch'),None)}
        save(out/'agent_result.json',result)
        return patch,result
    finally:m.cleanup_all()

def grade(spec,out,run,patch):
    ev=publisher();ev.LOGS_DIR=out/'grading'
    # Gold is absent from spec. An explicit override is mandatory.
    assert 'patch' not in spec
    m=Manager(spec['image_name'],spec,out,run,'grading');setup={}
    def transport(image,workdir,patch_dir,patch_name,test_patch_name,test_cmds):
        cid=m.start();c=m.client.containers.get(cid)
        for source in (patch_name,test_patch_name):copy_text(c,source,(patch_dir/source).read_text())
        m.checked(cid,'git reset --hard HEAD')
        if patch.strip():
            r=m.exec(cid,'git apply -v --3way --recount --ignore-space-change --whitespace=nowarn /tmp/'+patch_name,timeout=30)
            setup['model_patch_exit']=r.exit_code
            if r.exit_code: raise RuntimeError('model patch could not be applied: '+r.stderr)
        r=m.exec(cid,'git apply -v --3way --recount --ignore-space-change --whitespace=nowarn /tmp/'+test_patch_name,timeout=30)
        setup['test_patch_exit']=r.exit_code
        if r.exit_code:raise RuntimeError('publisher test patch could not be applied: '+r.stderr)
        result=m.exec(cid,'set -e\n'+'\n'.join(test_cmds),timeout=480)
        setup['test_exit']=result.exit_code;setup['test_timed_out']=result.timed_out
        if result.timed_out or result.exit_code==-1:raise RuntimeError('grading command timeout/transport failure: '+result.stderr)
        return result.exit_code,result.stdout+result.stderr
    ev.run_in_container=transport
    try:
        if patch.strip():
            report=ev.evaluate_instance(spec,spec['image_name'],{'patch':patch})
        else:
            # Empty generated patch means test unchanged base. Use the same official
            # parser/name normalization and exact passed-set criterion, without gold.
            import tempfile
            with tempfile.TemporaryDirectory(dir=out) as tmp:
                p=Path(tmp);(p/'patch.diff').write_text('');(p/'test_patch.diff').write_text(spec['test_patch'])
                code,output=transport(spec['image_name'],'/'+spec['repo'].split('/')[1],p,'patch.diff','test_patch.diff',ev.normalize_command_list(spec['install_config']['test_cmd'],'test_cmd',spec['instance_id']))
            parsed=ev.get_parser(spec['install_config']['log_parser'])(output)
            passed=sorted(ev._normalize_test_name(k) for k,v in parsed.items() if v=='PASSED')
            expected=sorted(ev._normalize_test_name(k) for k in spec['FAIL_TO_PASS']+spec['PASS_TO_PASS'])
            (out/'grading').mkdir(exist_ok=True);(out/'grading/test.log').write_text(output)
            report={'exit_code':code,'passed_match':passed==expected,'passed_actual':passed,'failed_actual':[k for k,v in parsed.items() if v=='FAILED'],'passed_expected':expected}
        report['setup']=setup;save(out/'grading_report.json',report)
        if not report['passed_actual'] and not report['failed_actual']:
            logpath=Path(report.get('log_path',out/'grading/test.log'))
            text=logpath.read_text() if logpath.exists() else ''
            parsed=ev.get_parser(spec['install_config']['log_parser'])(text)
            local_source='/'+spec['repo'].split('/')[1]+'/'
            source_import_failure=('cannot import name' in text and local_source in text and any(v=='ERROR' for v in parsed.values()))
            modified_paths={line.split(' b/',1)[1] for line in patch.splitlines()
                            if line.startswith('diff --git a/') and ' b/' in line}
            model_syntax_failure=('SyntaxError:' in text and any(path in text for path in modified_paths)
                                  and any(v=='ERROR' for v in parsed.values()))
            if not (source_import_failure or model_syntax_failure):
                return {'category':'infrastructure_grading_error','resolved':None,'reward':None,'error':'no passed/failed cases; collection or environment needs review'}
        resolved=bool(report['passed_match'])
        return {'category':'resolved' if resolved else 'unresolved','resolved':resolved,'reward':1 if resolved else 0,'passed_count':len(report['passed_actual']),'failed_count':len(report['failed_actual'])}
    except Exception as e:
        save(out/'grading_error.json',{'error':str(e),'setup':setup})
        return {'category':'infrastructure_grading_error','resolved':None,'reward':None,'error':str(e)}
    finally:m.cleanup_all()

def worker(args):
    out=args.out;spec=json.loads(args.spec.read_text());spec.pop('patch',None)
    try:
        if args.phase=='preflight':preflight(spec,out,args.run);return 0
        patch,agent=generate(spec,out,args.run,args.seed)
        if agent['llm_requests']==0:raise RuntimeError('generation returned without any model request: '+str(agent['agent_error']))
        result=grade(spec,out,args.run,patch)
        save(out/'outcome.json',dict(task_id=spec['instance_id'],seed=args.seed,agent=agent,**result))
        return 0
    except Exception as e:
        save(out/'worker_error.json',{'error':str(e),'time':now()});raise

def sample_container(c):
    c.reload();pid=c.attrs['State'].get('Pid',0)
    if not pid:return {'pid':0,'rss':0,'processes':0}
    try:namespace=os.readlink(f'/proc/{pid}/ns/pid')
    except FileNotFoundError:
        # The container can exit after Docker's state read and before /proc.
        c.reload()
        if not c.attrs['State'].get('Running') or not c.attrs['State'].get('Pid'):
            return {'pid':0,'rss':0,'processes':0}
        raise
    rss=0;count=0
    for p in psutil.process_iter():
        try:
            if os.readlink(f'/proc/{p.pid}/ns/pid')==namespace:rss+=p.memory_info().rss;count+=1
        except (psutil.Error,OSError):continue
    if not count:
        # A grading container often exits between the namespace read and
        # process enumeration. Verify that transition before treating it as
        # an inability to monitor a live container.
        c.reload()
        if not c.attrs['State'].get('Running') or not c.attrs['State'].get('Pid'):
            return {'pid':0,'rss':0,'processes':0}
        try:os.readlink(f'/proc/{pid}/ns/pid')
        except FileNotFoundError:return {'pid':0,'rss':0,'processes':0}
        raise RuntimeError(f'cannot monitor live container processes {c.id}')
    return {'pid':pid,'rss':rss,'processes':count}

def docker_disk_path():
    return Path(os.environ.get('GEMMA_DOCKER_DATA_ROOT',str(ROOT)))

def results_disk_path():
    return Path(os.environ.get('GEMMA_RESULTS_DATA_ROOT',str(ROOT)))

def mirror_result(batch,out=None):
    mirror=os.environ.get('GEMMA_RESULTS_MIRROR')
    if not mirror:return
    target=Path(mirror)
    if out is not None:
        destination=target/out.relative_to(batch)
        shutil.copytree(out,destination,dirs_exist_ok=True)
    manifest=batch/'manifest.json'
    if manifest.exists():
        target.mkdir(parents=True,exist_ok=True)
        shutil.copy2(manifest,target/'manifest.json')

def resource_check(min_disk=3*1024**3):
    results_disk=shutil.disk_usage(results_disk_path()).free
    image_disk=shutil.disk_usage(docker_disk_path()).free
    home_disk=shutil.disk_usage(ROOT).free
    home_min=min_disk if results_disk_path().resolve()==ROOT.resolve() else int(1.5*1024**3)
    ram=psutil.virtual_memory().available
    if results_disk<min_disk or image_disk<min_disk or home_disk<home_min or ram<16*1024**3:
        raise RuntimeError(f'resource condition: results disk={results_disk}, image disk={image_disk}, home disk={home_disk}, available RAM={ram}')
    return image_disk

def supervise(spec_path,out,run,seed,phase,client):
    out.mkdir(parents=True,exist_ok=True);deadline=time.monotonic()+(180 if phase=='preflight' else 900)
    owned(client,run);save(out/'monitor_start.json',{'time':now(),'before_worker':True})
    cmd=[sys.executable,str(Path(__file__).resolve()),'--worker','--spec',str(spec_path),'--out',str(out),'--run',run,'--seed',str(seed),'--phase',phase]
    error=None;peak=0;last=0;p=None
    try:
        with (out/'worker.log').open('w') as f:p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        while p.poll() is None:
            if STOP:raise RuntimeError('interrupted')
            if time.monotonic()>deadline:raise TimeoutError('outer deadline exceeded')
            disk=resource_check()
            for c in owned(client,run):
                try:s=sample_container(c)
                except (FileNotFoundError,docker.errors.NotFound):continue
                peak=max(peak,s['rss']);append(out/'monitor.jsonl',{'time':now(),'container_id':c.id,'disk_remaining':disk,**s})
                if s['rss']>12*1024**3:raise RuntimeError('observed container RSS exceeded 12 GiB')
            if time.monotonic()-last>15:
                progress=json.loads((out/'progress.json').read_text()) if (out/'progress.json').exists() else {'latest':'setup'}
                print(json.dumps({'attempt':out.name,'progress':progress,'disk_remaining_gib':round(disk/1024**3,2)}),flush=True);last=time.monotonic()
            time.sleep(1)
    except Exception as e:error=str(e)
    finally:
        if p and p.poll() is None:
            # Bounded capture before interrupting only our worker process group.
            for c in owned(client,run):
                try:
                    if c.labels.get('gemma.swerebench.phase')=='agent':
                        r=c.exec_run(['timeout','15','bash','-c','git add -N .; git diff --binary _swegemma_baseline'],demux=True)
                        (out/'interrupted_worktree.patch').write_bytes(r.output[0] or b'')
                except docker.errors.NotFound:
                    continue
                except Exception as e:append(out/'errors.jsonl',{'capture_error':str(e)})
            os.killpg(p.pid,signal.SIGINT)
            try:p.wait(timeout=15)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
        removed=clean(client,run)
        save(out/'cleanup.json',{'time':now(),'removed_ids':removed,'remaining':[],'success':True,'peak_observed_rss_bytes':peak,'supervisor_error':error,'worker_exit':p.returncode if p else None})
        mirror_result(out.parents[2],out)
    if error:raise RuntimeError(error)
    return p.returncode==0

def candidates():
    import pyarrow.parquet as pq
    overlap={r['training_instance_id'] for r in csv.DictReader((ROOT/'metadata/overlap_v2.csv').open())}
    competition={json.loads(l)['repo'].lower() for l in (PROJECT/'data/tasks.jsonl').read_text().splitlines()}
    cols=['instance_id','repo','base_commit','problem_statement','language','image_name','test_patch','FAIL_TO_PASS','PASS_TO_PASS','install_config']
    for batch in pq.ParquetFile(ROOT/'metadata/train.parquet').iter_batches(batch_size=32,columns=cols):
        for r in batch.to_pylist():
            if r['language'] not in ('python','py') or r['instance_id'] in overlap or r['repo'].lower() in competition:continue
            if not r['FAIL_TO_PASS'] or not r['test_patch'] or not r['problem_statement'] or not r['image_name']:continue
            try:publisher().get_parser(r['install_config']['log_parser'])
            except Exception:continue
            yield r

def image_ready(spec,client,batch,acquired):
    name=spec['image_name']
    try:return client.images.get(name)
    except docker.errors.ImageNotFound:pass
    r=subprocess.run(['docker','manifest','inspect',name],capture_output=True,text=True,timeout=60)
    if r.returncode:raise ValueError('image manifest unavailable: '+r.stderr)
    manifest=json.loads(r.stdout);size=sum(x['size'] for x in manifest.get('layers',[]))
    if not size:raise ValueError('image manifest has no directly inspectable layers')
    free=resource_check()
    if size*4+3*1024**3>free:raise ValueError(f'image does not fit conservative disk estimate: compressed={size}, free={free}')
    print('IMAGE PULL STARTED '+name,flush=True)
    with (batch/'image_pulls.log').open('a') as log:
        p=subprocess.Popen(['docker','pull',name],stdout=log,stderr=subprocess.STDOUT)
        begin=time.monotonic()
        try:
            while p.poll() is None:
                resource_check()
                if STOP or time.monotonic()-begin>600:raise RuntimeError('image pull deadline/interruption')
                time.sleep(2)
        finally:
            if p.poll() is None:p.terminate();p.wait(timeout=10)
        if p.returncode:raise ValueError(f'image pull failed: {name}, code={p.returncode}')
    acquired.add(name);save(batch/'acquired_images.json',sorted(acquired))
    image=client.images.get(name);print('IMAGE PULL COMPLETED '+name+' '+image.id,flush=True);return image

def release_image(client,name,acquired,batch):
    if name not in acquired:return
    image=client.images.get(name)
    if client.containers.list(all=True,filters={'ancestor':image.id}):raise RuntimeError('refusing image removal: container still uses '+name)
    # Do not force removal or prune shared layers.
    result=client.api.remove_image(name,force=False,noprune=True)
    append(batch/'image_removals.jsonl',{'image':name,'id':image.id,'result':result,'time':now()})
    acquired.remove(name);save(batch/'acquired_images.json',sorted(acquired))

def start_server(batch):
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',8001))==0:raise RuntimeError('port 8001 occupied by unowned server')
    free=gpu_free_mib()
    if free<62000:raise RuntimeError(f'insufficient GPU free memory: {free} MiB')
    env=os.environ.copy();env['BASELINE_GPU_FRACTION']='0.60';env['PATH']=str(Path(sys.executable).parent)+os.pathsep+env.get('PATH','')
    with (batch/'vllm.log').open('w') as log:p=subprocess.Popen(['bash',str(KIT/'serve.sh')],cwd=KIT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    created=psutil.Process(p.pid).create_time();save(batch/'server.json',{'pid':p.pid,'create_time':created,'pgid':p.pid,'gpu_fraction':.6,'concurrency':1,'serve_sha256':sha(KIT/'serve.sh')})
    return p,created

def wait_server(p,batch):
    deadline=time.monotonic()+600
    while time.monotonic()<deadline:
        resource_check()
        if STOP or p.poll() is not None:raise RuntimeError('server interrupted or exited during startup')
        try:
            with urllib.request.urlopen('http://127.0.0.1:8001/v1/models',timeout=2) as r:served=json.load(r)
            if {'main_lora','tool_lora','gemma-4-31b-it-qat-w4a16-ct'}<={m['id'] for m in served['data']}:break
        except Exception:pass
        time.sleep(2)
    else:raise RuntimeError('vLLM readiness timeout')
    probe_dir=batch/'model_probes'
    probe_dir.mkdir(exist_ok=True)
    probe_path=probe_dir/f'probe-{uuid.uuid4().hex}.json'
    subprocess.run([sys.executable,str(KIT/'probe_models.py'),'--output',str(probe_path)],timeout=390,check=True)
    append(batch/'model_probe_runs.jsonl',{'time':now(),'path':str(probe_path)})
    print('VLLM READY '+now(),flush=True)

def recover_completed_attempts(batch,state):
    """Checkpoint a finished worker if the supervisor lost the removal race."""
    known={(r['task_id'],r['attempt']) for r in state['attempts']}
    for out in sorted((batch/'tasks').glob('*/attempt-*')):
        parts=out.name.split('-')
        if len(parts)<3 or not parts[1].isdigit():continue
        tid,attempt=out.parent.name,int(parts[1])
        if (tid,attempt) in known:continue
        required=('outcome.json','trace.json','rollout.md','agent.patch','grading_report.json','cleanup.json','first_model_request.json')
        if any(not (out/name).exists() for name in required):continue
        cleanup=json.loads((out/'cleanup.json').read_text())
        result=json.loads((out/'outcome.json').read_text())
        if (not cleanup.get('success') or cleanup.get('remaining') or result.get('task_id')!=tid
                or result.get('agent',{}).get('llm_requests',0)<1):continue
        entry=dict(task_id=tid,attempt=attempt,result_dir=str(out),recovered_from_completed_worker=True,
                   **{k:v for k,v in result.items() if k!='task_id'})
        state['attempts'].append(entry);known.add((tid,attempt))
        print(f'RECOVERED COMPLETED ATTEMPT {tid} #{attempt} {entry["category"]}',flush=True)
    state['counts']={k:sum(r['category']==k for r in state['attempts'])
                     for k in ('resolved','unresolved','infrastructure_grading_error')}
    state['updated']=now()

def run_batch(args):
    signal.signal(signal.SIGINT,stopped);signal.signal(signal.SIGTERM,stopped)
    client=docker.from_env(timeout=30)
    batch=args.batch or ROOT/'results'/('batch-'+time.strftime('%Y%m%d-%H%M%S'))
    batch=batch.resolve();batch.mkdir(parents=True,exist_ok=True)
    path=batch/'manifest.json'
    state=json.loads(path.read_text()) if path.exists() else {'dataset':'nebius/SWE-rebench-V2','revision':REV,'harness_commit':COMMIT,'attempts':[],'setup_failures':[],'tasks':[],'created':now()}
    acquired=set(json.loads((batch/'acquired_images.json').read_text())) if (batch/'acquired_images.json').exists() else {FIRST_IMAGE}
    recover_completed_attempts(batch,state)
    if os.environ.get('GEMMA_DOCKER_DATA_ROOT'):
        old_store_skips=[r for r in state['setup_failures']
                         if str(r.get('error','')).startswith('image does not fit conservative disk estimate')]
        if old_store_skips:
            save(batch/'setup_failures_home_store.json',old_store_skips)
            state['setup_failures']=[r for r in state['setup_failures'] if r not in old_store_skips]
            state['retried_after_storage_change']=len(old_store_skips)
    state['docker_host']=os.environ.get('DOCKER_HOST')
    state['docker_data_root']=str(docker_disk_path())
    state['target_tasks']=100
    state['attempt_policy']='one attempt per distinct task; earlier extra attempts preserved'
    state['target_attempts']=len(state['attempts'])+max(0,100-len({r['task_id'] for r in state['attempts']}))
    state.pop('stop_reason',None)
    state.pop('server_cleanup',None)
    save(batch/'acquired_images.json',sorted(acquired));save(path,state)
    server=None;created=None;start=time.monotonic();watcher=None
    print('BATCH '+str(batch),flush=True)
    try:
        controller_pid=os.getpid();controller_created=psutil.Process(controller_pid).create_time()
        watcher=subprocess.Popen([sys.executable,str(ROOT/'watch_gpu.py'),str(batch),
                                  str(controller_pid),str(controller_created)],
                                 start_new_session=True,stdout=(batch/'gpu_watcher.log').open('a'),
                                 stderr=subprocess.STDOUT)
        append(batch/'gpu_watcher_runs.jsonl',{'time':now(),'controller_pid':controller_pid,
                                             'controller_create_time':controller_created,'watcher_pid':watcher.pid})
        for spec in candidates():
            if STOP:raise RuntimeError('interrupted')
            tid=spec['instance_id']
            if tid in {r['task_id'] for r in state.get('resource_skips',[])}:
                # Preserve an interrupted rollout that exceeded the observed
                # RSS stop limit; replace it with another eligible task.
                if spec['image_name'] in acquired:
                    release_image(client,spec['image_name'],acquired,batch)
                continue
            if tid in {r['task_id'] for r in state['setup_failures']}:continue
            done=[r for r in state['attempts'] if r['task_id']==tid]
            if done:
                # A resumed controller may have stopped before releasing this
                # task's pulled image. Release only tags recorded as acquired.
                if spec['image_name'] in acquired:
                    release_image(client,spec['image_name'],acquired,batch)
                continue
            if len({r['task_id'] for r in state['attempts']})>=100:break
            taskdir=batch/'tasks'/tid;taskdir.mkdir(parents=True,exist_ok=True)
            specpath=taskdir/'grading_spec.json';save(specpath,spec)
            try:
                image=image_ready(spec,client,batch,acquired)
                save(taskdir/'image.json',{'image':spec['image_name'],'id':image.id,'digests':image.attrs.get('RepoDigests'),'size':image.attrs['Size'],'dataset_revision':REV,'harness_commit':COMMIT})
                print('SELECTED TASK '+tid+' '+spec['image_name'],flush=True)
                pre=taskdir/('preflight-'+uuid.uuid4().hex[:8])
                if not supervise(specpath,pre,'rebench-pre-'+uuid.uuid4().hex,0,'preflight',client):
                    detail=json.loads((pre/'worker_error.json').read_text()) if (pre/'worker_error.json').exists() else {'error':'preflight worker failure'}
                    cleanup=json.loads((pre/'cleanup.json').read_text()) if (pre/'cleanup.json').exists() else {}
                    if not cleanup.get('success') or cleanup.get('remaining'):
                        raise RuntimeError('preflight cleanup failure: '+str(detail))
                    raise ValueError('task preflight failed: '+str(detail))
            except ValueError as e:
                state['setup_failures'].append({'task_id':tid,'error':str(e),'time':now()});save(path,state)
                print('TASK SETUP FAILURE '+tid+' '+str(e),flush=True)
                if spec['image_name'] in acquired:release_image(client,spec['image_name'],acquired,batch)
                continue
            if tid not in state['tasks']:state['tasks'].append(tid);save(path,state)
            if server is None:server,created=start_server(batch);wait_server(server,batch)
            for attempt in (1,):
                if server.poll() is not None:raise RuntimeError('owned vLLM server exited')
                run='rebench-'+uuid.uuid4().hex;out=taskdir/(f'attempt-{attempt}-'+run[-8:])
                # A prior interrupted rollout may already have used attempt 1's
                # seed. Keep its partial trace and use a fresh seed on retry.
                seed=100000+len(state['tasks'])*100+attempt+len(list(taskdir.glob('attempt-*')))
                print(f'TASK START {len({r["task_id"] for r in state["attempts"]})+1}/100 {tid} attempt={attempt} seed={seed}',flush=True)
                ok=supervise(specpath,out,run,seed,'attempt',client)
                if not ok:
                    detail=json.loads((out/'worker_error.json').read_text()) if (out/'worker_error.json').exists() else {'error':'worker failed'}
                    # An integration failure is not fixed by changing tasks.
                    raise RuntimeError('integration worker failure: '+str(detail))
                result=json.loads((out/'outcome.json').read_text())
                entry=dict(task_id=tid,attempt=attempt,result_dir=str(out),**{k:v for k,v in result.items() if k!='task_id'})
                state['attempts'].append(entry);state['updated']=now();save(path,state)
                counts={k:sum(r['category']==k for r in state['attempts']) for k in ('resolved','unresolved','infrastructure_grading_error')}
                state['counts']=counts;save(path,state)
                mirror_result(batch)
                print(json.dumps({'completed_attempts':len(state['attempts']),'target_tasks':100,'distinct_tasks':len({r['task_id'] for r in state['attempts']}),'counts':counts,'last':entry['category'],'elapsed_seconds':round(time.monotonic()-start),'results_disk_gib':round(shutil.disk_usage(ROOT).free/1024**3,2),'image_disk_gib':round(shutil.disk_usage(docker_disk_path()).free/1024**3,2)}),flush=True)
                if len(state['attempts'])==4:save(batch/'first_four_throughput.json',{'elapsed_seconds':time.monotonic()-start,'attempts':4,'attempts_per_hour':14400/(time.monotonic()-start),'counts':counts})
            release_image(client,spec['image_name'],acquired,batch)
        state['finished']=len({r['task_id'] for r in state['attempts']})>=100
    except Exception as e:
        state['stop_reason']=str(e);print('BATCH STOP '+str(e),flush=True)
    finally:
        if watcher and watcher.poll() is None:
            watcher.terminate()
            try:watcher.wait(timeout=10)
            except subprocess.TimeoutExpired:watcher.kill();watcher.wait()
        if server:state['server_cleanup']=stop_server(server,created)
        state['updated']=now();save(path,state)
        mirror_result(batch)
        print('FINAL STATE '+str(path),flush=True)
    return 0 if state.get('finished') else 1

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');p.add_argument('--spec',type=Path);p.add_argument('--out',type=Path);p.add_argument('--run');p.add_argument('--seed',type=int,default=0);p.add_argument('--phase',default='attempt');p.add_argument('--batch',type=Path)
    a=p.parse_args();raise SystemExit(worker(a) if a.worker else run_batch(a))
