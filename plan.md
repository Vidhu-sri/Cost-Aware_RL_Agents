# PLAN.md: Cost-aware preference learning, architecture and implementation

Window: Oct 31 → **Nov 6 training freeze** → Nov 7–9 final eval and stats → **Nov 11 submit** (one day of buffer before the Nov 12 deadline).
Data today: 100 SWE-rebench rollouts and 129 Kaggle dev rollouts, with mixed resolved and unresolved outcomes. More are being collected.

## Hardware: one A100. This section overrides the rest of the file.

Everything below this section assumed a multi-GPU box. With **one A100**, serving, scoring, training and evaluation all share one GPU, one job at a time. Estimates are in ARCHITECTURE.md §3.4.

**Odds (said once):**
- Core paper (A0, A1, listwise, RLCD, cost-blind ablation, 1–2 seeds): about 50%.
- Contrastive-teacher arm: about 10%.
- Any online method: about 5%.

**Scope changes:**
1. **Reference = the base model, not RFT.** Preference arms start from a zero-initialized LoRA, so the policy equals the base exactly and r = 0 at step 0. RFT (A2) becomes an optional small arm: best-1 per task, 6 sampled turns per trajectory.
2. **Arms that stay:**
   - A0 base
   - A1 stop-loss prompt
   - **A6b listwise, soft targets, κ=5** (headline)
   - **A6d RLCD pairs, hard targets**
   - **ablation: A6b with κ=0** (cost-blind; tests whether cost-awareness matters)
   - optional A2-lite and a hard-vs-soft ablation if time allows
3. **Dropped:** A6e (teacher scoring doubles scoring cost), R3/graphs, all online methods, and A6a as a separate arm (it becomes the hard-target ablation on the same groups).
4. **Rounds:**
   - Round 1 needs **no scoring at all**: with p uniform, $c_i=\beta(1/n-w_i)-\tfrac{\alpha}{n_b}\mathbb 1[i=b]$.
   - Round 2 (rescore, then train) only for the headline arm, about 5 h of scoring.
   - One round with fixed coefficients is a single large step of the listwise loss, without its self-limiting property. Keep lr ≤ 2e-5 and 1 epoch.
5. **Training cut:**
   - only candidates in groups with mixed outcomes, or RLCD pairs that pass the gate (about 300)
   - per candidate: stratum-A turns + k=1 sampled turn
   - segment packing if the append-only check passes
6. **Evaluation cut:**
   - triage on all 129 tasks × 1 seed (about 2 h per arm)
   - a second seed only for A0, A1 and the best arm
   - **use the Kaggle 4×L4 notebooks** (competition-attached, internet off, quota at 2× rate) for extra seeds, so the A100 stays free for training
7. **Hard rule: vLLM and training never run at the same time.** Stop vLLM before training. Keep rollouts at concurrency 8–16, because tool and test execution is CPU-bound and leaves the GPU idle between calls.

**One-GPU queue** (each row is GPU-serial; CPU work runs alongside):

| When | GPU job | CPU / Codex |
|---|---|---|
| Oct 31 | proxy test; measure prefill tok/s, train tok/s, append-only check; then overnight: +3 rollouts/task (≈300) + RLCD (≈200) | data layer, builders |
| Nov 1 | A1 eval (129); train A6b κ=5, round 1 | train_pref, stats |
| Nov 2 | transfer check + triage A6b; train A6d | write Methods |
| Nov 3 | triage A6d; train κ=0 ablation | |
| Nov 4 | triage κ=0; round-2 scoring + training for the best arm | |
| Nov 5 | triage round-2; optional A2-lite | Kaggle: 2nd seeds of A0, A1 |
| Nov 6 | **freeze**; 2nd seed of the best arm | |
| Nov 7–9 | leftover seeds only | stats, figures, draft |
| Nov 10–11 | none | submit Nov 11 |

If the measured rollout rate is under 0.7 per minute, drop the κ=0 ablation's triage to a stratified 40-task subset and skip A2-lite.

---

**Odds before the one-A100 constraint (superseded by the section above):**
- Core paper, about 60%: baselines + RFT + DPO + listwise + RLCD on the 129 dev tasks with stats.
- Adding the contrastive-teacher arm: about 40%.
- Any online method (GRPO, routed SDPO, online contrastive): about 15%.

Build all of it in tiers. The core is never cut.

---

## 0. Fixed decisions

