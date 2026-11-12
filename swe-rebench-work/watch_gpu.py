"""Stop only the recorded batch controller if shared GPU memory becomes scarce."""
import json,os,signal,subprocess,sys,time
from pathlib import Path
import psutil

def write(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2)+'\n');temp.replace(path)

def main(batch,pid,created):
    path=batch/'gpu_watch.jsonl';low=0
    while True:
        try:
            p=psutil.Process(pid)
            if p.create_time()!=created or not p.is_running() or p.status()==psutil.STATUS_ZOMBIE:break
        except psutil.Error:break
        try:
            r=subprocess.run(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=12,check=True)
            values=[int(s.strip()) for s in r.stdout.splitlines() if s.strip()]
            if len(values)!=1:raise RuntimeError('expected one GPU')
            free=values[0]
            low=low+1 if free<8000 else 0
            with path.open('a') as f:f.write(json.dumps({'time':time.time(),'gpu_free_mib':free,'controller_pid':pid})+'\n')
            if low>=2:
                write(batch/'gpu_resource_stop.json',{'time':time.time(),'gpu_free_mib':free,'controller_pid':pid,'reason':'GPU free below 8000 MiB twice'})
                os.kill(pid,signal.SIGINT);break
        except Exception as e:
            write(batch/'gpu_watch_error.json',{'time':time.time(),'error':str(e)})
            os.kill(pid,signal.SIGINT);break
        time.sleep(5)

if __name__=='__main__':main(Path(sys.argv[1]),int(sys.argv[2]),float(sys.argv[3]))
