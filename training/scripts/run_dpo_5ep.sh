#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
run_dir="artifacts/archive-dpo-5ep"
mkdir -p "$run_dir" artifacts/resolved-sft
exec 9> artifacts/resolved-sft/launch.lock
if ! flock -n 9; then echo 'A project training job is already active; leaving it untouched.' >&2; exit 1; fi
if [[ -f "$run_dir/training/complete.json" ]]; then echo 'Five-epoch experiment already completed.'; exit 0; fi
printf '%s\n' "$$" > "$run_dir/train.pid"
printf 'running\n' > "$run_dir/process-status.txt"
printf '%s\n' '{"stage":"direct_dpo_training","epochs":5,"evaluation":"not_run"}' > "$run_dir/progress.json"
trap 'code=$?; printf "exit_code=%s\n" "$code" > "$run_dir/process-status.txt"' EXIT
export PYTHONPATH="$PWD/training/src${PYTHONPATH:+:$PYTHONPATH}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-4}"
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
# Train directly. Docker, vLLM serving, and graded evaluation are separate jobs.
resume_args=()
if [[ -f "$run_dir/training/state.json" ]]; then resume_args=(--resume); fi
envs/train/bin/python -u training/scripts/train_archive_dpo.py \
  --dataset artifacts/archive-dpo-v1/dataset.json \
  --output "$run_dir/training" --epochs 5 --compact-checkpoints \
  "${resume_args[@]}" "$@"
