#!/usr/bin/env python3
"""Rebuild preregistered process metrics from saved Kaggle traces only.

No model or GPU is loaded. All derived files are written below results/process.
The script reports missing cohorts and logged fields rather than imputing them.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/process"
BOOTSTRAPS = 20_000
SEED = 20261118
EXPECTED_PILOT_ARMS = ("A0", "A1", "A2", "DPO", "A9", "router")
ACTION_TYPES = ("read", "shell", "edit", "graph", "test", "submit", "other")
PILOT_RUNS = {
    "A0": "paper40-20261106a-A0-test-seed-42",
    "A1": "paper40-20261106a-A1-test-seed-42",
    "A2": "paper40-20261106a-A2-test-seed-42",
    "DPO": "paper40-20261106a-DPO-test-seed-42",
    "A9": "paper40-20261106a-A9-contrast-test-seed-42",
    "router": "router40-20261108a-test-seed-42",
}


def _env() -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/gdac-process-matplotlib")
    os.environ.setdefault("XDG_CACHE_HOME", "/tmp/gdac-process-cache")
    Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)
    Path(os.environ["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _usage(step: dict, calls: list[dict]) -> dict:
    for call in calls:
        ex = call.get("extra") or {}
        if isinstance(ex.get("usage"), dict):
            return ex["usage"]
    extra = step.get("extra") or {}
    return extra.get("usage") if isinstance(extra.get("usage"), dict) else {}


def _reasoning_tokens(usage: dict):
    for key in ("reasoning_tokens", "thinking_tokens"):
        if isinstance(usage.get(key), (int, float)):
            return float(usage[key])
    for key in ("completion_tokens_details", "output_tokens_details", "details"):
        sub = usage.get(key)
        if isinstance(sub, dict):
            for field in ("reasoning_tokens", "thinking_tokens"):
                if isinstance(sub.get(field), (int, float)):
                    return float(sub[field])
    return None


def _test_command(command: str) -> bool:
    c = command.strip().lower()
    return bool(
        re.search(r"(^|\s)(pytest|tox)(\s|$)", c)
        or re.search(r"(^|\s)(python|python3)(\s+-m\s+)(pytest|unittest)(\s|$)", c)
        or re.search(r"(^|\s)(python|python3)(\s+[^\s]*test[^\s]*\.py)(\s|$)", c)
        or re.search(r"(^|\s)unittest(\s|$)", c)
    )


def _action(call: dict) -> str:
    name = str(call.get("function_name", ""))
    if name == "read_file":
        return "read"
    if name in {"edit_file", "write_file"}:
        return "edit"
    if name == "submit_patch":
        return "submit"
    if name in {"get_code_neighbors", "get_code_subgraph", "search_similar_code", "code_analyzer_agent"}:
        return "graph"
    if name == "run_command":
        args = call.get("arguments") or {}
        command = args.get("command", "") if isinstance(args, dict) else ""
        return "test" if _test_command(str(command)) else "shell"
    return "other"


def _timestamp(obj: dict | None):
    if not isinstance(obj, dict):
        return None
    extra = obj.get("extra") or {}
    value = extra.get("timestamp")
    return float(value) if isinstance(value, (int, float)) else None


def discover_confirmatory() -> list[tuple[str, str, Path]]:
    rows = []
    base = ROOT / "results/confirmatory"
    for arm in ("A0", "router"):
        arm_dir = base / arm
        if not arm_dir.is_dir():
            continue
        for trace_path in sorted(arm_dir.glob("*/attempt-0/evaluation/tasks/*/traces/trace_*.json")):
            task_id = trace_path.stem.removeprefix("trace_")
            rows.append((arm, task_id, trace_path))
    return rows


def discover_pilot_sources() -> list[tuple[str, str, Path]]:
    """Read the archived six-arm paper pilot under costagent/artifacts."""
    rows = []
    base = ROOT / "costagent/artifacts/mixed-temperature-v1/evaluation"
    for arm in EXPECTED_PILOT_ARMS:
        run_dir = base / PILOT_RUNS[arm]
        for task_dir in sorted((run_dir / "tasks").glob("*")):
            trace = task_dir / "traces" / f"trace_{task_dir.name}.json"
            if task_dir.is_dir() and trace.is_file():
                rows.append((arm, task_dir.name, trace))
    return rows


def detect_pilot_sources(rows: list[tuple[str, str, Path]]) -> dict:
    counts = {arm: sum(r[0] == arm for r in rows) for arm in EXPECTED_PILOT_ARMS}
    task_sets = {arm: {r[1] for r in rows if r[0] == arm} for arm in EXPECTED_PILOT_ARMS}
    same_tasks = all(task_sets[arm] == task_sets["A0"] for arm in EXPECTED_PILOT_ARMS)
    return {
        "found": [{"arm": arm, "path": str(ROOT / "costagent/artifacts/mixed-temperature-v1/evaluation" / PILOT_RUNS[arm]),
                   "trace_files": counts[arm]} for arm in EXPECTED_PILOT_ARMS if counts[arm]],
        "counts": counts,
        "unique_tasks_by_arm": {arm: len(task_sets[arm]) for arm in EXPECTED_PILOT_ARMS},
        "identical_task_sets": same_tasks,
        "complete": all(counts[arm] == 40 for arm in EXPECTED_PILOT_ARMS) and same_tasks,
    }


def extract_attempt(arm: str, task_id: str, trace_path: Path) -> tuple[dict, list[dict], list[dict]]:
    trace = load_json(trace_path)
    task_dir = trace_path.parent.parent
    outcome_path = task_dir / "outcome.json"
    monitor_path = task_dir / "monitor.json"
    outcome = load_json(outcome_path) if outcome_path.is_file() else {}
    monitor = load_json(monitor_path) if monitor_path.is_file() else {}

    turns, calls_out = [], []
    prev_signature = None
    agent_step_index = 0
    timestamps = []
    explicit_submit = False
    first_edit = None
    first_edit_turn = None
    prior_elapsed = None

    for step in trace.get("steps", []):
        if step.get("source") != "agent":
            if step.get("source") == "user":
                value = (step.get("extra") or {}).get("elapsed_s")
                if isinstance(value, (int, float)) and math.isfinite(float(value)):
                    prior_elapsed = float(value)
            continue
        agent_step_index += 1
        calls = step.get("tool_calls") or []
        usage = _usage(step, calls)
        obs = step.get("observation") or {}
        obs_content = obs.get("content", "") if isinstance(obs, dict) else ""
        if not isinstance(obs_content, str):
            obs_content = json.dumps(obs_content, ensure_ascii=False)
        obs_extra = obs.get("extra", {}) if isinstance(obs, dict) else {}
        obs_ts = _timestamp(obs)
        if obs_ts is not None:
            timestamps.append(obs_ts)
        obs_elapsed = obs_extra.get("elapsed_s") if isinstance(obs_extra, dict) else None
        call_extra = (calls[0].get("extra") or {}) if calls else {}
        call_elapsed = call_extra.get("elapsed_s")
        if call_elapsed is None:
            call_elapsed = (step.get("extra") or {}).get("elapsed_s")
        # elapsed_s is cumulative from session start: derive the current model
        # and tool durations from adjacent event boundaries.
        generation_seconds = (
            float(call_elapsed) - prior_elapsed
            if isinstance(call_elapsed, (int, float)) and prior_elapsed is not None
            else None
        )
        tool_seconds = (
            float(obs_elapsed) - float(call_elapsed)
            if isinstance(obs_elapsed, (int, float)) and isinstance(call_elapsed, (int, float))
            else None
        )
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        thinking_tokens = _reasoning_tokens(usage)
        step_ts = _timestamp(step)
        if step_ts is not None:
            timestamps.append(step_ts)
        if not calls:
            turns.append({
                "arm": arm, "task_id": task_id, "turn": agent_step_index,
                "action_type": "other", "completion_tokens": completion_tokens,
                "thinking_tokens": thinking_tokens, "prompt_tokens": prompt_tokens,
                "generation_seconds": generation_seconds, "tool_seconds": tool_seconds,
                "observation_chars": len(obs_content), "call_count": 0,
                "repeats_previous_call": None,
            })
            if isinstance(obs_elapsed, (int, float)):
                prior_elapsed = float(obs_elapsed)
            elif isinstance(call_elapsed, (int, float)):
                prior_elapsed = float(call_elapsed)
            continue

        repeated_flags = []
        for call in calls:
            name = str(call.get("function_name", ""))
            args = call.get("arguments") or {}
            try:
                canon = json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            except TypeError:
                canon = repr(args)
            signature = (name, canon)
            repeated = signature == prev_signature
            prev_signature = signature
            repeated_flags.append(repeated)
            action = _action(call)
            call_ts = _timestamp(call)
            if call_ts is not None:
                timestamps.append(call_ts)
            if action == "edit" and first_edit is None:
                first_edit = call_ts
                first_edit_turn = agent_step_index
            if name == "submit_patch":
                explicit_submit = True
            calls_out.append({
                "arm": arm, "task_id": task_id, "turn": agent_step_index,
                "tool": name, "action_type": action,
                "arguments_json": canon,
                "repeats_previous_call": repeated,
                "observation_chars": len(obs_content),
                "tool_seconds": tool_seconds,
            })
        turns.append({
            "arm": arm, "task_id": task_id, "turn": agent_step_index,
            "action_type": _action(calls[0]), "completion_tokens": completion_tokens,
            "thinking_tokens": thinking_tokens, "prompt_tokens": prompt_tokens,
            "generation_seconds": generation_seconds, "tool_seconds": tool_seconds,
            "observation_chars": len(obs_content), "call_count": len(calls),
            "repeats_previous_call": any(repeated_flags),
        })
        if isinstance(obs_elapsed, (int, float)):
            prior_elapsed = float(obs_elapsed)
        elif isinstance(call_elapsed, (int, float)):
            prior_elapsed = float(call_elapsed)

    start_candidates = []
    for step in trace.get("steps", []):
        if step.get("source") == "user":
            ts = _timestamp(step)
            if ts is not None:
                start_candidates.append(ts)
    start_ts = min(start_candidates) if start_candidates else (min(timestamps) if timestamps else None)
    end_ts = max(timestamps) if timestamps else None
    session_span = max(0.0, end_ts - start_ts) if start_ts is not None and end_ts is not None else None
    agent_timeout = bool(outcome.get("agent_timeout") or monitor.get("timed_out"))
    duration = min(300.0, session_span) if session_span is not None else None
    if agent_timeout:
        duration = 300.0
    first_edit_seconds = (
        max(0.0, first_edit - start_ts)
        if first_edit is not None and start_ts is not None else None
    )
    patch_bytes = outcome.get("patch_bytes")
    test_exit_code = outcome.get("test_exit_code")
    verified_resolved = True if test_exit_code == 0 else False if test_exit_code == 1 else None
    attempt = {
        "arm": arm, "task_id": task_id,
        "trace_path": str(trace_path.relative_to(ROOT)),
        "trace_sha256": sha256(trace_path),
        "turns": agent_step_index,
        "calls": len(calls_out),
        "mean_thinking_tokens_per_turn": (
            sum(t["thinking_tokens"] for t in turns if t["thinking_tokens"] is not None)
            / sum(t["thinking_tokens"] is not None for t in turns)
            if any(t["thinking_tokens"] is not None for t in turns) else None
        ),
        "thinking_token_turns": sum(t["thinking_tokens"] is not None for t in turns),
        "mean_generation_seconds_per_turn": _mean(t["generation_seconds"] for t in turns),
        "total_generation_seconds": sum(t["generation_seconds"] for t in turns if t["generation_seconds"] is not None),
        "generation_timed_turns": sum(t["generation_seconds"] is not None for t in turns),
        "mean_tool_seconds_per_turn": _mean(t["tool_seconds"] for t in turns),
        "total_tool_seconds": sum(t["tool_seconds"] for t in turns if t["tool_seconds"] is not None),
        "tool_timed_turns": sum(t["tool_seconds"] is not None for t in turns),
        "time_to_first_edit_seconds": first_edit_seconds,
        "first_edit_turn": first_edit_turn,
        "trace_session_seconds": session_span,
        "calls_per_trace_minute": (
            len(calls_out) * 60.0 / session_span if session_span and session_span > 0 else None
        ),
        "ended_with_explicit_submit_patch": explicit_submit,
        "agent_timeout": agent_timeout,
        "no_patch": patch_bytes == 0 if patch_bytes is not None else None,
        "verified_resolved": verified_resolved,
        "test_exit_code": test_exit_code,
        "verification_error": outcome.get("verification_error"),
        "agent_error": outcome.get("agent_error"),
        "outcome_duration_seconds": outcome.get("duration_seconds"),
        "survival_time_seconds": duration,
        "first_edit_event": first_edit_seconds is not None,
        "logged_prompt_tokens_total": (outcome.get("token_usage") or {}).get("total_prompt_tokens"),
        "logged_completion_tokens_total": (outcome.get("token_usage") or {}).get("total_completion_tokens"),
    }
    return attempt, turns, calls_out


def _mean(values):
    xs = [float(x) for x in values if isinstance(x, (int, float)) and math.isfinite(float(x))]
    return sum(xs) / len(xs) if xs else None


def write_csv(path: Path, rows: list[dict]) -> None:
    keys = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _bootstrap(values, seed=SEED, nboot=BOOTSTRAPS):
    import numpy as np
    a = np.asarray(values, dtype=float)
    if a.size == 0:
        return None, None, None
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, a.size, size=(nboot, a.size))
    means = a[draws].mean(axis=1)
    return float(a.mean()), float(np.quantile(means, .025)), float(np.quantile(means, .975))


def paired_diff_ci(rows_by_task, key, arm_a="router", arm_b="A0"):
    pairs = []
    for task, data in rows_by_task.items():
        a, b = data.get(arm_a), data.get(arm_b)
        if a is None or b is None:
            continue
        va, vb = a.get(key), b.get(key)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            pairs.append(float(va) - float(vb))
    if not pairs:
        return {"n_tasks": 0, "estimate": None, "ci_low": None, "ci_high": None}
    est, low, high = _bootstrap(pairs)
    return {"n_tasks": len(pairs), "estimate": est, "ci_low": low, "ci_high": high}


def paired_ratio_ci(rows_by_task, key, arm_a="router", arm_b="A0"):
    import math
    log_ratios = []
    for data in rows_by_task.values():
        a, b = data.get(arm_a), data.get(arm_b)
        if a is None or b is None:
            continue
        va, vb = a.get(key), b.get(key)
        if (isinstance(va, (int, float)) and isinstance(vb, (int, float))
                and va > 0 and vb > 0):
            log_ratios.append(math.log(float(va) / float(vb)))
    if not log_ratios:
        return {"n_tasks": 0, "ratio": None, "ci_low": None, "ci_high": None}
    est, low, high = _bootstrap(log_ratios)
    return {"n_tasks": len(log_ratios), "ratio": math.exp(est),
            "ci_low": math.exp(low), "ci_high": math.exp(high)}


def action_mix_test(call_rows, tasks, arms, nboot=BOOTSTRAPS, seed=SEED):
    import numpy as np
    rng = np.random.default_rng(seed)
    actions = list(ACTION_TYPES)
    counts = {arm: {a: 0 for a in actions} for arm in arms}
    task_arrays = []
    for task in tasks:
        task_array = np.zeros((len(arms), len(actions)), dtype=float)
        for row in call_rows:
            if row["task_id"] != task:
                continue
            if row["arm"] not in arms:
                continue
            vec = task_array[arms.index(row["arm"])]
            vec[actions.index(row["action_type"])] += 1
            counts[row["arm"]][row["action_type"]] += 1
        task_arrays.append(task_array)
    arr = np.asarray(task_arrays)

    def proportions(x):
        return x / np.maximum(1, x.sum(axis=-1, keepdims=True))

    def statistic(props):
        total = np.zeros(props.shape[0], dtype=float)
        for i in range(props.shape[1]):
            for j in range(i + 1, props.shape[1]):
                total += np.sum((props[:, i, :] - props[:, j, :]) ** 2, axis=1)
        return total

    pooled = arr.sum(axis=0)
    arm_props = proportions(pooled)
    observed = float(statistic(arm_props[None, :, :])[0])
    n = len(tasks)
    ge = 0
    for start in range(0, nboot, 250):
        size = min(250, nboot - start)
        perms = np.stack([rng.permuted(np.arange(len(arms))) for _ in range(size * n)]).reshape(size, n, len(arms))
        indices = np.broadcast_to(perms[:, :, :, None], (size, n, len(arms), len(actions)))
        swapped = np.take_along_axis(arr[None, :, :, :], indices, axis=2)
        perm_pooled = swapped.sum(axis=1)
        props = proportions(perm_pooled)
        stats = np.array([statistic(x[None, :, :])[0] for x in props])
        ge += int((stats >= observed).sum())
    return {
        "actions": actions,
        "counts": counts,
        "proportions": {arm: dict(zip(actions, arm_props[i].tolist())) for i, arm in enumerate(arms)},
        "permutation_statistic_l2_squared": observed,
        "paired_task_swap_permutations": nboot,
        "p_value": (ge + 1) / (nboot + 1),
    }


def km_curve(times, events, max_time=300.0):
    import numpy as np
    times = np.asarray(times, dtype=float)
    events = np.asarray(events, dtype=bool)
    survival = 1.0
    points = [(0.0, 1.0)]
    for t in sorted(set(times[events].tolist())):
        at_risk = int((times >= t).sum())
        at_event = int(((times == t) & events).sum())
        if at_risk:
            survival *= 1.0 - at_event / at_risk
        points.append((float(t), survival))
    points.append((max_time, survival))
    return points


def logrank_chisq(times_a, event_a, times_b, event_b):
    import numpy as np
    ta, ea = np.asarray(times_a, float), np.asarray(event_a, bool)
    tb, eb = np.asarray(times_b, float), np.asarray(event_b, bool)
    event_times = np.unique(np.concatenate([ta[ea], tb[eb]]))
    if len(event_times) == 0:
        return 0.0
    risk_a = (ta[:, None] >= event_times[None, :]).astype(float)
    risk_b = (tb[:, None] >= event_times[None, :]).astype(float)
    d_a = ((ta[:, None] == event_times[None, :]) & ea[:, None]).astype(float)
    d_b = ((tb[:, None] == event_times[None, :]) & eb[:, None]).astype(float)
    risk_total = risk_a.sum(axis=0) + risk_b.sum(axis=0)
    d_total = d_a.sum(axis=0) + d_b.sum(axis=0)
    score = 0.0
    variance = 0.0
    for j in range(len(event_times)):
        n1 = risk_a[:, j].sum(); n0 = risk_b[:, j].sum(); n = n1 + n0
        d = d_total[j]
        if n <= 0 or d <= 0:
            continue
        score += d_a[:, j].sum() - d * n1 / n
        if n > 1:
            variance += d * n1 * n0 * max(0.0, n - d) / (n * n * (n - 1))
    return float(score * score / variance) if variance > 0 else 0.0


def paired_logrank_permutation(times_a, event_a, times_b, event_b, nboot=BOOTSTRAPS, seed=SEED):
    import numpy as np
    ta, ea = np.asarray(times_a, float), np.asarray(event_a, bool)
    tb, eb = np.asarray(times_b, float), np.asarray(event_b, bool)
    event_times = np.unique(np.concatenate([ta[ea], tb[eb]]))
    n = len(ta)
    if not len(event_times):
        return {"statistic": 0.0, "p_value": 1.0, "permutations": nboot}
    ra = (ta[:, None] >= event_times[None, :]).astype(float)
    rb = (tb[:, None] >= event_times[None, :]).astype(float)
    da = ((ta[:, None] == event_times[None, :]) & ea[:, None]).astype(float)
    db = ((tb[:, None] == event_times[None, :]) & eb[:, None]).astype(float)
    rt = ra.sum(axis=0) + rb.sum(axis=0)
    dt = da.sum(axis=0) + db.sum(axis=0)

    def statistic(mask):
        n1 = ra.sum(axis=0)[None, :] + mask @ (rb - ra)
        n0 = rt[None, :] - n1
        nall = rt[None, :]
        d1sum = da.sum(axis=0)[None, :] + mask @ (db - da)
        exp = dt[None, :] * n1 / np.maximum(nall, 1)
        score = (d1sum - exp).sum(axis=1)
        v = dt[None, :] * n1 * n0 * np.maximum(0, nall - dt[None, :]) / np.maximum(nall * nall * (nall - 1), 1)
        variance = v.sum(axis=1)
        return np.divide(score * score, variance, out=np.zeros_like(score), where=variance > 0)

    observed = float(statistic(np.zeros((1, n)))[0])
    rng = np.random.default_rng(seed)
    ge = 0
    for start in range(0, nboot, 250):
        size = min(250, nboot - start)
        mask = rng.integers(0, 2, size=(size, n), dtype=np.int8)
        ge += int((statistic(mask) >= observed).sum())
    return {"statistic": observed, "p_value": (ge + 1) / (nboot + 1),
            "permutations": nboot, "method": "paired task-label swap log-rank permutation"}


def survival_plot(attempt_rows, out_path: Path) -> None:
    _env()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.0), sharey=True, constrained_layout=True)
    panels = [
        (axes[0], "pilot", ("A0", "A1", "A2", "DPO", "A9", "router")),
        (axes[1], "confirmatory", ("A0", "router")),
    ]
    palette = {"A0": "#3B6FB6", "A1": "#57A44C", "A2": "#9467BD",
               "DPO": "#D9534F", "A9": "#8C6D31", "router": "#E07A2D"}
    for ax, cohort, arms in panels:
        for arm in arms:
            subset = [r for r in attempt_rows if r.get("cohort") == cohort and r["arm"] == arm
                      and r["survival_time_seconds"] is not None]
            if not subset:
                continue
            pts = km_curve([r["survival_time_seconds"] for r in subset],
                           [r["first_edit_event"] for r in subset])
            x, y = zip(*pts)
            ax.step(x, y, where="post", linewidth=2.0, color=palette[arm], label=f"{arm} (n={len(subset)})")
        ax.set(xlim=(0, 300), ylim=(0, 1.02), xlabel="Seconds from issue prompt to first edit",
               title=f"{cohort.capitalize()} (Kaplan–Meier)")
        ax.grid(True, alpha=.22)
        ax.legend(frameon=False, fontsize=9)
    axes[0].set_ylabel("Probability no edit has occurred")
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def main() -> int:
    """Run the full preregistered pilot and confirmatory extraction."""
    from process_pilot_sources import main as run_all
    return run_all()


if __name__ == "__main__":
    sys.exit(main())
