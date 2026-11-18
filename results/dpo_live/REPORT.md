# Fresh A0 versus DPO live evaluation

**Status:** All 168 attempts are terminal. This file was opened before batch
completion at the user's request on 2026-11-18, a reporting-timing deviation
from `prereg/DPO_LIVE.md`. A subsequent read-only audit found a material
execution deviation: the live telemetry wrapper dropped the configured thinking
parameters from the actual model requests in both fresh arms. The task schedule
was unchanged, but the intended configuration was **not** preserved. The
within-run outcome counts below are retained as observations under the actual
configuration; they are not a clean replication of the confirmatory A0 protocol.

## Read-only audit: why fresh A0 differs from confirmatory A0

The [336-row termination audit](../../artifacts/dpo_live_termination_audit.csv)
gives **every selected attempt** in both 84-task runs: run, arm, task ID,
termination reason and raw error, harness task wall seconds (`outcome.json`'s
`duration_seconds`, including non-agent work), LLM turns, billed tool calls,
patch bytes, result, and source trace/outcome paths. No original result was
edited. Each arm has 84 unique task IDs, and the A0 task sets match exactly.
`explicit_submit` means a recorded patch-submission time with no agent
error; `other_model_error` is the saved context-window error, not a model solve
failure or a wall timeout. No selected attempt hit the 100-call cap or had a
recorded worker crash.

| Run / arm | n | Wall clock | Turn cap | Call cap | Explicit submit | Model/config error | Other | Mean wall s | Mean turns | Mean calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Confirmatory A0 | 84 | 50 | 0 | 0 | 25 | 9 | 0 | 277.6 | 23.1 | 21.9 |
| Confirmatory router | 84 | 58 | 1 | 0 | 25 | 0 | 0 | 288.1 | 23.7 | 21.3 |
| Fresh A0 | 84 | 4 | 53 | 0 | 26 | 1 | 0 | 166.1 | 39.7 | 36.4 |
| Fresh DPO | 84 | 7 | 49 | 0 | 25 | 1 | 2 | 171.2 | 39.8 | 37.0 |

Fresh DPO's two `Other` records are one completed-without-submit and one
completion without an agent error or submission timestamp; the CSV preserves
their exact raw fields. The frequently cited 44 fresh-A0 `no_patch` cases are
the mutually exclusive *verification category*. There are **45 zero-byte
patches** in raw fresh-A0 outcomes: one was categorized `failed` after a test
run despite having no patch. Fresh DPO analogously has 39 zero-byte patches,
but 37 in the `no_patch` category.

### Effective configuration and mechanism

| Setting | Confirmatory A0 | Fresh A0 |
|---|---|---|
| Recorded source commit | `ee4777ba`; prereg `2508c60` | `ee4777ba`; prereg `6e3a72c` |
| Worker implementation | `docker_eval_worker.py` SHA-256 `6dbb7aa1…` | Same path SHA-256 `127bd753…`, with live instrumentation |
| Installed harness | `swegemma 0.2.10`; frozen 642 installed-package file hashes | Same package version; all 642 hashes still match the confirmatory frozen manifest. No separate upstream harness Git commit was recorded. |
| Nominal budgets | 300 s agent, 100 billed tools, 50 LLM turns, 60 s per command, 900 s supervisor | Same |
| Counting | `SwegemmaContext` increments billed calls on budgeted tools and LLM turns on model events; free submit/status calls do not consume tool budget | Same harness counters; snapshot Docker exec bypasses them |
| Sampling file | 0.2 temperature, 0.95 top-p, seed 42, 16,384 max output tokens, 4,096 thinking budget, `include_thoughts: true` | Byte-identical effective sampling-file hash and values |
| **Actual model request** | 84/84 first A0 requests had `chat_template_kwargs.enable_thinking=true` and `thinking_token_budget=4096` | **0/84** first A0 requests had either field; they also lacked `reasoning` in all 84 first responses |
| vLLM | Same base model, 32,768 context, 0.60 GPU fraction, `max-num-seqs=1`, 4,096 batched tokens, Gemma 4 tool/reasoning parsers, FlashInfer sampler disabled; main/tool LoRAs | Same core flags; additional DPO LoRA loaded (even in A0 slots). Confirmatory A0 has 64 server-start logs across the interleaved run; fresh batch has 9 starts in one append-only server log. |
| Snapshot hook | None | After each edit/write/shell tool, direct Docker `git diff` capture; mean recorded snapshot time 12.3 s per A0 attempt (max 50.4 s). It is not a billed tool call. |

