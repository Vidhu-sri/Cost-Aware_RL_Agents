#!/usr/bin/env python3
"""Wait for all 84 DPO terminals and CPU snapshot grades, then analyze once.

This follower never sends model requests or touches Docker. It is intentionally
separate from the live GPU controller and the snapshot verifier.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/dpo_live_v2"
ANALYZER = ROOT / "costagent/scripts/analyze_dpo_live_v2_cohort.py"


def status():
    rows = {}
    for p in (OUT / "attempts").glob("*/DPO/done.json"):
        try:
            x = json.loads(p.read_text())
            if not x.get("smoke"):
                rows[x["task_id"]] = x
        except (OSError, ValueError, KeyError):
            pass
    grades = {}
    p = OUT / "snapshot_verification.jsonl"
    if p.exists():
        for line in p.read_text().splitlines():
            if line:
                x = json.loads(line)
                grades[(x["task_id"], x["patch_sha256"])] = x
    pending = []
    for tid, d in rows.items():
        if d.get("verification_status") not in ("failed", "no_patch"):
            continue
        p = Path(d["result_dir"]) / "snapshot_manifest.jsonl"
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            if not line:
                continue
            x = json.loads(line)
            if x.get("status") != "ok" or x.get("patch_bytes", 0) <= 0:
                continue
            key = (tid, x["patch_sha256"])
            grade = grades.get(key)
            if grade is None or grade.get("status") != "complete":
                pending.append(key)
    return len(rows), len(set(pending))


def main():
    target = OUT / "secondary_full84_analysis.json"
    if target.exists():
        print("Secondary analysis already exists; leaving it unchanged.", flush=True)
        return 0
    while True:
        done, pending = status()
        print(json.dumps({"time": time.time(), "dpo_terminal": done,
                          "snapshot_grades_pending": pending}), flush=True)
        if done == 84 and pending == 0:
            break
        if done > 84:
            raise RuntimeError(f"Expected 84 unique DPO terminal IDs, found {done}")
        time.sleep(120)
    proc = subprocess.run([sys.executable, str(ANALYZER), "--scope", "full"],
                          cwd=ROOT, check=False)
    if proc.returncode:
        raise RuntimeError(f"Secondary CPU analysis exited {proc.returncode}")
    result = json.loads(target.read_text())
    m = result["primary_mcnemar_descriptive"]
    lines = ["\n## Full-84 secondary analysis (completed after terminal records)\n",
             "This analysis uses all 84 DPO tasks paired with existing confirmatory A0. "
             "It is secondary to the frozen 48-task result and does not change it.\n",
             f"- Interpretable pairs: {m['interpretable_pairs']}/84; "
             f"DPO passes {m['DPO_solved_all']}, A0 passes {m['A0_solved_all']}; "
             f"DPO-only {len(m['DPO_only_ids'])}, A0-only {len(m['A0_only_ids'])}; "
             f"descriptive exact McNemar p={m['p_exact_two_sided_descriptive']:.4g}.\n"]
    for key in ("H1_generation_seconds_per_turn", "H2_tool_calls",
                "H3_edit_share", "H4_explicit_submit"):
        v = result[key]
        estimate = v.get("estimate_ratio", v.get("estimate_difference", None))
        lines.append(f"- {key}: estimate={estimate}; one-sided p={v.get('p_one_sided')}; "
                     f"Holm p={result['holm_corrected_p'].get(key)}.\n")
    f = result["found_then_lost_DPO"]
    lines.append(f"- Found-then-lost: {len(f['found_then_lost_ids'])}/"
                 f"{f['valid_failed_attempts']} valid failed DPO attempts; "
                 f"snapshot grades complete={f['all_snapshot_grades_complete']}; "
                 f"Wilson CI={f.get('wilson_ci95')}; bootstrap CI="
                 f"{f.get('task_cluster_bootstrap_ci95')}.\n")
    t = result["timeout_with_pass_DPO"]
    lines.append(f"- DPO timeout-with-pass: {t['timeout_with_pass']}/{t['solved']}; "
                 f"Wilson CI={t['wilson_ci95']}. Pilot40 overlap="
                 f"{result['pilot40_overlap']['n']}/40.\n")
    lines.append("Full machine-readable output: `secondary_full84_analysis.json`.\n")
    with (OUT / "REPORT.md").open("a") as f_out:
        f_out.writelines(lines)
    print("Secondary analysis and REPORT.md section complete.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
