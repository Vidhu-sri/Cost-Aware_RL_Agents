# Six-arm pilot process analysis

**Provenance update (2026-11-18):** Historical pilot token totals are
**unreconciled** against complete raw model-response usage and must not be used
for cross-arm cost claims. Timing and action counts come from trace timestamps
and tool-call names, respectively, and do not depend on token reconciliation.

Exploratory analysis of existing traces only. No GPU/model work was performed.
Sources are the six run directories listed in `pilot_statistics.json`; each has 40 task directories, one outcome, and one authoritative trace per task. All six manifests identify the same 40 task IDs.
Per-event timing is reconstructed from differences in adjacent `elapsed_s` values because the trace field is a cumulative session clock. This corrects the interpretation in the original extraction rule; see the main process report.
Intervals use 20,000 paired task-cluster bootstrap resamples (seed 20261118). Differences are comparison arm minus baseline; ratios are geometric ratios of task-level attempt means.

## Exploratory, hypothesis-generating: source of DPO_LIVE H1-H4 — timing contrasts

The comparisons below use timestamp-derived durations and observed tool calls.
The router timing rows are retained **pending the `router40-20261108a` config diff**;
their different output caps and phase policy may affect comparability.

| Arm vs baseline | Metric | n | Difference [95% CI] | Ratio [95% CI] |
|---|---|---:|---:|---:|
| DPO vs A2 | Turns/attempt | 40 | 3.675 [2.050, 5.475] | 1.236 [1.116, 1.384] |
| DPO vs A2 | Tool calls/attempt | 40 | 3.450 [1.800, 5.250] | 1.216 [1.098, 1.360] |
| DPO vs A2 | Generation seconds/turn | 40 | -5.276 [-8.996, -2.270] | 0.762 [0.666, 0.869] |
| DPO vs A2 | Tool seconds/turn | 40 | 0.197 [-0.009, 0.591] | 1.069 [0.935, 1.267] |
| DPO vs A2 | Summed generation seconds/attempt | 40 | -14.102 [-32.440, 4.430] | 0.941 [0.851, 1.045] |
| DPO vs A2 | Summed tool seconds/attempt | 40 | 2.136 [0.331, 5.370] | 1.300 [1.129, 1.544] |
| DPO vs A2 | Calls/observed trace minute | 40 | 0.969 [0.459, 1.466] | 1.281 [1.125, 1.457] |
| DPO vs A0 | Turns/attempt | 40 | 4.400 [2.625, 6.300] | 1.301 [1.164, 1.459] |
| DPO vs A0 | Tool calls/attempt | 40 | 4.200 [2.425, 6.100] | 1.285 [1.150, 1.439] |
| DPO vs A0 | Generation seconds/turn | 40 | -3.971 [-8.495, 2.050] | 0.724 [0.624, 0.853] |
| DPO vs A0 | Tool seconds/turn | 40 | 0.149 [-0.127, 0.581] | 1.049 [0.905, 1.255] |
| DPO vs A0 | Summed generation seconds/attempt | 40 | -18.659 [-39.650, 2.683] | 0.941 [0.821, 1.117] |
| DPO vs A0 | Summed tool seconds/attempt | 40 | 2.327 [0.523, 5.547] | 1.346 [1.147, 1.605] |
| DPO vs A0 | Calls/observed trace minute | 40 | 1.384 [0.870, 1.907] | 1.353 [1.146, 1.568] |
| router vs A0 | Turns/attempt | 40 | 0.700 [-1.250, 2.800] | 1.076 [0.905, 1.341] |
| router vs A0 | Tool calls/attempt | 40 | 0.600 [-1.300, 2.625] | 1.083 [0.922, 1.338] |
| router vs A0 | Generation seconds/turn | 40 | -7.968 [-10.910, -5.519] | 0.543 [0.470, 0.625] |
| router vs A0 | Tool seconds/turn | 40 | 0.302 [-0.001, 0.835] | 1.172 [0.971, 1.458] |
| router vs A0 | Summed generation seconds/attempt | 40 | -95.206 [-124.295, -63.208] | 0.584 [0.472, 0.747] |
| router vs A0 | Summed tool seconds/attempt | 40 | 3.112 [0.015, 7.606] | 1.215 [0.961, 1.608] |
| router vs A0 | Calls/observed trace minute | 40 | 3.374 [2.452, 4.382] | 1.806 [1.557, 2.098] |
| A9 vs A2 | Turns/attempt | 40 | -1.075 [-2.325, 0.125] | 0.940 [0.863, 1.021] |
| A9 vs A2 | Tool calls/attempt | 40 | -1.050 [-2.250, 0.100] | 0.939 [0.864, 1.018] |
| A9 vs A2 | Generation seconds/turn | 40 | -0.014 [-3.239, 2.624] | 1.102 [0.987, 1.234] |
| A9 vs A2 | Tool seconds/turn | 40 | 0.051 [-0.003, 0.150] | 1.019 [0.958, 1.086] |
| A9 vs A2 | Summed generation seconds/attempt | 40 | 4.177 [-16.099, 25.908] | 1.035 [0.935, 1.163] |
| A9 vs A2 | Summed tool seconds/attempt | 40 | -0.194 [-0.440, 0.031] | 0.955 [0.852, 1.056] |
| A9 vs A2 | Calls/observed trace minute | 40 | -0.525 [-1.015, -0.073] | 0.906 [0.811, 1.010] |

