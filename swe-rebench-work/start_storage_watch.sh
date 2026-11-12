#!/usr/bin/env bash
set -euo pipefail

project=/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent
batch=/tmp/gemma-swerebench-results-1017/gemma100-v2-20261021
python_bin=/home/mahesh/miniconda3/envs/gemma-harness/bin/python
controller_pid=$(cat "$batch/controller-nohup.pid")
created=$("$python_bin" -c 'import psutil,sys; p=psutil.Process(int(sys.argv[1])); c=p.cmdline(); assert any("run_batch.py" in x for x in c) and any("gemma100-v2-20261021" in x for x in c), c; print(p.create_time())' "$controller_pid")

cd "$project"
nohup setsid -f "$python_bin" swe-rebench-work/watch_storage.py \
    "$batch" "$controller_pid" "$created" 335 1.5 \
    >>"$batch/storage_watcher.log" 2>&1 </dev/null
echo "watching controller_pid=$controller_pid tmp_min_free=335GiB home_min_free=1.5GiB"
