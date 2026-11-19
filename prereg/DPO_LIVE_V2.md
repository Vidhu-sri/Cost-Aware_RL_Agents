# Pre-registration: fresh A0 vs DPO live evaluation, v2

**Frozen before any new model request.** The confirmatory run will not begin until
this file is committed, the model/adapter provenance gate is passed, and the GPU
is visible and can be monitored. Existing traces and results remain immutable.

## Question and arms

Compare a fresh A0 run with a fresh run using the pilot DPO adapter, paired on the
84 task IDs frozen for the confirmatory evaluation. DPO means the DPO adapter
alone: no method router, no adapter routing, and no phase controller. All other
execution, prompt, tool, model, sampling, and task-budget settings match the
confirmatory A0 recorded in `prereg/frozen.json` and its source run:

- five-minute agent limit, 100 billed tool calls, 50 turns, and 60-second command
  timeout;
- model seed 42, temperature 0.2, top-p 0.95, thinking budget 4096, and output
  cap 16384, using the frozen sampling and agent files;
- the same model, server flags, Docker images, task snapshots, offline network,
  command executor, and timeout-aware verifier as the confirmatory A0.

The A0 main adapter is the frozen sample adapter. The DPO main adapter is the
epoch-005 checkpoint identified below. Tool adapter and all non-adapter agent
files are byte-identical between arms. No results are inspected to choose or
alter the task order, settings, or analysis.

### DPO artifact identity gate

The pilot run at
`costagent/artifacts/mixed-temperature-v1/evaluation/paper40-20261106a-DPO-test-seed-42`
records the served `main_lora` root in its `served_models.json` as
`/tmp/costagent-pipeline-20261102/artifacts/mixed-temperature-v1/dpo/epoch-005`.
That path resolves to
`costagent/artifacts/mixed-temperature-v1/dpo/epoch-005` in this checkout.
The DPO submission provenance points to the same source checkpoint and pilot
evaluation; its recorded archive SHA-256 is
`8520c647932ce0d483202739ef3ce270583cf221312b17078917b395f1a0e148`, matching
the current `submission.zip`. The archive's `adapters/main_lora/adapter_model.safetensors`
SHA-256 is `0c5fe9518135b51ee846bad843a356f2026c99d5793082c93b8bba90e1a498a1`;
the checkpoint's `adapter_model.safetensors` at the recorded served path has the
same SHA-256. Its `adapter_config.json` SHA-256 is
`2d24af75f2f30c2207966e7dedef68b18eccc20203c68a8907fe351883cebde8`.

The run's per-task `agent_snapshot` hash `dcbedd…` is the submission-side
snapshot and is not used as the server adapter identity: the pilot's
`served_models.json` points to the separate DPO checkpoint above. Before the
first smoke request, the runner must recheck the checkpoint files and archive
hashes against the values in this section and persist the checks in the new run
manifest. **Stop without sending a model request if either hash differs, the
recorded path no longer resolves to this checkpoint, or the provenance chain
cannot be verified.**

## Tasks, shuffle, and paired execution

Use exactly the 84 task IDs in `prereg/frozen.json` from the confirmatory A0
design. Shuffle those IDs with Python `random.Random(20261119).shuffle`. After
the shuffle, use the same RNG instance and one `getrandbits(1)` coin flip per
task to choose the within-task arm order. Run the two arms back-to-back for each
task. The randomization schedule is written and hashed before the first smoke
request. Each attempt gets a fresh task checkout, container, and agent session.
No attempt runs concurrently with another attempt. There are 168 confirmatory
attempts. Smoke attempts are separately labeled, excluded from all analyses,
and do not count among the 168.

Two smoke task IDs are fixed in advance: `fastapi_14246` and `rich_4070`.
Exercise both arms on each smoke task. Verify the DPO identity, required log
fields on every turn, task-container execution, and that the final live diff
snapshot exactly matches the submitted/extracted patch. Do not use smoke results
as outcomes or include them in the confirmatory analysis.

