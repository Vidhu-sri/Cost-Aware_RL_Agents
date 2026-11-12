import json
from pathlib import Path
from types import SimpleNamespace
import torch
from costagent.train import run_pref,run_sft
from costagent import modeling

class Toy(torch.nn.Module):
    def __init__(self):super().__init__();self.theta=torch.nn.Parameter(torch.tensor(0.0))
    def disable_adapter(self):
        import contextlib
        return contextlib.nullcontext()
    def save_pretrained(self,directory,**kwargs):Path(directory).mkdir(parents=True,exist_ok=True)

def test_exact_pref_rescores_and_logs_each_epoch(tmp_path,monkeypatch):
    model=Toy();calls=[]
    def lp(m,ids,mask):
        calls.append((float(m.theta.detach()),torch.is_grad_enabled()))
        # Different responses with differentiable normalized log probabilities.
        return torch.nn.functional.logsigmoid(m.theta if ids[-1]==1 else -m.theta),1
    monkeypatch.setattr(modeling,'turn_logprob',lp)
    cs=[dict(rollout_id=str(i),solved=i==1,cost=.2,all_turns=[dict(input_ids=[0,i],mask=[0,1])]) for i in [1,2]]
    args=SimpleNamespace(adapter=None,kappa=5.,T=.1,lr=.1,accum=1,epochs=2,seed=42,targets='hard',beta=.1,alpha=1.,out=str(tmp_path))
    run_pref(args,model,[dict(task_id='t',candidates=cs)],tmp_path/'metrics.jsonl')
    records=[json.loads(x) for x in (tmp_path/'metrics.jsonl').read_text().splitlines()]
    assert [r['epoch'] for r in records if r.get('event')=='epoch_end']==[1,2]
    assert (tmp_path/'epoch-002/epoch_metrics.json').exists()
    assert any(value!=0 and not grad for value,grad in calls)
    assert float(model.theta)>0

def test_sft_partial_batch_not_underweighted(tmp_path,monkeypatch):
    model=Toy()
    monkeypatch.setattr(modeling,'turn_logprob',lambda m,ids,mask:(torch.nn.functional.logsigmoid(m.theta),1))
    args=SimpleNamespace(seed=0,lr=.1,accum=4,epochs=1,out=str(tmp_path))
    run_sft(args,model,[{'turns':[{'input_ids':[0,1],'mask':[0,1]}]}],tmp_path/'metrics.jsonl')
    assert (tmp_path/'epoch-001/epoch_metrics.json').exists()
    assert float(model.theta)>0
