import unittest
from unittest.mock import patch
from costagent.archive_dpo import select_pairs

class ArchivePairTests(unittest.TestCase):
    def row(self,id,solved,calls,**kw):
        return dict(id=id,solved=solved,calls=calls,timeout=not solved,task_id='x',prompt_sha256='p',environment_sha256='e',**kw)
    def test_compatible_competence_and_efficiency(self):
        rows=[self.row('a',True,10),self.row('b',True,20),self.row('c',False,15)]
        pairs=select_pairs(rows)
        self.assertEqual(len(pairs),3)
        self.assertIn(dict(task_id='x',chosen='a',rejected='b',type='efficiency_calls_proxy',shared_prefix_sha256='p',delta_calls=10),pairs)
    def test_never_cross_tasks_prompts_or_environments(self):
        for field in ('task_id','prompt_sha256','environment_sha256'):
            a=self.row('a',True,10);b=self.row('b',False,20);b[field]='different'
            self.assertEqual(select_pairs([a,b]),[])
    def test_two_failures_and_tiny_efficiency_gaps_excluded(self):
        self.assertEqual(select_pairs([self.row('a',False,10),self.row('b',False,20)]),[])
        self.assertEqual(select_pairs([self.row('a',True,19),self.row('b',True,20)]),[])

class ArchiveGradientTests(unittest.TestCase):
    def test_exact_two_pass_gradient(self):
        import torch
        from costagent.archive_dpo_train import pair_step
        class Model(torch.nn.Module):
            def __init__(self):super().__init__();self.w=torch.nn.Parameter(torch.tensor(.3,dtype=torch.float64))
            def set_adapter(self,name):self.adapter=name
        model=Model()
        chosen=dict(id='c',turns=[dict(x=2.,assistant_mask=[0,1,1]),dict(x=1.,assistant_mask=[0,1])])
        rejected=dict(id='r',turns=[dict(x=-1.,assistant_mask=[0,1])])
        refs={'c':-2.,'r':-1.}
        def score(m,t):return torch.nn.functional.logsigmoid(m.w*t['x'])*sum(t['assistant_mask'][1:])
        for alpha in (0.,1.):
            model.w.grad=None
            with patch('costagent.archive_dpo_train.score_turn',score):
                metrics=pair_step(model,chosen,rejected,refs,alpha=alpha)
            actual=model.w.grad.clone();model.w.grad=None
            c=sum(score(model,t) for t in chosen['turns']);r=sum(score(model,t) for t in rejected['turns'])
            loss=-torch.nn.functional.logsigmoid(.1*(c-r-refs['c']+refs['r']))-alpha*c/3
            loss.backward()
            torch.testing.assert_close(actual,model.w.grad)
            self.assertAlmostEqual(metrics['loss'],float(loss.detach()))