## Per-call working-tree snapshots

After every `edit_file`, `write_file`, or `run_command` that may change files,
save the task checkout's binary-safe `git diff` as a monotonically numbered
snapshot, together with task, arm, attempt, triggering tool-call number, diff
SHA-256, timestamp, and snapshot duration. Save empty diffs too. Never change the
tool result, model messages, tool-call count, or next action because of a
snapshot. Snapshot time is logged separately and excluded from the agent's
five-minute active budget; preserve both active-budget and total wall-clock
times. Do not modify repository files visible to the agent for snapshotting.
The smoke acceptance check compares the final snapshot to the exact submitted
or extracted patch; report normalization rules and any mismatch without repair.

## Turn-level telemetry

For each model turn record, without changing the request or response:

- attempt, task, arm, turn index, request start/end timestamps, and generation
  wall time;
- `prompt_tokens` and `completion_tokens` from that response's vLLM `usage`
  field; separately record reasoning-token usage when returned;
- if reasoning-token usage is absent, record it as absent in raw telemetry and
  count tokens within the logged thinking span offline with the Gemma tokenizer;
- at request start, vLLM `/metrics` running-request and waiting-request gauges,
  with raw sample and scrape timestamp;
- tool/action type, tool-call index, tool execution wall time, observation
  length, and whether the action repeats the previous call, when present in the
  original trace.

Smoke acceptance requires these telemetry fields for every model turn in all
four smoke attempts. Missing usage, metrics, or trace fields is an infrastructure
failure: stop before confirmatory attempts, preserve evidence, and document the
gap. Never impute missing token usage as zero. The load-adjusted H1 model is
specified below; raw generation time remains the primary H1 measurement.

## Outcomes and interpretation

Use the same timeout-aware verifier and outcome interpreter as the frozen
confirmatory A0. A pair is interpretable only when both arms have valid terminal
verification results. Verified pass is a solve, valid failed verification is a
non-solve, and verification/environment errors are unknown, not failures.
Timeout flags are recorded separately and do not override a verified result.
Submit status is an explicit `submit_patch` call in the trace, not inferred from
patch presence. Action shares use the frozen action mapping in
`AGENTS.md`/`costagent` and retain the complete action denominator.

## Pre-registered analyses

### Primary

Compare DPO vs fresh A0 verified solves on interpretable task pairs using the
exact two-sided McNemar test. Report each arm's solves and unknowns, the two
discordant counts, exact p-value, and paired task IDs. Do not drop timeout-with-
verified-pass pairs. Do not compare arms until all 168 attempts have terminal
records.

### Secondary outcome and cost analyses

- Paired Wilcoxon signed-rank tests for tool calls and total prompt-plus-
  completion tokens per task; report ties/zeros and the paired task set.
- Calls per solve and tokens per solve for each arm, with 20,000 paired
  task-cluster bootstrap resamples using NumPy `default_rng(20261119)`. Preserve
  task pairs in each resample; report undefined/zero-solve draws and suppress a
  finite interval if at least 2.5% of draws have a zero denominator.
- DPO vs the existing confirmatory A0 and DPO vs the existing confirmatory
  router are descriptive only, using the same 84 task IDs where records are
  comparable. State any unmatched, unknown, or missing records. These are not
  additional confirmatory tests.

### Confirmatory process hypotheses

Pilot directional values are context only, not guaranteed effects. Define one
paired observation per task and calculate task-level arm differences. Use
one-sided tests in the stated direction and Holm correction across H1–H4 at
family-wise alpha 0.05. Report raw and Holm-adjusted p-values. For H1–H3, use a
paired task-level permutation test on the log ratio or share difference; obtain
the reported ratio/difference confidence interval with 20,000 paired task
bootstrap resamples (seed 20261119). H4 uses one-sided exact McNemar. Report
the pilot point estimates alongside the new estimates:

- **H1:** geometric mean generation seconds per turn, DPO/A0 `< 1` (pilot 0.72).
  Report raw generation ratio and a mixed-effects load-adjusted arm ratio from
  log generation seconds with task random intercept plus request-start running
  and waiting request counts as covariates.
- **H2:** geometric mean tool calls per attempt, DPO/A0 `> 1` (pilot 1.28).
- **H3:** per-task share of actions that are edits is higher for DPO (pilot
  19.0% vs 14.8%). The test statistic is the paired difference in edit share.
- **H4:** explicit-submit probability is higher for DPO (pilot 9/40 vs 4/40),
  using one-sided exact McNemar on paired task indicators.

If a model or test cannot be fit because of separation, missingness, or
insufficient variation, report that failure and the available descriptive
estimate; do not substitute a different test after seeing results.

### Exploratory solve/process model

Fit mixed-effects logistic regression of verified solve on log generation
seconds per turn and explicit-submit indicator, with task random intercept.
Use only interpretable attempts and report sample size, convergence, estimates,
intervals, and warnings. Label the analysis exploratory; no causal interpretation.

### Found-then-lost and timeout-with-pass

After CPU verification of each saved intermediate diff, among valid failed
attempts report the proportion with at least one intermediate snapshot that
passes the hidden verifier, by arm, with Wilson 95% CI and a 20,000-resample
task-cluster bootstrap CI (seed 20261119). For each such attempt classify what
followed the first passing snapshot from the trace: further edits, timeout,
reversion, continued without reversion, or no final submission. Keep categories
mutually interpretable and include counts and example task IDs. Among verified
solves report the timeout-with-pass proportion and Wilson 95% CI, by arm.

## Execution, monitoring, and resumability

Run sequentially under `nohup` with one owned vLLM process and a resumable
manifest, one terminal done-marker per arm/task, and durable per-attempt logs.
Capture and record PID plus process creation time for owned processes and
explicit Docker run labels/container IDs. Monitor before starting the worker.
Cleanup may stop only this run's process group and remove only containers whose
ownership labels match this run. Never prune Docker globally or signal other
users' jobs. Stop on resource pressure, absent monitoring, cleanup failure,
identity drift, or missing required telemetry. The host has rootless Docker
with cgroup v1 and no enforced aggregate memory/CPU limits; reported RSS is
observed usage, not a hard cap.

Resume only unfinished slots. Do not rerun terminal attempts. Replace only a
crash that has no terminal record, and only after recording the crash evidence;
link the replacement to the original slot. Do not replace timeouts, valid
failures, no-patch outcomes, or verification errors. Preserve partial traces,
patches, snapshots, and cleanup records on every interruption.

## CPU-side work

Before analyzing outcomes, grade every pilot attempt marked ungraded that has a
patch with the same timeout-aware verifier. Do not change the original traces
or outcomes; write derived grading records separately and report exactly how
many pilot solve labels change. Separately compare
`router40-20261108a` with `paper40-20261106a` and the confirmatory run for config,
harness version, serving flags, timeout accounting, and maximum output tokens.
Report exact differences and whether the documented differences can explain
the 7 vs 58 timeout counts; do not claim explanation without evidence.

## Reporting and deviations

Write `results/dpo_live_v2/REPORT.md` only after all confirmatory attempts are
terminal and all intermediate snapshots have been verified. Include this
preregistration commit, exact DPO artifact identity, flow of task IDs, primary
and secondary results, confidence intervals, all H1–H4 tests and Holm
correction, exploratory model, found-then-lost cases, timeout-with-pass, pilot
grading changes, run comparisons, and every deviation/anomaly. Export
per-attempt, per-turn, and per-snapshot CSVs plus a schedule/provenance manifest.
Report crashes without terminal records and any allowed replacements explicitly.

## Deviation history and v2 execution gates