1. **Split.** SWE-rebench is the training pool. The 129 Kaggle tasks are **evaluation only**: baselines, final arms and the eval-side cost calibration. Kaggle tasks are never used in training data, pairs, groups or training calibration.
   - Fallback if the training data is too thin by Nov 3: train on `Textualize/rich` (48 tasks) and evaluate on fastapi + requests + httpx (81 tasks). Report that this costs statistical power.
2. **One preference trainer.** DPO, RLCD-DPO and listwise InfoNCE are all one loss over a group of candidates. A group of 2 with a one-hot target is exactly DPO. One script (`train_pref.py`) with different datasets and target modes gives every preference arm.
3. **Capture proxy first.** It sits in front of vLLM and logs the exact request and response for every model call. That gives exact training inputs (the template round-trip check) and, later, the sampler that online methods need. It is the critical path.
4. **Scoring in vLLM, gradients in torch.**
   - Sequence log-probs (reference, current policy, contrastive teacher) come from vLLM `prompt_logprobs`, which is prefill-only.
   - **Correction:** requests that ask for prompt log-probs probably can't reuse cached prefixes, so budget full prefill. THEORY.md §10.6 gives the budget formula, and §6.2 covers segment packing, which cuts the cost.
   - torch only does the gradient pass, on a sample of turns.
   - Mismatch acceptance test: THEORY.md §6.3.
5. **Cut order if behind:**
   1. online methods
   2. R3/Φ (code graphs for SWE-rebench)
   3. the contrastive teacher
   4. RLCD

   Never cut A0, A1, RFT, DPO, listwise, stats or the write-up.

---

## 1. Architecture

```
                          ROLLOUT LAYER (GPU: serving)
 tasks.jsonl (train | eval)
        │
        ▼
 swegemma eval --sandbox subprocess  (under guard.py)
        │  LiteLLM → http://127.0.0.1:8000/v1
        ▼
 capture_proxy :8000  ──logs──►  artifacts/capture/*.jsonl  (exact request/response per call)
        │
        ▼
 vLLM :8001  (QAT base, --enable-lora, max-loras 8, prefix caching; serves base + every arm adapter)
        │
        ▼
 results/<run>/  traces, patches, test_outputs, task_results.jsonl

                          DATA LAYER (CPU)
 join(traces, capture) ─► turns.parquet (exact input ids, assistant mask, per turn)
                       ─► trajectories.parquet (task, rollout, prompt variant, S, counts, C, R1/R2/R3)
 calibrate (train only) ─► configs/cost.yaml     graphs.py (optional) ─► S*, Φ per step

                          SIGNAL BUILDERS (CPU)
 rft_sets   groups   traj_pairs   rlcd_pairs   teacher_contexts (f+, f-)
        │
        ▼
                          SCORING (GPU: vLLM prompt_logprobs)
 r_ref (once, RFT adapter)   r_pol (per round, current adapter)   teacher ± (once, D_i)
        │
        ▼
                          TRAINERS (GPU: training)
 train_sft.py (RFT, A2) ─► train_pref.py (listwise ⊇ DPO; A6a/b/d/e) ─► [stretch: iterated online]
        │
        ▼
                          EVAL
 check_adapter (transfer) ─► build_submission ─► swegemma on 129 × seeds (multi-LoRA, arms in parallel)
 ─► stats.py ─► tables, Pareto, McNemar/Wilcoxon/bootstrap
```

**GPU split.** Serving (rollouts, scoring, eval) and training must not fight for memory. Dedicate GPUs to each, or run training only while no rollouts are running. Record your GPU count and type in `QUESTIONS.md`; the throughput estimates below assume the Kaggle 4×L4 figures and will differ on your server.

---

## 2. Arms

| Arm | Data | Method | Status |
|---|---|---|---|
| A0 | none | Base model | Core |
| A1 | none | Base + stop-loss prompt | Core |
| A2 | best-2 successes by R2 per train task | RFT (SFT). This is also the reference and starting policy for every preference arm | Core |
| A6a | sibling pairs from groups | `train_pref --targets hard` (= trajectory DPO + NLL anchor) | Core |
| A6b | full groups | `train_pref --targets soft --kappa {0, 5, 20}`. κ=0 is the cost-blind control | Core |
| A6d | RLCD paired runs (p+/p− prompts, gated) | `train_pref --targets hard`, prompt stripped (context distillation) | Core |
| A6e | groups + teacher scores | `train_pref --targets soft_teacher` (targets from R2 and the contrastive score D; all-fail groups by D) | Tier 2 |
| A3–A5 | online | Iterated GRPO with R1, R2, R3 | Stretch |
| A9 | online | Routed: GRPO-R2 on groups with a success, SDPO / contrastive on all-fail groups | Stretch |

