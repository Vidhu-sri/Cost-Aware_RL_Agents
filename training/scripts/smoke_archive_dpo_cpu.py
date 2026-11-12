#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import torch
from transformers import Gemma4Config,Gemma4TextConfig,Gemma4ForConditionalGeneration
from peft import LoraConfig,get_peft_model
from costagent.archive_dpo_train import trajectory_score,pair_step

torch.set_num_threads(2);torch.manual_seed(42)
cfg=Gemma4Config(text_config=Gemma4TextConfig(vocab_size=32,hidden_size=16,intermediate_size=32,
    num_hidden_layers=2,num_attention_heads=2,num_key_value_heads=1,head_dim=8,
    vocab_size_per_layer_input=32,hidden_size_per_layer_input=4,
    layer_types=['sliding_attention','full_attention'],max_position_embeddings=64,
    sliding_window=8,final_logit_softcapping=3.))
lora=LoraConfig(r=2,lora_alpha=4,lora_dropout=0.,task_type='CAUSAL_LM',target_modules=['q_proj','v_proj'])
model=get_peft_model(Gemma4ForConditionalGeneration(cfg).to(torch.bfloat16),lora,adapter_name='policy',autocast_adapter_dtype=False)
model.add_adapter('reference',lora)
model.config.use_cache=False;model.gradient_checkpointing_enable();model.enable_input_require_grads();model.train()
c=dict(id='c',turns=[dict(input_ids=[2,3,4,5,6],assistant_mask=[0,0,1,1,1])])
r=dict(id='r',turns=[dict(input_ids=[2,3,7,8,9],assistant_mask=[0,0,1,1,1])])
model.set_adapter('reference');refs={row['id']:trajectory_score(model,row) for row in (c,r)}
model.set_adapter('policy')
optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=.01,foreach=False)
metrics=pair_step(model,c,r,refs)
assert abs(metrics['margin'])<1e-6,metrics
assert all(p.grad is None for name,p in model.named_parameters() if '.reference.' in name)
assert any(p.grad is not None and p.grad.abs().sum()>0 for name,p in model.named_parameters() if '.policy.' in name)
optimizer.step()
model.set_adapter('reference')
assert {row['id']:trajectory_score(model,row) for row in (c,r)}==refs
print('PASS: tiny Gemma4 DPO, zero initial margin, nonzero policy gradient, optimizer step, unchanged reference',flush=True)
