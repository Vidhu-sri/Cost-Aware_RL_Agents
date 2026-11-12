"""Observe GPU pressure without interrupting the owner's workload."""
import json,subprocess,sys,time
from pathlib import Path
import psutil
batch=Path(sys.argv[1]);pid=int(sys.argv[2]);created=float(sys.argv[3])
while True:
    try:
        parent=psutil.Process(pid)
        if parent.create_time()!=created or not parent.is_running() or parent.status()==psutil.STATUS_ZOMBIE:break
    except psutil.NoSuchProcess:break
    record={'time':time.time(),'controller_pid':pid,'policy':'observe_only'}
    for key,query in [('gpu','--query-gpu=memory.free,utilization.gpu'),('processes','--query-compute-apps=pid,process_name,used_memory')]:
        try:
            result=subprocess.run(['nvidia-smi',query,'--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=12)
            record[key]=result.stdout.strip();record[key+'_error']=result.stderr.strip()
        except Exception as exc:record[key+'_error']=str(exc)
    with (batch/'gpu_pressure.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
    time.sleep(15)