**Ablations (cheap, core):**
- hard one-positive InfoNCE vs soft targets (the costly-success-as-negative failure)
- with vs without the NLL anchor
- κ=0 vs the best κ

**Key comparison:** A6d without the prompt must match or beat A1 with the prompt.

---

## 3. Step by step

### Step 0. Inventory (Oct 31, 2 h, CPU)
- Write `artifacts/data_report.md`. For each source (SWE-rebench, Kaggle):
  - distinct tasks
  - rollouts per task (min/median/max)
  - solve rate
  - median calls and tokens
  - whether traces contain thoughts, per-turn model input, `finish_reason` and compaction events
- **Decision rule:** if SWE-rebench has 1 rollout per task, there are no sibling groups yet, so Step 2a is mandatory before A6a/b/e. RLCD (2b) works either way.

### Step 1. Capture proxy (Oct 31, half a day, Codex)
`scripts/capture_proxy.py`: a transparent OpenAI-compatible passthrough. vLLM moves to :8001, and the proxy listens on :8000, where swegemma already points. It must not modify requests.

Sketch (Codex hardens it: non-JSON bodies, errors, log rotation):

```python
import json, time, uuid, httpx, uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse
UP = "http://127.0.0.1:8001"; LOG = open("artifacts/capture/calls.jsonl", "a", buffering=1)
app = FastAPI(); client = httpx.AsyncClient(timeout=None)

def log(rec): LOG.write(json.dumps(rec) + "\n")

@app.api_route("/{path:path}", methods=["GET", "POST"])
async def relay(path: str, req: Request):
    body = await req.body(); payload = json.loads(body) if body else None
    rec = {"id": uuid.uuid4().hex, "t": time.time(), "path": path, "request": payload}
    hdr = {"content-type": "application/json"}
    if payload and payload.get("stream"):
        async def gen():
            buf = []
            async with client.stream(req.method, f"{UP}/{path}", content=body, headers=hdr) as r:
                async for c in r.aiter_raw(): buf.append(c); yield c
            rec["stream"] = b"".join(buf).decode(errors="replace"); log(rec)
        return StreamingResponse(gen(), media_type="text/event-stream")
    r = await client.request(req.method, f"{UP}/{path}", content=body, headers=hdr)
    if payload is not None:
        try: rec["response"] = r.json()
        except Exception: rec["response_text"] = r.text
        log(rec)
    return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type"))

if __name__ == "__main__": uvicorn.run(app, host="127.0.0.1", port=8000)
```

- **Task attribution:** hash the problem statement found in the first user message (after `Problem Statement:`) and match it against `tasks.jsonl` and the SWE-rebench task file. Rollout attribution: run order plus the time window from `task_results.jsonl`; at `--concurrency 1` per proxy port it is unambiguous.
- **Acceptance test (the template round-trip check):**
  1. Run 1 task.
  2. Assert that the number of proxy records equals the number of model turns in the trace.
  3. For every record, render `tokenizer.apply_chat_template(request.messages, tools=request.tools, add_generation_prompt=True)` and assert the token count equals `response.usage.prompt_tokens` exactly. If it doesn't match, the training inputs would be wrong, so stop and fix it.
- Start every future rollout run through the proxy.

### Step 2. Collect more rollouts (start Oct 31, runs in the background through Nov 3)
All of it goes through the proxy and `guard.py`, with the competition budget (100 calls, 60 min).

- **2a Group sampling (train):**
  1. Run every SWE-rebench training task with G=4 at temperature 0.7 (diversity for groups; eval stays at 0.3).
  2. Then run 4 more for tasks with mixed outcomes or all successes.
  3. Stop sampling tasks that fail 8 of 8. They feed only A6e and SDPO.
- **2b RLCD runs (train):** 2 samples each with the p+ and p− system prompts:
  - **p+:** the stop-loss rules + "locate before reading; read only the line ranges you need; prefer `get_code_neighbors` to opening files; never repeat a call with identical arguments; run only the targeted test".
  - **p−:** "explore broadly before editing; read whole files; re-run the full test suite after every change".
