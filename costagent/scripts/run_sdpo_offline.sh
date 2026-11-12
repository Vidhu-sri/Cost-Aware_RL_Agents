#!/usr/bin/env bash
# Explicit offline contrastive arm; leaves the existing DPO job and its artifacts intact.
set -euo pipefail
cd "$(dirname "$0")/.."
source config.env
P=/home/mahesh/miniconda3/envs/gdac/bin/python
H=/home/mahesh/miniconda3/envs/gemma-harness/bin/python
B=artifacts/mixed-temperature-v1
export PYTHONPATH="$PWD"
mkdir -p "$B/sdpo"
echo $$ > "$B/sdpo/runner.pid"
trap 'echo exit_code=$? > "$B/sdpo/runner.status"' EXIT
exec 8>"$B/pipeline.lock"
if [[ "${1:-}" == --wait ]]; then
 echo 'Waiting for DPO/evaluation workflow lock'
 flock 8
else
 flock -n 8 || { echo 'DPO/evaluation pipeline owns the GPU workflow; use --wait to queue.'; exit 1; }
fi
[[ "$($P -c 'import json;print(json.load(open("artifacts/mixed-temperature-v1/status.json"))["stage"])')" == complete ]] || { echo 'Collection is incomplete; teacher-input preparation can be previewed separately.'; exit 1; }
echo preparing_data > "$B/sdpo/runner.status"
$P scripts/prepare_temperature_data.py
$H scripts/prepare_sdpo_gold.py
$P -m costagent.sdpo prepare --trajectories "$B/trajectories.jsonl" --training-tasks "$B/training_tasks.json" --gold-json "$B/teacher_only_gold.json" --model "$TRAIN_MODEL" --output "$B/sdpo" --max-len 8192
$P -m costagent.sdpo score --inputs "$B/sdpo/teacher_inputs.pt" --teacher artifacts/adapters/A2 --model "$TRAIN_MODEL" --output "$B/sdpo" --dry-run
echo waiting_for_gpu > "$B/sdpo/runner.status"
while true; do
 used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
 [[ "$used" -le 6000 ]] && break
 sleep 30
done
echo scoring_teacher > "$B/sdpo/runner.status"
$P -m costagent.sdpo score --inputs "$B/sdpo/teacher_inputs.pt" --teacher artifacts/adapters/A2 --model "$TRAIN_MODEL" --output "$B/sdpo"
for arm in contrast r2_only no_efficiency; do
 case "$arm" in
   r2_only) extra=(--contrast-weight 0);;
   contrast) extra=(--contrast-weight 1);;
   no_efficiency) extra=(--contrast-weight 1 --no-efficiency-contrast);;
 esac
 echo "training_$arm" > "$B/sdpo/runner.status"
 # Identical encoded candidates, reference, epochs and learning rate in each arm.
 $P -m costagent.train pref --teacher-contrast --data "$B/sdpo/student_groups.pt" --adapter artifacts/adapters/A2 --model "$TRAIN_MODEL" --load bf16 --epochs 5 --accum 1 --lr 1e-5 --out "$B/sdpo/$arm" "${extra[@]}"
done