The cause of the missing thinking fields is localized. `LiveRecorder.wrap_model`
stores an instance-level async wrapper that closes over the **original bound**
`LiteLlm.generate_content_async`. The ADK submission resolver then shallow-copies
the model and attaches thinking/seed `extra_body` to the **clone**. The copied
instance wrapper still invokes the original model, whose `extra_body` has no
thinking settings. A CPU-only reproduction showed: clone has
`enable_thinking=true` and budget 4096, original does not, and the cloned
wrapper still calls the original. Saved HTTP requests independently confirm
the omission: all 84 first confirmatory-A0 requests include the fields, and
none of the 84 first fresh-A0 requests do. First-response median completion
tokens fell from 162.5 to 22; reasoning content was present in 84/84 old and
0/84 fresh first responses. Across attempts, mean completion tokens fell from
5,445 to 2,422, while mean turns rose from 23.1 to 39.7. This explains the
direction and much of the size of the wall-time/turn-cap shift. Different
sampled trajectories and server lifecycle may also contribute; the saved data
do not isolate their effects.

The snapshot hook tries to exclude its time from the budget by advancing
`context.agent_start_time`. It also tries to reschedule a 300-second
`asyncio.timeout` through `swegemma.evaluate.asyncio`, but the hard deadline
used by `run_agent_sandbox` lives in `swegemma.harness.agent_runner.asyncio`.
That proxy does **not** reschedule the hard timeout. Thus snapshot work remains
inside the hard 300-second wall deadline and the 900-second supervisor, even
though the context's soft elapsed-time check discounts it. Snapshot duration
was recorded for 79 A0 attempts; missing manifests are not treated as zero.
This asymmetry is another protocol deviation, but it would tend to increase
wall-time pressure, opposite the observed collapse in timeout count.

### Three matched trace endings

Each pair below is an old A0 wall timeout **with a nonempty extracted patch**
versus a fresh A0 run ending at the 50-turn cap **without a patch**. These are
the final five saved ATIF agent events in chronological order. The full event
arguments, observations, and outputs remain in the linked traces.

| Task / event | Confirmatory A0 | Fresh A0 |
|---|---|---|
| `rich_3930` 1 | #10 `read_file rich/cells.py`, ok | #48 `grep -r "grapheme" /workspace/rich/cells.py`, exit 1 |
| 2 | #11 `edit_file rich/cells.py`, ok | #49 same grep, exit 1 |
| 3 | #12 `read_file rich/cells.py`, ok | #50 same grep, exit 1 |
| 4 | #13 `edit_file rich/cells.py`, ok | #51 same grep, exit 1 |
| 5 | #14 `edit_file rich/cells.py`, ok; then wall timeout, 2,309-byte patch | #52 same grep rejected by turn-budget check; zero-byte patch |
| `fastapi_14371` 1 | #15 `read_file fastapi/params.py`, ok | #48 `pytest ... -k "validation_alias" --no-xfail-first`, exit 4 |
| 2 | #16 `read_file fastapi/params.py`, ok | #49 same pytest command, exit 4 |
| 3 | #17 `edit_file fastapi/dependencies/utils.py`, ok | #50 same pytest command, exit 4 |
| 4 | #18 `pytest -v tests/test_request_params/test_body/test_list.py`, exit 0 | #51 same pytest command, exit 4 |
| 5 | #19 `find tests/test_request_params -name "*.py"`, exit 0; then wall timeout, 920-byte patch | #52 same pytest command rejected by turn-budget check; zero-byte patch |
| `rich_3063` 1 | #16 `write_file 「repro_trailing.py」`, ok | #48 `python3 -c ...` markup probe, exit 0 |
| 2 | #17 `write_file repro_trailing.py`, ok | #49 same probe, exit 0 |
| 3 | #18 `python3 repro_trailing.py`, exit 0 | #50 same probe, exit 0 |
| 4 | #19 `write_file repro_escape.py`, ok | #51 same probe, exit 0 |
| 5 | #20 `python3 repro_escape.py`, exit 0; then wall timeout, 3,402-byte patch | #52 same probe rejected by turn-budget check; zero-byte patch |

