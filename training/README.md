# Cost-aware DPO, GRPO and graph-guided training

All new code lives in this folder. Derived reports, plans, datasets and adapters go
under the repository's `artifacts/`. Raw `data/` and rollout directories are read-only.
Graph training means Gemma adapter training with R3 graph rewards, not a GNN.

## Entry points

- `scripts/train_dpo.py`: a plain PyTorch loop with a two-pass assistant-token-only objective,
  beta 0.1, frozen R2 RFT reference adapter and alpha=1.0 NLL anchor (`--no-nll`
  disables the anchor). Each continuation is scored using its exact per-turn model
  contexts, preserving compaction boundaries and excluding tool observations from loss.
  Reference scores are cached once per run. Each backward retains only one turn’s
  graph; the detached first pass computes exact scalar DPO weights. Accumulation
  averages over pairs, including the final partial batch (`--grad-accum`, default 8).
- `scripts/train_grpo.py`: iterated sampling, old-policy forward logprobs, clipped
  updates, fixed RFT reference, iteration checkpoints and metrics. Tasks are sampled
  anew with seed + iteration. Updates shuffle turns and normalize tokens within
  minibatches (`--minibatch-turns`, default 8), stepping after each minibatch. R1, R2,
  R3_traj and R3_rtg supported. `--smoke` means 5 iterations, 4 tasks, G=4.
- `scripts/train_graph.py`: the same GRPO trainer with R3_rtg by default. Use
  `--reward R3_traj` for the whole-trajectory shaping variant.
- `python -m costagent.graphs`: build AST graphs from a clean base-commit checkout,
  locate gold-patch symbols with unidiff and compute undirected BFS relevance.
- `python -m costagent.traces`: audit the real ATIF and request-log formats; write
  `artifacts/data_report.md`, `steps.parquet` and `trajectories.parquet`. The step
  parquet preserves each complete ATIF step in `step_json`; it is an audit table,
  not the full normalized Step schema from the broader implementation brief.
- `scripts/sample_more.sh`: seeded baseline sampling through the existing SWE
  worker. Defaults to a dry run; `--run` launches real inference and Docker grading.
- `scripts/check_adapter.py`: standalone vLLM LoRA transfer check.

## Run without a GPU

From the repository root:

```bash
make -C training test
make -C training audit
make -C training dry-run
bash training/scripts/sample_more.sh
```

Dry runs do not load a model or claim training readiness. They write plans and report
missing datasets. With `--dataset`, they validate every supplied record and mask.
All current raw traces parsed: 106 SWE attempts / 100 tasks, and 129 Kaggle tasks.
Only SWE tasks may enter training. The effective manifest's reviewed labels win;
9 unknown grading outcomes stay unknown. Kaggle is audit/evaluation only.

## Isolated training environment

Create and install explicitly; these commands have **not** been run:

```bash
python -m venv envs/train
envs/train/bin/python -m pip install -r training/requirements.txt
```

GPU entry points require that exact environment and CUDA. Requirements are unpinned
because the target training environment does not exist yet; record and pin a tested
combination before a real run. DPO computes its NLL anchor directly and has no dependency on the TRL trainer API. Gemma 4 QAT loading
and LoRA transfer still require a compatibility smoke test. `--qlora` enables NF4
loading of a **bf16** base; do not combine it with a prequantized QAT base.

```bash
envs/train/bin/python training/scripts/train_dpo.py \
  --dataset artifacts/pairs/tokenized.jsonl --model /path/to/bf16-gemma \
  --rft-adapter artifacts/sft/R2-adapter --output artifacts/dpo --qlora

envs/train/bin/python training/scripts/train_grpo.py \
  --model /path/to/bf16-gemma --rft-adapter artifacts/sft/R2-adapter \
  --sampler-command training/configs/local_sampler.json --smoke --qlora

envs/train/bin/python training/scripts/train_graph.py \
  --model /path/to/bf16-gemma --rft-adapter artifacts/sft/R2-adapter \
  --sampler-command training/configs/local_sampler.json --smoke --qlora
```

`local_sampler.json` is a user-supplied JSON argv list, e.g.
`["/path/to/harness/python", "/path/to/instrumented_sampler.py"]`. The script appends
`--request <iteration/request.json> --output <iteration/rollouts.jsonl>` without a shell.
The request gives train task IDs, adapter path/hash, seed, G and iteration. The driver
must start/stop serving that adapter, sample groups, grade, compute costs
with train-only calibration, and emit the tokenized schema below. **That instrumented
sampler is not supplied:** existing swegemma logs lack the required response capture.
`sample_more.sh` samples the baseline only and is not this adapter-aware driver.

