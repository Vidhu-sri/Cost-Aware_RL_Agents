# AGENTS.md: Cost-Aware Agent RL, implementation brief for Codex

Paper deadline: 2026-11-12 23:59 UTC. Training freeze: Nov 6. Final eval and figures: Nov 7–9.
Source of truth for the method: the blueprint doc "Cost-Aware Agent RL: Implementation Blueprint". This file translates it to the real harness and data. Where they disagree, this file wins (the blueprint predates the real harness).

## 0. Ground rules
- Before writing any parser, open real files and print their structure. Do not guess formats. You produced these runs, so check them.
- Never modify anything under `data/` or the raw run directories. Write derived artifacts under `artifacts/`.
- Never install packages into the harness env (the swegemma subprocess sandbox runs task tests on it). Training code gets its own env (`envs/train`): torch, transformers, peft, trl, accelerate, datasets, pandas, scipy, statsmodels, scikit-learn, networkx, unidiff, pyarrow, matplotlib, pytest.
- Every module gets unit tests in `tests/` that run on CPU with no model, no GPU, no sandbox. GPU scripts get a `--dry-run` that builds datasets and configs and exits.
- One CLI per stage (`python -m costagent.<module> ...`), plus Makefile targets. All outputs deterministic given a seed.
- When a decision below can't be made from the data, stop and write the question in `artifacts/QUESTIONS.md` instead of guessing.

## 1. Data and splits (critical)
- **Train:** the 100 SWE-rebench runs. **Eval only:** the Kaggle dev runs (129 tasks: fastapi, rich, requests, httpx). Never put a Kaggle dev task into any training set, pair set or reward calibration used for training.
- First task: write `artifacts/data_report.md` with, per source:
  - number of distinct tasks
  - rollouts per task (min/median/max)
  - solve rate
  - median tool calls and tokens
  - which fields each trace has: per-turn prompt tokens, generated tokens, thoughts, logprobs, compaction events, `finish_reason`
  - whether SWE-rebench tasks have gold patches and code graphs available
- If rollouts per task is 1, trajectory-pair DPO and GRPO advantages are impossible without more sampling. Flag this in the report and write `scripts/sample_more.sh` that reruns swegemma with K samples per task (seeded) on the train tasks.

## 2. Real harness facts (replace the blueprint's tool names)
- **Tools:** `run_command`, `read_file(filepath, start_line, end_line)`, `edit_file`, `write_file`, `get_code_neighbors`, `search_similar_code`, `get_code_subgraph`, `submit_patch`, `get_status`.
- **Free tools:** `submit_patch` and `get_status` don't count as calls.
- **Map to the blueprint's actions:**
  - search = `run_command` matching grep/rg/find/ls
  - test = `run_command` matching pytest, `python -m pytest`, unittest, tox or `python <file under tests/>`
  - read = `read_file`, or `run_command` doing cat/sed -n/head/tail/nl
  - edit = `edit_file`/`write_file`
  - graph = the three graph tools
- **Duplicate read:** a `read_file` (or a cat/sed read) whose line range overlaps a range of the same file already read, with no edit to that file in between. Also count identical consecutive `run_command` strings ("spin").
- **Format trap:** the harness compacts context at 14,336 tokens. Training examples must use the exact context the model saw at each turn, not the full history. If the trace logs per-turn model input, use it. If it doesn't, reconstruct it and document how in the data report.
- **Model and adapters:** `gemma-4-31b-it-qat-w4a16-ct` served by vLLM. Adapters are PEFT `.safetensors` with rank ≤128 (use 16), targeting q,k,v,o,gate,up,down.

## 3. Repo layout
```
src/costagent/
  traces.py      # raw trace -> list[Step]; both sources -> one schema
  costs.py       # n_k counts, duplicate detection, C(tau)
  calibrate.py   # nbar_k(q), w_k fit, c_max -> configs/cost.yaml
  graphs.py      # load/build code graph, gold symbols S*, relevance map, symbols_touched
  rewards.py     # R1, R2, R2-ungated, R3 (whole-trajectory and per-step return-to-go)
  chatdata.py    # Step list -> per-turn chat examples with assistant-token masks
  rft.py         # select R1/R2/R3 trajectory sets -> SFT jsonl
  pairs.py       # trajectory-pair DPO and step-level pair builder
  grpo.py        # group advantages, iterated GRPO data + loss
  router.py      # router labels + Gemma-LoRA router subagent config (lowest priority)
  stats.py       # McNemar, Wilcoxon, bootstrap, Pareto, hypervolume, figures
  build_submission.py
scripts/
  train_sft.py   train_dpo.py   train_grpo.py   sample_more.sh   eval_arm.sh   guard.py
configs/
  cost.yaml  splits.yaml  arms/*.yaml  train/{sft,dpo,grpo}.yaml
tests/
artifacts/       # all derived data, gitignored
```

