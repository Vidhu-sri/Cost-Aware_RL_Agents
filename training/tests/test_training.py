import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from costagent import datasets,graphs,grpo,pairs,rewards,traces
from train_grpo import prepare


def turn():
    return dict(input_ids=[1,2,3,4],assistant_mask=[0,0,1,1],template_roundtrip=True,
                request_sha256='a'*64,response_sha256='b'*64,template_sha256='c'*64)


class RewardTests(unittest.TestCase):
    def test_worked_examples(self):
        self.assertEqual(rewards.rewards(True,.2,[0])['R2'],.9)
        self.assertEqual(rewards.rewards(True,.6,[0])['R2'],.7)
        self.assertEqual(rewards.rewards(False,.1,[0])['R2'],0)
        self.assertEqual(rewards.rewards(False,.1,[0])['R2_ungated'],-.05)
        self.assertEqual(rewards.rewards(False,.9,[0])['R2_ungated'],-.45)
        r=rewards.rewards(True,.2,[0,.25,1])
        self.assertAlmostEqual(r['R3_traj'],1.)
        self.assertEqual(r['R3_rtg'],[1.,.9750000000000001])
    def test_invalid_potential_and_weights(self):
        with self.assertRaises(ValueError): rewards.rewards(True,.2,[0,1,.5])
        with self.assertRaises(ValueError): rewards.rewards(True,.2,[0],eta=.5)
        with self.assertRaises(ValueError): rewards.cost({'calls':1},{'calls':1},{'calls':2})
    def test_cost_and_fallback(self):
        counts={k:2 for k in rewards.WEIGHTS};baseline={k:1 for k in counts}
        self.assertAlmostEqual(rewards.cost(counts,baseline),1)
        global_,tasks=rewards.calibrate([dict(source='swe_rebench',policy='base',task_id='x',solved=True,counts=counts)])
        self.assertEqual(tasks.get('missing',global_),counts)
        with self.assertRaises(ValueError): rewards.calibrate([dict(source='kaggle_dev')])


class TraceTests(unittest.TestCase):
    def test_atif_and_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'trace.json'
            p.write_text(json.dumps({'schema_version':'ATIF-v1.7','steps':[{'source':'agent','tool_calls':[{'arguments':{}}]}]}))
            self.assertEqual(len(traces.load_trace(p)['steps']),1)
            p.write_text('{}')
            with self.assertRaises(ValueError): traces.load_trace(p)
    def test_no_eval_leakage(self):
        with self.assertRaises(ValueError): traces.assert_train([dict(source='kaggle_dev',task_id='x')],{'x'})
    def test_output_guard(self):
        with self.assertRaises(ValueError): traces.write_json('/tmp/not-artifacts.json',{})


class DataTests(unittest.TestCase):
    def test_masks_and_provenance(self):
        datasets.validate_turn(turn())
        for change in [dict(assistant_mask=[1,1,1,1]),dict(assistant_mask=[0]*4),
                       dict(template_roundtrip=False),dict(response_sha256=''),dict(input_ids=[1])]:
            with self.assertRaises(ValueError): datasets.validate_turn(dict(turn(),**change))


class PairTests(unittest.TestCase):
    def row(self,ident,solved,cost):
        return dict(source='swe_rebench',task_id='x',rollout_id=ident,sampling_policy='base',solved=solved,cost=cost,
                    messages=[{'role':'user','content':'issue'},{'role':'assistant','content':ident}])
    def test_pairs_and_balance(self):
        result=pairs.build_pairs([self.row('a',True,.1),self.row('b',True,.5),self.row('c',False,.3)])
        self.assertEqual({r['type'] for r in result},{'efficiency','competence'})
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]['chosen'],[{'role':'assistant','content':'a'}])
        self.assertEqual(result[0]['prompt'],[{'role':'user','content':'issue'}])
    def test_singleton_unknown_and_leak(self):
        self.assertEqual(pairs.build_pairs([self.row('a',True,.1)]),[])
        self.assertEqual(pairs.build_pairs([self.row('a',None,.1),self.row('b',True,.5)]),[])
        with self.assertRaises(ValueError): pairs.build_pairs([dict(self.row('a',True,.1),source='kaggle_dev')])


