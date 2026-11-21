# Claims audit: paired scores and final-patch localization

CPU-only analysis of saved files; no agent or verifier was run. Empty CSV fields denote unknown. Solves are verified passing patches; failed/no-patch are non-solves and uninterpretable tests remain unknown unless a scoring rule itself forces failure.
Pilot uses original retained manifest labels; later pilot regrades produced no additional passes, with some outcomes still uninterpretable. No unknown is recoded as failed based solely on a regrade timeout.

## Pilot: 40 paired tasks

| Comparison | Passes on all 40 (arm / baseline) | Interpretable pairs | Passes on pairs (arm / baseline) | Arm only | Baseline only | Exact McNemar p | Excluded IDs |
|---|---:|---:|---:|---:|---:|---:|---|
| DPO vs A2 | 9 / 5 | 38 | 9 / 5 | 4 | 0 | 0.125 | fastapi_14306, rich_4006 |
| A2 vs A0 | 5 / 5 | 38 | 4 / 5 | 0 | 1 | 1 | rich_3480, rich_4006 |
| DPO vs A0 | 9 / 5 | 37 | 8 / 5 | 3 | 0 | 0.25 | fastapi_14306, rich_3480, rich_4006 |

## Replication: 84 tasks, three scoring policies

Final = observed valid final-patch verification. Timeout failure = every recorded timeout becomes a non-solve regardless of test outcome. Submit only = no trace `submit_patch` call becomes a non-solve; where a call exists, its observed final-patch verification is used. A submit tool call is evidence of an attempted submit, not proof that it succeeded or that a later final patch is byte-identical to the submitted patch. Missing traces/timeout fields remain unknown when needed. These are retrospective policy scores, not new live runs.

| Comparison / rule | Passes on all 84 (arm / baseline) | Interpretable pairs | Passes on pairs (arm / baseline) | Arm only | Baseline only | Exact McNemar p | Excluded IDs |
|---|---:|---:|---:|---:|---:|---:|---|
| DPO / final vs A0 | 23 / 18 | 76 | 23 / 18 | 5 | 0 | 0.0625 | fastapi_14186, fastapi_14262, fastapi_14448, fastapi_14609, fastapi_14978, fastapi_15030, rich_3772, rich_3930 |
| DPO / timeout_failure vs A0 | 17 / 14 | 82 | 17 / 14 | 3 | 0 | 0.25 | fastapi_14978, fastapi_15030 |
| DPO / submit_only vs A0 | 18 / 14 | 83 | 18 / 14 | 4 | 0 | 0.125 | fastapi_15030 |
| router / final vs A0 | 21 / 18 | 77 | 21 / 18 | 6 | 3 | 0.50781 | fastapi_14186, fastapi_14262, fastapi_14609, fastapi_14978, fastapi_15030, rich_3772, rich_3930 |
| router / timeout_failure vs A0 | 14 / 14 | 82 | 14 / 14 | 3 | 3 | 1 | fastapi_14978, fastapi_15030 |
| router / submit_only vs A0 | 15 / 14 | 83 | 15 / 14 | 4 | 3 | 1 | fastapi_15030 |

### Changed categories by arm

Listed as task ID: final → rule outcome. `unknown` is not a verified failure; the rule can force a non-solve without resolving the underlying test result.
- A0, timeout_failure (9): fastapi_14186: none → false; fastapi_14262: none → false; fastapi_14303: true → false; fastapi_14360: true → false; fastapi_14372: true → false; fastapi_14609: none → false; fastapi_14873: true → false; rich_3772: none → false; rich_3930: none → false
- A0, submit_only (10): fastapi_14186: none → false; fastapi_14262: none → false; fastapi_14303: true → false; fastapi_14360: true → false; fastapi_14372: true → false; fastapi_14609: none → false; fastapi_14873: true → false; fastapi_14978: none → false; rich_3772: none → false; rich_3930: none → false
- DPO, timeout_failure (13): fastapi_14186: none → false; fastapi_14262: none → false; fastapi_14303: true → false; fastapi_14360: true → false; fastapi_14372: true → false; fastapi_14448: none → false; fastapi_14609: none → false; fastapi_14873: true → false; fastapi_15030: none → false; fastapi_15589: true → false; fastapi_5077: true → false; rich_3772: none → false; rich_3930: none → false
- DPO, submit_only (12): fastapi_14186: none → false; fastapi_14262: none → false; fastapi_14303: true → false; fastapi_14360: true → false; fastapi_14372: true → false; fastapi_14448: none → false; fastapi_14609: none → false; fastapi_14873: true → false; fastapi_15030: none → false; fastapi_15589: true → false; rich_3772: none → false; rich_3930: none → false
- router, timeout_failure (9): fastapi_11194: true → false; fastapi_13207: true → false; fastapi_14186: none → false; fastapi_14349: true → false; fastapi_14372: true → false; fastapi_14458: true → false; fastapi_14978: none → false; rich_3043: true → false; rich_3777: true → false
- router, submit_only (8): fastapi_11194: true → false; fastapi_13207: true → false; fastapi_14186: none → false; fastapi_14349: true → false; fastapi_14372: true → false; fastapi_14458: true → false; fastapi_14978: none → false; rich_3777: true → false

