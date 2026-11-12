#!/usr/bin/env python3
"""Check a trained adapter before evaluating it.

Static (always): rank <= 128, safetensors present, size, finite weights, and every
LoRA target module matches a weight in the serving (QAT) checkpoint.
--vllm: also load the QAT model in vLLM with the adapter and generate a few tokens.
Exit code 1 on failure.
"""
import argparse
import json
import re
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("adapter"); ap.add_argument("--serve-model", required=True, help="QAT checkpoint dir served by vLLM")
    ap.add_argument("--vllm", action="store_true")
    a = ap.parse_args()
    from safetensors import safe_open
    ad = Path(a.adapter)
    cfg = json.loads((ad / "adapter_config.json").read_text())
    ok = True
    if cfg.get("r", 0) > 128:
        print("FAIL rank > 128"); ok = False
    st = ad / "adapter_model.safetensors"
    print(f"adapter size {st.stat().st_size / 2**20:.1f} MiB, rank {cfg.get('r')}")
    import torch
    mods = set()
    with safe_open(st, "pt") as f:
        for k in f.keys():
            t = f.get_tensor(k)
            if not torch.isfinite(t).all():
                print("FAIL non-finite", k); ok = False
            m = re.search(r"((?:layers)\.\d+\..*?)\.lora_[AB]", k)
            if m:
                mods.add(m.group(1))
    serve = Path(a.serve_model)
    names = set()
    idx = serve / "model.safetensors.index.json"
    if idx.exists():
        names = set(json.loads(idx.read_text())["weight_map"])
    else:
        for p in serve.glob("*.safetensors"):
            with safe_open(p, "pt") as f:
                names |= set(f.keys())
    flat = "\n".join(names)
    missing = [m for m in sorted(mods) if m not in flat]
    print(f"{len(mods)} LoRA modules, {len(missing)} not found in serving checkpoint")
    if missing:
        print("  e.g.", missing[:5]); ok = False
    if a.vllm and ok:
        from vllm import LLM, SamplingParams
        from vllm.lora.request import LoRARequest
        llm = LLM(model=str(serve), enable_lora=True, max_lora_rank=128, max_model_len=4096,
                  gpu_memory_utilization=0.8)
        out = llm.generate(["Hello"], SamplingParams(max_tokens=8, temperature=0),
                           lora_request=LoRARequest("costlora", 1, str(ad)))
        print("vLLM generation with adapter:", repr(out[0].outputs[0].text))
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
