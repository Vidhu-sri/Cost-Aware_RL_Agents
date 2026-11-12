import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
import psutil
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from container_monitor import namespace_rss, SamplingHealth

class Process:
    def __init__(self, pid, value):self.pid,self.value=pid,value
    def memory_info(self):
        if isinstance(self.value,Exception):raise self.value
        return SimpleNamespace(rss=self.value)

def test_exit_between_listing_and_memory_read():
    processes=[Process(1,100),Process(2,psutil.NoSuchProcess(2)),Process(3,300)]
    result=namespace_rss(1,lambda attrs:processes,lambda path:'pid:[42]')
    assert result=={'observed_pid_namespace_rss_bytes':400,'pid_namespace_processes':2,'vanished_during_sample':1}

def test_access_denied_is_not_silently_undercounted():
    with pytest.raises(psutil.AccessDenied):
        namespace_rss(1,lambda attrs:[Process(1,psutil.AccessDenied(1))],lambda path:'pid:[42]')

def test_other_namespaces_excluded():
    assert namespace_rss(1,lambda attrs:[Process(1,100),Process(2,999)],lambda path: 'a' if '/1/' in path else 'b')['observed_pid_namespace_rss_bytes']==100

def test_persistent_loss_stops_but_transient_recovers():
    now=[0];h=SamplingHealth(clock=lambda:now[0]);exc=OSError('failure')
    assert h.failure('x',exc)['monitor_gap_seconds']==0
    now[0]=4;h.failure('x',exc);h.success('x')
    now[0]=10;h.failure('x',exc)
    now[0]=15
    with pytest.raises(RuntimeError,match='5.0s'):h.failure('x',exc)

def test_empty_live_namespace_is_not_zero_rss():
    with pytest.raises(RuntimeError):namespace_rss(1,lambda attrs:[],lambda path:'a')
