import unittest
from costagent.compare_runs import METRICS, compare, metrics

def row(task='a',seed=1,solved=1,cost=10):
    r={k:cost for k in METRICS}
    r.update(task_id=task,seed=seed,solve_rate=solved,base_commit='abc',configuration={'budget':100})
    return r

class CompareTest(unittest.TestCase):
    def test_paired_task_weighting(self):
        a=[row('a',1),row('a',2),row('b',1)]
        b=[row('a',1,cost=8),row('a',2,cost=8),row('b',1,cost=4)]
        r=compare(a,b,100)['cohorts']['all_graded_pairs']['generated_tokens']
        self.assertEqual(r['delta'],-4)
        self.assertEqual(r['change_percent'],-40)
        self.assertEqual(r['tasks'],2)
    def test_cheaper_failure_and_unknown(self):
        a=[row('a'),row('b'),row('c')]
        b=[row('a',solved=0,cost=1),row('b',cost=8),row('c',solved=None,cost=0)]
        r=compare(a,b,100)
        self.assertEqual(r['known_outcome_pairs'],2)
        self.assertEqual(r['cohorts']['all_graded_pairs']['solve_rate']['delta'],-.5)
        self.assertEqual(r['cohorts']['both_solved_pairs']['generated_tokens']['delta'],-2)
    def test_reject_duplicates_unmatched_and_budgets(self):
        with self.assertRaises(ValueError):compare([row(),row()],[row()],100)
        with self.assertRaises(ValueError):compare([row()],[row(seed=2)],100)
        other=row();other['configuration']={'budget':50}
        with self.assertRaises(ValueError):compare([row()],[other],100)
        self.assertEqual(len(compare([row()],[other],100,exploratory=True)['configuration_mismatches']),1)
    def test_metric_missing_and_file_counts(self):
        r={'steps':[{'tool_calls':[
            {'function_name':'read_file','arguments':{'filepath':'a/../b.py'}},
            {'function_name':'read_file','arguments':{'filepath':'b.py'}},
            {'function_name':'run_command','arguments':{'command':'cat hidden.py'}},
            {'function_name':'submit_patch','arguments':{}}]}],
            'final_metrics':{'total_completion_tokens':42},'task_id':'x','seed':1,
            'rollout_id':'/nonexistent','base_commit':'abc','solved':True,'wall_s':12}
        m=metrics(r)
        self.assertEqual(m['unique_explicit_files_read'],1)
        self.assertEqual(m['read_file_calls'],2)
        self.assertEqual(m['tool_calls'],4)
        self.assertEqual(m['charged_tool_calls'],3)
        self.assertIsNone(m['prompt_tokens'])
        self.assertIsNone(m['observation_text_tokens'])
        self.assertEqual(m['agent_wall_seconds'],12)

if __name__=='__main__':unittest.main()
