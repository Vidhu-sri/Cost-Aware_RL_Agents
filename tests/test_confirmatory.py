import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from confirmatory import retry_allowed,arm_env
from analyze_confirmatory import mcnemar,paired,summary
class ConfirmatoryTests(unittest.TestCase):
 def test_terminal_blocks_replacement(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'infrastructure_failure.json').write_text('{"kind":"vllm_crash"}')
   self.assertTrue(retry_allowed(p))
   for f in ['outcome.json','terminal_unknown.json']:
    (p/f).write_text('{}');self.assertFalse(retry_allowed(p));(p/f).unlink()
 def test_noninfra_not_retried(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'infrastructure_failure.json').write_text('{"kind":"timeout"}')
   self.assertFalse(retry_allowed(p))
 def test_arms_no_leakage(self):
  import os
  from unittest.mock import patch
  with patch.dict(os.environ,{'MAIN_ADAPTER':'wrong','COSTAGENT_ROUTER':'method-v1'}):
   self.assertNotIn('MAIN_ADAPTER',arm_env('A0'));self.assertNotIn('COSTAGENT_ROUTER',arm_env('A0'))
   self.assertEqual(arm_env('router')['COSTAGENT_ROUTER'],'method-v1')
 def test_order(self):
  p=json.loads((ROOT/'prereg/frozen.json').read_text());self.assertEqual(len(p['tasks']),84)
  self.assertEqual(len(set(p['tasks'])),84)
  self.assertTrue(all(set(r['arms'])=={'A0','router'} for r in p['order']))
  self.assertFalse(set(p['tasks'])&set(p['pilot_excluded']+p['training_excluded']))
 def test_mcnemar_direction(self):
  r=mcnemar([False]*4,[True]*4);self.assertEqual(r['router_only'],4);self.assertEqual(r['baseline_only'],0);self.assertEqual(r['exact_two_sided_p'],.125)
 def test_unknown_exclusion_and_zero_ratios(self):
  rows=[{'task_id':str(i),'arm':a,'resolved':None if i==0 else False,'calls':2,'tokens':3} for i in range(3) for a in ['A0','router']]
  r=paired(rows);self.assertEqual(r['paired_n'],2);self.assertEqual(r['excluded_ids'],['0']);self.assertIsNone(r['calls']['ci95']);self.assertIsNone(r['calls']['difference'])
 def test_bootstrap_paired_identity(self):
  rows=[{'task_id':str(i),'arm':a,'resolved':True,'calls':i+1,'tokens':4*(i+1)} for i in range(8) for a in ['A0','router']]
  r=paired(rows);self.assertEqual(r['tokens']['difference'],0);self.assertEqual(r['calls']['ci95'],[0,0])
if __name__=='__main__':unittest.main()
