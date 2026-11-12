#!/usr/bin/env bash
set -euo pipefail

root=/tmp/gemma-swerebench-docker-1017
project=/home/mahesh/mahesh/tmp/Gemma4_Developer_Agent
log="$project/swe-rebench-work/results/gemma100-v2-20261021/tmp-dockerd.log"
pid_file="$root/controller.pid"

mkdir -p "$root/runtime" "$root/data" "$root/exec" "$root/state"
chmod 700 "$root" "$root/runtime" "$root/state"
if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "isolated Docker daemon already running: $(cat "$pid_file")"
    exit 0
fi

: >"$pid_file"
nohup setsid -f bash -c '
    printf "%s\n" "$$" >"$1"
    export XDG_RUNTIME_DIR="$2/runtime"
    export DOCKERD_ROOTLESS_ROOTLESSKIT_STATE_DIR="$2/state"
    exec /home/mahesh/bin/dockerd-rootless.sh \
        --data-root="$2/data" --exec-root="$2/exec" \
        --host="unix://$2/docker.sock" --pidfile="$2/dockerd.pid"
' bash "$pid_file" "$root" >>"$log" 2>&1 </dev/null

for ((i=0;i<50;i++)); do
    [[ -s "$pid_file" ]] && break
    sleep 0.1
done
[[ -s "$pid_file" ]] || { echo 'isolated Docker daemon did not write PID' >&2; exit 1; }
echo "daemon_pid=$(cat "$pid_file") socket=$root/docker.sock log=$log"
