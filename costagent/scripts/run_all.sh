#!/usr/bin/env bash
# Whole pipeline, resumable. Launch:  nohup bash scripts/run_all.sh > logs/run_all.log 2>&1 &
# Each finished step leaves artifacts/done/<step>; rerunning skips finished steps.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
source ./config.env
mkdir -p logs
exec 9>logs/run_all.lock
flock -n 9 || exit 1
trap vllm_stop EXIT
mkdir -p logs artifacts/done results/eval results/subs
FAILED=artifacts/FAILED.md; SKIPPED=artifacts/SKIPPED.md
touch "$FAILED" "$SKIPPED"
ts() { date '+%F %T'; }
say() { echo "[$(ts)] $*"; }

H() { bash -c "$HARNESS_ACTIVATE && cd '$ROOT' && $*"; }   # run in harness env
T() { bash -c "$TRAIN_ACTIVATE && cd '$ROOT' && export PYTHONPATH='$ROOT' && $*"; }  # run in training env

step() {  # step NAME command...
  local name=$1; shift
  if [ -e "artifacts/done/$name" ]; then say "skip $name (done)"; return 0; fi
  say "START $name"
  if "$@" > "logs/$name.log" 2>&1; then touch "artifacts/done/$name"; say "DONE $name"; return 0
  else local rc=$?; say "FAIL $name (exit $rc), see logs/$name.log"
       echo "- $name failed (exit $rc) at $(ts): $(tail -n 3 logs/$name.log | tr '\n' ' ')" >> "$FAILED"; return $rc; fi
}
skip() { say "SKIP $1: $2"; grep -q "^- $1:" "$SKIPPED" || echo "- $1: $2" >> "$SKIPPED"; }

vllm_stop() { [ -n "$VLLM_STOP_CMD" ] && { bash -c "$VLLM_STOP_CMD" || true; sleep 20; }; true; }
vllm_start() {  # vllm_start [adapter_dir]
  [ -z "$VLLM_START_CMD" ] && return 0
  vllm_stop
  wait_gpu || return 1
  local lora=""; [ -n "${1:-}" ] && lora="costlora=$1"
  local cmd=${VLLM_START_CMD//\{LORA_ARGS\}/$lora}
  /home/mahesh/miniconda3/envs/gemma-harness/bin/python -c 'import socket; s=socket.socket(); assert s.connect_ex(("127.0.0.1",8001)) != 0, "port 8001 occupied"' || return 1
  nohup setsid bash -c "$cmd" > logs/vllm.log 2>&1 & echo $! > logs/vllm.pid
  /home/mahesh/miniconda3/envs/gemma-harness/bin/python -c 'import json,psutil; from pathlib import Path; p=int(Path("logs/vllm.pid").read_text()); Path("logs/owned-server.json").write_text(json.dumps(dict(pid=p,created=psutil.Process(p).create_time())))' 
  for i in $(seq 1 120); do curl -sf "$VLLM_URL" > /dev/null && { say "vLLM up"; return 0; }; sleep 10; done
  say "vLLM did not come up"; return 1
}
wait_gpu() {
  for ((i=0;i<5760;i++)); do
    local used
    used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1) || return 1
    if [ "$used" -le 6000 ]; then return 0; fi
    say "Waiting for shared GPU: ${used} MiB used (requires <=6000); no other jobs stopped"
    sleep 30
  done
  return 1
}
gpu_free() { vllm_stop; wait_gpu; }

