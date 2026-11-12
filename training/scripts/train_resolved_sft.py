#!/usr/bin/env python3
"""LoRA supervised imitation of successful SWE-rebench and Kaggle rollouts."""
import argparse
import json
import time
from pathlib import Path
import random
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from costagent.traces import ROOT, ARTIFACTS, write_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',default=str(ROOT/'gemma-4-31b-it-qat-w4a16-ct'))
    p.add_argument('--output',type=Path,default=ARTIFACTS/'resolved-sft')
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--reuse-dataset',action='store_true',help='Use this output directory’s completed dataset and report')
    p.add_argument('--epochs',type=int,default=1)
    p.add_argument('--max-length',type=int,default=4096)
    p.add_argument('--grad-accum',type=int,default=8)
    p.add_argument('--loss-chunk-size',type=int,default=64)
    p.add_argument('--learning-rate',type=float,default=2e-5)
    p.add_argument('--seed',type=int,default=42)
    args=p.parse_args();args.output=args.output.resolve()
    if not args.output.is_relative_to(ARTIFACTS.resolve()): p.error('Output must be under artifacts/')
    if min(args.epochs,args.grad_accum,args.max_length,args.loss_chunk_size)<1 or args.learning_rate<=0: p.error('Invalid hyperparameters')
    from transformers import AutoTokenizer,set_seed
    from costagent.resolved_sft import build
    tokenizer=AutoTokenizer.from_pretrained(args.model,local_files_only=True)
    dataset=args.output/'train.jsonl'
    if args.reuse_dataset:
        report=json.loads(dataset.with_suffix('.report.json').read_text())
        if report['max_length'] < args.max_length: raise ValueError('Requested length exceeds prepared dataset')
    else:
        report=build(tokenizer,dataset,args.max_length)
    all_rows=[json.loads(line) for line in dataset.open()]
    rows=[r for r in all_rows if len(r['input_ids'])<=args.max_length]
    selection=dict(examples=len(rows),excluded_long=len(all_rows)-len(rows),max_length=args.max_length,
                   tasks=len({(r['source'],r['task_id']) for r in rows}),
                   sources={source:sum(r['source']==source for r in rows) for source in ('swe_rebench','kaggle_dev')},
                   saved_activations='cpu',compute_dtype='bfloat16')
    if not rows: raise ValueError('No examples fit the selected context length')
    write_json(args.output/'selection.json',selection)
    print(json.dumps(selection),flush=True)
    if not report['examples']: raise ValueError('No usable supervised examples')
    if args.dry_run:return
    from costagent.train import require_train_env
    require_train_env()
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('Training cannot start: CUDA is unavailable in this session. Dataset is ready.')
    from transformers import AutoModelForImageTextToText,CompressedTensorsConfig
    from peft import LoraConfig,get_peft_model
    from costagent.sft_loss import backward_example
    set_seed(args.seed)
    # Decompress the local QAT weights for differentiable LoRA training; not NF4
    # re-quantization of a quantized checkpoint. Requires enough aggregate GPU RAM.
    config=json.loads((Path(args.model)/'config.json').read_text())
    kwargs=dict(local_files_only=True,dtype=torch.bfloat16,device_map='auto',attn_implementation='sdpa')
    if config.get('quantization_config'):
        kwargs['quantization_config']=CompressedTensorsConfig(**dict(config['quantization_config'],dequantize=True))
    model=AutoModelForImageTextToText.from_pretrained(args.model,**kwargs)
    if any(str(v) in ('cpu','disk') for v in getattr(model,'hf_device_map',{}).values()):
        raise RuntimeError('Insufficient GPU memory for decompressed 31B training; CPU/disk offload is not supported')
    # Text-only data never invokes these encoders; keep their frozen weights on CPU.
    for name in ('vision_tower','audio_tower','embed_vision','embed_audio'):
        module=getattr(model.model,name,None)
        if module is not None: module.to('cpu')
    model=get_peft_model(model,LoraConfig(r=16,lora_alpha=32,lora_dropout=.05,task_type='CAUSAL_LM',
        target_modules=r'.*language_model.*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)'),autocast_adapter_dtype=False)
    torch.cuda.empty_cache()  # release temporary QAT decompression allocations
    model.config.use_cache=False;model.gradient_checkpointing_enable();model.enable_input_require_grads();model.train()
    optimizer=torch.optim.AdamW([x for x in model.parameters() if x.requires_grad],lr=args.learning_rate,foreach=False)
    step=0;skipped=[];started=time.time()
    print(json.dumps(dict(event='model_ready',allocated_gib=torch.cuda.memory_allocated()/2**30,
                         trainable_parameters=sum(p.numel() for p in model.parameters() if p.requires_grad))),flush=True)
    for epoch in range(args.epochs):
        random.Random(args.seed+epoch).shuffle(rows)
        for offset in range(0,len(rows),args.grad_accum):
            batch=rows[offset:offset+args.grad_accum];optimizer.zero_grad(set_to_none=True)
            tokens=sum(sum(r['assistant_mask'][1:]) for r in batch);loss_sum=0.
            try:
                for micro,row in enumerate(batch):
                    print(json.dumps(dict(event='microbatch',epoch=epoch,batch=offset//args.grad_accum,
                                          micro=micro,length=len(row['input_ids']))),flush=True)
                    loss_sum+=backward_example(model,row,tokens,args.loss_chunk_size)
            except torch.cuda.OutOfMemoryError:
                # Discard the entire accumulation batch: never step partial gradients.
                optimizer.zero_grad(set_to_none=True)
                import gc
                gc.collect();torch.cuda.empty_cache()
                skipped.append(dict(epoch=epoch,offset=offset,tasks=[r['task_id'] for r in batch]))
                print(json.dumps(dict(event='oom_batch_skipped',epoch=epoch,offset=offset)),flush=True)
                write_json(args.output/'oom_skips.json',skipped)
                continue
            torch.nn.utils.clip_grad_norm_(model.parameters(),1.,error_if_nonfinite=True)
            optimizer.step();step+=1
            metrics=dict(step=step,epoch=epoch,loss=loss_sum,tokens=tokens,
                         elapsed_s=time.time()-started,allocated_gib=torch.cuda.memory_allocated()/2**30,
                         peak_gib=torch.cuda.max_memory_allocated()/2**30,skipped_batches=len(skipped))
            print(json.dumps(metrics),flush=True)
            write_json(args.output/'latest_metrics.json',metrics)
            if step==1 or step%5==0:
                model.save_pretrained(args.output/f'checkpoint-{step}',safe_serialization=True)
        if step: model.save_pretrained(args.output/f'epoch-{epoch+1}',safe_serialization=True)
    if not step: raise RuntimeError('No optimizer steps completed; see oom_skips.json')
    model.save_pretrained(args.output/'adapter',safe_serialization=True);tokenizer.save_pretrained(args.output/'adapter')
    write_json(args.output/'complete.json',dict(steps=step,adapter=str(args.output/'adapter'),report=report,selection=selection,skipped_batches=skipped))

if __name__=='__main__':main()
