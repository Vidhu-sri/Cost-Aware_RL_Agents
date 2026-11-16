# Confirmatory evaluation preregistration — 2026-11-16

This protocol is committed before any new model request (including smokes).
The final report records this commit. Existing pilot artifacts are immutable.

## Population and prior exposure
129 unique published dev IDs minus the five training IDs and the 40 matched pilot
IDs yields exactly 84. The sets are disjoint. This is a prospective comparison
outside the matched pilot, NOT a claim of never-seen tasks: the earlier 129-task
baseline covered these IDs. No selection uses those previous outcomes. In addition, 12 eligible IDs were used in previous checkpoint-development evaluations: fastapi_11194, fastapi_14099, fastapi_14186, fastapi_14459, fastapi_14851, fastapi_15280, fastapi_15763, fastapi_5077, requests_7315, rich_3063, rich_3454, rich_3518. Thus this is a preregistered prospective replication on the requested complement, not an untouched validation set.
Training exclusion: fastapi_14492, fastapi_14786, httpx_3672, requests_7205, rich_3894.
The complete exclusions, file hashes, package versions, image IDs and pilot
source paths are in frozen.json. There is one seed, no retraining or tuning.

## Hypothesis and tests
Primary hypothesis: the method router resolves more tasks than the A0 sample agent.
Primary test: exact TWO-SIDED McNemar, alpha=0.05, on matched interpretable pairs
among all 84 tasks. Report excluded unknown pairs and IDs. Timeout and no-patch
are outcomes, not grounds for exclusion unless verification is uninterpretable.
Use the frozen pilot interpreter; a timeout can coexist with a verified pass.
Report baseline-only and router-only discordances; direction is router minus A0.
If no discordances, p=1. No interim arm comparisons or outcome-based stopping.

Secondary DESCRIPTIVE estimates: router-minus-A0 difference in calls per solve
and tokens per solve, with 20,000 PAIRED task-bootstrap draws, numpy default_rng
seed 20261116, percentile 95% intervals. Use the same complete interpretable
pairs for these paired differences. The per-arm all-84 tables include all attempt
costs (including unknowns) divided by verified passes; unknowns are not asserted
to be failures. Report Wilson 95% intervals for verified yield on all 84.
Billed calls exclude get_status/submit_patch; tokens sum trace prompt/completion
usage, including repeated context. Missing usage is flagged, never imputed as zero.
Zero solve ratios are undefined, not zero. Bootstrap draws with zero solves in
either arm are excluded, their fraction reported; suppress a finite interval
when that fraction is >=2.5%. No secondary significance claims.

Optional phase 2: DPO on these same 84 IDs in the same shuffled task order, ONLY
after phase 1 completes and the user confirms GPU hours remain. DPO vs A0 is
secondary; if run, report Holm-adjusted p-values across primary router-vs-A0 and
DPO-vs-A0 (as well as raw p-values). No automatic phase-2 execution.

## Frozen execution
A0 uses data/sample_submission unchanged. Router uses the same sample prompts,
original analyzer adapter, and the recorded RFT, DPO epoch-005, and SDPO contrast
epoch-005 adapters with the byte-identical method_router.py and phase_router.py.
Both: 5 minutes, 100 billed calls, 50 turns, 60-second command timeout; ordinary
sampling temperature .2, top-p .95, seed42, thinking4096, output cap16384.
Preserve pilot compaction and summary quirks: summary temperature1.0, top-k64,
and inherited uncapped summary requests. No context-limit bug fixes.
Router phase overrides remain exactly as saved (not a flat4096/16384 policy).

Use unchanged serve_local.sh, A10080GB, bfloat16/QAT base, context32768,
GPU fraction .60, max sequences1, max batched tokens4096, max LoRA rank128,
max LoRAs8, gemma4 tool/reasoning parsers, CUDA compatibility and FlashInfer
sampling disabled. A0 main_lora points to sample; router main_lora points to DPO
and loads rft_lora/dpo_lora/sdpo_lora. Restart the owned server when the arm changes
to preserve these distinct pilot launch configurations; reuse it for adjacent
attempts of the same arm. Server startup/probes are outside the agent budget.

Use unchanged Docker worker, offline network none, private namespace veth,
NET_ADMIN capability, no privileged mode, host network, Docker socket, or host
bind mounts; rootless cgroup-v1 has NO enforced aggregate CPU/memory caps.
900s outer deadline, outer process watchdog960s plus45s SIGINT/15s SIGTERM grace.
Monitor before worker starts; clean only each recorded run label's containers.
Pre-start free GPU >=62000MiB; stop on free GPU<8000MiB, host available<16GiB,
disk free<12GiB, observed container namespace RSS>12GiB, monitor/cleanup failure.
Summed process RSS is an observed metric, not a hard cgroup memory cap.