## Final-patch localization

A match means any exact repository-relative path occurs in both the final agent diff and the published gold diff (old and new paths included). This is file overlap, not line/symbol localization or evidence that the edit is correct. A known no-patch attempt is a non-match; missing/corrupt saved patch is unknown. Gold patches were found in data/tasks.jsonl for pilot and replication.

- Replication A0: 44/84 evaluable attempts touched a gold file; 0 unknown.
- Replication DPO: 48/84 evaluable attempts touched a gold file; 0 unknown.
- Paired localization: 84 evaluable pairs; DPO-only touched 7, A0-only touched 3; exact two-sided McNemar p=0.34375. DPO-only IDs: fastapi_11194, fastapi_14791, fastapi_15589, fastapi_5077, rich_3043, rich_3506, rich_3772; A0-only IDs: fastapi_13713, fastapi_14978, requests_7427.

### DPO-only solves versus A0: 3 pilot + 5 replication

| Cohort | Task | DPO touched gold file | A0 touched gold file | Gold paths | DPO paths | A0 paths |
|---|---|---|---|---|---|---|
| pilot | fastapi_12942 | True | None | ["fastapi/_compat.py"] | ["fastapi/_compat.py", "reproduce_issue.py"] | null |
| pilot | fastapi_14356 | True | None | ["fastapi/dependencies/utils.py"] | ["fastapi/dependencies/utils.py"] | null |
| pilot | fastapi_9753 | True | None | ["fastapi/dependencies/models.py"] | ["fastapi/dependencies/models.py", "fastapi/dependencies/utils.py"] | null |
| replication | fastapi_11194 | True | False | ["fastapi/dependencies/utils.py"] | ["fastapi/dependencies/utils.py"] | ["reproduce_issue.py", "reproduce_issue_complex.py", "reproduce_issue_simple.py"] |
| replication | fastapi_14791 | True | False | ["fastapi/openapi/utils.py"] | ["fastapi/openapi/utils.py", "verify_schema.py"] | ["verify_fix.py"] |
| replication | fastapi_15589 | True | False | ["fastapi/dependencies/utils.py"] | ["fastapi/dependencies/utils.py"] | ["repro.py", "repro_model.py"] |
| replication | fastapi_5077 | True | False | ["fastapi/dependencies/utils.py"] | ["fastapi/dependencies/utils.py"] | ["module_a.py", "module_b.py", "reproduce_issue.py"] |
| replication | rich_3043 | True | False | ["rich/_export_format.py"] | ["rich/_export_format.py"] | ["verify_html.py"] |

Across these eight selected DPO-only solves, DPO touched a gold file 8/8. In the five replication cases A0 touched a gold file 0/5. For the three pilot cases the A0 final patch files are absent despite nonzero recorded patch sizes, so A0 overlap is unknown (not false). This subgroup was selected by solve outcome and does not establish localization as a cause of success.

The pilot tasks are disjoint from these 84, but the 84 were previously seen in baseline evaluations and 12 in checkpoint development. Single seed; router settings and controller differ from A0. The v2 analysis follows an interim look and amended cutoff. No causal or statistically significant improvement is inferred.

Inputs and per-attempt fields: `pilot_per_task.csv`, `replication_per_task.csv`, `localization_per_attempt.csv`. Regenerate with `python results/claims/build_claims.py`.

## Final diff categories and the reproduction trap

Classification uses saved Git diff headers against each attempt’s baseline: `new file mode` / `--- /dev/null` denotes a new file; other modified files pre-existed. This uses Git’s baseline-relative diff metadata, not an independent listing of every snapshot. Category **preexisting source** includes non-deleted existing project code or text files, including documentation and configuration. Category **scratch only** requires every change to create a scratch-named `.py`, `.sh`, `.js`, or `.ts` file outside the repository package; recognized name fragments are repro, reproduce, verify, check, test, debug, scratch, tmp, temp, demo, diagnos, issue. Category **empty/no patch** requires a saved empty diff or a recorded zero-byte patch. Deletions, new non-scratch files, and other ambiguous changes are **other**. Missing nonzero patches and unparseable diffs are **unknown**, never empty.
Scratch-only is an operational proxy for the reproduction trap; it does not establish the agent’s intent or show that a scratch file was executed. In each category, solve rate is verified passes divided by interpretable attempts; unknown grades are reported separately.

