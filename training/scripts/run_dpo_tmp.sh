#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

run_dir=/tmp/mahesh-gemma-dpo-5ep
mkdir -p "$run_dir/training" "$run_dir/cache" artifacts/resolved-sft
exec 9> artifacts/resolved-sft/launch.lock
if ! flock -n 9; then
    echo 'A project training job is already active; leaving it untouched.' >&2
    exit 1
fi
if [[ -f "$run_dir/training/complete.json" ]]; then
    echo 'Five-epoch DPO training already completed.'
    exit 0
fi

tmp_free=$(df -B1 --output=avail /tmp | tail -n 1)
if (( tmp_free < 20 * 1024 * 1024 * 1024 )); then
    echo 'Less than 20 GiB free on /tmp; refusing to train.' >&2
    exit 1
fi
home_free=$(df -B1 --output=avail . | tail -n 1)
if (( home_free < 1024 * 1024 * 1024 )); then
    echo 'Less than 1 GiB free on the project filesystem; refusing to train.' >&2
    exit 1
fi
gpu_free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -n 1 | tr -d ' ')
if (( gpu_free < 70000 )); then
    echo "Only ${gpu_free} MiB free on GPU; refusing to train on shared compute." >&2
    exit 1
fi

printf '%s\n' "$$" > "$run_dir/train.pid"
printf 'running\n' > "$run_dir/process-status.txt"
printf '%s\n' '{"stage":"direct_dpo_training","epochs":5,"evaluation":"not_run"}' > "$run_dir/progress.json"
trap 'code=$?; printf "exit_code=%s\n" "$code" > "$run_dir/process-status.txt"' EXIT
export GEMMA_DPO_OUTPUT_ROOT="$run_dir"
export PYTHONPATH="$PWD/training/src${PYTHONPATH:+:$PYTHONPATH}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-4}"
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export XDG_CACHE_HOME="$run_dir/cache"
export TMPDIR="$run_dir/cache"
resume_args=()
if [[ -f "$run_dir/training/state.json" ]]; then resume_args=(--resume); fi
envs/train/bin/python -u training/scripts/train_archive_dpo.py \
  --dataset artifacts/archive-dpo-v1/dataset.json \
  --output "$run_dir/training" --epochs 5 --compact-checkpoints \
  "${resume_args[@]}" "$@"