## Smoke, stopping, replacement and resumption
One fresh fastapi_14246 pilot smoke per arm, in A0/router order; excluded from
confirmatory statistics and retained only as infrastructure audit evidence.
No requirement that the patch solves; valid model responses, trace, terminal
record and monitor/cleanup suffice. Configuration identity must match pilot.
All84tasks, botharms, no additions or outcome-based reruns. Stop on an actual
permission/resource/configuration/monitor/cleanup failure; resume at the next
unfinished preregistered slot, never rerun a terminal record.
One replacement only when there is NO terminal record and documented GPU/vLLM/
Docker infrastructure failure. Preserve original partial files and log cause,
replacement linkage and timestamp. No retry for timeout, no patch, failed or
unknown verification, controller exception, or an exhausted replacement.
A hard outer timeout without outcome is recorded terminal unknown, never retried.
Unexpected incomplete slots without qualifying crash evidence require a stop.
Terminal outcome is checkpointed before resource checks so completed tasks cannot
be rerun after a stop. One process lock; one task/model job at a time. No processes
or containers outside this batch are stopped. A resumed batch refuses to steal
an occupied model port or kill an unverified PID. Checkpoint every result; emit
progress counts at least every30minutes without arm comparisons. Preserve all
raw outputs and anomalies. Analysis runs only once all168slots have terminal
records. Pooled pilot40+confirmatory84 table is DESCRIPTIVE, not the primary test.

## Exact randomized order
Start with lexicographically sorted eligible IDs. Python random.Random(20261116),
shuffle once, then one getrandbits(1) per shuffled task:0=A0 then router,
1=router then A0. The following concrete order, not an implementation-dependent
regeneration, is authoritative:

| Position | Task ID | First arm | Second arm |
|---:|---|---|---|
| 1 | rich_3944 | router | A0 |
| 2 | fastapi_14463 | router | A0 |
| 3 | rich_3930 | A0 | router |
| 4 | fastapi_14372 | A0 | router |
| 5 | fastapi_14794 | A0 | router |
| 6 | fastapi_14371 | A0 | router |
| 7 | fastapi_14458 | router | A0 |
| 8 | fastapi_13713 | A0 | router |
| 9 | requests_6592 | A0 | router |
| 10 | fastapi_15030 | A0 | router |
| 11 | fastapi_14962 | A0 | router |
| 12 | rich_3905 | router | A0 |
| 13 | fastapi_15280 | router | A0 |
| 14 | requests_7505 | A0 | router |
| 15 | rich_4079 | A0 | router |
| 16 | rich_3180 | A0 | router |
| 17 | fastapi_14459 | router | A0 |
| 18 | fastapi_14186 | router | A0 |
| 19 | rich_3130 | router | A0 |
| 20 | fastapi_14430 | A0 | router |
| 21 | fastapi_13786 | A0 | router |
| 22 | fastapi_13537 | router | A0 |
| 23 | rich_3942 | router | A0 |
| 24 | fastapi_5077 | router | A0 |
| 25 | fastapi_14448 | A0 | router |
| 26 | rich_2725 | router | A0 |
| 27 | fastapi_14609 | A0 | router |
| 28 | requests_6589 | router | A0 |
| 29 | fastapi_13920 | A0 | router |
| 30 | rich_3043 | A0 | router |
| 31 | fastapi_14419 | A0 | router |
| 32 | fastapi_15588 | router | A0 |
| 33 | requests_7328 | router | A0 |
| 34 | fastapi_15763 | router | A0 |
| 35 | rich_3486 | router | A0 |
| 36 | fastapi_14978 | A0 | router |
| 37 | fastapi_14964 | A0 | router |
| 38 | fastapi_14361 | router | A0 |
| 39 | fastapi_14099 | router | A0 |
| 40 | fastapi_14303 | A0 | router |
| 41 | fastapi_14262 | A0 | router |
| 42 | rich_3469 | router | A0 |
| 43 | rich_3105 | router | A0 |
| 44 | requests_6757 | router | A0 |
| 45 | rich_3063 | router | A0 |
| 46 | rich_3675 | A0 | router |
| 47 | fastapi_15023 | A0 | router |
| 48 | rich_3006 | router | A0 |
| 49 | fastapi_14266 | router | A0 |
| 50 | fastapi_14349 | A0 | router |
| 51 | requests_7433 | router | A0 |
| 52 | requests_7309 | router | A0 |
| 53 | fastapi_14077 | router | A0 |
| 54 | rich_3934 | A0 | router |
| 55 | fastapi_14791 | A0 | router |
| 56 | fastapi_14512 | router | A0 |
| 57 | rich_4076 | router | A0 |
| 58 | fastapi_14986 | A0 | router |
| 59 | fastapi_14360 | router | A0 |
| 60 | fastapi_13207 | A0 | router |
| 61 | rich_3471 | A0 | router |
| 62 | rich_3454 | router | A0 |
| 63 | requests_7427 | router | A0 |
| 64 | fastapi_14873 | A0 | router |
| 65 | fastapi_9425 | router | A0 |
| 66 | requests_7502 | router | A0 |
| 67 | rich_3518 | router | A0 |
| 68 | fastapi_14851 | router | A0 |
| 69 | rich_3506 | A0 | router |
| 70 | fastapi_9555 | router | A0 |
| 71 | rich_3777 | A0 | router |
| 72 | rich_3468 | router | A0 |
| 73 | fastapi_11194 | router | A0 |
| 74 | fastapi_14482 | router | A0 |
| 75 | rich_3935 | router | A0 |
| 76 | fastapi_11355 | A0 | router |
| 77 | rich_3772 | router | A0 |
| 78 | fastapi_15589 | A0 | router |
| 79 | rich_3296 | A0 | router |
| 80 | fastapi_15800 | router | A0 |
| 81 | requests_7315 | A0 | router |
| 82 | rich_4075 | router | A0 |
| 83 | fastapi_14605 | A0 | router |
| 84 | fastapi_14583 | router | A0 |