GPU ownership is sequential: sampling runs before the training model is loaded.
The driver must stop and join all vLLM workers before returning. Training then loads
both adapters, updates, saves, deletes the model/optimizer, collects garbage and
empties the CUDA allocator before the next sampling call. This avoids simultaneous
31B serving/training residency at the cost of model reload time; GPU validation is
still required. Both adapters initialize from the RFT checkpoint; later iterations
reload the saved policy while retaining the original RFT reference.

Incomplete groups with at least four rollouts are retained; smaller incomplete
groups are dropped. Metrics distinguish partial groups kept, incomplete groups
dropped, zero-variance groups, and entirely missing tasks. Unexpected tasks, stale
policies, and oversized groups still fail validation. No usable groups stops the
iteration without committing a checkpoint. R3 return/turn lengths must match.

Both trainers expose `--learning-rate` (default 1e-5). Planned GPU comparisons should
sweep 1e-5, 2e-5 and 5e-5, and compare graph `--reward R3_rtg` with
`--reward R3_traj` using separate output directories. No sweep has run.

Resume with the same arguments plus `--resume`. Resume starts after the last complete
iteration; partial iterations are resampled. Optimizer state resets each iteration. Older state files from the fixed-task loop
are incompatible with the new configuration signature; use a fresh output directory.
Dropout is disabled during DPO/GRPO likelihood comparisons so policy ratios are stable.
Adapters are saved at `<output>/policy` (DPO) or
`<output>/iteration-NNNN/adapter/policy` (GRPO). Run the transfer check separately in
the serving environment, after training has released GPU memory:

```bash
/path/to/vllm/python training/scripts/check_adapter.py \
  --model /path/to/qat-gemma --adapter artifacts/dpo/policy
```

## Verified token dataset contract

The current ATIF files **cannot yet be used as exact training examples**. Request
bodies exist for SWE, but response token IDs and rendered prompts do not. See
[`QUESTIONS.md`](../artifacts/QUESTIONS.md). Do not invent these fields from ATIF.

Each `turn` is one captured model invocation:

```json
{
  "input_ids": [1, 2, 3, 4],
  "assistant_mask": [0, 0, 1, 1],
  "template_roundtrip": true,
  "request_sha256": "<64 hex chars>",
  "response_sha256": "<64 hex chars>",
  "template_sha256": "<64 hex chars>"
}
```

`input_ids` must be the actual prompt plus response. Mask 1 marks only generated
assistant tokens, including thoughts and tool-call syntax; system/user/tool and old
assistant-history tokens are 0. The first token must be masked out. Max length is
32768; overlong examples are rejected rather than truncated in a way that invalidates
captured contexts. A producer must preserve system/first-user messages if it implements
verified truncation. Hashes are provenance supplied by a trusted capture producer;
these validators cannot independently prove a hash against absent raw captures.

GRPO rows contain `source: "swe_rebench"`, `task_id`, unique `rollout_id`, boolean
`solved`, bounded `cost`, `calibration_source: "swe_rebench"`, `group_id`,
`sampling_policy_sha256`, `turns: [turn,...]`, and `potentials: [0,...]` with one value
after each turn. For R1/R2 the potentials may be all zero. For graph rewards they
must come from symbols actually visited and gold relevance. A group is one task,
one sampling batch and one adapter. Unknown outcomes are rejected. R3_rtg advantages
normalize among siblings reaching the same turn index; unsupported singleton or
zero-variance positions are excluded. This turn-index alignment is not a claim that
those siblings share an identical environment state.

DPO rows contain `source`, `task_id`, `type` (`efficiency` or `competence`),
`variant: "cheap_trajectory_pair"`, `shared_prefix_sha256`, and `chosen_turns` /
`rejected_turns`. These are the full remaining continuations following the same
message prefix, scored on their actual logged per-turn contexts. The pair-selection
helper in `costagent.pairs` produces TRL-style message pairs with the longest common
prefix; conversion to verified tokens remains blocked on capture. It balances the
two pair types when both exist, and never pairs different tasks or sampling policies.

## Limits of this delivery

