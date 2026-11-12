import unittest
from unittest.mock import patch
from costagent.curated_sft import history_blocks,bounded_encode

class CuratedTests(unittest.TestCase):
    def test_complete_exchange_removal(self):
        messages=[dict(role='system',content='system'),dict(role='user',content='issue'),
                  dict(role='assistant',content='old action'),dict(role='tool',content='old output'),
                  dict(role='assistant',content='recent read'),dict(role='tool',content='recent output')]
        fixed,blocks=history_blocks(messages)
        self.assertEqual(fixed,messages[:2]);self.assertEqual(blocks,[messages[2:4],messages[4:]])
        seen=[]
        def encode(tokenizer,item,limit):
            seen.append(item)
            return ({'input_ids':[1,2],'assistant_mask':[0,1]},None) if len(item['messages'])<=4 else (None,'overlength')
        target=dict(role='assistant',content='important edit')
        with patch('costagent.curated_sft.encode',encode):
            result,dropped,reason=bounded_encode(None,dict(messages=messages,completion=target),4)
        self.assertEqual(dropped,1);self.assertIsNone(reason)
        self.assertEqual(seen[-1]['messages'],messages[:2]+messages[4:])
        self.assertEqual(seen[-1]['completion'],target)

    def test_never_truncates_issue_or_target(self):
        with patch('costagent.curated_sft.encode',return_value=(None,'overlength')):
            result,_,reason=bounded_encode(None,dict(messages=[dict(role='user',content='issue')],completion={}),2)
        self.assertIsNone(result);self.assertEqual(reason,'issue_or_completion_overlength')

    def test_template_mismatch_not_hidden(self):
        with patch('costagent.curated_sft.encode',return_value=(None,'template_prefix')):
            result,_,reason=bounded_encode(None,dict(messages=[dict(role='user',content='issue')],completion={}),2)
        self.assertIsNone(result);self.assertEqual(reason,'template_prefix')
