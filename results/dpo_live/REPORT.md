# Fresh A0 versus DPO live evaluation

**Status:** The 168-attempt batch is still running. This interim file contains
configuration and analysis-method notes only. It reports no arm-level outcomes or
comparisons. Creating it before batch completion was requested on 2026-11-18 and
is a reporting-timing deviation from `prereg/DPO_LIVE.md`; the experimental
design, settings, and task schedule are unchanged.

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

Cross-arm comparisons using the historical pilot arms in this report will use
**tool calls and turns only**. Historical pilot token totals are
**unreconciled**: raw model-response usage is absent or incomplete for several
arms, and saved response-usage sums disagree with outcome totals in others.
They are not used for cross-arm pilot comparisons. This restriction does not
apply to the fresh live run, whose per-turn usage is captured and audited.

## Token-usage sensitivity analysis

After all 168 terminal records exist, run
`python costagent/scripts/dpo_live_token_sensitivity.py`. It refuses to compare
arms on an incomplete batch. For each missing usage row, the sensitivity total
adds the median observed prompt-plus-completion tokens per response **within
that arm**. The script preserves raw totals, checks per-turn sums against each
attempt's recorded total, and writes `results/dpo_live/token_sensitivity.json`.
It compares raw and imputed paired Wilcoxon token results and 20,000-resample
paired task-bootstrap tokens-per-solve intervals. Missing usage can represent
failed requests without a billed token count; median imputation is a sensitivity
scenario, not a reconstruction of actual billing.

The numerical analysis and whether either token conclusion changes will be
added only after the batch is complete.
