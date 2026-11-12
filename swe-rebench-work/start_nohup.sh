#!/usr/bin/env bash
set -euo pipefail

project=/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent
batch=/tmp/gemma-swerebench-results-1017/gemma100-v2-20261021
mirror="$project/swe-rebench-work/results/gemma100-v2-20261021"
python_bin=/home/mahesh/miniconda3/envs/gemma-harness/bin/python
docker_root=/tmp/gemma-swerebench-docker-1017
docker_host="unix://$docker_root/docker.sock"
pid_file="$batch/controller-nohup.pid"
log_file="$batch/nohup-controller.log"

if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "controller already running: $(cat "$pid_file")"
    exit 1
fi

cd "$project"
[[ -f "$batch/manifest.json" ]] || { echo 'staged batch manifest is unavailable' >&2; exit 1; }
[[ -S "$docker_root/docker.sock" ]] || { echo 'isolated Docker socket is unavailable' >&2; exit 1; }
actual_root=$(DOCKER_HOST="$docker_host" docker info --format '{{.DockerRootDir}}')
[[ "$actual_root" == "$docker_root/data" ]] || { echo "unexpected Docker root: $actual_root" >&2; exit 1; }
: >"$pid_file"
# setsid -f forks away from the invoking tool's process group. The child
# writes its own PID before exec, while nohup makes SIGHUP ignored by the
# controller, its GPU watcher, and its owned vLLM child.
nohup setsid -f bash -c 'printf "%s\n" "$$" >"$1"; export DOCKER_HOST="$5" GEMMA_DOCKER_DATA_ROOT="$6" GEMMA_RESULTS_DATA_ROOT="$4" GEMMA_RESULTS_MIRROR="$7"; exec "$2" -u "$3" --batch "$4"' \
    bash "$pid_file" "$python_bin" swe-rebench-work/run_batch.py "$batch" "$docker_host" "$docker_root/data" "$mirror" \
    >>"$log_file" 2>&1 </dev/null
for ((i=0;i<20;i++)); do
    [[ -s "$pid_file" ]] && break
    sleep 0.1
done
[[ -s "$pid_file" ]] || { echo 'detached controller did not write PID' >&2; exit 1; }
echo "controller_pid=$(cat "$pid_file") log=$log_file"
