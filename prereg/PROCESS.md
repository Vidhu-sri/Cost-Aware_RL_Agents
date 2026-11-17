# Preregistered exploratory process analysis

Status: frozen before process-metric extraction or outcome analysis.

## Scope and sources

This is an exploratory analysis of existing local traces only. It will not
start model inference, use the GPU, alter original result files, or interact
with currently running jobs. The intended pilot cohort is the 40-task set with
arms A0, A1, A2, DPO, A9, and router. The confirmatory cohort is the paired
84-task A0/router evaluation. Source files, unique attempt IDs, missing
records, and exclusions will be listed in the report before results are
interpreted. If a source cohort is absent or incomplete, report that as a
limitation; do not silently substitute tasks or arms.

All analyses are exploratory. Task is the resampling unit. Confidence
intervals use 20,000 task-cluster bootstrap resamples with seed 20261118,
keeping all arms and turns for a sampled task together. Where an explicitly
requested mixed-effects model converges, report its estimate as well; do not
replace a failed or singular model with an unregistered alternative without
labeling the change.

## Frozen trace extraction rules

Create one per-call record in original trace order. A call's tool is read for
`read_file`; shell or test for `run_command`; edit for `edit_file` and
`write_file`; graph for code-graph tools; submit for `submit_patch`; and other
for status or unrecognized tools. A shell call is a test when its command
matches the harness's recognized pytest, unittest, tox, or test-file command
patterns. A repeated call is an exact repeat of the immediately preceding
call's tool name and canonicalized arguments.

Use logged usage fields without inferring unlogged tokens. Completion and
prompt tokens come from the call's recorded usage object. Thinking tokens are
reported only when a distinct reasoning/thinking token field is explicitly
present; otherwise mark them missing. Generation time is the model/tool-call
event's recorded elapsed seconds. Tool execution time is the matching
observation's recorded elapsed seconds. Observation length is its UTF-8
character count. Missing fields remain missing and are counted; they are not
imputed. A model turn is an agent step; when a step contains multiple tool
calls, retain one call row per tool call and do not duplicate turn-level token
or generation usage in attempt totals.

For each attempt, report agent turns, tool calls, mean logged thinking tokens
per turn, mean generation seconds per turn, mean tool-execution seconds per
turn, time and turn index of first edit, explicit `submit_patch`, agent
timeout, no-patch status, and verified outcome. A timeout is an agent/session
timeout recorded in the agent result or supervisor record. Test timeout or
test-environment error is not an agent timeout. No patch means the recorded
submitted/final patch is empty. A verified outcome is taken only from the
saved verifier result; absent/invalid verifier output is ungraded, not a
failure.

## Analyses

1. **Per-turn model effort and latency.** Fit log-scale mixed-effects models
   with task random intercepts for thinking tokens per turn and generation
   seconds per turn. Because zeros may occur, use `log1p(thinking_tokens)`;
   use `log(generation_seconds)` for positive durations. Report exponentiated
   contrasts as ratios with 95% task-cluster bootstrap intervals for DPO vs
   A2, DPO vs A0, router vs A0, and A9 vs A2. If a distinct thinking-token
   field is not logged, report that the thinking analysis is unavailable.

2. **Turn-count decomposition.** For each arm, show paired per-task
   differences in turns, summed/mean generation time, and summed/mean tool
   time. Use task-cluster bootstrap intervals to describe whether additional
   turns co-occur with shorter generation time, shorter tool time, or both.
   Do not claim that either component caused the turn-count difference.

3. **Action mix and first edit.** Report action proportions by arm and a
   task-cluster permutation test of arm differences (20,000 permutations,
   seed 20261118). Estimate time to first edit with Kaplan-Meier curves;
   attempts without an edit are censored at their observed end time, capped
   at the configured 300-second session limit. Report log-rank comparisons
   and a Cox model with shared task frailty. If a frailty model is unsupported
   by the available packages or fails to converge, state this and show the
   Kaplan-Meier and task-cluster bootstrap estimates without relabeling them
   as frailty-adjusted.

4. **Within-task association with solving.** Fit a mixed-effects logistic
   model for verified solve using log thinking tokens per turn, log turns,
   arm, and a task random intercept. Use `log1p` for zero-valued predictors.
   Report odds ratios and task-cluster bootstrap intervals. Treat associations
   as descriptive, not causal; do not describe them as predictors for new
   tasks.

5. **Confirmatory replication check.** Repeat the same extraction and
   relevant models for the 84-task A0/router cohort. Compare directions and
   interval overlap with the pilot process differences; call this a
   replication check only where the same process metric is observed and both
   arms have paired records.

No hypotheses, metrics, exclusions, or arm contrasts will be changed after
the result tables are inspected. Any deviations or unavailable metrics will
be listed in `results/process/REPORT.md`.
