"""Capture local model request/response bytes, including streamed SSE."""
import json
from pathlib import Path
import httpx

def install(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    original=httpx.AsyncClient.send
    counter=0
    async def send(client,request,*args,**kwargs):
        nonlocal counter
        capture=request.url.host=='127.0.0.1' and request.url.port==8001 and '/chat/completions' in request.url.path
        if capture:
            counter+=1;number=counter
            with (out/'model_requests.jsonl').open('a') as f:f.write(json.dumps({'number':number,'body':json.loads(request.content)})+'\n')
        response=await original(client,request,*args,**kwargs)
        if capture:
            path=out/f'model_response_{number:04d}.bin'
            if response.is_stream_consumed:path.write_bytes(response.content)
            else:
                stream=response.stream
                class Capture(httpx.AsyncByteStream):
                    async def __aiter__(self):
                        with path.open('wb') as f:
                            async for chunk in stream:
                                f.write(chunk);f.flush();yield chunk
                    async def aclose(self):await stream.aclose()
                response.stream=Capture()
        return response
    httpx.AsyncClient.send=send
