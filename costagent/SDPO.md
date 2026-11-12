# Offline cost-aware contrastive self-distillation

Implemented as a separate experimental arm inspired by SDPO, not a reproduction of standard online SDPO. `costagent.sdpo prepare` builds good/bad feedback for compatible same-task groups. Mixed groups contrast a lowest-cost success with an unsuccessful attempt and observed failure text; all-success groups contrast lowest/highest cost action lists with exact repeated calls marked. All-failure groups require an authorized reference patch; unavailable gold produces an explicit exclusion. No graph-symbol S* extraction is claimed.

Teacher and student views share identical assistant target tokens and the same retained history blocks. Context truncation is joint across all three views. Template or alignment failures reject the entire group. These remain reconstructed historical contexts. Feedback and gold occur only in teacher inputs. `student_groups.pt` contains clean contexts and scalar contrast scores, never teacher contexts.

For consecutive assistant messages merged by Gemma's template, the rendered context without a new generation header must be an exact prefix. Only the newly appended tokens receive loss. Token-prefix checks still apply in all three views. This preserves narrative final answers instead of silently dropping them.

A frozen A2 teacher scores each assistant token under the two feedback contexts. `d = logp_good - logp_bad`. Clip d to [-c,c], then average over assistant tokens. The score cache is bound to encoded inputs, teacher adapter weights/config, model path/config and clipping setting; score entries checkpoint after each candidate. Changing base weights in place without changing config/path requires a new output/cache directory. Teacher scoring is two forward passes per encoded turn; no backward or full-vocabulary distribution storage across chunks. This is extra compute, not free supervision.

Targets: `softmax(k1*R2 + k2*D)`, k1=1/T and lambda=kappa*T. Enforce `2*k2*c < k1*(1-lambda)` to preserve success/failure *score ordering*. This does not guarantee learned behavior or online standardized-advantage ordering. No Bayes calibration, global trajectory telescoping, or exact InfoNCE reward-model claim is made.

Trainer recomputes policy/reference ratios and listwise gradients per group. The teacher is frozen, not EMA. All-failure groups use contrast alone and no NLL imitation anchor. Epoch checkpoints and summary/step JSON logs are shared with the DPO trainer.

Controlled arms in `scripts/run_sdpo_offline.sh`: R2-only on the exact same encoded groups (`--contrast-weight 0`), teacher contrast, and no efficiency contrast on all-success groups. The script is separate from the running DPO workflow, takes its workflow lock, requires collection complete, and waits for GPU memory. Do not launch a competing scorer on the shared GPU. It trains checkpoints only; use the existing `evaluate_checkpoint.py` on the frozen dev split for every epoch, select on dev, and evaluate selected checkpoints on the test split. Do not select using test outcomes.

Current cost code still uses prompt+completion tokens and fixed component weights. That is a model-processing-token proxy, not exact generated-plus-observation cost or fitted latency cost. File counts are tool-based proxies. These limits apply equally to both contrast and R2-only arms and must appear in the paper.

Example CPU preparation (no GPU):

```bash
python -m costagent.sdpo prepare --trajectories artifacts/mixed-temperature-v1/trajectories.jsonl --training-tasks artifacts/mixed-temperature-v1/training_tasks.json --gold-json artifacts/mixed-temperature-v1/teacher_only_gold.json --model ../gemma-4-31b-it-qat-w4a16-ct --output artifacts/mixed-temperature-v1/sdpo --max-len 8192
```

No online teacher-conditioned PPO/GRPO advantage arm is implemented here. Existing DPO run remains unchanged as the hard-pair comparator.

Detached launch after the existing workflow releases its lock:

```bash
mkdir -p logs
nohup bash scripts/run_sdpo_offline.sh > logs/sdpo_offline.log 2>&1 < /dev/null &
```

The script exits explicitly if collection is incomplete. By default it exits when another workflow holds its lock; pass --wait to queue behind that workflow. This lock coordinates our jobs only and does not reserve the shared GPU. A successful CPU dry-run is not evidence of GPU scoring or training completion.
