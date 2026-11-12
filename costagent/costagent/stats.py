"""Compare evaluated arms on the Kaggle dev tasks (THEORY.md section 11).

    python -m costagent.stats --kaggle-tasks data/tasks.jsonl --baseline A0 \
        --arm A0=results/a0 --arm A1=results/a1 --arm A6b=results/a6b_s1,results/a6b_s2 --out results

    Unit of analysis is the task; seeds are averaged within a task. Missing tasks
    block inferential output unless --allow-incomplete is explicitly requested.
    """
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from .costs import counts
from .traces import kaggle_ids, load_run


def arm_table(dirs, kid):
    solved, calls, toks = defaultdict(list), defaultdict(list), defaultdict(list)
    for d in dirs:
        for r in load_run(Path(d), kid):
            c = counts(r)
            solved[r["task_id"]].append(float(r["solved"]))
            calls[r["task_id"]].append(c["calls"])
            toks[r["task_id"]].append(c["tokens"])
    return {t: (np.mean(solved[t]), np.mean(calls[t]), np.mean(toks[t])) for t in solved}


def boot(fn, n, B=10000, seed=0):
    rng = np.random.default_rng(seed)
    vals = np.array([fn(rng.integers(0, n, n)) for _ in range(B)])
    return np.percentile(vals, [2.5, 97.5])


def signflip_p(d, B=20000, seed=0):
    d = np.asarray(d, float)
    if not np.any(d):
        return 1.0
    rng = np.random.default_rng(seed)
    obs = abs(d.mean())
    flips = rng.choice([-1.0, 1.0], size=(B, d.size))
    return float((np.abs((flips * d).mean(1)) >= obs - 1e-12).mean())


def holm(ps):
    order = np.argsort(ps); m = len(ps); adj = [0.0] * m; run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * ps[i]))
        adj[i] = run
    return adj


def ensure_complete_coverage(arms, tasks):
    """Refuse inferential statistics when any arm lacks a task outcome/trace."""
    expected = set(tasks)
    missing = {name: sorted(expected - set(records)) for name, records in arms.items()
               if expected - set(records)}
    if missing:
        details = "; ".join(f"{name}: {len(ids)} missing ({', '.join(ids[:5])})"
                            for name, ids in missing.items())
        raise ValueError(f"Incomplete evaluation coverage; refusing paired statistics: {details}")