## 4. Module specs

### 4.1 traces.py
```python
@dataclass
class Step:
    task_id: str; rollout_id: str; t: int
    tool: str; args: dict; action: str  # action in {search, read, edit, test, graph, other, submit, status}
    prompt_tokens: int; gen_tokens: int; obs_tokens: int; thought_tokens: int
    files_touched: list[str]; read_ranges: list[tuple[str, int, int]]
    symbols_touched: list[str]          # filled by graphs.py
    is_dup_read: bool; is_spin: bool; counts_as_call: bool
    gen_text: str                        # exactly what Gemma generated this turn (thoughts + tool call)
    model_input: list[dict] | None       # chat messages the model saw this turn, if recoverable

@dataclass
class Trajectory:
    task_id: str; rollout_id: str; source: str  # "swe_rebench" | "kaggle_dev"
    repo: str; steps: list[Step]; solved: bool; patch: str; nudges: int; wall_s: float
```
- `load_run(dir) -> list[Trajectory]`. Write one parquet table at `artifacts/steps.parquet` and one at `artifacts/trajectories.parquet`.
- Tests: duplicate detection (overlap vs non-overlap, edit in between resets it), action mapping for 15 representative `run_command` strings, free tools excluded from calls.

### 4.2 costs.py
- `counts(traj) -> dict`: calls (excluding free tools), tokens (generated plus observation), unique files, test runs, duplicate reads, nudges.
- `cost(traj, nbar, w, cmax)` follows the blueprint formula:
  - `C = Σ_k w_k · min(n_k / max(nbar_k(q), 1), c_max) / c_max`, with `Σ w = 1`
  - output is in [0,1]
  - when q has no baseline success, fall back to the global median

### 4.3 calibrate.py
- `nbar_k(q)`: median over the **base policy's successful** rollouts per task, computed separately for train (SWE-rebench) and eval (Kaggle dev). Training rewards use train calibration only.
- `w_k`: non-negative regression (`LinearRegression(positive=True)`) of wall-clock seconds on counts, normalized to sum to 1. If the fit is degenerate, fall back to `{calls: .35, tokens: .35, files: .1, tests: .15, dups: .05}` and log it.
- `c_max`: the 90th–95th percentile of the baseline ratios (default 0.95). Write `configs/cost.yaml` and a calibration table in `artifacts/`.

### 4.4 graphs.py
- **Kaggle repos:** load `data/graphs/<repo>.json`. Print its schema first and match node naming to what `get_code_neighbors` returns.
- **SWE-rebench repos:** build a graph in the **same schema** from the repo at `base_commit` using `ast`: nodes for modules, classes and functions; edges for DEFINED_IN, CALLS (best-effort name resolution) and IMPORTS.
- `gold_symbols(patch, repo_snapshot) -> set[str]`: use unidiff hunks, then the enclosing function, class or module via `ast` on the pre-patch file. File nodes are always included.
- `relevance(graph, gold, gamma_g=0.5) -> dict[node, float]`: multi-source BFS on the undirected view, giving `gamma_g ** hops`.
- `symbols_touched(step)`: map read ranges and edited ranges to the enclosing nodes via `ast`, and add graph-tool node args, resolved with the harness's 4-tier rule (exact, suffix, case-insensitive, substring).
- Tests: a toy repo with a known patch gives the expected S* and the hop distances 0, 1 and 2.

