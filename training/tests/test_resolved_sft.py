import unittest
from costagent.resolved_sft import demonstrations,encode

class ResolvedSFTTests(unittest.TestCase):
    def test_failures_excluded(self):
        self.assertEqual(list(demonstrations(dict(solved=False),[])),[])

    def test_tool_result_not_target(self):
        row=dict(solved=True,requests=[],steps=[dict(source='user',message='fix'),
            dict(source='agent',message='think',tool_calls=[dict(tool_call_id='c',function_name='read_file',arguments={})],observation=dict(content='file text')),
            dict(source='agent',message='done')])
        rows=list(demonstrations(row,[]))
        self.assertEqual(rows[0]['completion']['reasoning'],'think')
        self.assertNotIn('file text',str(rows[0]['completion']))
        self.assertEqual(rows[1]['messages'][-1]['role'],'tool')

    def test_missing_observation_stops_prefix(self):
        row=dict(solved=True,requests=[],steps=[dict(source='user',message='fix'),
            dict(source='agent',tool_calls=[dict(tool_call_id='c',function_name='read_file',arguments={})]),
            dict(source='agent',message='later')])
        self.assertEqual(len(list(demonstrations(row,[]))),1)

    def test_request_deduplication(self):
        body=dict(messages=[dict(role='user',content='fix'),dict(role='assistant',content='done')])
        row=dict(solved=True,requests=[dict(body=body),dict(body=body)])
        self.assertEqual(len(list(demonstrations(row,[]))),1)

    def test_mask_and_length(self):
        class Tokenizer:
            def apply_chat_template(self,messages,add_generation_prompt,**kwargs):
                return 'prompt' if add_generation_prompt else 'prompttarget'
            def encode(self,text,**kwargs):return list(text.encode())
        item=dict(messages=[],completion={},tools=[])
        encoded,reason=encode(Tokenizer(),item,20)
        self.assertIsNone(reason)
        self.assertEqual(encoded['assistant_mask'],[0]*6+[1]*6)
        self.assertEqual(encode(Tokenizer(),item,8),(None,'overlength'))