def complete_case_tasks(arms, tasks):
    """Keep only tasks with an interpretable outcome in every arm."""
    available = set(tasks)
    for records in arms.values():
        available &= set(records)
    included = sorted(available)
    if not included:
        raise ValueError("No tasks have interpretable outcomes in every arm")
    excluded = {task: [arm for arm, records in arms.items() if task not in records]
                for task in sorted(set(tasks) - available)}
    return included, excluded


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kaggle-tasks", required=True)
    ap.add_argument("--arm", action="append", required=True, help="NAME=dir[,dir...]")
    ap.add_argument("--baseline", default="A0")
    ap.add_argument("--out", default="results")
    ap.add_argument("--ni-margin", type=float, default=0.05)
    ap.add_argument("--allow-incomplete", action="store_true",
                    help="Exploratory only: treat absent task outcomes as unsolved")
    ap.add_argument("--complete-case", action="store_true",
                    help="Use only tasks with interpretable outcomes in every arm; report exclusions")
    args = ap.parse_args()
    from scipy.stats import wilcoxon

    kid = kaggle_ids(Path(args.kaggle_tasks))
    arms = {}
    for spec in args.arm:
        name, dirs = spec.split("=", 1)
        arms[name] = arm_table([d for d in dirs.split(",") if d], kid)
    requested_tasks = sorted(kid) if kid else sorted(set().union(*[set(a) for a in arms.values()]))
    if args.complete_case and args.allow_incomplete:
        ap.error("--complete-case and --allow-incomplete are mutually exclusive")
    excluded = {}
    tasks = requested_tasks
    if args.complete_case:
        tasks, excluded = complete_case_tasks(arms, requested_tasks)
    elif not args.allow_incomplete:
        ensure_complete_coverage(arms, tasks)
    n = len(tasks)

    def vec(a, j, fill):
        return np.array([arms[a][t][j] if t in arms[a] else fill for t in tasks], float)

    rows, comps = [], []
    base_s, base_c = vec(args.baseline, 0, 0.0), vec(args.baseline, 1, np.nan)
    for a in arms:
        s, c, tk = vec(a, 0, 0.0), vec(a, 1, np.nan), vec(a, 2, np.nan)
        cc = np.nan_to_num(c, nan=np.nanmean(c))
        row = {"arm": a, "tasks_present": sum(t in arms[a] for t in tasks), "solve_rate": s.mean(),
            "solve_ci": boot(lambda i: s[i].mean(), n).tolist(),
            "mean_calls": float(np.nanmean(c)), "calls_ci": boot(lambda i: np.nanmean(c[i]), n).tolist(),
            "mean_tokens": float(np.nanmean(tk)),
            "calls_per_solve": float(cc.sum() / max(s.sum(), 1e-9)),
            "calls_per_solve_ci": boot(lambda i: cc[i].sum() / max(s[i].sum(), 1e-9), n).tolist()}
        if a != args.baseline:
            d = s - base_s
            row["delta_solve"] = d.mean()
            row["delta_solve_ci"] = boot(lambda i: d[i].mean(), n).tolist()
            row["p_solve"] = signflip_p(d)
            ok = ~np.isnan(c) & ~np.isnan(base_c)
            try:
                row["p_calls"] = float(wilcoxon(np.log1p(c[ok]), np.log1p(base_c[ok])).pvalue)
            except ValueError:
                row["p_calls"] = 1.0
            lo = np.percentile([d[np.random.default_rng(k).integers(0, n, n)].mean() for k in range(4000)], 5)
            row["non_inferior"] = bool(lo >= -args.ni_margin)
            comps.append(row)
        rows.append(row)
    for key in ("p_solve", "p_calls"):
        adj = holm([r[key] for r in comps]) if comps else []
        for r, p in zip(comps, adj):
            r[key + "_holm"] = p

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "coverage.json").write_text(json.dumps({
        "requested_tasks": len(requested_tasks),
        "paired_tasks": len(tasks),
        "included_task_ids": tasks,
        "excluded_task_ids": excluded,
        "per_arm_interpretable": {arm: len(set(records) & set(requested_tasks))
                                  for arm, records in arms.items()},
        "method": "complete_case" if args.complete_case else
                  "missing_as_unsolved" if args.allow_incomplete else "strict",
    }, indent=2) + "\n")
    json.dump(rows, open(out / "results.json", "w"), indent=1, default=float)
    f = lambda x: f"{x:.3f}"
    lines = [f"Tasks: {n} paired of {len(requested_tasks)} requested. Baseline: {args.baseline}. "
             "CIs are 95% task-cluster bootstrap.", "",
            "| arm | tasks | solve rate [CI] | Δ solve vs base [CI] | p (Holm) | non-inferior (−5 pts) | "
            "mean calls [CI] | p calls (Holm) | calls per solve [CI] | mean tokens |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        ds = (f"{f(r['delta_solve'])} [{f(r['delta_solve_ci'][0])}, {f(r['delta_solve_ci'][1])}]"
            if "delta_solve" in r else "—")
        lines.append(
            f"| {r['arm']} | {r['tasks_present']} | {f(r['solve_rate'])} [{f(r['solve_ci'][0])}, {f(r['solve_ci'][1])}] "
            f"| {ds} | {f(r['p_solve_holm']) if 'p_solve_holm' in r else '—'} | "
            f"{r.get('non_inferior', '—')} | {r['mean_calls']:.1f} [{r['calls_ci'][0]:.1f}, {r['calls_ci'][1]:.1f}] | "
            f"{f(r['p_calls_holm']) if 'p_calls_holm' in r else '—'} | {r['calls_per_solve']:.1f} "
            f"[{r['calls_per_solve_ci'][0]:.1f}, {r['calls_per_solve_ci'][1]:.1f}] | {r['mean_tokens']:.0f} |")
    (out / "results_table.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(5, 4))
        for r in rows:
            ax.errorbar(r["mean_calls"], r["solve_rate"],
                        xerr=[[r["mean_calls"] - r["calls_ci"][0]], [r["calls_ci"][1] - r["mean_calls"]]],
                        yerr=[[r["solve_rate"] - r["solve_ci"][0]], [r["solve_ci"][1] - r["solve_rate"]]],
                        fmt="o", capsize=3)
            ax.annotate(r["arm"], (r["mean_calls"], r["solve_rate"]), xytext=(4, 4), textcoords="offset points")
        ax.set_xlabel("mean tool calls per task"); ax.set_ylabel("solve rate")
        fig.tight_layout(); fig.savefig(out / "pareto.png", dpi=150)
    except ImportError:
        print("matplotlib not installed; skipped pareto.png")


if __name__ == "__main__":
    main()