The completed `dpo_live` run is retained as a protocol deviation. Its telemetry
wrapper closed over the pre-configuration LiteLLM object; after ADK cloned the
model and attached thinking settings, the wrapper invoked the original object.
Actual HTTP requests from both arms lacked `chat_template_kwargs.enable_thinking`
and `thinking_token_budget=4096`, although the saved YAML specified them. The
snapshot hook also patched `swegemma.evaluate.asyncio`, while the hard
300-second timeout lives in `swegemma.harness.agent_runner.asyncio`; snapshot
time therefore reduced the effective agent wall budget. The earlier run is not
analyzed as a DPO confirmatory test. Its raw results and deviation report remain
untouched.

V2 instruments the configured model clone after the ADK resolver has attached
thinking parameters. An HTTP-level guard must reject and durably log **every**
model request lacking `enable_thinking=true` or `thinking_token_budget=4096`;
the controller must stop on any such violation. The snapshot hook must extend
the actual agent runner's hard deadline by each measured snapshot duration and
shift the context budget clock by the same amount; all adjustments are logged.
Snapshots remain outside the billed tool-call and turn budgets. Unit tests must
pass before launch. The two smoke tasks must verify all requests carry the
thinking fields, first-response completion tokens are in the confirmatory
range (median near 160 rather than near 20), turn-cap terminations do not
dominate wall-clock terminations, and every final snapshot equals the extracted
patch. Report those findings before the first non-smoke attempt. If any gate
fails, stop and retain the smoke evidence.

The task order, per-task coin flip, arms, DPO checkpoint, H1-H4 definitions,
analyses, seeds, replacement rule, CPU snapshot verification, and resource
constraints above are unchanged. The v2 output root is `results/dpo_live_v2/`;
all slots, manifests, traces, and report are separate from `dpo_live`.

A separate exploratory, descriptive analysis may compare confirmatory A0 with
`dpo_live` A0 on the same tasks: paired solves and exact McNemar, completion
tokens, and termination reasons. It must be labeled an accidental thinking-off
contrast confounded by snapshot-time accounting. It is not a v2 arm analysis.

## Fixed stop rule (registered before arm results are examined)

If all 168 attempts are not terminal by 2026-11-20 14:00 IST, stop at the next
task boundary and analyse only tasks where both arms are terminal. The stop time
is fixed in advance and does not depend on outcomes.

## Prospective design amendment, 2026-11-19 (supersedes conflicting text above)

This amendment was committed before examining any outcomes by arm. Seven
non-smoke v2 attempts had terminal records at the pause; their existence was
counted, but their arm-specific results were not examined. The watchdog and
controller were stopped before this amendment; no further attempt may start
until the request-equivalence gate below passes.

- Run **DPO only** on the 84 frozen confirmatory task IDs, in the existing
  seed-20261119 shuffled task order. Use one DPO attempt per task. The paired
  control is the **existing confirmatory A0** attempt for the same task, not
  a fresh v2 A0 attempt. The fresh v2 A0 attempts already completed are retained
  and described separately, without using them as the primary control.
- Before the next DPO attempt, compare the first model request from the new
  DPO run with the first confirmatory A0 request for the same task, field by
  field. The adapter is the only permitted difference. A missing request or
  any other difference stops execution and is reported; no field is silently
  normalized or waived.
- H1 is generation seconds per turn, available in both runs. Completion
  tokens per turn are reported for DPO only, descriptively; they are not a
  paired H1 outcome.
- The fixed stop is **2026-11-20 14:15 IST**, replacing the earlier 14:00
  time. At the next task boundary after that time, stop DPO generation and
  analyze only DPO tasks with terminal records paired to their existing
  confirmatory A0 records. The stop time is independent of observed outcomes.

All other preregistered DPO settings, snapshot and telemetry hooks, owned
process monitoring, CPU verification, and replacement rule remain in force.
