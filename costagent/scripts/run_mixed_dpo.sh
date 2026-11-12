#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source config.env
P=/home/mahesh/miniconda3/envs/gdac/bin/python
H=/home/mahesh/miniconda3/envs/gemma-harness/bin/python
B=artifacts/mixed-temperature-v1
mkdir -p "$B/done" logs
exec 8>"$B/pipeline.lock"
flock -n 8 || exit 1
trap 'echo exit_code=$? > "$B/pipeline.status"' EXIT
echo $$ > "$B/pipeline.pid"
echo waiting_for_collection > "$B/pipeline.status"
while true; do
 stage=$($P -c 'import json,pathlib; p=pathlib.Path("artifacts/mixed-temperature-v1/status.json"); print(json.loads(p.read_text()).get("stage","") if p.exists() else "")')
 [[ "$stage" == complete ]] && break
 [[ "$stage" == stopped ]] && { echo 'Collection stopped; inspect status.json'; exit 1; }
 sleep 30
done
step() {
 name=$1;shift
 [[ -f "$B/done/$name" ]] && return 0
 echo "START $name"
 echo "$name" > "$B/pipeline.status"
 "$@" > "$B/$name.log" 2>&1
 touch "$B/done/$name"
 echo "DONE $name"
}
export PYTHONPATH="$PWD"
step prepare "$P" scripts/prepare_temperature_data.py
step build "$P" -m costagent.builders --trajectories "$B/trajectories.jsonl" --tokenizer "$TRAIN_MODEL" --out "$B/data" --all-turns --max-len 8192 --allow-kaggle-tasks "$B/allow_kaggle_tasks.json"
# One pair is enough to execute; dataset report exposes task coverage for interpretation.
"$P" -c 'import torch; p=torch.load("artifacts/mixed-temperature-v1/data/pairs.pt",weights_only=False); assert p,"No valid pairs: do not train"; print("pairs",len(p),"tasks",len({x["task_id"] for x in p}))'
for ((i=0;i<5760;i++)); do
 used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
 [[ "$used" -le 6000 ]] && break
 sleep 30
done
[[ "$used" -le 6000 ]] || exit 1
step train "$P" -m costagent.train pref --data "$B/data/pairs.pt" --model "$TRAIN_MODEL" --adapter artifacts/adapters/A2 --out "$B/dpo" --load bf16 --targets hard --epochs 5 --accum 1 --lr 1e-5
step dev_original "$H" scripts/evaluate_checkpoint.py --arm original --split dev
step dev_sft "$H" scripts/evaluate_checkpoint.py --arm sft --split dev --adapter artifacts/adapters/A2
for ep in 1 2 3 4 5; do
 printf -v folder 'epoch-%03d' "$ep"
 step "dev_$folder" "$H" scripts/evaluate_checkpoint.py --arm "$folder" --split dev --adapter "$B/dpo/$folder"
done
step select "$P" scripts/select_temperature_checkpoint.py
best=$("$P" -c 'import json; print(json.load(open("artifacts/mixed-temperature-v1/evaluation/selection.json"))["epoch"])')
step test_original "$H" scripts/evaluate_checkpoint.py --arm original --split test
step test_sft "$H" scripts/evaluate_checkpoint.py --arm sft --split test --adapter artifacts/adapters/A2
step test_dpo "$H" scripts/evaluate_checkpoint.py --arm dpo --split test --adapter "$B/dpo/$best"
step compare "$P" -m costagent.compare_runs --arm original="$B/evaluation/original-test-manifest.json" --arm sft="$B/evaluation/sft-test-manifest.json" --arm dpo="$B/evaluation/dpo-test-manifest.json" --baseline sft --output "$B/evaluation/comparison"
echo 'COMPLETE: held-out comparison and epoch logs available'
