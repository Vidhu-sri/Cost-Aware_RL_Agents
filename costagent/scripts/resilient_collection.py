"""Retry resource-interrupted collection; preserve progress and stop on code errors."""
import fcntl,json,os,subprocess,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
batch=root/'artifacts/mixed-temperature-v1'
lock=(batch/'retry-supervisor.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
(batch/'retry-supervisor.pid').write_text(str(os.getpid())+'\n')
started=time.time();attempt=0
while True:
    attempt+=1
    print(json.dumps({'event':'collection_start','attempt':attempt,'time':time.time()}),flush=True)
    result=subprocess.run([sys.executable,'-u',str(root/'scripts/collect_temperatures.py')],cwd=root)
    status=json.loads((batch/'status.json').read_text()) if (batch/'status.json').exists() else {}
    if result.returncode==0 and status.get('stage')=='complete':break
    if not status.get('retryable'):
        status.update(stage='stopped',retryable=False,supervisor_exit=result.returncode)
        (batch/'status.json').write_text(json.dumps(status,indent=2)+'\n')
        raise SystemExit(result.returncode or 1)
    print(json.dumps({'event':'resource_retry_in_60_seconds','completed':status.get('completed')}),flush=True)
    time.sleep(60)
