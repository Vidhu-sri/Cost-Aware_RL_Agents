# DPO live v2 — running record

**Status:** the amended design runs DPO only on 84 tasks and pairs it with the existing confirmatory A0 records. Fresh v2 A0 attempts remain descriptive. The DPO run is ongoing; final statistics are pending the fixed stop or all 84 DPO terminal records.

## Protocol identity

- Preregistration: `prereg/DPO_LIVE_V2.md`, committed as `97042b5` before non-smoke inference.
- Task order and per-task arm order: frozen seed 20261119 schedule in `schedule.json`.
- DPO adapter SHA-256: `0c5fe9518135b51ee846bad843a356f2026c99d5793082c93b8bba90e1a498a1`.
- Both arms use the same five-minute agent budget, 100-call cap, 50-turn cap, temperature 0.2, and sampling seed 42. Each attempt has an outer supervisor and owned-container cleanup.

## Deviation history and gate

The original `dpo_live` is a protocol deviation: its wrapper invoked the unconfigured LiteLLM instance, leaving thinking disabled in both arms, and snapshot duration consumed agent wall time. It remains in the record but is excluded from the v2 arm analysis. A separately labeled exploratory, confounded A0 contrast is in `EXPLORATORY_THINKING_OFF.md`.

V2 wraps the configured clone. A request guard fails a run if `enable_thinking=true` and thinking budget 4096 are absent. The agent deadline is extended by measured snapshot and telemetry overhead; adjustments are logged separately. Four discarded smoke attempts (A0 and DPO on `fastapi_14246` and `rich_4070`) passed the corrected gate: every outgoing request had the required thinking settings, first-response completion tokens were 339, 339, 505, and 505 (median 422), all four ended at the wall deadline rather than the turn cap, and every final snapshot matched the extracted patch. Each deadline-canceled final request has no server response or token usage; it is explicitly recorded as `CancelledError`, not imputed.

The first smoke controller stopped on an expired-timeout reschedule error. This was fixed before the four completed smoke attempts. A controller process that had loaded the older telemetry gate rejected those completed attempts because it treated their deadline-canceled requests as missing successful-response usage. The corrected gate validated the saved attempts without rerunning them; the owned server was restarted and the four attempts were reused before the batch began. These events are preserved in `SMOKE_DEVIATIONS.md` and the controller logs.

## In-run grading instrumentation notes

The first terminal non-smoke attempt produced a patch, and its tests exited 2 with collection errors caused by that patch. The conservative result parser records this as `could_not_interpret`; the raw test log and exit code are retained for final adjudication. No correctness label is inferred from that parser status alone.

The third attempt, `fastapi_14794/A0`, submitted a 791-byte patch at 197 seconds and passed verification (test exit 0). A trailing telemetry callback attempted to reschedule an already-finished asyncio timeout and wrote a `deadline_guard_violation.jsonl` entry, causing the controller to stop after the terminal outcome was saved. Inspection established that this was a post-submission instrumentation false positive: the agent had already exited its timeout context, every model request carried thinking=true/budget4096, the worker exited 0, and all owned containers were removed. The original guard entry remains untouched. The timeout hook now records post-completion overhead without attempting to extend a finished deadline; a focused regression test covers this state. A recovery record was written from the existing terminal outcome without rerunning the agent. The server cleanup succeeded. This stop and fix are deviations from uninterrupted batch execution.

The CPU snapshot verifier initially omitted an unknown final-grade attempt from its queue; commit `e18a153` expanded selection to include patched unknown outcomes. Its first checks then exposed a worker argument-forwarding bug: the outer worker accepted `--patch-path` but did not pass it to its child. Commit `2482cdc` fixed forwarding and made only those parser-error snapshot rows retryable. The original failed verifier rows remain in `snapshot_verification.jsonl`; successful retries use distinct directories and owned labels. The agent batch was not stopped or rerun for these verifier-only faults.

## Pending final report

After 84 DPO terminal records or the amended fixed stop at 2026-11-20 14:15 IST, and CPU snapshot verification, report the preregistered solve, cost, process, and found-then-lost analyses on completed DPO tasks paired with existing confirmatory A0 records; token-usage limitations; all deviations and anomalies; and per-attempt, per-turn, and per-snapshot CSVs. `controller-watchdog-nohup.log`, `WATCHDOG.log`, `snapshot-verifier-nohup.log`, and `progress.jsonl` are the live status sources.

## Disclosed interim look (user request, 2026-11-19 13:53 IST)

The user requested analysis before the batch ended, overriding the original
no-comparison-before-completion instruction. At this look, 43 distinct DPO
tasks had terminal records. DPO had 13 verified passes, 21 valid failed
verifications, five no-patch outcomes, and four outcomes that the verifier
could not interpret. The existing confirmatory A0 run had 10 verified passes
on those same 43 task IDs. Among 39 pairs interpretable in both arms, 10 were
solved by both, three only by DPO, none only by A0, and 26 by neither. No
hypothesis test or stopping decision was made from these interim outcomes.
The task schedule, 84-task target, and fixed stop remain unchanged. These
descriptive figures are not the final registered estimate.

