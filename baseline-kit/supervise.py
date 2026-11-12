"""Reactive job watchdog, separate from vLLM. Not a cgroup substitute."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import psutil

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--seconds',type=int,default=1800)
    p.add_argument('--rss-gib',type=float,default=8)
    p.add_argument('--processes',type=int,default=128)
    p.add_argument('command',nargs=argparse.REMAINDER)
    a=p.parse_args(); cmd=a.command
    if cmd and cmd[0]=='--':cmd=cmd[1:]
    if not cmd:p.error('command required after --')
    def limited():
        os.nice(10)
        available=sorted(os.sched_getaffinity(0))
        os.sched_setaffinity(0,available[:2])
    child=subprocess.Popen(cmd,start_new_session=True,preexec_fn=limited)
    tracked={};start=time.monotonic();reason=None;peak=0
    def collect():
        try:procs=[psutil.Process(child.pid)]+psutil.Process(child.pid).children(recursive=True)
        except psutil.NoSuchProcess:procs=[]
        for proc in procs:
            try:tracked[(proc.pid,proc.create_time())]=proc
            except psutil.NoSuchProcess:pass
        live=[]
        for proc in tracked.values():
            try:
                if proc.is_running() and proc.status()!=psutil.STATUS_ZOMBIE:live.append(proc)
            except psutil.NoSuchProcess:pass
        return live
    try:
        while child.poll() is None:
            live=collect();rss=0
            for proc in live:
                try:rss+=proc.memory_info().rss
                except psutil.NoSuchProcess:pass
            peak=max(peak,rss)
            if time.monotonic()-start>a.seconds:reason='job_deadline'
            elif rss>a.rss_gib*1024**3:reason='aggregate_rss_watchdog'
            elif len(live)>a.processes:reason='process_count_watchdog'
            if reason:break
            time.sleep(0.2)
    except KeyboardInterrupt:
        reason='user_interrupt'
    finally:
        live=collect()
        # Kill namespace monitors first through their process groups, then descendants.
        for proc in live:
            try:
                pgid=os.getpgid(proc.pid)
                if pgid!=os.getpgrp():os.killpg(pgid,signal.SIGKILL)
            except (ProcessLookupError,PermissionError):pass
        for proc in live:
            try:proc.kill()
            except psutil.NoSuchProcess:pass
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:child.kill();child.wait()
    print(json.dumps({'watchdog_reason':reason,'peak_rss_gib':peak/1024**3,'returncode':child.returncode}),flush=True)
    return 124 if reason else child.returncode

if __name__=='__main__':sys.exit(main())
