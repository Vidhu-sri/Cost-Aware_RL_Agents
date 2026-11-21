#!/usr/bin/env python3
"""Extract and analyze the archived 40-task six-arm pilot, CPU only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import process_analysis as pa


def main() -> int:
    pa._env()
    out = pa.OUT
    out.mkdir(parents=True, exist_ok=True)
    sources = pa.discover_pilot_sources()
    discovery = pa.detect_pilot_sources(sources)
    if not discovery["complete"]:
        raise RuntimeError(f"Pilot source set incomplete or mispaired: {discovery}")

    attempts, turns, calls = [], [], []
    for arm, task_id, trace in sources:
        a, t, c = pa.extract_attempt(arm, task_id, trace)
        a["cohort"] = "pilot"
        for row in t + c:
            row["cohort"] = "pilot"
        attempts.append(a)
        turns.extend(t)
        calls.extend(c)
    pa.write_csv(out / "pilot_attempts.csv", attempts)
    pa.write_csv(out / "pilot_turns.csv", turns)
    pa.write_csv(out / "pilot_calls.csv", calls)

    by_task = {}
    for row in attempts:
        by_task.setdefault(row["task_id"], {})[row["arm"]] = row
    paired_tasks = sorted(t for t, d in by_task.items() if all(a in d for a in pa.EXPECTED_PILOT_ARMS))
    contrasts = []
    metrics = ["turns", "calls", "mean_generation_seconds_per_turn",
               "mean_tool_seconds_per_turn", "total_generation_seconds",
               "total_tool_seconds", "calls_per_trace_minute"]
    comparisons = [("DPO", "A2"), ("DPO", "A0"), ("router", "A0"), ("A9", "A2")]
    for arm, baseline in comparisons:
        for metric in metrics:
            diff = pa.paired_diff_ci(by_task, metric, arm, baseline)
            ratio = pa.paired_ratio_ci(by_task, metric, arm, baseline)
            contrasts.append({"arm": arm, "baseline": baseline, "metric": metric,
                              **diff, "geometric_ratio": ratio["ratio"],
                              "ratio_ci_low": ratio["ci_low"], "ratio_ci_high": ratio["ci_high"],
                              "ratio_n_tasks": ratio["n_tasks"]})

    mix = pa.action_mix_test(calls, paired_tasks, list(pa.EXPECTED_PILOT_ARMS))
    survival = {}
    for arm, baseline in comparisons:
        times_a, events_a, times_b, events_b = [], [], [], []
        for task in paired_tasks:
            a, b = by_task[task][arm], by_task[task][baseline]
            times_a.append(a["survival_time_seconds"]); events_a.append(a["first_edit_event"])
            times_b.append(b["survival_time_seconds"]); events_b.append(b["first_edit_event"])
        survival[f"{arm}_vs_{baseline}"] = pa.paired_logrank_permutation(
            times_a, events_a, times_b, events_b
        )

    summaries = {}
    coverage = {}
    for arm in pa.EXPECTED_PILOT_ARMS:
        aa = [r for r in attempts if r["arm"] == arm]
        tt = [r for r in turns if r["arm"] == arm]
        cc = [r for r in calls if r["arm"] == arm]
        summaries[arm] = {
            "attempts": len(aa),
            "verified_pass": sum(r["verified_resolved"] is True for r in aa),
            "verified_fail": sum(r["verified_resolved"] is False for r in aa),
            "ungraded": sum(r["verified_resolved"] is None for r in aa),
            "timeouts": sum(r["agent_timeout"] for r in aa),
            "no_patch": sum(r["no_patch"] is True for r in aa),
            "explicit_submit": sum(r["ended_with_explicit_submit_patch"] for r in aa),
            "mean_turns": pa._mean(r["turns"] for r in aa),
            "mean_calls": pa._mean(r["calls"] for r in aa),
            "mean_calls_per_minute": pa._mean(r["calls_per_trace_minute"] for r in aa),
            "mean_generation_seconds_per_turn": pa._mean(r["mean_generation_seconds_per_turn"] for r in aa),
            "mean_tool_seconds_per_turn": pa._mean(r["mean_tool_seconds_per_turn"] for r in aa),
            "mean_total_generation_seconds": pa._mean(r["total_generation_seconds"] for r in aa),
            "mean_total_tool_seconds": pa._mean(r["total_tool_seconds"] for r in aa),
        }
        coverage[arm] = {
            "model_turns": len(tt),
            "completion_token_turns": sum(t["completion_tokens"] is not None for t in tt),
            "prompt_token_turns": sum(t["prompt_tokens"] is not None for t in tt),
            "thinking_token_turns": sum(t["thinking_tokens"] is not None for t in tt),
            "generation_timed_turns": sum(t["generation_seconds"] is not None for t in tt),
            "tool_timed_turns": sum(t["tool_seconds"] is not None for t in tt),
            "observation_turns": sum(t["observation_chars"] > 0 for t in tt),
            "calls": len(cc),
            "repeated_calls": sum(bool(c["repeats_previous_call"]) for c in cc),
        }

    labels = {"turns": "Turns/attempt", "calls": "Tool calls/attempt",
              "mean_generation_seconds_per_turn": "Generation seconds/turn",
              "mean_tool_seconds_per_turn": "Tool seconds/turn",
              "total_generation_seconds": "Summed generation seconds/attempt",
              "total_tool_seconds": "Summed tool seconds/attempt",
              "calls_per_trace_minute": "Calls/observed trace minute"}
    report = [
        "# Six-arm pilot process analysis",
        "",
        "Exploratory analysis of existing traces only. No GPU/model work was performed.",
        "Sources are the six run directories listed in `pilot_statistics.json`; each has 40 task directories, one outcome, and one authoritative trace per task. All six manifests identify the same 40 task IDs.",
        "Per-event timing is reconstructed from differences in adjacent `elapsed_s` values because the trace field is a cumulative session clock. This corrects the interpretation in the original extraction rule; see the main process report.",
        "Intervals use 20,000 paired task-cluster bootstrap resamples (seed 20261118). Differences are comparison arm minus baseline; ratios are geometric ratios of task-level attempt means.",
        "",
        "## Preregistered contrasts",
        "",
        "| Arm vs baseline | Metric | n | Difference [95% CI] | Ratio [95% CI] |",
        "|---|---|---:|---:|---:|",
    ]
    for r in contrasts:
        d = "NA" if r["estimate"] is None else f"{r['estimate']:.3f} [{r['ci_low']:.3f}, {r['ci_high']:.3f}]"
        q = "NA" if r["geometric_ratio"] is None else f"{r['geometric_ratio']:.3f} [{r['ratio_ci_low']:.3f}, {r['ratio_ci_high']:.3f}]"
        report.append(f"| {r['arm']} vs {r['baseline']} | {labels[r['metric']]} | {r['n_tasks']} | {d} | {q} |")
    report += ["", "## Action mix", "",
               f"Six-arm task-label permutation test: L2²={mix['permutation_statistic_l2_squared']:.6f}, p={mix['p_value']:.4f} over {mix['paired_task_swap_permutations']:,} permutations.",
               "", "| Action | " + " | ".join(f"{a} n (%)" for a in pa.EXPECTED_PILOT_ARMS) + " |",
               "|---|" + "---:|" * len(pa.EXPECTED_PILOT_ARMS)]
    for action in pa.ACTION_TYPES:
        cells = [f"{mix['counts'][arm][action]} ({100*mix['proportions'][arm][action]:.1f}%)" for arm in pa.EXPECTED_PILOT_ARMS]
        report.append("| " + action + " | " + " | ".join(cells) + " |")
    report += ["", "## Outcomes and logging coverage", "",
               "| Arm | n | Pass | Fail | Ungraded | Timeout | No patch | Mean turns | Mean calls | Calls/min | Gen sec/turn | Tool sec/turn |",
               "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for arm, s in summaries.items():
        report.append(f"| {arm} | {s['attempts']} | {s['verified_pass']} | {s['verified_fail']} | {s['ungraded']} | {s['timeouts']} | {s['no_patch']} | {s['mean_turns']:.2f} | {s['mean_calls']:.2f} | {s['mean_calls_per_minute']:.2f} | {s['mean_generation_seconds_per_turn']:.3f} | {s['mean_tool_seconds_per_turn']:.3f} |")
    report += ["", "Token/field coverage by arm is in `pilot_statistics.json`. No distinct thinking-token field is logged; the registered thinking-effort contrasts and solve association are unavailable. Cox shared-task-frailty support is absent from the installed environment. Pilot log-rank pairwise results are available in the JSON; the KM curves are in the combined `survival.png`.", ""]
    (out / "pilot_REPORT.md").write_text("\n".join(report), encoding="utf-8")

    (out / "pilot_statistics.json").write_text(json.dumps({
        "exploratory": True, "seed": pa.SEED, "bootstrap_resamples": pa.BOOTSTRAPS,
        "source_discovery": discovery, "paired_tasks": len(paired_tasks),
        "outcomes": summaries, "field_coverage": coverage, "contrasts": contrasts,
        "action_mix": mix, "time_to_first_edit": survival,
        "source_dirs": {arm: str(pa.ROOT / "costagent/artifacts/mixed-temperature-v1/evaluation" / pa.PILOT_RUNS[arm])
                        for arm in pa.EXPECTED_PILOT_ARMS},
    }, indent=2) + "\n", encoding="utf-8")

    # Refresh the combined KM figure with pilot and confirmatory records.
    conf_rows = []
    conf_turns, conf_calls = [], []
    for arm, task, trace in pa.discover_confirmatory():
        row, turn_rows, call_rows = pa.extract_attempt(arm, task, trace)
        row["cohort"] = "confirmatory"
        conf_rows.append(row)
        for x in turn_rows + call_rows:
            x["cohort"] = "confirmatory"
        conf_turns.extend(turn_rows)
        conf_calls.extend(call_rows)
    pa.write_csv(out / "attempts.csv", conf_rows)
    pa.write_csv(out / "turns.csv", conf_turns)
    pa.write_csv(out / "calls.csv", conf_calls)
    pa.survival_plot(attempts + conf_rows, out / "survival.png")

    # The previous report incorrectly said the pilot was missing. Replace that
    # discovery note and link the fully reported pilot supplement.
    report_path = out / "REPORT.md"
    if report_path.exists():
        text = report_path.read_text(encoding="utf-8")
        old = "The requested six-arm, 40-task pilot was not found in the local result roots. Candidate arm-specific pilot trace directories: `[]`. The older `baseline-kit/results/docker-gemma129-*` traces are single competition-task runs without these arm labels, so they were not substituted. Pilot-only contrasts are unavailable."
        new = "The six-arm, 40-task pilot was located under `costagent/artifacts/mixed-temperature-v1/evaluation/`; each of A0, A1, A2, DPO, A9-contrast, and router has 40 task directories with matching IDs. See `pilot_REPORT.md` and `pilot_statistics.json` for the preregistered pilot contrasts, action mix, and arm outcomes."
        if old in text:
            text = text.replace(old, new)
        summary = {}
        for arm in ("A0", "router"):
            subset = [r for r in conf_rows if r["arm"] == arm]
            summary[arm] = {
                "attempts": len(subset),
                "verified_pass": sum(r["verified_resolved"] is True for r in subset),
                "verified_fail": sum(r["verified_resolved"] is False for r in subset),
                "ungraded": sum(r["verified_resolved"] is None for r in subset),
                "agent_timeouts": sum(r["agent_timeout"] for r in subset),
                "no_patch": sum(r["no_patch"] is True for r in subset),
                "explicit_submit": sum(r["ended_with_explicit_submit_patch"] for r in subset),
                "first_edit_observed": sum(r["first_edit_event"] for r in subset),
                "mean_turns": pa._mean(r["turns"] for r in subset),
                "mean_calls": pa._mean(r["calls"] for r in subset),
                "mean_actions_per_minute": pa._mean(r["calls_per_trace_minute"] for r in subset),
            }
        section = [
            "## Outcome snapshot", "",
            "| Arm | Attempts | Verified pass | Verified fail | Ungraded | Agent timeouts | No patch | Explicit submit | First edit observed | Mean turns | Mean calls | Mean calls/min |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for arm in ("A0", "router"):
            x = summary[arm]
            section.append(f"| {arm} | {x['attempts']} | {x['verified_pass']} | {x['verified_fail']} | {x['ungraded']} | {x['agent_timeouts']} | {x['no_patch']} | {x['explicit_submit']} | {x['first_edit_observed']} | {x['mean_turns']:.2f} | {x['mean_calls']:.2f} | {x['mean_actions_per_minute']:.2f} |")
        begin = text.find("## Outcome snapshot")
        end = text.find("## Preregistration deviations and limitations", begin)
        if begin >= 0 and end > begin:
            text = text[:begin] + "\n".join(section) + "\n\n" + text[end:]
        text += "\n\nThe six-arm pilot analysis is in [pilot_REPORT.md](pilot_REPORT.md); arm paths and detailed coverage are in [pilot_statistics.json](pilot_statistics.json). The combined Kaplan–Meier figure includes pilot and confirmatory panels.\n"
        report_path.write_text(text, encoding="utf-8")
        stats_path = out / "statistics.json"
        if stats_path.exists():
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
            stats["pilot_discovery"] = discovery
            stats["pilot_outcomes"] = summaries
            stats["confirmatory_outcomes"] = summary
            stats_path.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(f"Pilot extraction complete: {len(attempts)} attempts, {len(paired_tasks)} paired tasks, action-mix p={mix['p_value']:.4g}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
