"""Stop only a server launched by this package, checking PID creation time."""
import json,os,signal
from pathlib import Path
import psutil
p=Path('logs/owned-server.json')
if p.exists():
 d=json.loads(p.read_text())
 try:
  proc=psutil.Process(d['pid'])
  if proc.create_time()==d['created']:
   os.killpg(d['pid'],signal.SIGTERM)
   try:proc.wait(timeout=30)
   except psutil.TimeoutExpired:os.killpg(d['pid'],signal.SIGKILL)
 except psutil.NoSuchProcess:pass
 p.unlink()
