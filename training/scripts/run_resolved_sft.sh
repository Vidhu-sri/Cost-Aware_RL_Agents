#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
run_dir="artifacts/resolved-sft"
mkdir -p "$run_dir"
# Prevent duplicate runs from modifying the same environment or checkpoints.
exec 9> "$run_dir/launch.lock"
if ! flock -n 9; then
  echo 'A resolved-SFT launch is already active; leaving it untouched.' >&2
  exit 1
fi
if [ -f "$run_dir/complete.json" ]; then
  echo 'This training run already completed; leaving its adapter untouched.'
  exit 0
fi
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-4}"
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
printf '%s\n' "$$" > "$run_dir/train.pid"
printf 'running\n' > "$run_dir/process-status.txt"
trap 'code=$?; printf "exit_code=%s\n" "$code" > "$run_dir/process-status.txt"' EXIT
envs/train/bin/python -u training/scripts/train_resolved_sft.py "$@"
