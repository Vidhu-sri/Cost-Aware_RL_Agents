#!/usr/bin/env python3
"""Build an exact weighted sum of two compatible LoRA updates by rank concatenation.

This creates an experimental checkpoint, not a trained router. For each layer,
the output update equals weight * left + (1 - weight) * right before dtype
rounding. Inputs are never changed.
"""
import argparse
import hashlib
import json
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import save_file


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def blend_pair(a_left, b_left, a_right, b_right, weight, source_scale, output_scale):
    if a_left.shape != a_right.shape or b_left.shape != b_right.shape:
        raise ValueError("LoRA matrices have different shapes")
    if b_left.shape[1] != a_left.shape[0]:
        raise ValueError("LoRA A/B rank mismatch")
    a = torch.cat((a_left, a_right), dim=0).contiguous()
    b = torch.cat((b_left * (weight * source_scale / output_scale),
                   b_right * ((1 - weight) * source_scale / output_scale)), dim=1).contiguous()
    return a, b


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--left-weight", type=float, default=0.5)
    args = parser.parse_args()
    if not 0 <= args.left_weight <= 1:
        parser.error("--left-weight must be between zero and one")
    if args.out.exists():
        parser.error(f"Output already exists: {args.out}")

    configs = [json.loads((p / "adapter_config.json").read_text())
               for p in (args.left, args.right)]
    if configs[0] != configs[1]:
        parser.error("Adapter configurations differ")
    config = configs[0].copy()
    rank = config["r"]
    if not isinstance(rank, int) or rank <= 0 or config.get("use_rslora"):
        parser.error("Expected a positive, ordinary LoRA rank")
    if config.get("rank_pattern") or config.get("alpha_pattern") or config.get("modules_to_save"):
        parser.error("Per-module rank/alpha and saved modules are unsupported")
    output_rank = 2 * rank
    if output_rank > 128:
        parser.error("Blended rank exceeds the harness's 128-rank limit")
    source_scale = config["lora_alpha"] / rank
    config["r"] = output_rank
    config["lora_alpha"] = output_rank  # output_scale = 1

    left_file = args.left / "adapter_model.safetensors"
    right_file = args.right / "adapter_model.safetensors"
    tensors = {}
    with safe_open(left_file, framework="pt", device="cpu") as left, \
            safe_open(right_file, framework="pt", device="cpu") as right:
        if set(left.keys()) != set(right.keys()):
            parser.error("Adapter tensor keys differ")
        keys = set(left.keys())
        if not keys or any(not (k.endswith(".lora_A.weight") or k.endswith(".lora_B.weight")) for k in keys):
            parser.error("Expected only paired LoRA A/B tensors")
        for key in sorted(k for k in keys if k.endswith(".lora_A.weight")):
            b_key = key.replace(".lora_A.weight", ".lora_B.weight")
            if b_key not in keys:
                parser.error(f"Missing B tensor for {key}")
            a, b = blend_pair(left.get_tensor(key), left.get_tensor(b_key),
                              right.get_tensor(key), right.get_tensor(b_key),
                              args.left_weight, source_scale, 1.0)
            tensors[key], tensors[b_key] = a, b
        if len(tensors) != len(keys):
            parser.error("Unpaired LoRA tensor")

    args.out.mkdir(parents=True)
    save_file(tensors, args.out / "adapter_model.safetensors")
    (args.out / "adapter_config.json").write_text(json.dumps(config, indent=2) + "\n")
    (args.out / "provenance.json").write_text(json.dumps({
        "kind": "untrained_weighted_lora_sum",
        "left": str(args.left.resolve()), "left_sha256": digest(left_file),
        "right": str(args.right.resolve()), "right_sha256": digest(right_file),
        "left_weight": args.left_weight, "right_weight": 1 - args.left_weight,
        "source_rank": rank, "output_rank": output_rank,
        "output_sha256": digest(args.out / "adapter_model.safetensors"),
        "evaluation_status": "untested",
    }, indent=2) + "\n")
    print(args.out)


if __name__ == "__main__":
    main()