The first-request equivalence guard passed for 40 of these DPO attempts. The
three attempts completed before the guard was installed were checked from
their saved raw request bodies after the fact: `fastapi_14609`,
`fastapi_14794`, and `fastapi_14986` each differed from the corresponding
confirmatory A0 first request only in the `model` adapter field.

## User-directed cutoff and frozen primary cohort (2026-11-19)

The interim outcome look was delivered at approximately **13:57 IST** using
terminal records available at **13:53 IST**, before the user-directed 19 November
14:15 cutoff. The material viewed was: 43 DPO terminals; 13 DPO verified passes,
21 valid failed verifications, five no-patch outcomes, and four uninterpretable
verifications; 10 existing confirmatory A0 passes on those 43 IDs; and, among
39 interpretable pairs, 10 both solved, three DPO only, zero A0 only, and 26
neither. The three DPO-only IDs were `fastapi_14791`, `fastapi_15589`, and
`rich_3043`. Also viewed were 26 DPO versus 27 A0 timeout flags, mean calls
23.74 versus 22.42, no-patch counts five versus seven, and explicit-submit
counts 18 versus 16. DPO logged prompt/completion totals averaged 230,728/6,344
tokens per attempt, but 27 of 43 attempts had at least one missing usage row.
The first-request equivalence status (40 live guards plus three retrospective
checks) was viewed. A snapshot-verifier status check showed 113 DPO snapshot
records and no passing intermediate diff at that time. No H1-H4 test was run
then. This look was a protocol deviation from the no-arm-comparison-before-end
rule and was disclosed before the cohort analysis.

The committed preregistration names **2026-11-20 14:15 IST** as its stop. The
subsequent user instruction refers to a 13:57 look *before* a 14:15 stop and
requires the run to continue past that stop. We interpreted this as a new
**2026-11-19 14:15 IST** cutoff. This is a post-interim, user-directed deviation,
not the original preregistered stop. The first DPO terminal task boundary after
that cutoff was `requests_7505` at **2026-11-19 14:17:09.820102 IST**. The
48 tasks terminal through that boundary were frozen in
`primary_cohort.txt` and committed as `6ede18d` **before** the analyses below.
Generation continues to all 84 tasks; the remaining tasks form a separately
labeled secondary full-set analysis. The original 20 November stop has not yet
occurred; saying the run has already passed that *pre-registered* stop would be
incorrect. No task order, generation setting, or verifier setting was changed
after the interim look.

### Frozen 48-task analysis

The frozen cohort has 44 interpretable DPO/A0 verification pairs and four
unknown pairs (`fastapi_14186`, `fastapi_14262`, `fastapi_14609`,
`fastapi_15030`). DPO had 14 verified passes, A0 had 11; within interpretable
pairs, 11 were solved by both, three by DPO only, none by A0 only, and 30 by
neither. The exact two-sided McNemar p-value is **0.25**, reported descriptively
because the cutoff followed an interim outcome look.

| Process hypothesis (DPO versus confirmatory A0) | Estimate | 95% paired task bootstrap CI | One-sided p | Holm p |
| --- | ---: | ---: | ---: | ---: |
| H1 generation seconds per turn, geometric ratio | 0.985 | 0.918 to 1.054 | 0.335 | 0.375 |
| H2 tool calls per attempt, geometric ratio | 1.057 | 0.992 to 1.130 | 0.0506 | 0.152 |
| H3 edit share, paired difference | +0.0282 | -0.0011 to +0.0590 | 0.0358 | 0.143 |
| H4 explicit submit (DPO 20/48, A0 17/48) | four DPO-only, one A0-only | — | 0.1875 | 0.375 |

H1-H3 use 20,000 paired task sign-flip permutations and 20,000 paired task
bootstrap draws, seed 20261119. H4 uses one-sided exact McNemar. None of the
four hypotheses survives Holm correction. H1 uses the same trace-timestamp
extraction for both runs; it is not a direct comparison of DPO HTTP telemetry
to unavailable confirmatory A0 HTTP telemetry.

Among 30 DPO attempts with valid failed or no-patch final verification, the
CPU verifier completed all **94 unique non-empty** intermediate diffs. None
passed hidden verification: found-then-lost **0/30** (Wilson 95% CI 0 to
0.114; task-cluster bootstrap CI 0 to 0). Empty diffs were excluded because
they contain no patch and cannot pass; their patch-file verifier errors remain
in the raw log. DPO timeout-with-pass was **3/14** verified solves (Wilson 95%
CI 0.076 to 0.476). The cohort overlaps **0/40** pilot DPO task IDs.

The immutable analysis data are in `primary_analysis.json` (SHA-256
`7f70416135cb886838a1b0f7f197294b4567f563f59fcb2359ac637f06b47791`).
Two earlier incomplete derived drafts are retained as
`primary_analysis_incomplete_h2.json` and
`primary_analysis_pending_empty_diffs.json`; the former omitted confirmatory
A0's per-task outcome join for H2, and the latter treated empty diffs as
ungraded. Neither is used for interpretation. The full-84 analysis will be
written to a different file and will not alter this frozen result.
