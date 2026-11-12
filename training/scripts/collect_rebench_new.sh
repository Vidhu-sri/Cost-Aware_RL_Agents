#!/usr/bin/env bash
set -euo pipefail
cd /home/mahesh/mahesh/tmp/Gemma4_Developer_Agent
batch="$PWD/artifacts/rebench-new-20x4"
exec 9>"$batch/collection.lock"
flock -n 9 || { echo 'This collector is already running'; exit 1; }
export DOCKER_HOST=unix:///tmp/gemma-swerebench-docker-1017/docker.sock
export GEMMA_DOCKER_DATA_ROOT=/tmp/gemma-swerebench-docker-1017/data
export GEMMA_RESULTS_DATA_ROOT="$batch"
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false
unset GEMMA_RESULTS_MIRROR
python_bin=/home/mahesh/miniconda3/envs/gemma-harness/bin/python
printf '%s\n' "$$" > "$batch/controller.pid"
trap 'printf "exit_code=%s\n" "$?" > "$batch/process-status.txt"' EXIT
actual_root=$(docker info --format '{{.DockerRootDir}}')
[[ "$actual_root" == "$GEMMA_DOCKER_DATA_ROOT" ]] || { echo 'Unexpected Docker data root'; exit 1; }
printf 'waiting_for_gpu\n' > "$batch/process-status.txt"
# Require three successive idle checks; do not stop or reuse another user's server.
ready=0
for ((i=0;i<5760;i++)); do
  stats=$(nvidia-smi --query-gpu=memory.free,utilization.gpu --format=csv,noheader,nounits)
  read -r free utilization <<< "${stats//,/ }"
  if [[ "$free" -ge 62000 && "$utilization" -le 20 ]]; then
    ready=$((ready+1))
  else
    ready=0
  fi
  printf '%s free_mib=%s utilization=%s ready_checks=%s\n' "$(date -Is)" "$free" "$utilization" "$ready" > "$batch/gpu-wait.txt"
  if [[ "$ready" -ge 3 ]]; then break; fi
  sleep 30
done
[[ "$ready" -ge 3 ]] || { echo 'GPU wait expired after 48 hours'; exit 1; }
printf 'collecting\n' > "$batch/process-status.txt"
"$python_bin" -u "$batch/collector.py" --batch "$batch"