- **2c Eval baselines:**
  - A0 on all 129 Kaggle tasks × 3 seeds. The existing 129 rollouts count as seed 1 if the config matches.
  - A1 on all 129 × 3 seeds.
- **Throughput estimate** (Kaggle 4×L4 measurements: about 8–20 s per tool call, about 40 calls per rollout):
  - about 6–14 min per rollout, so about 1 rollout/min at concurrency 8
  - 2a ≈ 800 rollouts ≈ 13 h
  - 2b ≈ 400 rollouts ≈ 7 h
  - 2c ≈ 774 rollouts ≈ 13 h

  Measure the real rate on your server in the first hour and rescale.

### Step 3. Data layer (Nov 1, Codex, CPU)
- `traces.py`:
  - join each trace step to its proxy record
  - write `turns.parquet`: `task_id, rollout_id, t, input_ids, assistant_mask, n_assistant`
  - write `trajectories.parquet`: `task_id, rollout_id, source, variant (base|p+|p-|adapter), solved, counts, nudges`
  - in `input_ids`, the assistant tokens are the exact generated tokens appended to the rendered prompt
- `costs.py`, `calibrate.py`:
  - counts: calls excluding free tools, tokens, unique files, test runs, duplicate reads
  - `nbar_k(q)` from base-prompt successes, **train only**
  - `w_k` from the positive regression, else the defaults
  - `c_max` at the 95th percentile
  - eval-side calibration computed separately, for reporting only
- `rewards.py`: R1, R2, R2-ungated, plus R3 if graphs exist. Tests come from the blueprint's worked examples.
- **Compute check:** log the total tokens per rollout over all turns. If `sum_t |x_t|` exceeds about 300k, turn sampling in Step 8 is mandatory.
- **Check whether earlier turns' thoughts are stripped from later contexts.** If they are not stripped and history is append-only between compactions, then one forward pass over the last turn of each compaction segment gives exact log-probs for every turn in that segment ("segment packing", a 5–10× saving). Use it if it holds.

### Step 4. RFT warm start, A2 (Nov 1–2, GPU)
1. **Data:** per training task, the best 2 successes by R2. This includes p+ successes with the p+ prompt swapped for the standard system prompt (context distillation).
2. **Train:** `train_sft.py`, LoRA r=16, α=32, all linear layers, assistant-only loss, from the bf16 base (QLoRA if needed).
3. **Check transfer immediately** with `check_adapter.py`: load the adapter on the QAT model in vLLM, generate one turn, and compare log-probs on 20 held-out training turns, bf16 vs QAT. If transfer fails, everything downstream is wasted, so fix this first. The fallback is training on dequantized QAT weights.
4. **Start the A2 eval** on 129 × 3 seeds in the background, using multi-LoRA vLLM so several arms evaluate concurrently.

### Step 5. Build preference data (Nov 2, Codex, CPU)
Every record is a group:
```json
{"task_id": "...", "group_kind": "sibling|rlcd",
 "candidates": [{"rollout_id": "...", "solved": true, "cost": 0.31, "r2": 0.85, "variant": "base",
                 "turn_ids": ["..."], "n_assistant": 4123}]}
```
- **Groups (A6b/e):** all base-prompt rollouts of a task, keeping groups with ≥2 candidates and ≥1 success.
- **Sibling pairs (A6a):** from each group, pick pairs in about a 1:1 mix:
  - efficiency pairs: both solve, ΔC > 0.1
  - competence pairs: one solves, one fails
- **RLCD pairs (A6d), gated:** keep (p+, p−) only if:
  - p+ solves and p− fails, **or**
  - both solve and C(p+) < C(p−) − 0.1

  Drop everything else. **Swap the p± system prompt for the standard one** in every turn's `input_ids`, then re-render.
- Write `artifacts/pref/{groups,pairs,rlcd}.jsonl`, with counts by kind and type in `data_report.md`.
- **Gate (Nov 3):** fewer than about 150 usable pairs or groups → spend Nov 3 on more RLCD runs (they manufacture contrast) or switch to the rich-split fallback.

### Step 6. Scoring service (Nov 2, Codex + GPU)
`scoring.py`: sequence log-prob of a candidate's assistant tokens under a given adapter, via vLLM:

