import pytest
from costagent.traces import parse_trace

def test_direct_observation():
    p=parse_trace({'steps':[{'source':'agent','tool_calls':[{'tool_call_id':'x','function_name':'read_file','arguments':{'filepath':'a.py'}}],'observation':{'content':'source code'}}]})
    assert p['turns'][0]['results']==[{'id':'x','content':'source code'}]

def test_ambiguous_observation_rejected():
    calls=[{'tool_call_id':str(i),'function_name':'read_file','arguments':{}} for i in range(2)]
    with pytest.raises(ValueError):parse_trace({'steps':[{'source':'agent','tool_calls':calls,'observation':{'content':'unknown mapping'}}]})
