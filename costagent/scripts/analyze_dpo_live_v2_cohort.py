#!/usr/bin/env python3
"""CPU-only analysis of a frozen DPO cohort against confirmatory A0.

The primary ID list is immutable input. The full-84 analysis is written to a
different file and never modifies the primary result.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/dpo_live_v2"
sys.path.insert(0, str(ROOT / "scripts"))
from process_analysis import extract_attempt  # noqa: E402

N_BOOT = 20_000
SEED = 20261119


def read_json(path: Path):
    return json.loads(path.read_text())


def wilson(k: int, n: int) -> list[float] | None:
    if n == 0:
        return None
    z = 1.959963984540054
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [max(0.0, mid - half), min(1.0, mid + half)]


def sample_test(values: list[float], direction: int, *, log_ratio=False, seed=SEED):
    """Paired sign-flip test and paired task bootstrap, 20k each."""
    v = np.asarray(values, dtype=float)
    if len(v) == 0 or not np.all(np.isfinite(v)):
        return {"n": len(v), "error": "missing or nonfinite paired observations"}
    rng = np.random.default_rng(seed)
    obs = float(v.mean())
    # Chunk draws to avoid competing with the live CPU snapshot verifier.
    null_exceed = 0
    boot = []
    for _ in range(N_BOOT // 1000):
        signs = rng.choice((-1.0, 1.0), size=(1000, len(v)))
        null = (signs * v).mean(axis=1)
        null_exceed += int(np.count_nonzero(direction * null >= direction * obs))
        ix = rng.integers(0, len(v), size=(1000, len(v)))
        boot.extend(v[ix].mean(axis=1).tolist())
    ci = np.quantile(np.asarray(boot), [.025, .975]).tolist()
    if log_ratio:
        return {"n": len(v), "estimate_ratio": math.exp(obs),
                "ci95_ratio": [math.exp(x) for x in ci],
                "p_one_sided": (null_exceed + 1) / (N_BOOT + 1)}
    return {"n": len(v), "estimate_difference": obs, "ci95_difference": ci,
            "p_one_sided": (null_exceed + 1) / (N_BOOT + 1)}


def load_pair(tid: str):
    dp = OUT / "attempts" / tid / "DPO" / "done.json"
    ap = ROOT / "results/confirmatory/A0" / tid / "attempt-0/evaluation/manifest.json"
    d = read_json(dp)
    am = read_json(ap)["attempts"]
    assert len(am) == 1 and am[0]["task_id"] == tid
    a = dict(am[0])
    a.update(read_json(ROOT / "results/confirmatory/A0" / tid /
                       "attempt-0/evaluation/tasks" / tid / "outcome.json"))
    dtrace = Path(d["result_dir"]) / "traces" / f"trace_{tid}.json"
    atrace = ROOT / "results/confirmatory/A0" / tid / "attempt-0/evaluation/tasks" / tid / "traces" / f"trace_{tid}.json"
    df, _, dc = extract_attempt("DPO", tid, dtrace)
    af, _, ac = extract_attempt("A0", tid, atrace)
    return d, a, df, af, dc, ac


def latest_snapshot_grades():
    p = OUT / "snapshot_verification.jsonl"
    latest = {}
    if p.exists():
        for line in p.read_text().splitlines():
            if line:
                row = json.loads(line)
                latest[(row["task_id"], row["patch_sha256"])] = row
    return latest


def found_lost(tids, pairs):
    grades = latest_snapshot_grades()
    failed = []
    found = []
    pending = []
    snapshots = 0
    for tid in tids:
        d = pairs[tid][0]
        if d.get("verification_status") not in ("failed", "no_patch"):
            continue
        failed.append(tid)
        manifest = Path(d["result_dir"]) / "snapshot_manifest.jsonl"
        rows = [json.loads(x) for x in manifest.read_text().splitlines() if x] if manifest.exists() else []
        # An empty working-tree diff cannot be a passing candidate patch. The
        # verifier rejects it as an infrastructure error because patch-file
        # mode requires a non-empty diff; that is not a missing grade.
        seen = {x.get("patch_sha256") for x in rows
                if x.get("status") == "ok" and x.get("patch_sha256")
                and x.get("patch_bytes", 0) > 0}
        snapshots += len(seen)
        state = [grades.get((tid, sha)) for sha in seen]
        if any(x and x.get("status") == "complete" and x.get("resolved") is True for x in state):
            found.append(tid)
        if any(x is None or x.get("status") != "complete" for x in state):
            pending.append(tid)
    # A found case remains found even if other snapshots are pending. The
    # denominator's negative cases are only final once all grades complete.
    settled = not pending
    result = {"valid_failed_attempts": len(failed), "unique_snapshot_diffs": snapshots,
              "found_then_lost_ids": found, "pending_grade_ids": pending,
              "all_snapshot_grades_complete": settled}
    if settled:
        result["proportion"] = len(found) / len(failed) if failed else None
        result["wilson_ci95"] = wilson(len(found), len(failed))
        if failed:
            rng = np.random.default_rng(SEED)
            binary = np.asarray([t in found for t in failed], dtype=float)
            draws = []
            for _ in range(N_BOOT // 1000):
                ix = rng.integers(0, len(failed), size=(1000, len(failed)))
                draws.extend(binary[ix].mean(axis=1).tolist())
            result["task_cluster_bootstrap_ci95"] = np.quantile(draws, [.025, .975]).tolist()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("primary", "full"), required=True)
    args = parser.parse_args()
    if args.scope == "primary":
        cohort = OUT / "primary_cohort.txt"
        assert cohort.exists(), "freeze and commit primary cohort before analysis"
        tids = [x for x in cohort.read_text().splitlines() if x and not x.startswith("#")]
    else:
        tids = sorted(p.parent.parent.name for p in (OUT / "attempts").glob("*/DPO/done.json")
                    if not read_json(p).get("smoke"))
        assert len(tids) == len(set(tids)) == 84, f"full scope requires 84 terminal DPO IDs, found {len(tids)}"
    assert len(tids) == len(set(tids))
    pairs = {tid: load_pair(tid) for tid in tids}
    result = {"scope": args.scope, "n_tasks": len(tids), "task_ids": tids,
              "control": "existing confirmatory A0", "seed": SEED,
              "permutation_resamples": N_BOOT, "bootstrap_resamples": N_BOOT}
    valid = lambda x: x.get("verification_status") in ("passed", "failed", "no_patch")
    interpretable = [t for t in tids if valid(pairs[t][0]) and valid(pairs[t][1])]
    both = [t for t in interpretable if pairs[t][0].get("resolved") is True and pairs[t][1].get("resolved") is True]
    d_only = [t for t in interpretable if pairs[t][0].get("resolved") is True and pairs[t][1].get("resolved") is not True]
    a_only = [t for t in interpretable if pairs[t][1].get("resolved") is True and pairs[t][0].get("resolved") is not True]
    discordant = len(d_only) + len(a_only)
    p_mcn = min(1.0, 2 * binomtest(min(len(d_only), len(a_only)), discordant,
                                .5, alternative="less").pvalue) if discordant else 1.0
    result["primary_mcnemar_descriptive"] = {"interpretable_pairs": len(interpretable),
        "unknown_pair_ids": sorted(set(tids) - set(interpretable)),
        "both_solved_ids": both, "DPO_only_ids": d_only, "A0_only_ids": a_only,
        "neither_solved": len(interpretable) - len(both) - discordant,
        "DPO_solved_all": sum(pairs[t][0].get("resolved") is True for t in tids),
        "A0_solved_all": sum(pairs[t][1].get("resolved") is True for t in tids),
        "p_exact_two_sided_descriptive": p_mcn}
    gen = []
    calls = []
    edit = []
    submit = {"DPO_only": [], "A0_only": [], "both": [], "neither": []}
    missing_gen = []
    for tid in tids:
        d, a, df, af, dc, ac = pairs[tid]
        dg, ag = df["mean_generation_seconds_per_turn"], af["mean_generation_seconds_per_turn"]
        if isinstance(dg, (int, float)) and isinstance(ag, (int, float)) and dg > 0 and ag > 0:
            gen.append(math.log(dg / ag))
        else:
            missing_gen.append(tid)
        dcall, acall = d["tool_calls"], a.get("tool_calls")
        if dcall > 0 and isinstance(acall, int) and acall > 0:
            calls.append(math.log(dcall / acall))
        de = sum(x["action_type"] == "edit" for x in dc) / len(dc) if dc else 0
        ae = sum(x["action_type"] == "edit" for x in ac) / len(ac) if ac else 0
        edit.append(de - ae)
        ds = any(x["tool"] == "submit_patch" for x in dc)
        ass = any(x["tool"] == "submit_patch" for x in ac)
        submit["both" if ds and ass else "DPO_only" if ds else "A0_only" if ass else "neither"].append(tid)
    result["H1_generation_seconds_per_turn"] = sample_test(gen, -1, log_ratio=True, seed=SEED)
    result["H1_generation_seconds_per_turn"]["missing_ids"] = missing_gen
    result["H2_tool_calls"] = sample_test(calls, +1, log_ratio=True, seed=SEED + 1)
    result["H3_edit_share"] = sample_test(edit, +1, seed=SEED + 2)
    sb, sc = len(submit["A0_only"]), len(submit["DPO_only"])
    result["H4_explicit_submit"] = {"A0_submit": len(submit["A0_only"]) + len(submit["both"]),
        "DPO_submit": len(submit["DPO_only"]) + len(submit["both"]),
        "discordant": submit,
        "p_one_sided": binomtest(sc, sb + sc, .5, alternative="greater").pvalue if sb + sc else 1.0}
    keys = ["H1_generation_seconds_per_turn", "H2_tool_calls", "H3_edit_share", "H4_explicit_submit"]
    raw = np.asarray([result[k].get("p_one_sided", np.nan) for k in keys])
    adjusted = [None] * 4
    if np.all(np.isfinite(raw)):
        maximum = 0.0
        for rank, ix in enumerate(np.argsort(raw)):
            maximum = max(maximum, min(1.0, float(raw[ix] * (4 - rank))))
            adjusted[ix] = maximum
    result["holm_corrected_p"] = dict(zip(keys, adjusted))
    result["found_then_lost_DPO"] = found_lost(tids, pairs)
    for arm, ix in (("DPO", 0), ("A0", 1)):
        solved = [t for t in tids if pairs[t][ix].get("resolved") is True]
        timed = [t for t in solved if pairs[t][ix].get("agent_timeout") is True]
        result[f"timeout_with_pass_{arm}"] = {"solved": len(solved),
            "timeout_with_pass": len(timed), "ids": timed,
            "rate": len(timed) / len(solved) if solved else None,
            "wilson_ci95": wilson(len(timed), len(solved))}
    pilot = ROOT / "costagent/artifacts/mixed-temperature-v1/evaluation/paper40-20261106a-DPO-test-seed-42/task_results.jsonl"
    pilot_ids = {json.loads(x)["instance_id"] for x in pilot.read_text().splitlines() if x}
    result["pilot40_overlap"] = {"n": len(pilot_ids & set(tids)), "ids": sorted(pilot_ids & set(tids)),
                                  "pilot_n": len(pilot_ids)}
    path = OUT / ("primary_analysis.json" if args.scope == "primary" else "secondary_full84_analysis.json")
    if args.scope == "primary" and path.exists():
        raise FileExistsError("Primary analysis already exists; do not overwrite frozen result")
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(path), "n_tasks": len(tids),
                      "mcnemar": result["primary_mcnemar_descriptive"],
                      "holm": result["holm_corrected_p"],
                      "found_lost": result["found_then_lost_DPO"]}, indent=2))


if __name__ == "__main__":
    main()
