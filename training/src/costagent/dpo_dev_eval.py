"""Fresh graded development attempts, using existing isolated SWE worker images.

This is a small failure-enriched development set, not an unbiased final benchmark.
Only owned child process groups and containers are cleaned up.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
import urllib.request
import uuid
from .traces import ROOT,ARTIFACTS,TRAIN,write_json
from .train import fingerprint


def docker_environment(environ,recorded):
    """Reuse the original dataset daemon while honoring an explicit host override."""
    env=dict(environ)
    if not env.get('DOCKER_HOST'):
        if not recorded.get('docker_host'):raise ValueError('Original Docker host was not recorded')
        env['DOCKER_HOST']=recorded['docker_host']
    expected=recorded.get('docker_data_root') if env['DOCKER_HOST']==recorded.get('docker_host') else None
    return env,expected


def disk_guard():
    if shutil.disk_usage(ARTIFACTS).free < 20*2**30:
        raise RuntimeError('Less than 20 GiB free; preserving shared workspace headroom')


def candidates():
    manifest=json.loads(TRAIN.read_text())
    trained={r['task_id'] for r in manifest['attempts'] if r['resolved'] is True}
    result=[];seen=set()
    for row in manifest['attempts']:
        task=row['task_id'];spec_path=TRAIN.parent/'tasks'/task/'grading_spec.json'
        if task in trained or task in seen or row['resolved'] is not False or not spec_path.exists():continue
        spec=json.loads(spec_path.read_text());seen.add(task)
        result.append(dict(task_id=task,repo=spec['repo'],image=spec['image_name'],spec=str(spec_path),
                           spec_sha256=hashlib.sha256(spec_path.read_bytes()).hexdigest()))
    return sorted(result,key=lambda r:hashlib.sha256(('dpo-dev-20261029:'+r['task_id']).encode()).hexdigest())


def freeze_manifest(path,client,count=4):
    if path.exists():return json.loads(path.read_text())
    selected=[];repos=set()
    for row in candidates():
        if row['repo'] in repos:continue
        try:client.images.get(row['image'])
        except Exception as exc:
            import docker
            if isinstance(exc,docker.errors.ImageNotFound):continue
            raise
        selected.append(dict(row,seed=88000+len(selected)));repos.add(row['repo'])
        if len(selected)==count:break
    if len(selected)<count:raise RuntimeError(f'Only {len(selected)} cached distinct-repo development images found; need {count}. No images pulled.')
    data=dict(tasks=selected,split='failure_enriched_training_unseen_development',
              caveat='Selected from prior baseline failures; tuning set, not final test set',
              images_pulled=False)
    write_json(path,data);return data


def stop_owned(process):
    if process.poll() is None:
        os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)


def launch_server(adapter,directory):
    # Existing worker uses this loopback port. Refuse to replace a shared service.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',8001))
    env=os.environ.copy()
    compat=ROOT/'baseline-kit/cuda-compat-local/usr/local/cuda-13.0/compat'
    env['LD_LIBRARY_PATH']=str(compat)+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    env.update(VLLM_USE_FLASHINFER_SAMPLER='0',VLLM_WORKER_MULTIPROC_METHOD='spawn',VLLM_NO_USAGE_STATS='1',
               OTEL_SDK_DISABLED='true',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',VLLM_ENGINE_READY_TIMEOUT_S='1200')
    command=[str(Path(os.sys.executable).with_name('vllm')),'serve',str(ROOT/'gemma-4-31b-it-qat-w4a16-ct'),
        '--served-model-name','gemma-4-31b-it-qat-w4a16-ct','--host','127.0.0.1','--port','8001',
        '--tensor-parallel-size','1','--dtype','bfloat16','--max-model-len','32768',
        '--gpu-memory-utilization','0.55','--max-num-seqs','1','--max-num-batched-tokens','4096',
        '--enable-auto-tool-choice','--tool-call-parser','gemma4','--reasoning-parser','gemma4',
        '--reasoning-config','{"reasoning_start_str":"<|channel>","reasoning_end_str":"<channel|>"}',
        '--enable-lora','--max-loras','2','--max-lora-rank','128','--lora-modules',
        'main_lora='+str(adapter),'tool_lora='+str(ROOT/'data/sample_submission/adapters/tool_lora')]
    with (directory/'vllm.log').open('a') as log:
        process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:
        deadline=time.monotonic()+1200
        while time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('Owned vLLM server exited; see vllm.log')
            try:
                with urllib.request.urlopen('http://127.0.0.1:8001/v1/models',timeout=3) as response:
                    models=json.load(response)
                if 'main_lora' in {m['id'] for m in models['data']}:return process
            except (OSError,ValueError):pass
            time.sleep(3)
        raise RuntimeError('vLLM startup timeout')
    except BaseException:
        stop_owned(process);raise


def run(adapter,directory,manifest_path):
    import docker
    directory.mkdir(parents=True,exist_ok=True)
    recorded=json.loads((TRAIN.parent/'manifest.json').read_text())
    worker_env,expected_root=docker_environment(os.environ,recorded)
    client=docker.from_env(environment=worker_env)
    actual_root=client.info()['DockerRootDir']
    write_json(directory/'docker_environment.json',dict(host=worker_env['DOCKER_HOST'],data_root=actual_root))
    if expected_root and actual_root!=expected_root:
        client.close();raise RuntimeError('Recorded Docker host has an unexpected data root')
    manifest=freeze_manifest(manifest_path,client)
    signature=dict(adapter_sha256=fingerprint(adapter),manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest())
    summary_path=directory/'summary.json'
    if summary_path.exists():
        summary=json.loads(summary_path.read_text())
        if summary['signature']!=signature:raise ValueError('Existing evaluation signature differs')
        return summary
    if (directory/'signature.json').exists():
        if json.loads((directory/'signature.json').read_text())!=signature:raise ValueError('Partial evaluation signature differs')
    write_json(directory/'signature.json',signature)
    disk_guard();server=launch_server(adapter,directory);results=[]
    try:
        for task in manifest['tasks']:
            disk_guard();spec=Path(task['spec'])
            if hashlib.sha256(spec.read_bytes()).hexdigest()!=task['spec_sha256']:raise ValueError('Task spec changed')
            task_root=directory/task['task_id'];task_root.mkdir(exist_ok=True)
            previous=list(sorted(task_root.glob('attempt-*/outcome.json')))
            outcome=None
            for path in previous:
                value=json.loads(path.read_text())
                if type(value.get('resolved')) is bool:outcome=value;break
            if outcome is None:
                attempt=1+len(list(task_root.glob('attempt-*')))
                if attempt>3:raise RuntimeError('Development task exhausted infrastructure retries')
                out=task_root/f'attempt-{attempt}';out.mkdir()
                tag='dpo-dev-'+uuid.uuid4().hex
                command=[os.sys.executable,str(ROOT/'swe-rebench-work/run_batch.py'),'--worker','--spec',str(spec),
                         '--out',str(out),'--run',tag,'--seed',str(task['seed']),'--phase','attempt']
                with (out/'worker.log').open('w') as log:
                    worker=subprocess.Popen(command,env=worker_env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                    try:
                        if worker.wait(timeout=1200)!=0:raise RuntimeError('Development worker failed: '+str(out))
                    finally:
                        stop_owned(worker)
                        for container in client.containers.list(all=True,filters={'label':'gemma.swerebench.batch='+tag},ignore_removed=True):
                            container.remove(force=True)
                outcome=json.loads((out/'outcome.json').read_text())
            if type(outcome.get('resolved')) is not bool:raise RuntimeError('Unknown grading outcome; evaluation incomplete')
            result=dict(task_id=task['task_id'],resolved=outcome['resolved'],calls=outcome['agent']['tool_calls'])
            results.append(result);print(json.dumps(result),flush=True)
        solved=[r for r in results if r['resolved']]
        summary=dict(signature=signature,adapter=str(adapter),tasks=len(results),solved=len(solved),
            solve_rate=len(solved)/len(results),mean_calls=sum(r['calls'] for r in results)/len(results),
            mean_calls_solved=sum(r['calls'] for r in solved)/len(solved) if solved else None,
            results=results,split=manifest['split'],caveat=manifest['caveat'])
        write_json(summary_path,summary);return summary
    finally:stop_owned(server);client.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adapter',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    if not all(p.resolve().is_relative_to(ARTIFACTS.resolve()) for p in (a.output,a.manifest)):
        raise ValueError('Evaluation outputs must be under artifacts/')
    if a.dry_run:print(json.dumps(dict(candidate_tasks=len(candidates()),manifest=str(a.manifest),gpu_evaluation=False)));return
    print(json.dumps(run(a.adapter.resolve(),a.output.resolve(),a.manifest.resolve()),indent=2),flush=True)

if __name__=='__main__':main()
