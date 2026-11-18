#!/usr/bin/env python3
"""Post-batch token sensitivity for the 84 paired fresh A0/DPO tasks.

Refuses to compare arms until all 168 non-smoke slots are terminal.
Missing response-usage rows are imputed with the observed per-arm median
prompt-plus-completion tokens per response. Raw usage is never overwritten.
"""

import argparse
import json
from pathlib import Path
import statistics

import numpy as np
from scipy.stats import wilcoxon


ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "results/dpo_live"


def interval(values):
    good = np.asarray([x for x in values if np.isfinite(x)], dtype=float)
    if len(good) < 0.975 * len(values):
        return None
    return [float(np.quantile(good, 0.025)), float(np.quantile(good, 0.975))]


def analyze(root):
    rows = {}
    for file in (root / "attempts").glob("*/*/done.json"):
        done = json.loads(file.read_text())
        if done.get("smoke"):
            continue
        key = (done["task_id"], done["arm"])
        if key in rows:
            raise RuntimeError(f"Duplicate terminal slot: {key}")
        if done["arm"] not in {"A0", "DPO"}:
            raise RuntimeError(f"Unexpected arm: {key}")
        telemetry = Path(done["result_dir"]) / "turn_telemetry.jsonl"
        if not telemetry.is_file():
            raise RuntimeError(f"Missing telemetry: {telemetry}")
        turns = [json.loads(line) for line in telemetry.read_text().splitlines() if line.strip()]
        rows[key] = (done, turns)
    if len(rows) != 168:
        raise RuntimeError(f"Batch incomplete: {len(rows)}/168 terminal attempts; no arm comparison performed")
    tasks = sorted({key[0] for key in rows})
    if len(tasks) != 84 or any((task, arm) not in rows for task in tasks for arm in ("A0", "DPO")):
        raise RuntimeError("Terminal records are not 84 complete task pairs")

    medians = {}
    for arm in ("A0", "DPO"):
        observed = [int(t["prompt_tokens"]) + int(t["completion_tokens"])
                    for (task, a), (_, turns) in rows.items() if a == arm
                    for t in turns if t.get("usage_present")
                    and t.get("prompt_tokens") is not None and t.get("completion_tokens") is not None]
        if not observed:
            raise RuntimeError(f"No observed usage for {arm}")
        medians[arm] = statistics.median(observed)

    attempt_rows = []
    for task in tasks:
        for arm in ("A0", "DPO"):
            done, turns = rows[(task, arm)]
            missing_turns = [t for t in turns if not t.get("usage_present")
                             or t.get("prompt_tokens") is None or t.get("completion_tokens") is None]
            missing = len(missing_turns)
            raw = int(done["prompt_tokens"]) + int(done["completion_tokens"])
            telemetry_sum = sum(int(t.get("prompt_tokens") or 0) + int(t.get("completion_tokens") or 0)
                                for t in turns)
            if raw != telemetry_sum:
                raise RuntimeError(f"Per-turn token mismatch for {task}/{arm}: {raw} != {telemetry_sum}")
            fallback_sum = sum(int(t.get("prompt_tokens") or 0) + int(t.get("completion_tokens") or 0)
                               for t in missing_turns)
            attempt_rows.append({"task_id": task, "arm": arm, "resolved": done.get("resolved"),
                                 "raw_tokens": raw, "missing_usage_rows": missing,
                                 "fallback_tokens_replaced": fallback_sum,
                                 "median_imputed_tokens": raw - fallback_sum + missing * medians[arm]})

    by_key = {(r["task_id"], r["arm"]): r for r in attempt_rows}
    rng = np.random.default_rng(20261119)
    out = {"method": "Per-arm median observed prompt-plus-completion tokens per response; replace any fallback token estimate on each missing-usage row with that arm's median",
           "n_tasks": 84, "n_attempts": 168,
           "median_tokens_per_observed_response": medians,
           "missing_usage_rows": {arm: sum(r["missing_usage_rows"] for r in attempt_rows if r["arm"] == arm)
                                  for arm in ("A0", "DPO")}, "analyses": {}}
    for field in ("raw_tokens", "median_imputed_tokens"):
        a = np.array([by_key[(task, "A0")][field] for task in tasks], dtype=float)
        d = np.array([by_key[(task, "DPO")][field] for task in tasks], dtype=float)
        diff = d - a
        test = wilcoxon(diff, alternative="two-sided", zero_method="wilcox")
        solve_a = np.array([by_key[(task, "A0")]["resolved"] is True for task in tasks])
        solve_d = np.array([by_key[(task, "DPO")]["resolved"] is True for task in tasks])
        indices = rng.integers(0, len(tasks), size=(20000, len(tasks)))
        counts_a = solve_a[indices].sum(axis=1)
        counts_d = solve_d[indices].sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            cps_a = a[indices].sum(axis=1) / counts_a
            cps_d = d[indices].sum(axis=1) / counts_d
            cps_diff = cps_d - cps_a
        out["analyses"][field] = {
            "mean_tokens_per_attempt": {"A0": float(a.mean()), "DPO": float(d.mean())},
            "wilcoxon_dpo_minus_a0": {"p_two_sided": float(test.pvalue), "statistic": float(test.statistic),
                                      "zero_differences": int(np.sum(diff == 0))},
            "tokens_per_verified_solve": {"A0": float(a.sum()/solve_a.sum()) if solve_a.sum() else None,
                                          "DPO": float(d.sum()/solve_d.sum()) if solve_d.sum() else None,
                                          "dpo_minus_a0_ci_95": interval(cps_diff),
                                          "undefined_bootstrap_draws": int(np.sum(~np.isfinite(cps_diff)))}}
    raw = out["analyses"]["raw_tokens"]
    imp = out["analyses"]["median_imputed_tokens"]
    out["conclusion_changed"] = {
        "paired_wilcoxon_p_below_0_05": (raw["wilcoxon_dpo_minus_a0"]["p_two_sided"] < 0.05)
                                        != (imp["wilcoxon_dpo_minus_a0"]["p_two_sided"] < 0.05),
        "tokens_per_solve_ci_excludes_zero": (
            (raw["tokens_per_verified_solve"]["dpo_minus_a0_ci_95"] is not None and
             all(x > 0 for x in raw["tokens_per_verified_solve"]["dpo_minus_a0_ci_95"]) or
             raw["tokens_per_verified_solve"]["dpo_minus_a0_ci_95"] is not None and
             all(x < 0 for x in raw["tokens_per_verified_solve"]["dpo_minus_a0_ci_95"])) !=
            (imp["tokens_per_verified_solve"]["dpo_minus_a0_ci_95"] is not None and
             (all(x > 0 for x in imp["tokens_per_verified_solve"]["dpo_minus_a0_ci_95"]) or
              all(x < 0 for x in imp["tokens_per_verified_solve"]["dpo_minus_a0_ci_95"]))))}
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT)
    parser.add_argument("--output", type=Path, default=DEFAULT / "token_sensitivity.json")
    args = parser.parse_args()
    result = analyze(args.root)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