```python
def seq_logprob(model: str, input_ids: list[int], mask: list[int]) -> float:
    out = requests.post(f"{VLLM}/v1/completions", json={"model": model, "prompt": input_ids,
          "max_tokens": 1, "temperature": 0, "prompt_logprobs": 0}).json()
    plp = out["choices"][0]["prompt_logprobs"]                  # position 0 is None
    return sum(plp[i][str(input_ids[i])]["logprob"] for i in range(1, len(input_ids)) if mask[i])
```

- **Verify the response format** of the installed vLLM on one turn. The dict keys and the `prompt_logprobs` semantics vary by version.
- **What it computes:**
  - `r_ref` once per candidate under the RFT adapter. Cache it.
  - `r_pol` per training round under the current adapter, loaded at runtime with `VLLM_ALLOW_RUNTIME_LORA_UPDATING=True` and `/v1/load_lora_adapter`.
- **Known approximation:** scores come from the QAT model, while gradients come from the bf16 model. The margin is computed entirely in one model, so the bias cancels to first order. State this in the paper.

### Step 7. Contrastive teacher scores for A6e (Nov 3, Tier 2)
- **Teacher:** the RFT adapter, frozen. Two contexts per turn, each a feedback block inserted into the system message, under 1.5k tokens, with the 32k limit asserted:

| Group | f+ | f− |
|---|---|---|
| mixed | cheapest success's action list + files in S* | a failure's failing tests (log tail) + its action list |
| all success | cheapest success's action list | costliest success's actions, redundant reads and spins marked |
| all fail | gold-patch diff + S* (training tasks only) | the group's common failing tests + mistakes |

- **Score:** `D_i = (r_teacher+(τ_i) − r_teacher−(τ_i)) / n_assistant_i`, with the per-token mean controlling for length.
- **Build f± leave-one-out:** never from candidate i's own logs or actions (THEORY.md §8). Before using D, its leave-one-out AUROC for predicting success must be ≥ 0.65; otherwise drop A6e.
- **Cost-saving option:** score only the turns up to and including the first edit (the localization phase). Report which variant you used.

### Step 8. `train_pref.py`, the unified listwise trainer (Nov 2–4, Codex writes it, GPU runs it)
For a group with successes $\mathcal S$, scores $r_i = r^{pol}_i - r^{ref}_i$ and model distribution $p = \mathrm{softmax}(\beta r)$:

- **Target modes** (THEORY.md §4):
  - `hard`: one-hot on the cheapest success (pairs reduce to DPO)
  - `soft` (**default; corrected**): $w=\mathrm{softmax}(R2/T)$ over **all** candidates, $T=0.1$. The optimum stays finite and the success/failure gate is preserved (Theorem 1). Sweep $\kappa=\lambda/T$.
  - `soft_teacher`: $w_i \propto \exp(R2_i/T + \kappa_2 \bar D_i)$. For all-fail groups, $w_i \propto \exp(\kappa_2 \bar D_i)$ with the loss scaled by $\mu_{\text{fail}} \le 0.3$.
- **Coefficient per candidate:** $c_i = \beta(p_i - w_i) - \frac{\alpha}{n_b}\mathbb 1[i=b]$, where $b=\arg\max w$, $\alpha=1$ and $\beta=0.1$.
- **Gradient pass with turn sampling.** For each candidate, sample $k$ of its $T_i$ turns uniformly (k=4 default, or every turn if $T_i \le k$). This gives an unbiased gradient estimate:

```python
for i, cand in enumerate(group):
    for turn in random.sample(cand.turns, min(k, len(cand.turns))):
        lp, m = logps(model, turn)                         # torch, policy adapter, dropout off
        ((c[i] * len(cand.turns) / min(k, len(cand.turns))) * lp[m].sum() / accum).backward()
```

  With segment packing (Step 3), sample segments instead of turns.
- **Rounds:**
  - round 0: policy = a copy of the RFT adapter, so r=0 and p is uniform
  - each round: one pass over all groups, optimizer step every 4 groups, then save the adapter, reload it into vLLM and rescore `r_pol`
  - 3 rounds by default
  - lr 2e-5, LoRA r=16
  - log the loss, mean margin, $\sum_i w_i \log p_i$, and the chosen-sequence log-prob. A falling chosen log-prob is likelihood displacement: raise α.
- **Arms from this one script:** A6a (pairs, hard), A6b (groups, soft, κ∈{0,5,20}), A6d (rlcd, hard), A6e (groups, soft_teacher), the ablations (`--no-nll`, `hard` on groups).