run_swegemma() {  # run_swegemma CMD_TEMPLATE SUB OUT
  local c=${1//\{SUB\}/$2}; c=${c//\{OUT\}/$3}
  H "$c"
}

eval_arm() {  # eval_arm NAME ADAPTER_DIR|none EXTRA_PROMPT|none
  local name=$1 ad=$2 pr=$3 args=""
  [ "$ad" != none ] && args="$args --adapter $ad"
  [ "$pr" != none ] && args="$args --append-prompt $pr"
  H "python scripts/make_submission.py '$BASE_SUB' results/subs/$name $args" || return 1
  if [ "$ad" != none ]; then
    H "python scripts/check_adapter.py $ad --serve-model '$SERVE_MODEL'" || return 1
    vllm_start "$ROOT/results/subs/$name/adapters/costlora" || return 1
  else vllm_start || return 1; fi
  run_swegemma "$EVAL_CMD" "results/subs/$name" "results/eval/${name}_s1"
}

train_pref() {  # train_pref NAME DATA ARGS...  (retries once with alpha=2 on likelihood displacement)
  local name=$1 data=$2; shift 2
  gpu_free || return 1
  T "python -m costagent.train pref --data $data --model '$TRAIN_MODEL' --out artifacts/adapters/$name $* ${TRAIN_EXTRA_ARGS:-}"
  local rc=$?
  if [ $rc -eq 3 ]; then
    say "$name: likelihood displacement detected, retrying with alpha=2"
    rm -rf "artifacts/adapters/$name"
    T "python -m costagent.train pref --data $data --model '$TRAIN_MODEL' --out artifacts/adapters/$name $* ${TRAIN_EXTRA_ARGS:-} --alpha 2 --displacement-tol 10"
    rc=$?
  fi
  return $rc
}

train_sft() {
  gpu_free || return 1
  T "python -m costagent.train sft --data artifacts/data/sft.pt --model '$TRAIN_MODEL' --out artifacts/adapters/A2 ${TRAIN_EXTRA_ARGS:-}"
}

count() { T "python -c \"import torch;print(len(torch.load('$1',weights_only=False)))\"" 2>/dev/null || echo 0; }

# ---------------- 0. tests ----------------
step tests T "python -m pytest -q tests" || { say "tests failed: not training"; exit 1; }

# ---------------- 1. extra rollouts (optional) ----------------
EXTRA_RUNS=""
if [ "$COLLECT" = 1 ]; then
  H "python scripts/make_submission.py '$BASE_SUB' results/subs/collect_base --temperature 0.7" && \
  H "python scripts/make_submission.py '$BASE_SUB' results/subs/rlcd_pos --temperature 0.7 --append-prompt prompts/rlcd_pos.md" && \
  H "python scripts/make_submission.py '$BASE_SUB' results/subs/rlcd_neg --temperature 0.7 --append-prompt prompts/rlcd_neg.md"
  vllm_start
  for s in $(seq 1 "$COLLECT_SEEDS"); do
    step collect_base_s$s run_swegemma "$TRAIN_RUN_CMD" results/subs/collect_base results/collect/train_extra_s$s
    EXTRA_RUNS="$EXTRA_RUNS results/collect/train_extra_s$s"
  done
  if [ "$COLLECT_RLCD" = 1 ]; then
    step collect_rlcd_pos run_swegemma "$TRAIN_RUN_CMD" results/subs/rlcd_pos results/collect/rlcd_pos
    step collect_rlcd_neg run_swegemma "$TRAIN_RUN_CMD" results/subs/rlcd_neg results/collect/rlcd_neg
    EXTRA_RUNS="$EXTRA_RUNS results/collect/rlcd_pos results/collect/rlcd_neg"
  fi
fi
EXISTING=""; for d in $EXTRA_RUNS; do [ -d "$d/traces" ] && EXISTING="$EXISTING $d"; done

# ---------------- 2. parse + build ----------------
rm -f artifacts/done/collect_traj artifacts/done/build   # always rebuild from whatever runs exist
step collect_traj T "python -m costagent.traces collect --runs $RUNS_TRAIN $EXISTING $RUNS_A0 --kaggle-tasks '$KAGGLE_TASKS' --out artifacts/trajectories.jsonl" || exit 1
step build T "python -m costagent.builders --trajectories artifacts/trajectories.jsonl --tokenizer '$TRAIN_MODEL' --out artifacts/data --pos-text prompts/rlcd_pos.md --neg-text prompts/rlcd_neg.md --all-turns --max-len 4096" || exit 1
cat artifacts/data/data_report.md
N_SFT=$(count artifacts/data/sft.pt); N_G=$(count artifacts/data/groups.pt)
N_P=$(count artifacts/data/pairs.pt); N_R=$(count artifacts/data/rlcd.pt)
N_SFT=${N_SFT:-0}; N_G=${N_G:-0}; N_P=${N_P:-0}; N_R=${N_R:-0}
say "data: sft=$N_SFT groups=$N_G pairs=$N_P rlcd=$N_R"

# ---------------- 3. A1 baseline (prompt only) ----------------
step eval_A1 eval_arm A1 none prompts/stop_loss.md

# ---------------- 4. arms: train then eval ----------------
if [ "$N_SFT" -ge "$MIN_SFT" ]; then
  step train_A2 train_sft && step eval_A2 eval_arm A2 artifacts/adapters/A2 none
else skip A2 "only $N_SFT training successes (< $MIN_SFT)"; fi

if [ "$N_G" -ge "$MIN_GROUPS" ]; then
  step train_A6b_k5 train_pref A6b_k5 artifacts/data/groups.pt --targets soft --kappa 5 && step eval_A6b_k5 eval_arm A6b_k5 artifacts/adapters/A6b_k5 none
  step train_A6b_k0 train_pref A6b_k0 artifacts/data/groups.pt --targets soft --kappa 0 && step eval_A6b_k0 eval_arm A6b_k0 artifacts/adapters/A6b_k0 none
else skip A6b "only $N_G usable groups (< $MIN_GROUPS): need >=2 rollouts with >=1 success per task"; fi

if [ "$N_P" -ge "$MIN_PAIRS" ]; then
  step train_A6a_hard train_pref A6a_hard artifacts/data/pairs.pt --targets hard && step eval_A6a_hard eval_arm A6a_hard artifacts/adapters/A6a_hard none
else skip A6a "only $N_P sibling pairs (< $MIN_PAIRS)"; fi

if [ "$N_R" -ge "$MIN_PAIRS" ]; then
  step train_A6d train_pref A6d artifacts/data/rlcd.pt --targets hard && step eval_A6d eval_arm A6d artifacts/adapters/A6d none
else skip A6d "only $N_R gated RLCD pairs (< $MIN_PAIRS)"; fi

# ---------------- 5. stats + report ----------------
ARMS="--arm A0=$(echo $RUNS_A0 | tr ' ' ',')"
for d in results/eval/*_s1; do [ -f "$d/task_results.jsonl" ] && ARMS="$ARMS --arm $(basename "$d" _s1)=$d"; done
rm -f artifacts/done/stats
step stats T "python -m costagent.stats --kaggle-tasks '$KAGGLE_TASKS' --baseline A0 $ARMS --out results"
{
  echo "# Results"; echo
  echo "Generated $(ts). Every number below is regenerated by: python -m costagent.stats --kaggle-tasks $KAGGLE_TASKS --baseline A0 $ARMS --out results"; echo
  echo "## Main table"; cat results/results_table.md 2>/dev/null; echo
  echo "![pareto](pareto.png)"; echo
  echo "## Data used"; cat artifacts/data/data_report.md; echo
  echo "## Training runs (last logged step)"
  for m in artifacts/adapters/*/metrics.jsonl; do [ -f "$m" ] && echo "- $(basename "$(dirname "$m")"): $(grep '"step"' "$m" | tail -1)"; done; echo
  echo "## Skipped"; cat "$SKIPPED"; echo
  echo "## Failed"; cat "$FAILED"
} > results/REPORT.md
say "ALL DONE. See results/REPORT.md"