class GraphTests(unittest.TestCase):
    def test_ast_hops_and_ranges(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'auth.py';p.write_text('def auth():\n    return token()\n\ndef token():\n    return 1\n')
            g=graphs.build_graph(temp)
            scores=graphs.relevance(g,{'auth.token'})
            self.assertEqual(scores['auth.token'],1.)
            self.assertEqual(scores['auth.auth'],.5)
            self.assertIn('auth.auth',graphs.range_symbols(g,'auth.py',1,2))
            self.assertEqual(graphs.resolve(g,'TOKEN'),['auth.token'])
            self.assertEqual(graphs.potentials([['unknown'],['auth.auth'],['auth.token']],scores),[0,0,.5,1])
    def test_distance_two(self):
        g=dict(nodes=[{'id':v} for v in 'abc'],edges=[dict(source='a',target='b'),dict(source='b',target='c')])
        self.assertEqual(graphs.relevance(g,{'a'}),{'a':1,'b':.5,'c':.25})
    @unittest.skipUnless(importlib.util.find_spec('unidiff'),'unidiff requires envs/train')
    def test_gold_patch(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/'a.py').write_text('def f():\n    return 1\n')
            patch='--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 2\n'
            self.assertEqual(graphs.gold_symbols(patch,graphs.build_graph(temp)),{'a','a.f'})


class GRPOTests(unittest.TestCase):
    def test_advantages(self):
        self.assertIsNone(grpo.advantages([1,1]))
        self.assertAlmostEqual(grpo.advantages([0,1])[0],-1,places=5)
        with self.assertRaises(ValueError): grpo.advantages([1])
        self.assertEqual(grpo.step_advantages([[0],[0,1]]),[[None],[None,None]])
    def test_groups(self):
        rows=[dict(task_id='x',group_id='g',sampling_policy_sha256='p',solved=v,cost=.2,
                   turns=[turn()],potentials=[0,1]) for v in (False,True)]
        prepared,dropped=prepare(rows,'R2',2,'p')
        self.assertEqual(len(prepared),2);self.assertEqual(dropped['zero_variance'],0)
        self.assertEqual(prepare(rows,'R2',4,'p')[1]['incomplete'],1)
        with self.assertRaises(ValueError): prepare(rows,'R2',2,'wrong')
    def test_loss_masks_and_gradient(self):
        import torch
        current=torch.tensor([-.5,-1.],requires_grad=True)
        old=torch.tensor([-.5,-1.]);ref=old.clone();mask=torch.tensor([False,True])
        loss,metrics=grpo.clipped_loss(current,old,ref,1.,mask)
        self.assertEqual(float(loss.detach()),-1.)
        loss.backward();self.assertEqual(float(current.grad[0]),0.)
        self.assertEqual(metrics['kl'],0.)


class RuntimeTests(unittest.TestCase):
    def test_adapter_fingerprint(self):
        from costagent.train import fingerprint
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'adapter_config.json').write_text('{}')
            (root/'adapter_model.safetensors').write_bytes(b'one')
            first=fingerprint(root)
            self.assertEqual(first,fingerprint(root))
            (root/'adapter_model.safetensors').write_bytes(b'two')
            self.assertNotEqual(first,fingerprint(root))
    def test_train_env_guard(self):
        from costagent.train import require_train_env
        from unittest.mock import patch
        with patch('sys.prefix','/tmp/not-train'):
            with self.assertRaises(RuntimeError): require_train_env()




class TrainingRegressionTests(unittest.TestCase):
    def test_task_batches(self):
        from train_grpo import sample_tasks
        pool=list(range(100))
        self.assertEqual(sample_tasks(pool,4,42,3),sample_tasks(pool,4,42,3))
        self.assertNotEqual(sample_tasks(pool,4,42,3),sample_tasks(pool,4,42,4))

    def test_partial_groups_and_alignment(self):
        rows=[dict(task_id='x',group_id='g',sampling_policy_sha256='p',solved=bool(i%2),
                   cost=.2,turns=[turn()],potentials=[0,1]) for i in range(4)]
        prepared,counts=prepare(rows,'R2',16,'p')
        self.assertEqual(len(prepared),4)
        self.assertEqual(counts['partial_kept'],1)
        rows[0]['potentials']=[0,0,1]
        with self.assertRaisesRegex(ValueError,'alignment'): prepare(rows,'R3_rtg',4,'p')

    def test_streamed_dpo_matches_full_gradient(self):
        import torch
        from unittest.mock import patch
        from train_dpo import dpo_pair_step,reference_scores
        class Model(torch.nn.Module):
            def __init__(self):
                super().__init__();self.weight=torch.nn.Parameter(torch.tensor(.4,dtype=torch.float64))
            def set_adapter(self,name): self.adapter=name
        model=Model()
        def lp(model,t):
            w=model.weight if model.adapter=='policy' else model.weight.detach()*0+.2
            return torch.nn.functional.logsigmoid(w*torch.tensor(t['x'])),torch.tensor(t['assistant_mask'][1:],dtype=torch.bool)
        pair=dict(chosen_turns=[dict(x=[1.,2.,3.],assistant_mask=[0,0,1,1])]*3,
                  rejected_turns=[dict(x=[-2.,1.,-1.],assistant_mask=[0,1,0,1])]*2)
        with patch('costagent.train.logps',lp):
            ref=reference_scores(model,pair)
            for alpha in (0.,1.):
                model.weight.grad=None
                value=dpo_pair_step(model,pair,ref,alpha=alpha,scale=.25)
                streamed=model.weight.grad.clone();model.weight.grad=None
                totals={side:sum(lp(model,t)[0][lp(model,t)[1]].sum() for t in pair[side+'_turns']) for side in ('chosen','rejected')}
                loss=-torch.nn.functional.logsigmoid(.1*(totals['chosen']-totals['rejected']-ref['chosen']+ref['rejected']))-alpha*totals['chosen']/6
                (loss*.25).backward()
                self.assertAlmostEqual(value,float(loss.detach()),places=6)
                torch.testing.assert_close(streamed,model.weight.grad)

    def test_grpo_multiple_optimizer_steps(self):
        import torch
        from unittest.mock import patch
        from train_grpo import update_policy
        class Model(torch.nn.Module):
            def __init__(self):
                super().__init__();self.weight=torch.nn.Parameter(torch.tensor(-1.))
            def set_adapter(self,name): self.adapter=name
        model=Model()
        def lp(model,t):
            w=model.weight if model.adapter=='policy' else model.weight.detach()*0-1
            return w.expand(3).clone(),torch.tensor([False,True,True])
        with patch('costagent.train.logps',lp):
            metrics,steps=update_policy(model,[(turn(),1.)]*5,2,2,.2,42)
        self.assertEqual(steps,6)
        self.assertTrue(any(m['clip_fraction']>0 for m in metrics))
        self.assertNotEqual(float(model.weight.detach()),-1.)

if __name__=='__main__':unittest.main()
