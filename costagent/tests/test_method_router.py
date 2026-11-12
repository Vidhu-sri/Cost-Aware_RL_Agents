import asyncio
import json
import sys
from pathlib import Path
import httpx
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import method_router as m


def payload(exchanges=(), model='main_lora', tools=True):
    messages=[{'role':'system','content':'original'}]
    for i,(name,args,result) in enumerate(exchanges):
        messages += [{'role':'assistant','tool_calls':[{'id':str(i),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]},
                     {'role':'tool','tool_call_id':str(i),'content':json.dumps(result)}]
    p={'model':model,'messages':messages,'temperature':.2,'seed':42,'max_tokens':16384}
    if tools:p['tools']=[{'type':'function','function':{'name':n}} for n in ['read_file','run_command','edit_file','submit_patch']]
    return p


def command(cmd='ls',out='file\n',code=0,err=''):
    return 'run_command',{'command':cmd},{'stdout':out,'stderr':err,'exit_code':code}


def test_sticky_priority_and_two_switches():
    now=[0];r=m.MethodRouter(clock=lambda:now[0])
    assert r.route(payload())[1]['method']=='rft'
    e=[command('ls'),command('pwd')]
    assert r.route(payload(e))[1]['method']=='dpo'
    e += [command('pytest tests/a.py','failed',1),command('pytest tests/a.py','failed',1)]
    d=r.route(payload(e))[1]
    assert d['reason']=='repeat' and d['method']=='sdpo'
    e += [command('false','different',1)]
    assert r.route(payload(e))[1]['method']=='sdpo'
    assert r.switches==2
    # Compaction cannot reset state.
    assert r.route(payload([command('new')]))[1]['method']=='sdpo'


def test_repeat_exact_output_and_consecutive():
    for e in ([command(),command(out='different')], [command(),('read_file',{},{}),command()],
              [command(),command(err='different')]):
        assert m.MethodRouter().route(payload(e))[1]['method']=='dpo'
    assert m.MethodRouter().route(payload([command(),command()]))[1]['reason']=='repeat'
    assert m.MethodRouter().route(payload([('run_command',{'command':'ls'},{}),('run_command',{'command':'ls'},{})]))[1]['method']=='dpo'


@pytest.mark.parametrize('cmd', ['pytest tests/test_x.py','python -m pytest tests/x.py','python3.13 -m unittest tests.x','cd /workspace && pytest tests/x.py','tox -e py'])
def test_test_success(cmd):
    assert m.MethodRouter().route(payload([command(cmd)]))[1]['reason']=='successful_test'
    assert m.MethodRouter().route(payload([command(cmd,code=1)]))[1]['method']=='rft'


@pytest.mark.parametrize('cmd', ['echo pytest','grep pytest x','pytest x | tee log','pytest x; true','pytest x || true','python -c "print(\'pytest\')"'])
def test_not_test_success(cmd):
    assert not m.recognized_test(cmd)


def test_clock_and_conflicts():
    now=[0];r=m.MethodRouter(clock=lambda:now[0]);r.start()
    now[0]=239.999
    assert r.route(payload())[1]['method']=='rft'
    now[0]=240
    d=r.route(payload([command('pytest x'),command('pytest x')]))[1]
    assert d['reason']=='budget_240s' and all(d['triggers'].values())


def test_retry_and_subagent_and_no_tools():
    r=m.MethodRouter();p=payload(model='tool_lora')
    assert r.route(p)==(p,None) and r.started is None
    p=payload(tools=False);body,d=r.route(p)
    assert 'tools' not in body and body['messages']==p['messages']
    assert r.route(p)[1]['retry_same_request']
    assert r.phase.turn==1


def test_http_switches_and_capture(tmp_path,monkeypatch):
    old=httpx.AsyncClient.send
    router=m.install(tmp_path)
    routed=httpx.AsyncClient.send
    httpx.AsyncClient.send=old
    monkeypatch.setattr(httpx.AsyncClient,'send',routed)
    seen=[]
    def handle(req):
        assert int(req.headers['content-length'])==len(req.content)
        seen.append(json.loads(req.content))
        return httpx.Response(200,json={'choices':[{'message':{'content':'ok'}}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as c:
            for p in [payload(),payload([command('ls'),command('pwd')]),payload([command('ls'),command('pwd'),command('pytest x')]),payload(model='tool_lora')]:
                await c.post('http://127.0.0.1:8001/v1/chat/completions',json=p)
    asyncio.run(run())
    assert [p['model'] for p in seen]==['rft_lora','dpo_lora','sdpo_lora','tool_lora']
    assert all(p['temperature']==.2 and p['seed']==42 for p in seen)
    assert len((tmp_path/'router_decisions.jsonl').read_text().splitlines())==3
    assert router.switches==2
    assert seen[0]['max_tokens']==2048 # phase controls remain active
