"""Common adapter loading and token likelihood routines; heavy imports are lazy."""
import hashlib
from pathlib import Path
import sys
from .traces import ROOT, ARTIFACTS


def require_train_env():
    expected=(ROOT/'envs/train').resolve()
    if Path(sys.prefix).resolve()!=expected:
        raise RuntimeError(f'GPU training must run in {expected}; current prefix is {sys.prefix}')


def fingerprint(directory):
    h=hashlib.sha256()
    for name in ('adapter_config.json','adapter_model.safetensors'):
        with (Path(directory)/name).open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def load_model(base, adapter, qlora=False):
    require_train_env()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel, prepare_model_for_kbit_training
    if not torch.cuda.is_available(): raise RuntimeError('Training requires CUDA; use --dry-run on CPU')
    kwargs=dict(torch_dtype=torch.bfloat16)
    if qlora:
        kwargs['quantization_config']=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',
                                                        bnb_4bit_compute_dtype=torch.bfloat16,bnb_4bit_use_double_quant=True)
    model=AutoModelForCausalLM.from_pretrained(base,**kwargs)
    if qlora: model=prepare_model_for_kbit_training(model)
    model=PeftModel.from_pretrained(model,adapter,adapter_name='policy',is_trainable=True)
    model.load_adapter(adapter,adapter_name='reference',is_trainable=False)
    model.set_adapter('policy')
    config=model.peft_config['policy']
    if config.r!=16 or config.lora_alpha!=32: raise ValueError('Expected rank-16, alpha-32 RFT adapter')
    required={'q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj'}
    if config.target_modules!='all-linear' and not required<=set(config.target_modules):
        raise ValueError('Adapter misses required Gemma linear targets')
    for module in model.modules():
        if isinstance(module,torch.nn.Dropout): module.p=0.0  # deterministic policy ratios
    model.config.use_cache=False;model.gradient_checkpointing_enable();model.enable_input_require_grads()
    if not qlora: model.to('cuda')
    tokenizer=AutoTokenizer.from_pretrained(base)
    if tokenizer.pad_token_id is None: tokenizer.pad_token=tokenizer.eos_token
    return model,tokenizer


def logps(model,turn):
    import torch
    ids=torch.tensor([turn['input_ids']],dtype=torch.long,device=model.device)
    logits=model(input_ids=ids,attention_mask=torch.ones_like(ids)).logits[0,:-1].float()
    values=logits.log_softmax(-1).gather(-1,ids[0,1:,None]).squeeze(-1)
    mask=torch.tensor(turn['assistant_mask'][1:],device=model.device,dtype=torch.bool)
    return values,mask


def save_adapter(model,tokenizer,path):
    path=Path(path).resolve()
    if not path.is_relative_to(ARTIFACTS.resolve()): raise ValueError('Adapter output must be under artifacts/')
    path.mkdir(parents=True,exist_ok=True)
    model.save_pretrained(path,selected_adapters=['policy'],safe_serialization=True)
    saved=path/'policy'
    if not (saved/'adapter_model.safetensors').exists(): raise RuntimeError('PEFT did not save adapter weights')
    tokenizer.save_pretrained(saved)
    return saved
