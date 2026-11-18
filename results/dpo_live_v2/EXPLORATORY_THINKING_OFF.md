# Exploratory, descriptive accidental thinking-off contrast

This compares **confirmatory A0** with **`dpo_live` A0** on the same 84 task
IDs. It is not a v2 arm analysis or a randomized thinking ablation: the live
run also had different snapshot deadline accounting and server lifecycle.
`dpo_live` remains a protocol deviation, not a DPO confirmatory experiment.

Among the 76 tasks with interpretable resolution in both records, confirmatory
A0 solved 17 and `dpo_live` A0 solved 11. Nine were solved by both, eight by
confirmatory A0 only, two by `dpo_live` A0 only, and 57 by neither. Exact
two-sided McNemar p = **0.109375** (10 discordant pairs). The original full-run
counts are 18/84 and 11/84; this paired test excludes eight tasks with an
uninterpretable outcome in at least one run.

Recorded completion tokens per attempt (all 84 task IDs, including errors)
averaged **5,444.9** in confirmatory A0 and **2,421.7** in `dpo_live` A0;
medians were 5,649 and 1,920.5. The first-response medians were 162.5 and
22.0 tokens, respectively. All 84 first confirmatory A0 requests carried
`enable_thinking=true` and budget 4096; none of the 84 first `dpo_live` A0
requests carried those fields.

| Termination reason | Confirmatory A0 | `dpo_live` A0 |
|---|---:|---:|
| 300-second wall deadline | 50 | 4 |
| 50-turn cap | 0 | 53 |
| Explicit submit without agent error | 25 | 26 |
| Context-window/model configuration error | 9 | 1 |

These are descriptive process differences, not an isolated effect of turning
thinking off. The per-attempt source records and classification are in
[`artifacts/dpo_live_termination_audit.csv`](../../artifacts/dpo_live_termination_audit.csv),
and the execution deviation is documented in [`dpo_live/REPORT.md`](../dpo_live/REPORT.md).
