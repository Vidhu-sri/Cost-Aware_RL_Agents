import pytest
import torch
from costagent.sdpo import contrast_targets,feedback,aligned_views

def test_gate_worst_case():
    w=contrast_targets(torch.tensor([.5,0.]),[-1.,1.])
    assert w[0]>w[1]
    with pytest.raises(ValueError):contrast_targets(torch.tensor([.5,0.]),[-1.,1.],k2=2.5)

def test_all_failure_uses_teacher_contrast():
    w=contrast_targets(torch.zeros(2),[-.5,.5]);assert w[1]>w[0]

def test_zero_contrast_recovers_r2_targets():
    r=torch.tensor([.7,.9]);assert torch.allclose(contrast_targets(r,[1.,-1.],k2=0),torch.softmax(r/.1,0))

def test_feedback_cases():
    def row(solved,cost,identity):return dict(solved=solved,cost=cost,rollout_id=identity,turns=[])
    assert feedback([row(True,.1,'a'),row(False,.8,'b')])[2]=='mixed'
    assert feedback([row(True,.1,'a'),row(True,.8,'b')])[2]=='all_success'
    with pytest.raises(ValueError):feedback([row(False,.1,'a'),row(False,.8,'b')])
    assert feedback([row(False,.1,'a'),row(False,.8,'b')],gold='TRAINING SECRET')[2]=='all_failure'

def test_teacher_feedback_absent_from_student_view():
    class Tokenizer:
        def apply_chat_template(self,msgs,tools,tokenize,add_generation_prompt,**kwargs):
            text=''.join(m['role']+':'+str(m['content'])+';' for m in msgs)
            return text+('assistant:' if add_generation_prompt else '')
        def __call__(self,text,**kwargs):return {'input_ids':list(text.encode())}
    row=dict(system='system',first_user='issue',turns=[dict(kind='assistant',text='answer',calls=[],results=[])])
    views=aligned_views(Tokenizer(),row,'GOLD_SECRET','BAD_FEEDBACK',1000)
    assert views is not None
    assert b'GOLD_SECRET' not in bytes(views[0][0]['input_ids'])
    assert b'GOLD_SECRET' in bytes(views[1][0]['input_ids'])
    target=lambda e:[v for v,m in zip(e['input_ids'],e['mask']) if m]
    assert target(views[0][0])==target(views[1][0])==target(views[2][0])

def test_merged_assistant_continuation():
    class Tokenizer:
        def apply_chat_template(self,msgs,tools,tokenize,add_generation_prompt,**kwargs):
            text='';previous=None
            for m in msgs:
                text+=('' if previous==m['role']=='assistant' else m['role']+':')+m['content']+';'
                previous=m['role']
            return text+('assistant:' if add_generation_prompt else '')
        def __call__(self,text,**kwargs):return {'input_ids':list(text.encode())}
    row=dict(system='system',first_user='issue',turns=[dict(kind='assistant',text=s,calls=[],results=[]) for s in ['first','second']])
    views=aligned_views(Tokenizer(),row,'GOOD','BAD',1000)
    assert views is not None and len(views[0])==2
    for v in views:
        e=v[1]
        assert bytes(t for t,m in zip(e['input_ids'],e['mask']) if m)==b'second;'


def test_teacher_scoring_cache_and_clean_student_data(tmp_path,monkeypatch):
    import argparse,json
    from costagent import sdpo,modeling
    teacher=tmp_path/'teacher';teacher.mkdir()
    (teacher/'adapter_model.safetensors').write_bytes(b'test weights')
    (teacher/'adapter_config.json').write_text('{}')
    modeldir=tmp_path/'model';modeldir.mkdir();(modeldir/'config.json').write_text('{}')
    clean={'input_ids':[1,2],'mask':[0,1]}
    candidate=dict(rollout_id='r',all_turns=[clean],teacher_plus=[{'lp':[3.,-4.]}],teacher_minus=[{'lp':[0.,0.]}])
    inputs=tmp_path/'inputs.pt'
    torch.save([dict(task_id='t',compatibility_sha256='h',candidates=[candidate])],inputs)
    class Model:
        def requires_grad_(self,x):assert not x
        def eval(self):pass
    calls=[]
    monkeypatch.setattr(torch.cuda,'is_available',lambda:True)
    monkeypatch.setattr(modeling,'load',lambda *a,**kw:Model())
    def score_tokens(m,e):calls.append(e);return torch.tensor(e['lp'])
    monkeypatch.setattr(sdpo,'token_scores',score_tokens)
    args=argparse.Namespace(inputs=str(inputs),teacher=str(teacher),model=str(modeldir),output=str(tmp_path/'output'),clip=1.,dry_run=False)
    sdpo.score(args)
    groups=torch.load(tmp_path/'output/student_groups.pt',weights_only=False)
    c=groups[0]['candidates'][0]
    assert c['teacher_contrast']==0. # per-token clipping, then mean
    assert c['all_turns']==[clean] and 'teacher_plus' not in c and 'teacher_minus' not in c
    assert groups[0]['teacher_clip']==1.
    sdpo.score(args)
    assert len(calls)==2 # second run reuses cache
    (teacher/'adapter_model.safetensors').write_bytes(b'changed weights')
    with pytest.raises(ValueError,match='signature mismatch'):sdpo.score(args)
