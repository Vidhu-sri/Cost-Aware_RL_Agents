#!/usr/bin/env python3
"""Run in the vLLM serving environment after releasing training GPU memory."""
import argparse
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',required=True)
    p.add_argument('--adapter',type=Path,required=True);p.add_argument('--dry-run',action='store_true');a=p.parse_args()
    for name in ('adapter_config.json','adapter_model.safetensors'):
        if not (a.adapter/name).is_file(): p.error(f'Missing {name}')
    if a.dry_run: print('Adapter files exist; GPU transfer has not been tested');return
    from vllm import LLM,SamplingParams
    from vllm.lora.request import LoRARequest
    llm=LLM(model=a.model,enable_lora=True,max_lora_rank=128)
    output=llm.chat([{'role':'user','content':'Reply with OK.'}],SamplingParams(max_tokens=32,temperature=0),
                    lora_request=LoRARequest('trained',1,str(a.adapter.resolve())))
    if not output or not output[0].outputs or not output[0].outputs[0].token_ids:
        raise RuntimeError('Adapter generated no tokens')
    print(output[0].outputs[0].text)
if __name__=='__main__':main()