Trace pairs: [`rich_3930` old](../confirmatory/A0/rich_3930/attempt-0/evaluation/tasks/rich_3930/traces/trace_rich_3930.json) / [fresh](attempts/rich_3930/A0/evaluation/traces/trace_rich_3930.json), [`fastapi_14371` old](../confirmatory/A0/fastapi_14371/attempt-0/evaluation/tasks/fastapi_14371/traces/trace_fastapi_14371.json) / [fresh](attempts/fastapi_14371/A0/evaluation/traces/trace_fastapi_14371.json), [`rich_3063` old](../confirmatory/A0/rich_3063/attempt-0/evaluation/tasks/rich_3063/traces/trace_rich_3063.json) / [fresh](attempts/rich_3063/A0/evaluation/traces/trace_rich_3063.json).

**Verdict:** `dpo_live` did **not** meet “every other setting identical to the
confirmatory A0.” The material deviations are the dropped thinking parameters,
the model-wrapping/telemetry path that caused them, the snapshot hook's
non-equivalent deadline accounting, the extra loaded DPO adapter and different
server restart pattern. The same nominal YAML, temperature, seed, output cap,
tool/turn caps, model weights, and installed harness are not sufficient to make
these runs protocol-equivalent. The fresh A0-versus-DPO comparison still shares
the same flawed request path within its own run; it cannot support a claim that
DPO behaves as preregistered under the confirmatory A0 configuration.

## Pilot configuration note

The `paper40-20261106a-DPO-test-seed-42` pilot used the DPO checkpoint through
`run_paper40_after_contrast.py` → `evaluate_checkpoint.py` → the standard Docker
evaluation worker. The pilot launcher did not set `COSTAGENT_ROUTER`, which is
the worker's switch for installing a phase controller. The distinct
`router40-20261108a` launcher explicitly set `COSTAGENT_ROUTER=phase-v1`.
Therefore the paper40 DPO arm ran **without** the phase controller. The presence
of an `agent_phase.json` file in each task directory is not evidence that the
controller was active; that file records the agent outcome/timeout phase.

## Pilot comparisons and token provenance

Cross-arm comparisons using the historical pilot arms may use trace-based
calls, turns, timing, and actions. Historical pilot token totals are
**unreconciled**: raw model-response usage is absent or incomplete for several
arms, and saved response-usage sums disagree with outcome totals in others.
They are not used for cross-arm pilot comparisons. This restriction does not
apply to the fresh live run, whose per-turn usage is captured and audited.

## Token-usage sensitivity analysis

After all 168 terminal records exist, run
`python costagent/scripts/dpo_live_token_sensitivity.py`. It refuses to compare
arms on an incomplete batch. For each missing usage row, the sensitivity total
replaces any fallback token estimate with the median observed
prompt-plus-completion tokens per response **within that arm**. The script
preserves raw totals, checks per-turn sums against each
attempt's recorded total, and writes `results/dpo_live/token_sensitivity.json`.
It compares raw and imputed paired Wilcoxon token results and 20,000-resample
paired task-bootstrap tokens-per-solve intervals. Missing usage can represent
failed requests without a billed token count; median imputation is a sensitivity
scenario, not a reconstruction of actual billing.

The numerical analysis appears below.

## Final execution and grading

The preregistration is commit `6e3a72c`. The saved schedule contains 84 task IDs,
one A0 and one DPO attempt per task, in the seeded paired order. All **168/168**
non-smoke attempts have terminal records, with no duplicate task-arm slot. Four
separately labeled smoke attempts passed the telemetry and final-snapshot checks
and are excluded. The batch completed at **04:10 IST, 19 November 2026**. The
owned vLLM process exited and port 8001 closed. All 168 attempt records report
successful owned-container cleanup; no outer-deadline timeout is recorded.
The largest observed task-container process-tree RSS sample was 0.218 GiB;
this is a monitor observation, not an enforced cgroup memory cap. Mean recorded
controller wall time was 179 seconds across the 166 attempts with a duration
field; two recovered terminal records lack that field.