### 4.5 rewards.py
- `R1 = S`
- `R2 = S · (1 − λC)`, with λ ∈ [0,1)
- `R2_ungated = S − λC` (ablation)
- **Two R3 variants, both required** (per the blueprint's caveat):
  - `R3_traj = R2 + η·Σ_t[γΦ(s_{t+1}) − Φ(s_t)]`, which with γ=1 equals `R2 + η·(Φ_T − Φ_0)`
  - `R3_rtg`: per-step returns-to-go `G_t = R2 + η·Σ_{u≥t}[γΦ(s_{u+1}) − Φ(s_u)]`, used for per-step advantages
- Φ(s) = max relevance over symbols seen so far, so Φ is non-decreasing. Assert `η < 1 − λ`.
- Defaults: λ=0.5, η=0.1, γ=1.0. λ grid: {0, 0.1, 0.25, 0.5, 0.75, 0.9}.
- Tests, from the blueprint's worked examples:
  - λ=0.5: a solve with C=0.2 scores 0.9, a solve with C=0.6 scores 0.7, any failure scores 0
  - ungated: a failure with C=0.1 scores −0.05, a failure with C=0.9 scores −0.45
  - Φ example (auth.py at 2 hops, then token.py): 0.25, then 1.0; bonus = η·1.0

### 4.6 chatdata.py
- Turn each trajectory into per-turn examples: `(messages_seen_by_model, assistant_completion)`. The assistant completion is the exact generated text, including the tool-call syntax and thoughts if logged.
- Use the Gemma 4 chat template with the same tool schemas the harness sends. Verify by re-rendering one logged turn and diffing it against the logged model input: they must match except for whitespace. If they can't be made to match, write that in QUESTIONS.md.
- The mask is 1 only on assistant-generated tokens. Tool outputs, system and user messages are 0.
- Long contexts: truncate from the left, but keep the system prompt and first user message. Max length is 32,768.

### 4.7 rft.py (arm A2, Tier 1)
Write three SFT sets, all from train tasks only:
- **R1:** all successful trajectories
- **R2:** the best 2 successes per task by R2
- **R3:** the best 2 successes per task by R3_traj

Output jsonl goes to `artifacts/sft/{R1,R2,R3}.jsonl`, with a stats table of tasks, examples, tokens and mean cost.

### 4.8 pairs.py (arm A6, Tier 2)
- **Trajectory-pair DPO (the cheap variant; label it that way in outputs).** For sibling rollouts of the same task, build two pair types in roughly equal numbers:
  - efficiency: both solve, chosen has lower C, with gap > δ_C (default 0.1)
  - competence: chosen solves, rejected fails
- **Pair format.** The prompt is the longest common prefix of the two message histories (often just system + issue). Chosen and rejected are the full remaining continuations, tokenized from the same prefix so the masks line up.
- **Step-level pairs (shared prefix, the valid variant).**
  - Branch states: in solved trajectories, the step just before the first correct localization (the first step with Φ = 1 or seen ∩ S* ≠ ∅).
  - At each branch state, sample K=8 next actions, run m=8 continuations from each through swegemma, and compute Q̂ = mean R3.
  - Keep (a+, a−) when Q̂(a+) − Q̂(a−) > δ and a+ has at least one solve.
  - Implementation: a replay mode that rebuilds the state by re-executing the logged tool calls in a fresh sandbox, then continues sampling. Ship it with a `--max-states` budget.
  - If replay can't be made to work, ship the builder plus a test on a mocked environment, and write why in QUESTIONS.md.
- Output: `artifacts/pairs/{traj,step}.jsonl` in TRL format: `prompt`, `chosen`, `rejected`, plus metadata (`task_id`, `type`, ΔC, ΔQ).

### 4.9 grpo.py and train_grpo.py (arms A3–A5, Tier 3)
- **Advantages.** For each task's group of G rollouts: `A_i = (R_i − mean) / (std + 1e-6)`. Groups with zero std are dropped and counted. With `R3_rtg`, use per-step advantages on that step's tokens.
- **Loss** (per token, Gemma-generated tokens only):
  `L = −mean_tokens[min(ρA, clip(ρ, 1−ε, 1+ε)A)] + β·KL(π_θ‖π_ref)`, with ε=0.2 and β=0.04. The reference is the RFT adapter.
- **Iterated GRPO loop (default implementation; works with the real harness):**
  1. Serve the current adapter in vLLM.
  2. Run swegemma on a batch of train tasks with G=16 samples each.
  3. Parse, compute rewards and advantages.
  4. Compute old log-probs with a forward pass of the sampling adapter. This is also the ρ denominator, since traces lack logprobs.
  5. Run 1–2 epochs of the clipped update.
  6. Save the adapter, then repeat.
  The loop is resumable. It logs reward mean, solve rate, mean C, KL and clip fraction per iteration.
- **Optional integration:** a SkyRL or verl-agent environment adapter whose observations are the swegemma tool outputs and whose reward comes from rewards.py. Build it only after the iterated loop passes a 5-step smoke test.
- `--smoke`: 5 iterations, 4 tasks, G=4. The acceptance check is that it runs end to end and writes an adapter.

### 4.10 Training scripts
- `train_sft.py`: TRL `SFTTrainer`, LoRA r=16, α=32, dropout 0.05, all linear layers, assistant-only loss via the masks, bf16, gradient checkpointing. Must support QLoRA on the bf16 base and also loading the QAT checkpoint if PEFT allows it.
- `train_dpo.py`: TRL `DPOTrainer`, starting from the R2 RFT adapter (reference = the RFT adapter). β=0.1, with the NLL anchor via `rpo_alpha` (check the installed TRL version for the exact arg name; default 1.0). Ablation flag `--no-nll`.
- Every script saves a PEFT dir containing `adapter_config.json` and `adapter_model.safetensors`. After training, run a check that loads the adapter on the quantized model in vLLM (`--enable-lora --max-lora-rank 128`) and generates one turn. This is the adapter transfer check; do it first, on the first adapter.

### 4.11 router.py (lowest priority; cut first if late)
- Labels per step: phase (localize/read_span/edit/run_test/submit, mapped from the action), think level (off/low/high by thought tokens, terciles), ready_to_edit (whether the step is before or after the first edit).
- State string under 400 characters: issue gist, last action, observation tail, steps used, tokens used, unique files seen, whether the failure was reproduced.
- Output: a label dataset for Laya fine-tuning (paper-only arm A7) and the config for a submittable Gemma-LoRA router subagent (arm A8). No training run is required unless time allows.

### 4.12 stats.py
- Paired over tasks: McNemar on solve (`statsmodels`), and Wilcoxon plus bootstrap 95% CI on cost per solved task, tool calls and tokens.
- Non-inferiority margin: 5 points.
- Pareto plot: resolve rate against mean calls per task, one point per arm and λ, with CIs. Also the hypervolume.
- Extra metrics:
  - time to first correct localization
  - localization precision
  - spin fraction
  - nudge count
- One script regenerates every table and figure from `artifacts/results.parquet`.

### 4.13 Arms and eval
- `configs/arms/`:
  - A0: base
  - A1: stop-loss prompt (no repeated identical calls)
  - A1b: `max_tool_calls` ∈ {10, 20, 30, 50, 100}
  - A2: RFT R1, R2 and R3
  - A3–A5: GRPO with R1, R2 and R3
  - A6: DPO trajectory-pair and step variants
  - A8: router subagent
- `eval_arm.sh` builds the submission via `build_submission.py` and runs swegemma on all 129 dev tasks with `--sandbox subprocess`, 5 seeds, under `guard.py`.
- `guard.py` kills a shard's process groups that exceed a wall-clock cap or 4 GiB RSS, because verification uses `-o timeout=0`.
- `build_submission.py` writes `agent.yaml` (with adapter), `eval_config.yaml`, prompts and `configs/sampling.yaml`:
  - `temperature: 0.3`, `max_output_tokens: 16384`
  - `thinking_config: {include_thoughts: true, thinking_budget: 4096}`, with no `thinking_level`
  It then validates with `adk_submission` and asserts the size is under 3 GiB.

## 5. Order of work and acceptance
1. `data_report.md` + traces.py + costs.py + tests. Done when both sources parse with zero exceptions and the counts look sane.
2. graphs.py + calibrate.py + rewards.py + tests. Done when `cost.yaml` exists and all worked-example tests pass.
3. chatdata.py + rft.py, and train_sft.py with `--dry-run`. Done when the template round-trip diff passes and the three SFT sets are written.
4. pairs.py (trajectory pairs), and train_dpo.py with `--dry-run`. Done when pair counts are reported by type.
5. grpo.py + train_grpo.py `--smoke` (mocked env in tests; real smoke on GPU).
6. Step-level pair builder with replay.
7. stats.py + arms + eval_arm.sh + build_submission.py.
8. router.py.

After each stage, append a short entry to `artifacts/PROGRESS.md`: what ran, the numbers, what's open.