This is an isolated training-script implementation, not completion of every stage
in AGENTS.md. No training or sampling job was launched, no adapter was produced,
and no model compatibility or real five-iteration smoke result is claimed. Full
normalized cost extraction/calibration, exact chat-template round-trip, RFT training,
step-level replay DPO, and adapter-aware sampler integration remain open. No fabricated
pairs, token counts, graph snapshots or calibration file are produced to bypass those
prerequisites. The graph builder performs conservative AST name resolution and stops
on ambiguous duplicate qualified names or unparsable source files.

## Resolved-rollout SFT (user-authorized mixed sources, 2026-10-28)

`train_resolved_sft.py` trains a fresh LoRA adapter from resolved SWE-rebench and
Kaggle examples without requiring a prior RFT adapter. This explicitly supersedes
the original Kaggle holdout restriction for this separate experiment only. Existing
DPO/GRPO validation remains unchanged. Kaggle results are no longer held-out results
for this adapter.

SWE examples come from structured assistant messages in saved request histories;
Kaggle examples reconstruct single-tool ATIF turns. These are offline imitation
examples, not claims of exact historical token capture. Only the current assistant
completion is supervised. Tool results and historical assistant messages are masked.
The native local Gemma template must preserve the prompt prefix in both text and
tokens. Overlength examples are skipped without cutting away context or targets.

The current 8192-token dataset has 453 examples from 58 resolved rollouts (219 SWE,
234 Kaggle), with 81,822 target tokens. 730 overlength candidates and 29 template
prefix mismatches were skipped. This is a usable subset, not full trajectory coverage.

```bash
envs/train/bin/python training/scripts/train_resolved_sft.py --dry-run
nohup bash training/scripts/run_resolved_sft.sh --reuse-dataset \
  > artifacts/resolved-sft/nohup.log 2>&1 < /dev/null &
echo $! > artifacts/resolved-sft/train.pid
```

The created `envs/train` venv inherits installed packages from the local `blora`
environment; no harness packages were changed. The nohup launch was attempted and
exited with code 1 before model loading: this session has no exposed NVIDIA devices,
and its PyTorch CUDA build also reports an incompatible driver. No training steps
or adapters were produced. See `artifacts/resolved-sft/nohup.log` and
`process-status.txt`. The GPU host needs a working compatible CUDA runtime and
compressed-tensors>=0.15 installed in the training environment. QAT loading is
configured to decompress weights for training, requiring enough aggregate GPU RAM
for the 31B weights plus activations; it has not yet been tested on GPU.

The first host run passed CUDA matmul/backward and loaded the 31B model, then ran
out of memory in the default full-vocabulary float32 loss before an optimizer step.
The SFT trainer now uses the adapted Gemma backbone and computes next-token loss
only at assistant target positions, projecting 64 tokens at a time with activation
checkpointing. `--loss-chunk-size` controls this bound. Softcapping and token-mean
normalization are preserved. Launchers enable expandable CUDA allocator segments
by default. This addresses the observed loss-allocation failure; full GPU training
still requires a successful retry. Reuse the completed setup with:

```bash
nohup bash training/scripts/run_resolved_sft.sh --reuse-dataset \
  >> artifacts/resolved-sft/nohup.log 2>&1 < /dev/null &
```

The second host retry OOMed inside MLP/LoRA backward. The current default is 4096
context tokens and uses only 112 fitting examples from the original dataset
(64 SWE, 48 Kaggle, 44 tasks); no context or completion is truncated. See
`selection.json`. LoRA parameters/computation use bf16, saved forward activations
are offloaded to CPU, and unused frozen image/audio encoders reside on CPU.
`smoke_sft_cpu.py` checks this path on a tiny real Gemma4+PEFT model through an
optimizer update. Full-size GPU behavior remains unverified until the host retry.

Per-example progress appears immediately in nohup.log. `latest_metrics.json` is
written after each optimizer step. Adapters are saved after step 1 and every 5
steps. Forward/backward OOMs discard the entire accumulation batch, clear gradients,
and record skipped tasks in `oom_skips.json`; final metadata reports all skips.
No successful completion is reported if no optimizer step succeeded. No external
GPU process is killed to obtain memory.

## Archived-rollout DPO (separate experiment)

`costagent.archive_dpo` audits archived agent outcomes in addition to the final
indexes. Nine eligible pairs exist on `requests_7505`: six solved-over-budget-timeout
and three lower-tool-call preferences between solved runs. Five rollouts share
initial system/issue text, snapshot, Docker image, task bundle, model/adapter hash
and evaluation budgets. Reference/saved-gold runs and untrusted outcomes are excluded.
This corrects the narrower final-index finding of zero available preference pairs.

