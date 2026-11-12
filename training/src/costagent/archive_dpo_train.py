"""Memory-bounded, exact two-pass DPO gradient on reconstructed action trajectories."""


def score_turn(model,turn):
    import torch
    from .sft_loss import gemma_assistant_loss
    device=model.get_input_embeddings().weight.device
    ids=torch.tensor([turn['input_ids']],device=device)
    mask=torch.tensor([turn['assistant_mask']],device=device,dtype=torch.bool)
    count=sum(turn['assistant_mask'][1:])
    with torch.autograd.graph.save_on_cpu(pin_memory=True):
        with torch.autocast(device_type=device.type,dtype=torch.bfloat16):
            score=-gemma_assistant_loss(model,ids,mask,64)*count
    return score


def trajectory_score(model,row,progress=None):
    import torch
    total=0.
    with torch.no_grad():
        for i,turn in enumerate(row['turns']):
            total+=float(score_turn(model,turn))
            if progress:progress(dict(event='scored_turn',rollout=row['id'],turn=i+1,total_turns=len(row['turns'])))
    return total


def pair_step(model,chosen,rejected,reference,beta=.1,alpha=1.,progress=None):
    import torch
    model.set_adapter('policy')
    c=trajectory_score(model,chosen,progress);r=trajectory_score(model,rejected,progress)
    n=sum(sum(t['assistant_mask'][1:]) for t in chosen['turns'])
    margin=(c-r)-(reference[chosen['id']]-reference[rejected['id']])
    margin_tensor=torch.tensor(margin,dtype=torch.float64)
    g=float(-beta*torch.sigmoid(-beta*margin_tensor))
    for row,weight in ((chosen,g-alpha/n),(rejected,-g)):
        for i,turn in enumerate(row['turns']):
            score=score_turn(model,turn)
            (score*weight).backward()
            del score
            if progress:progress(dict(event='backward_turn',rollout=row['id'],turn=i+1,total_turns=len(row['turns'])))
    return dict(loss=float(-torch.nn.functional.logsigmoid(beta*margin_tensor))-alpha*c/n,
                margin=margin,chosen_logp=c,rejected_logp=r,chosen_nll=-c/n)


def load_model(base,adapter,current=None):
    import json
    from pathlib import Path
    import torch
    from transformers import AutoModelForImageTextToText,CompressedTensorsConfig
    from peft import PeftModel
    cfg=json.loads((Path(base)/'config.json').read_text())
    kwargs=dict(local_files_only=True,dtype=torch.bfloat16,device_map='auto',attn_implementation='sdpa')
    if cfg.get('quantization_config'):
        kwargs['quantization_config']=CompressedTensorsConfig(**dict(cfg['quantization_config'],dequantize=True))
    model=AutoModelForImageTextToText.from_pretrained(base,**kwargs)
    if any(str(v) in ('cpu','disk') for v in getattr(model,'hf_device_map',{}).values()):
        raise RuntimeError('Insufficient GPU memory for model weights')
    for name in ('vision_tower','audio_tower','embed_vision','embed_audio'):
        module=getattr(model.model,name,None)
        if module is not None:module.to('cpu')
    model=PeftModel.from_pretrained(model,str(current or adapter),adapter_name='policy',is_trainable=True,autocast_adapter_dtype=False)
    model.load_adapter(str(adapter),adapter_name='reference',is_trainable=False,autocast_adapter_dtype=False)
    model.set_adapter('policy')
    for module in model.modules():
        if isinstance(module,torch.nn.Dropout):module.p=0.
    model.config.use_cache=False;model.gradient_checkpointing_enable();model.enable_input_require_grads();model.train()
    torch.cuda.empty_cache()
    return model
