import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from resource_retry import gpu_memory_failure

def test_kv_cache_memory_failure_retries():
    assert gpu_memory_failure('ValueError: 6.42 GiB KV cache is needed, which is larger than the available KV cache memory (5.39 GiB)')

def test_unrelated_startup_error_is_not_hidden():
    assert not gpu_memory_failure('RuntimeError: unknown model architecture')
    assert not gpu_memory_failure('Engine core initialization failed')

def test_cuda_memory_failure_retries():
    assert gpu_memory_failure('torch.OutOfMemoryError: CUDA out of memory')


def test_swe_manifest_row_accepts_outcome_identity_fields():
    import ast
    source=(Path(__file__).resolve().parents[1]/'scripts/collect_temperatures.py').read_text()
    tree=ast.parse(source)
    node=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='row' for t in n.targets))
    context=dict(outcome={'task_id':'task','seed':17,'resolved':False},tid='task',task={'source':'swe_rebench'},temp=.2,seed=17,out=Path('/tmp/result'),trace=Path('/tmp/result/trace.json'))
    row=eval(compile(ast.Expression(node),'<manifest row>','eval'),context)
    assert row['task_id']=='task' and row['seed']==17 and row['resolved'] is False
    assert row['trace_path']=='/tmp/result/trace.json'