## Exploratory, hypothesis-generating: source of DPO_LIVE H1-H4 — action mix

Six-arm paired task-label permutation test: L2²=0.079059, p=0.0140 over
20,000 permutations. Counts are observed tool actions; percentages use the
complete action denominator within each arm.

| Action | A0 n (%) | A1 n (%) | A2 n (%) | DPO n (%) | A9 n (%) | router n (%) |
|---|---:|---:|---:|---:|---:|---:|
| read | 233 (39.6%) | 251 (45.9%) | 239 (38.6%) | 282 (37.3%) | 230 (39.9%) | 252 (41.1%) |
| shell | 245 (41.6%) | 223 (40.8%) | 244 (39.4%) | 288 (38.0%) | 238 (41.2%) | 234 (38.2%) |
| edit | 87 (14.8%) | 55 (10.1%) | 102 (16.5%) | 144 (19.0%) | 90 (15.6%) | 70 (11.4%) |
| graph | 5 (0.8%) | 5 (0.9%) | 10 (1.6%) | 10 (1.3%) | 5 (0.9%) | 35 (5.7%) |
| test | 10 (1.7%) | 8 (1.5%) | 15 (2.4%) | 15 (2.0%) | 9 (1.6%) | 11 (1.8%) |
| submit | 7 (1.2%) | 5 (0.9%) | 7 (1.1%) | 16 (2.1%) | 4 (0.7%) | 10 (1.6%) |
| other | 2 (0.3%) | 0 (0.0%) | 2 (0.3%) | 2 (0.3%) | 1 (0.2%) | 1 (0.2%) |

The `submit` action row counts tool calls, including repeated submissions.
The explicit-submit count below is the number of attempts with at least one
`submit_patch` call; these are different denominators.

## Exploratory, hypothesis-generating: source of DPO_LIVE H1-H4 — explicit submits and outcomes

| Arm | n | Pass | Fail | Ungraded | Timeout | No patch | Explicit-submit attempts | Mean turns | Mean calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A0 | 40 | 5 | 18 | 17 | 35 | 15 | 4 | 14.93 | 14.72 |
| A1 | 40 | 4 | 20 | 16 | 36 | 14 | 4 | 13.90 | 13.68 |
| A2 | 40 | 5 | 19 | 16 | 36 | 15 | 5 | 15.65 | 15.47 |
| DPO | 40 | 9 | 16 | 15 | 32 | 13 | 9 | 19.32 | 18.93 |
| A9 | 40 | 4 | 18 | 18 | 35 | 16 | 3 | 14.57 | 14.43 |
| router | 40 | 8 | 15 | 17 | 7 | 14 | 9 | 15.62 | 15.32 |

Token/field coverage by arm is in `pilot_statistics.json`; pilot token totals
there are **unreconciled** and excluded from cross-arm comparisons. No distinct
thinking-token field is logged; the registered thinking-effort contrasts and
solve association are unavailable. Cox shared-task-frailty support is absent
from the installed environment. Pilot log-rank pairwise results are available
in the JSON; the KM curves are in the combined `survival.png`.