### Step 9. Evaluate every arm (rolling from Nov 2, final Nov 6–9)
1. For every adapter: `check_adapter.py`, then `build_submission.py`. Use the sampling config:
   - `temperature: 0.3`
   - `max_output_tokens: 16384`
   - `thinking_config: {include_thoughts: true, thinking_budget: 4096}`
   - no `thinking_level`
2. Run swegemma on the 129 tasks with `--sandbox subprocess` under `guard.py`.
3. **Seeds:** 1 seed per arm as soon as it is trained, for triage. 3 seeds for A0, A1, A2 and the best 3 preference arms after the freeze.
4. Serve all arms from one vLLM with multi-LoRA (max 8) and run arms concurrently.
5. `stats.py`, from `artifacts/results.parquet` with one script for everything:
   - McNemar on solve
   - Wilcoxon + bootstrap 95% CI on calls, tokens and cost per solved task
   - 5-point non-inferiority margin
   - Pareto plot (resolve rate vs mean calls) with CIs and hypervolume
   - spin fraction, time to first correct localization

### Step 10. Stretch online methods (only after Nov 4, only if Steps 1–8 are green)
The proxy is the sampler, so the iterated loop is: serve the adapter, run swegemma on a batch of training tasks with G=8 through the proxy, build groups, update. Try these in order:
1. **Iterated listwise:** rerun Step 8 on fresh on-policy groups from the best adapter. This is the cheapest "online" result.
2. **GRPO-R2:** the fixed `train_grpo.py` (per-iteration task sampling, minibatches, assert turn/advantage alignment, drop rather than crash on incomplete groups).
3. **Routed SDPO / online contrastive (A9):** GRPO-R2 on groups with a success; on all-fail groups, the sampled-token teacher advantage $\log q^+ - \log q^-$ (contrastive) or $\log q - \log p$ (SDPO).

Anything without a dev eval by **Nov 6 night** stays out of the paper's results.

### Step 11. Write-up (parallel, from Nov 1)
- **Methods (Nov 2–3):** cost, R2 gate, listwise loss and its reduction to DPO, RLCD gating, contrastive teacher.
- **Results:** generated from `stats.py` output.
- **Limitations:** QAT/bf16 scoring split, turn sampling, small training set, dev set size.
- **Dates:** draft by Nov 9, submit Nov 11.

---

## 4. Schedule

| Date | GPU (serving) | GPU (training) | Codex / CPU |
|---|---|---|---|
| Oct 31 | proxy up → start 2a, 2b | idle | Step 0, Step 1, fix `train_dpo` → start `train_pref` |
| Nov 1 | 2a, 2b continue; 2c (A0, A1) | RFT on current successes | Step 3 data layer, tests |
| Nov 2 | A2 eval (1 seed); scoring service | transfer check; RFT v2 on new data | Step 5 builders, Step 6 scoring |
| Nov 3 | scoring (r_ref, teacher ±); more RLCD if gated | A6a, A6d | Step 7 contexts, stats.py |
| Nov 4 | triage evals (1 seed per arm) | A6b κ sweep, ablations | Step 10 code if green |
| Nov 5 | triage evals | A6e; stretch online smoke | writing |
| Nov 6 | **freeze**; start final evals (3 seeds) | stretch only if evaluating tonight | writing |
| Nov 7–9 | final evals | none | stats, figures, draft |
| Nov 10–11 | reruns for missing cells only | none | polish, **submit Nov 11** |

## 5. Gates
- **Nov 1 noon:** the proxy round-trip test passes. If not, fall back to reconstruction from traces and mark every preference arm "approximate inputs".
- **Nov 2:** the RFT adapter transfers to QAT. If not, fix this before anything else.
- **Nov 3:** ≥150 usable groups or pairs. If not, more RLCD runs or the rich-split fallback.
- **Nov 4:** at least one preference arm beats A2 on cost per solved task at 1 seed. If not, freeze the scope at core arms and spend the GPU time on seeds.

## 6. Open questions (answer in `artifacts/QUESTIONS.md`)
1. GPU count and type on the server, and whether serving and training can run at the same time.
2. Is "100 SWE-rebench" 100 tasks × 1 rollout, or 100 rollouts across fewer tasks?
3. Do the existing traces contain thoughts and per-turn inputs, or only ATIF steps?
4. What temperature were the existing rollouts sampled at?