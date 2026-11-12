#!/usr/bin/env python3
"""Exercise the real Gemma/PEFT activation-offload training path on a tiny CPU model."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import torch
from transformers import Gemma4Config,Gemma4TextConfig,Gemma4ForConditionalGeneration
from peft import LoraConfig,get_peft_model
from costagent.sft_loss import backward_example,gemma_assistant_loss

torch.set_num_threads(2)
torch.manual_seed(42)
cfg=Gemma4Config(text_config=Gemma4TextConfig(vocab_size=32,hidden_size=16,intermediate_size=32,
    num_hidden_layers=2,num_attention_heads=2,num_key_value_heads=1,head_dim=8,
    vocab_size_per_layer_input=32,hidden_size_per_layer_input=4,
    layer_types=['sliding_attention','full_attention'],max_position_embeddings=64,
    sliding_window=8,final_logit_softcapping=3.))
model=get_peft_model(Gemma4ForConditionalGeneration(cfg).to(torch.bfloat16),
    LoraConfig(r=2,lora_alpha=4,lora_dropout=0.,task_type='CAUSAL_LM',target_modules=['q_proj','v_proj']),
    autocast_adapter_dtype=False)
model.config.use_cache=False;model.gradient_checkpointing_enable();model.enable_input_require_grads();model.train()
row=dict(input_ids=[2,3,4,5,6,7],assistant_mask=[0,0,0,1,1,1])
ids=torch.tensor([row['input_ids']]);mask=torch.tensor([row['assistant_mask']],dtype=torch.bool)
labels=ids.clone();labels[~mask]=-100
with torch.autocast('cpu',dtype=torch.bfloat16):
    dense=model(input_ids=ids,attention_mask=torch.ones_like(ids),labels=labels).loss
dense.backward();grads={n:p.grad.clone() for n,p in model.named_parameters() if p.grad is not None}
model.zero_grad(set_to_none=True)
actual=backward_example(model,row,3,2)
assert abs(actual-float(dense.detach()))<.01
for n,p in model.named_parameters():
    if n in grads: torch.testing.assert_close(p.grad,grads[n],atol=3e-4,rtol=.03)
optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=1e-3,foreach=False)
before={n:p.detach().clone() for n,p in model.named_parameters() if p.requires_grad}
optimizer.step()
assert any(not torch.equal(p,before[n]) for n,p in model.named_parameters() if n in before)
print('PASS: real tiny Gemma4+PEFT, bf16, checkpointing, CPU activation offload, dense gradient comparison, optimizer update',flush=True)
