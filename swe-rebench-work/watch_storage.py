"""Stop only the recorded batch controller if shared disk headroom shrinks."""
import json,os,signal,shutil,sys,time
from pathlib import Path
import psutil

def main(batch,pid,created,tmp_min_gib,home_min_gib):
    log=batch/'storage_watch.jsonl';low=0
    (batch/'storage_watcher_record.json').write_text(json.dumps({
        'watcher_pid':os.getpid(),'controller_pid':pid,'controller_create_time':created,
        'tmp_min_gib':tmp_min_gib,'home_min_gib':home_min_gib},indent=2)+'\n')
    while True:
        try:
            p=psutil.Process(pid)
            if p.create_time()!=created or not p.is_running() or p.status()==psutil.STATUS_ZOMBIE:break
        except psutil.Error:break
        tmp=shutil.disk_usage('/tmp').free/1024**3
        home=shutil.disk_usage(Path(__file__).resolve().parent).free/1024**3
        low=low+1 if tmp<tmp_min_gib or home<home_min_gib else 0
        with log.open('a') as f:f.write(json.dumps({'time':time.time(),'tmp_free_gib':tmp,
                                                   'home_free_gib':home,'controller_pid':pid})+'\n')
        if low>=2:
            (batch/'storage_resource_stop.json').write_text(json.dumps({
                'time':time.time(),'tmp_free_gib':tmp,'home_free_gib':home,
                'controller_pid':pid,'reason':'disk headroom below agreed local batch limit'},indent=2)+'\n')
            os.kill(pid,signal.SIGINT)
            break
        time.sleep(5)

if __name__=='__main__':
    main(Path(sys.argv[1]),int(sys.argv[2]),float(sys.argv[3]),float(sys.argv[4]),float(sys.argv[5]))
