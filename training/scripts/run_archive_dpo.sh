#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
run_dir="artifacts/archive-dpo-v1"
mkdir -p "$run_dir" artifacts/resolved-sft
exec 9> artifacts/resolved-sft/launch.lock
if ! flock -n 9; then echo 'Another project training job holds the lock.' >&2; exit 1; fi
if [[ -f "$run_dir/complete.json" ]]; then echo 'DPO already completed; existing output preserved.'; exit 0; fi
printf '%s\n' "$$" > "$run_dir/train.pid"
printf 'preparing\n' > "$run_dir/process-status.txt"
trap 'code=$?; printf "exit_code=%s\n" "$code" > "$run_dir/process-status.txt"' EXIT
export PYTHONPATH="$PWD/training/src${PYTHONPATH:+:$PYTHONPATH}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-4}"
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
if [[ ! -f "$run_dir/dataset.json" ]]; then
    envs/train/bin/python -u -m costagent.archive_dpo
fi
printf 'training\n' > "$run_dir/process-status.txt"
resume_args=()
if [[ -f "$run_dir/state.json" ]]; then resume_args=(--resume); fi
envs/train/bin/python -u training/scripts/train_archive_dpo.py "${resume_args[@]}" "$@"
