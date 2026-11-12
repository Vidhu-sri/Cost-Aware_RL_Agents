#!/usr/bin/env bash
# Run from the host terminal; this session's sandbox has no GPU device access.
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
printf 'installing_compatible_runtime\n' > "$run_dir/process-status.txt"
trap 'code=$?; printf "exit_code=%s\n" "$code" > "$run_dir/process-status.txt"' EXIT
train_python="$PWD/envs/train/bin/python"
"$train_python" - <<'PY'
import sys
from pathlib import Path
assert Path(sys.prefix).resolve() == Path('envs/train').resolve(), sys.prefix
PY
# Installed locally in the venv; inherited blora/harness packages are not modified.
"$train_python" -m pip install --no-cache-dir \
  torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 \
  --index-url https://download.pytorch.org/whl/cu124
printf 'torch==2.6.0\ntorchvision==0.21.0\ntorchaudio==2.6.0\n' > "$run_dir/runtime-constraints.txt"
"$train_python" -m pip install --no-cache-dir \
  -c "$run_dir/runtime-constraints.txt" 'compressed-tensors>=0.15,<0.16'
printf 'checking_gpu\n' > "$run_dir/process-status.txt"
"$train_python" - <<'PY'
import torch
import transformers
import peft
import compressed_tensors
from transformers import Gemma4ForConditionalGeneration
print('torch:', torch.__version__, 'CUDA:', torch.version.cuda, flush=True)
print('transformers:', transformers.__version__, 'peft:', peft.__version__, flush=True)
if not torch.cuda.is_available():
    raise RuntimeError('CUDA unavailable; training was not started')
print('GPU:', torch.cuda.get_device_name(0), flush=True)
x=torch.randn(128,128,device='cuda',dtype=torch.bfloat16,requires_grad=True)
(x @ x.T).float().square().mean().backward()
torch.cuda.synchronize()
if not torch.isfinite(x.grad).all(): raise RuntimeError('GPU backward produced nonfinite gradients')
print('GPU matmul and backward passed',flush=True)
PY
"$train_python" -m pip freeze > "$run_dir/runtime-packages.txt"
printf 'training\n' > "$run_dir/process-status.txt"
"$train_python" -u training/scripts/train_resolved_sft.py --reuse-dataset "$@"
