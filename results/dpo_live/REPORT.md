# Fresh A0 versus DPO live evaluation

**Status:** All 168 attempts are terminal. This file was opened before batch
completion at the user's request on 2026-11-18, a reporting-timing deviation
from `prereg/DPO_LIVE.md`; the experimental design, settings, and task schedule
were unchanged.

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