The DPO adapter was the epoch-005 weight with SHA-256
`0c5fe9518135b51ee846bad843a356f2026c99d5793082c93b8bba90e1a498a1`.
The local settings were seed 42, temperature 0.2, top-p 0.95, 5-minute agent
session, 100 tool calls, 50 turns, 60-second tool command timeout, and 900-second
outer deadline. DPO had no phase or method router. The controller was resumed
after an interruption; two terminal records were recovered from their preserved
result directories without another model attempt. See `run_manifest.json` and
`progress.jsonl` for provenance and resume events.

| Arm | Verified pass | Verified fail | No patch | Grading unknown | Agent timeout | Timeout with pass | Mean wall time/attempt |
|---|---:|---:|---:|---:|---:|---:|---:|
| Fresh A0 | 11/84 | 25 | 44 | 4 | 4 | 0 | 175 s |
| Fresh DPO | 9/84 | 33 | 37 | 5 | 7 | 1 | 183 s |

“No patch” is a known non-solve for the primary paired analysis. The nine
`could_not_interpret` records are unknown outcomes, not model failures. This
leaves **79 interpretable pairs** and five pairs excluded because at least one
arm has unknown grading. The fresh A0 pass rate is 13.1% (Wilson 95% CI
7.5–21.9%); DPO is 10.7% (5.7–19.1%). These marginal intervals are descriptive;
the paired test below is primary.
If “valid terminal verification” is read strictly as requiring tests to have
run in both arms, 35 pairs remain; the same four discordant pairs give the same
McNemar p-value. Excluding known no-patch attempts therefore does not change
the primary test, although it changes the denominator and selects on patch
generation.

## Preregistered primary outcome

**Protocol caveat:** The arithmetic below compares the two fresh arms as they
actually ran, with thinking parameters absent from both. It does not test the
preregistered comparison under the confirmatory A0 request configuration.

On the 79 interpretable pairs, A0 alone solved `fastapi_11194`, `fastapi_9555`,
and `rich_3043`; DPO alone solved `fastapi_14349`. The other 75 pairs were
concordant. The paired DPO-minus-A0 solve-rate difference is **−2.53 percentage
points**; a 20,000-resample paired task bootstrap interval is **[−7.59, +2.53]
points**. Exact two-sided McNemar **p = 0.625**. The live evaluation therefore
does not establish a resolution improvement for DPO over fresh A0.

## Cost and token sensitivity

| Metric | Fresh A0 | Fresh DPO | Paired test / interval |
|---|---:|---:|---|
| Mean billed tool calls/attempt | 36.43 | 37.02 | Wilcoxon p = 0.837; 49 exact ties |
| Calls per verified solve | 278.2 | 345.6 | DPO−A0 bootstrap 95% CI [−69.9, +365.2] |
| Mean recorded tokens/attempt | 379,011 | 374,819 | Wilcoxon p = 0.176; 15 exact ties |
| Recorded tokens per verified solve | 2,894,268 | 3,498,308 | DPO−A0 bootstrap 95% CI [−808,525, +3,623,340] |

The token denominator includes all attempts, while the solve denominator is
verified passes. The 7,099 non-smoke request telemetry rows include **65 rows
without vLLM usage** (34 A0, 31 DPO). Recorded totals agree exactly with the
sum of per-turn logged values, but missing usage may mean unrecorded billing.
These are observed or fallback token counts, not a complete bill.

In the requested sensitivity analysis, each missing-usage row's fallback value
was replaced by the median observed tokens per response in that arm: 9,205 for
A0 and 9,040 for DPO. Mean tokens/attempt become **382,737** and **377,960**;
paired Wilcoxon **p = 0.177**. Tokens/solve become **2,922,720** and
**3,527,628**, with paired bootstrap DPO−A0 95% CI **[−821,783, +3,653,019]**.
Neither token conclusion changes: the paired per-task test is not significant
and the tokens-per-solve interval includes zero under both treatments. See
`token_sensitivity.json`. Pilot token totals remain unreconciled and are not used
here.

For context only, the earlier confirmatory run on the same 84 IDs recorded
18 A0 and 21 method-router passes, mean calls 22.14 and 22.62, respectively.
Against fresh DPO, there are 76 mutually interpretable task records for the old
A0 (DPO 9 passes, old A0 17; DPO-only 1, old-A0-only 9) and 79 for the old
router (DPO 9, old router 21; DPO-only 0, old-router-only 12). These are
descriptive cross-run comparisons with different controller/serving conditions,
**not** substitutes for the paired fresh A0 control or additional tests.

