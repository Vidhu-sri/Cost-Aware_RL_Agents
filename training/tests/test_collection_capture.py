"""Exercise the frozen collector's HTTP logging without a GPU or server."""
import ast
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
import httpx

ROOT = Path(__file__).resolve().parents[2]

class CaptureTest(unittest.TestCase):
    def run_capture(self, streaming):
        tree = ast.parse((ROOT/'artifacts/rebench-new-20x4/collector.py').read_text())
        generate = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'generate')
        fn = next(n for n in generate.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'logged_send')
        fn.body = [ast.Global(names=n.names) if isinstance(n, ast.Nonlocal) else n for n in fn.body]
        module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
        chunks = [b'data: {"choices":[]}\n\n', b'data: [DONE]\n\n']
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                for chunk in chunks: yield chunk
        async def send(*args, **kwargs):
            if streaming: return httpx.Response(200, stream=Stream())
            return httpx.Response(200, content=b''.join(chunks))
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            def append(path, value):
                with path.open('a') as f: f.write(json.dumps(value)+'\n')
            env = dict(httpx=httpx,json=json,request_count=0,original_send=send,out=out,
                       now=lambda:'test',spec={'instance_id':'test'},seed=1,
                       append=append,
                       save=lambda p,x:p.write_text(json.dumps(x)))
            exec(compile(module,'capture','exec'),env)
            async def check():
                request = httpx.Request('POST','http://127.0.0.1:8001/v1/chat/completions',json={'stream':streaming})
                response = await env['logged_send'](None,request)
                body = await response.aread()
                await response.aclose()
                self.assertEqual(body,b''.join(chunks))
                self.assertEqual((out/'model_response_0001.bin').read_bytes(),body)
                self.assertEqual(json.loads((out/'model_requests.jsonl').read_text())['number'],1)
            asyncio.run(check())
    def test_stream(self): self.run_capture(True)
    def test_nonstream(self): self.run_capture(False)

if __name__=='__main__': unittest.main()