| Cohort / arm | Existing source | Scratch only | Empty / no patch | Other | Unknown patch |
|---|---:|---:|---:|---:|---:|
| pilot / A0 | 0 | 1 | 15 | 0 | 24 |
| pilot / A1 | 0 | 0 | 14 | 0 | 26 |
| pilot / A2 | 0 | 0 | 15 | 0 | 25 |
| pilot / DPO | 17 | 10 | 13 | 0 | 0 |
| pilot / A9 | 0 | 0 | 16 | 0 | 24 |
| pilot / router | 1 | 2 | 14 | 0 | 23 |
| replication / A0 | 47 | 16 | 19 | 2 | 0 |
| replication / DPO | 52 | 14 | 16 | 2 | 0 |
| replication / router | 46 | 12 | 25 | 1 | 0 |

### Verified solve rates by category and arm

| Cohort / arm | Category | Passes / interpretable | Unknown verification |
|---|---|---:|---:|
| pilot / A0 | scratch_only | 0/0 | 1 |
| pilot / A0 | empty_no_patch | 0/15 | 0 |
| pilot / A0 | unknown | 5/23 | 1 |
| pilot / A1 | empty_no_patch | 0/14 | 0 |
| pilot / A1 | unknown | 4/24 | 2 |
| pilot / A2 | empty_no_patch | 0/15 | 0 |
| pilot / A2 | unknown | 5/24 | 1 |
| pilot / DPO | preexisting_source | 9/16 | 1 |
| pilot / DPO | scratch_only | 0/9 | 1 |
| pilot / DPO | empty_no_patch | 0/13 | 0 |
| pilot / A9 | empty_no_patch | 0/16 | 0 |
| pilot / A9 | unknown | 4/22 | 2 |
| pilot / router | preexisting_source | 0/0 | 1 |
| pilot / router | scratch_only | 0/0 | 2 |
| pilot / router | empty_no_patch | 0/14 | 0 |
| pilot / router | unknown | 8/23 | 0 |
| replication / A0 | preexisting_source | 18/41 | 6 |
| replication / A0 | scratch_only | 0/15 | 1 |
| replication / A0 | empty_no_patch | 0/19 | 0 |
| replication / A0 | other | 0/2 | 0 |
| replication / DPO | preexisting_source | 23/45 | 7 |
| replication / DPO | scratch_only | 0/14 | 0 |
| replication / DPO | empty_no_patch | 0/16 | 0 |
| replication / DPO | other | 0/2 | 0 |
| replication / router | preexisting_source | 21/43 | 3 |
| replication / router | scratch_only | 0/12 | 0 |
| replication / router | empty_no_patch | 0/25 | 0 |
| replication / router | other | 0/1 | 0 |

### Paired reproduction-trap comparison: DPO vs A0

Pairs with an unknown patch category in either arm are excluded. The exact two-sided McNemar test compares scratch-only status, not solve status.

- pilot: 16/40 pairs; DPO-only scratch 3, A0-only scratch 0, exact p=0.25; DPO-only IDs: fastapi_14246, fastapi_14455, fastapi_5624; A0-only IDs: none; excluded: fastapi_12942, fastapi_14258, fastapi_14297, fastapi_14356, fastapi_14479, fastapi_14485, fastapi_14616, fastapi_14953, fastapi_9753, requests_6629, requests_6644, rich_2943, rich_3052, rich_3067, rich_3470, rich_3480, rich_3535, rich_3676, rich_3718, rich_3782, rich_3882, rich_3953, rich_4070, rich_4077.
- replication: 84/84 pairs; DPO-only scratch 4, A0-only scratch 6, exact p=0.753906; DPO-only IDs: requests_6589, requests_7427, rich_3063, rich_3180; A0-only IDs: fastapi_11194, fastapi_11355, fastapi_14791, fastapi_15589, rich_3043, rich_3772; excluded: none.

Row-level classifications and changed files: `reproduction_trap_per_attempt.csv`. The pilot includes missing saved patches, so its evaluable subset need not represent all 40 tasks. Single seed and prior evaluation exposure remain limitations.