## Confirmatory process hypotheses

**Protocol caveat:** The recorded contrasts below are retained for audit, but
the missing thinking parameters invalidate their interpretation as tests of
the preregistered confirmatory process hypotheses.

The pilot values were hypothesis-generating: generation-time ratio DPO/A0 0.72,
call ratio 1.28, edit-action shares 19.0% versus 14.8%, and explicit-submit
attempts 9/40 versus 4/40. The fresh results are:

| Hypothesis | Fresh estimate | 95% paired-task bootstrap CI | One-sided permutation/exact p | Holm-adjusted p |
|---|---:|---:|---:|---:|
| H1, generation seconds/turn ratio DPO/A0 < 1 | 1.022 | [0.951, 1.093] | 0.727 | 1.000 |
| H2, calls/attempt ratio DPO/A0 > 1 | 1.026 | [0.958, 1.101] | 0.246 | 0.984 |
| H3, edit-action share DPO−A0 > 0 | −1.33 points | [−4.09, +0.98] points | 0.835 | 1.000 |
| H4, explicit-submit probability DPO > A0 | 25/84 vs 26/84 | 5 DPO-only, 6 A0-only | 0.726 | 1.000 |

None of H1–H4 is supported after Holm correction. The H1 task-level ratio
weights tasks equally. A turn-level Gaussian random-intercept fit on log
seconds, adjusted for request-start running-request count, converged on 7,096
turns and 84 tasks and estimated DPO/A0 **1.041 [1.009, 1.074]**. Waiting-request
count was zero throughout and could not be used as a covariate. This fit weights
tasks with more turns more heavily and points in the opposite direction to the
pilot's faster-DPO hypothesis. It does not override the preregistered task-level
test. See `load_adjusted_H1.json`.

The exploratory task-random-intercept logistic model of verified solve on log
mean generation time and explicit submit was attempted on 159 interpretable
attempts from 80 tasks. Although the optimizer returned a convergence flag, the
intercept hit its parameter bound and the random-intercept SD inflated to 11.17;
the model is **not reliably identified**. No coefficient or causal association is
interpreted. See `exploratory_logit.json` for the failed fit diagnostics.

## Intermediate patches and timeout-with-pass

There are 3,145 saved non-smoke snapshots, all with `status=ok`. Among the 139
known failed/no-patch attempts, 2,806 candidate snapshots reduce to 222 unique
(task ID, diff SHA-256) verification keys. All 167 unique **nonempty** candidate
diffs received a valid failed verification; **none passed**. The other 55 unique
keys are empty diffs that the patch-file verifier cannot grade as patches;
all their owned containers cleaned up. Thus the observed found-then-lost count
is **0/69 A0** and **0/70 DPO** failed attempts. Wilson 95% upper bounds are
5.27% and 5.20%, respectively. A 20,000-resample task-cluster bootstrap is
[0, 0] for both arms because there are no observed cases; it does not rule out
unseen cases. There are no passing-intermediate-state trace excerpts to show.

One of 20 verified solves carried an agent-timeout flag: DPO 1/9 (Wilson 95%
CI 2.0–43.5%); A0 0/11 (0–25.9%). A timeout flag does not negate a verified
passing patch.

## Data files and limits

`per_attempt.csv`, `per_turn.csv`, `per_snapshot.csv`, and
`snapshot_verification.csv` are the row-level exports. `analysis_summary.json`,
`token_sensitivity.json`, `load_adjusted_H1.json`, and
`exploratory_logit.json` hold derived statistics. Each attempt directory retains
its full trace, model-response capture, patch, test output, settings, and monitor.
The pilot regrade plan listed 10 eligible patches. The 12 retained verifier
result directories include initial/retry records; none passed (some timed out in
the test environment), so no pilot solve count increased. The separate
`router40_comparison.md` documents serving flags, output-cap, and timeout
accounting differences; those do not establish a causal explanation for the
pilot router's lower timeout count.

The main limitation is small discordance: only four interpretable pairs differ
in pass status. Single-seed results, nine unknown attempt grades, 65 missing
usage rows, and a non-identifiable exploratory model further limit inference.
The pilot speed effect and higher edit/submit rates did not replicate here.
