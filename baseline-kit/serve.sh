#!/usr/bin/env bash
export LD_LIBRARY_PATH="/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent/baseline-kit/cuda-compat-local/usr/local/cuda-13.0/compat${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export VLLM_USE_FLASHINFER_SAMPLER=0
set -euo pipefail
cd -- "$(dirname -- "$0")"
MODEL_DIR=$(cat ../model-path.txt)
test -f "$MODEL_DIR/config.json"
mkdir -p logs
export LITELLM_LOCAL_MODEL_COST_MAP=True TRANSFORMERS_NO_TF=1
export VLLM_WORKER_MULTIPROC_METHOD=spawn VLLM_NO_USAGE_STATS=1
export OTEL_SDK_DISABLED=true HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export VLLM_ENGINE_READY_TIMEOUT_S=1200
export CUDA_VISIBLE_DEVICES=0
exec vllm serve "$MODEL_DIR" \
  --served-model-name gemma-4-31b-it-qat-w4a16-ct \
  --host 127.0.0.1 --port 8001 --tensor-parallel-size 1 \
  --dtype bfloat16 --max-model-len 32768 \
  --gpu-memory-utilization "${BASELINE_GPU_FRACTION:-0.60}" \
  --max-num-seqs 1 --max-num-batched-tokens 4096 --enable-auto-tool-choice \
  --tool-call-parser gemma4 --reasoning-parser gemma4 \
  --reasoning-config '{"reasoning_start_str":"<|channel>","reasoning_end_str":"<channel|>"}' \
  --enable-lora --max-loras 8 --max-lora-rank 128 \
  --lora-modules \
    "main_lora=$PWD/../data/sample_submission/adapters/main_lora" \
    "tool_lora=$PWD/../data/sample_submission/adapters/tool_lora"
