#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH=/home/mahesh/miniconda3/envs/gemma-harness/bin:$PATH
export LD_LIBRARY_PATH="$PWD/../baseline-kit/cuda-compat-local/usr/local/cuda-13.0/compat${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export VLLM_USE_FLASHINFER_SAMPLER=0 VLLM_WORKER_MULTIPROC_METHOD=spawn HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
extra_loras=()
if [[ "${COSTAGENT_METHOD_ROUTER:-0}" == 1 ]]; then
  extra_loras=("rft_lora=$PWD/artifacts/adapters/A2" "dpo_lora=$PWD/artifacts/mixed-temperature-v1/dpo/epoch-005" "sdpo_lora=$PWD/artifacts/mixed-temperature-v1/sdpo/contrast/epoch-005")
fi
exec vllm serve "$PWD/../gemma-4-31b-it-qat-w4a16-ct" --served-model-name gemma-4-31b-it-qat-w4a16-ct --host 127.0.0.1 --port 8001 --dtype bfloat16 --max-model-len 32768 --gpu-memory-utilization 0.60 --max-num-seqs 1 --max-num-batched-tokens 4096 --enable-auto-tool-choice --tool-call-parser gemma4 --reasoning-parser gemma4 --reasoning-config '{"reasoning_start_str":"<|channel>","reasoning_end_str":"<channel|>"}' --enable-lora --max-lora-rank 128 --max-loras 8 --lora-modules "main_lora=${MAIN_ADAPTER:-$PWD/../data/sample_submission/adapters/main_lora}" "tool_lora=$PWD/../data/sample_submission/adapters/tool_lora" "${extra_loras[@]}" "$@"
