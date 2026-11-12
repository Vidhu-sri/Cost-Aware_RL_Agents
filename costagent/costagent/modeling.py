"""Model loading (QLoRA) and exact per-turn log-probs of assistant tokens."""
from __future__ import annotations

import torch
from torch.utils.checkpoint import checkpoint

LORA_TARGET = r"^(?!.*(vision|audio|multi_modal|mm_)).*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)$"


def load(model_path: str, load: str = "nf4", lora_r: int = 16, lora_alpha: int = 32,
         adapter: str | None = None, grad_ckpt: bool = True):
    from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig

    kw = {"dtype": torch.bfloat16, "attn_implementation": "sdpa"}
    if torch.cuda.is_available():
        kw["device_map"] = {"": 0}
    import json
    from pathlib import Path
    cfg_json = json.loads((Path(model_path) / "config.json").read_text())
    qat = cfg_json.get("quantization_config")
    if qat:
        if load != "bf16":
            raise ValueError("Local QAT checkpoint requires --load bf16 (explicit dequantization)")
        from transformers import CompressedTensorsConfig
        kw["quantization_config"] = CompressedTensorsConfig(**dict(qat, dequantize=True))
    if load == "nf4":
        kw["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16)
    try:
        model = AutoModelForCausalLM.from_pretrained(model_path, **kw)
    except (ValueError, KeyError):
        from transformers import AutoModelForImageTextToText
        model = AutoModelForImageTextToText.from_pretrained(model_path, **kw)
    model.config.use_cache = False
    if load == "nf4":
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=grad_ckpt,
                                                gradient_checkpointing_kwargs={"use_reentrant": False})
    elif grad_ckpt:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.enable_input_require_grads()
    if adapter:
        model = PeftModel.from_pretrained(model, adapter, is_trainable=True, autocast_adapter_dtype=False)
    else:
        cfg = LoraConfig(r=lora_r, lora_alpha=lora_alpha, lora_dropout=0.0, bias="none",
                         target_modules=LORA_TARGET, task_type="CAUSAL_LM")
        model = get_peft_model(model, cfg, autocast_adapter_dtype=False)  # B initialised to zero: policy == base at step 0
    for m in model.modules():
        if isinstance(m, torch.nn.Dropout):
            m.p = 0.0
    return model


def _parts(model):
    base = model.get_base_model() if hasattr(model, "get_base_model") else model
    dec = base.get_decoder()
    head = base.get_output_embeddings()
    cfg = base.config
    cap = getattr(cfg, "final_logit_softcapping", None)
    if cap is None and hasattr(cfg, "text_config"):
        cap = getattr(cfg.text_config, "final_logit_softcapping", None)
    return dec, head, cap


def _chunk_lp(head, cap, h, tgt):
    logits = head(h).float()
    if cap:
        logits = torch.tanh(logits / cap) * cap
    return torch.log_softmax(logits, -1).gather(-1, tgt[:, None]).squeeze(-1)


def turn_logprob(model, input_ids, mask, chunk: int = 64):
    """Sum of log p(token) over masked (assistant) tokens and their count.

    The head runs only at assistant positions, in fp32 chunks, each chunk
    checkpointed so full-vocabulary logits never sit in memory together.
    """
    dev = next(model.parameters()).device
    ids = torch.as_tensor(input_ids, device=dev)[None]
    m = torch.as_tensor(mask, device=dev, dtype=torch.bool)
    dec, head, cap = _parts(model)
    with torch.autograd.graph.save_on_cpu(pin_memory=True), torch.autocast(device_type=dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
        h = dec(input_ids=ids, use_cache=False).last_hidden_state[0]           # [L, d]
    pos = torch.nonzero(m[1:], as_tuple=False).squeeze(-1)  # predicting token pos+1
    tgt = ids[0, 1:][pos]
    hs = h[pos]
    total = torch.zeros((), device=dev, dtype=torch.float32)
    for s in range(0, hs.shape[0], chunk):
        if torch.is_grad_enabled():
            lp = checkpoint(_chunk_lp, head, cap, hs[s:s + chunk], tgt[s:s + chunk], use_reentrant=False)
        else:
            lp = _chunk_lp(head, cap, hs[s:s + chunk], tgt[s:s + chunk])
        total = total + lp.sum()
    return total, int(pos.numel())