`artifacts/archive-dpo-v1/dataset.report.json` records eligibility and limitations.
All tool-action targets (including their recorded reasoning) are retained. Older
complete conversation blocks are removed to fit 8192 tokens. These are reconstructed
ATIF contexts, not exact historical captures. Terminal narratives are excluded from
this tool-action trajectory objective. Efficiency is a tool-call proxy, not the
blueprint's calibrated C. The fixed reference is our completed SFT adapter, not a
cost-selected R2 RFT model. This is not shared-prefix Q-estimated step-level DPO.

`train_archive_dpo.py` runs actual DPO with beta=.1, chosen-only NLL alpha=1
(`--no-nll` disables it), fixed SFT reference, identical policy initialization,
reference scores computed once per run, and exact two-pass per-turn backwards.
The proven bf16/offload/chunked-head path is reused. Defaults: one epoch, lr=1e-5,
one pair per optimizer step. Each completed pair saves adapter and optimizer state;
`run_archive_dpo.sh` resumes automatically from completed checkpoints. No failed
pair is silently skipped. Completed SFT artifacts are never overwritten.

From the host terminal:

```bash
nohup bash training/scripts/run_archive_dpo.sh \
  >> artifacts/archive-dpo-v1/nohup.log 2>&1 < /dev/null &
tail -f artifacts/archive-dpo-v1/nohup.log
```

The launcher records PID/status and takes the same project lock as SFT. It never
kills other users' processes or modifies the shared harness. Per-turn scoring and
backward progress are logged. Successful output is
`artifacts/archive-dpo-v1/adapter/policy`. One task and nine correlated pairs are a
DPO pilot, not evidence of generalization. Full-size DPO training and inference
transfer have not yet been verified. A tiny real Gemma4+PEFT DPO optimizer update
passed with nonzero policy gradients and an unchanged reference adapter.

## Five-epoch monitored DPO experiment

User authorized 5 epochs on 2026-10-29. `run_dpo_5ep.sh` creates the separate
`artifacts/archive-dpo-5ep/` experiment: 45 pair updates, effective batch 1 pair,
lr=1e-5, beta=.1, chosen NLL alpha=1, frozen completed-SFT reference. It does not
automatically extend to 10 epochs. The original adapters and nine-pair data remain
unchanged.

Stages are: fresh SFT baseline evaluation, then training and fresh evaluation after
each of five epochs. Four distinct-repository SWE tasks are selected deterministically
from prior baseline failures with locally cached images, excluding every SWE task
with a successful training rollout. The frozen manifest and identical sampling seeds
are reused across all six stages. This is a small failure-enriched development set,
not an unbiased final benchmark. Unknown grading outcomes stop the pipeline. No
images are pulled. Serving must load the adapter before training proceeds.

Evaluation uses the existing isolated SWE worker and publisher grading. vLLM uses
loopback port 8001 and 55% GPU memory; an occupied port causes a clean failure rather
than replacement of another service. Training and serving run sequentially in separate
processes. Cleanup addresses only child process groups launched by this evaluation
and containers bearing that attempt's unique label. All project launchers share a
lock. The job stops below 20GiB free space. Only epoch checkpoints and the latest
resumable pair checkpoint are retained in this new run to limit disk use.

```bash
nohup bash training/scripts/run_dpo_5ep.sh \
  >> artifacts/archive-dpo-5ep/nohup.log 2>&1 < /dev/null &
tail -f artifacts/archive-dpo-5ep/nohup.log
```

`progress.json` records the active stage; `comparison.csv` and `comparison.json`
record solve rate and calls for baseline/epochs. `training/epoch-N-training-metrics.json`
contains post-epoch training-pair margin/accuracy/NLL, explicitly not validation.
The final selection favors development solves, then calls among solved tasks, and
retains SFT on ties. Restarting the same launcher resumes saved training/evaluation
boundaries. Runtime serving/training integration remains unverified until host
execution; CPU tests and tiny real Gemma DPO smoke passed.

Update 2026-10-29: at the user's request, `run_dpo_5ep.sh` now runs five DPO epochs
DIRECTLY. Docker/vLLM/fresh grading are no longer launch prerequisites or epoch
hooks. `run_monitored_dpo.py` remains an optional separate orchestration entry point.
The default five-epoch launcher uses the prepared nine-pair dataset, fixed SFT
reference, compact epoch/latest checkpoints, and automatic resume, for 45 updates.
Its training completion marker is `artifacts/archive-dpo-5ep/training/complete.json`.
Training-pair diagnostics are not evidence of held-out task improvement.
