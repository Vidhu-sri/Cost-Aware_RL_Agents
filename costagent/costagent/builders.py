"""Build training sets from trajectories.jsonl.

Writes to --out:
  data_report.md       what the data supports (read this first)
  cost.json            calibration (training rollouts only)
  sft.pt               RFT-lite examples (best success per training task)
  groups.pt            listwise groups (>=2 base rollouts, >=1 success per task)
  pairs.pt             sibling pairs (efficiency + competence), hard-target ablation
  rlcd.pt              gated RLCD pairs, p+/p- prompt swapped for the standard prompt
Kaggle dev tasks never enter any training file (asserted).
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path

import torch

from .chat import assistant_turn_meta, turn_examples
from .costs import calibrate, cost, counts, r2

LEAK_RE = re.compile(r"instruct|minimi[sz]e (tool )?calls|budget rule|as (i was )?told|stop-loss", re.I)


def patch_files(patch: str) -> set[str]:
    return {m.group(1) for m in re.finditer(r"^\+\+\+ b/(\S+)", patch or "", re.M)}


def strata(traj: dict) -> tuple[list[int], list[int]]:
    """A = edit turns, first turn touching a file in the final patch, final turn. B = the rest."""
    meta = assistant_turn_meta(traj)
    if not meta:
        return [], []
    pf = patch_files(traj["patch"])
    A = {i for i, m in enumerate(meta) if any(n in ("edit_file", "write_file") for n in m["names"])}
    A.add(len(meta) - 1)
    for i, m in enumerate(meta):
        if pf and (set(m["files"]) & pf or any(f in m["cmd"] for f in pf)):
            A.add(i)
            break
    B = [i for i in range(len(meta)) if i not in A]
    return sorted(A), B


def variant(traj: dict) -> str:
    run = traj["run"].lower()
    if "rlcd_pos" in run or "rlcd-pos" in run:
        return "pos"
    if "rlcd_neg" in run or "rlcd-neg" in run:
        return "neg"
    return "base"


def candidate(tok, traj, rng, k_b, max_len, system_override=None, all_turns=False):
    A, B = strata(traj)
    pick = rng.sample(B, min(k_b, len(B))) if B else []
    weight_b = (len(B) / len(pick)) if pick else 0.0
    want = None if all_turns else set(A) | set(pick)
    exs = turn_examples(tok, traj, max_len=max_len, system_override=system_override, only=want)
    turns, every, skipped = [], [], defaultdict(int)
    for e in exs:
        if "skip" in e:
            skipped[e["skip"]] += 1
            continue
        every.append(e)
        if e["turn"] in A or e["turn"] in pick:
            turns.append(dict(e, weight=1.0 if e["turn"] in A else weight_b))
    c = {"rollout_id": traj["rollout_id"], "task_id": traj["task_id"], "solved": traj["solved"],
         "cost": traj["cost"], "n_turns_total": len(A) + len(B), "turns": turns}
    if all_turns:
        c["all_turns"] = every  # exact rescoring for round 2 (--rescore)
    return c, dict(skipped)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trajectories", default="artifacts/trajectories.jsonl")
    ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--pos-text", default=None, help="file: text appended to the prompt for RLCD p+ runs")
    ap.add_argument("--neg-text", default=None, help="file: text appended to the prompt for RLCD p- runs")
    ap.add_argument("--out", default="artifacts/data")
    ap.add_argument("--max-len", type=int, default=16384)
    ap.add_argument("--k-sft", type=int, default=5)
    ap.add_argument("--k-pref", type=int, default=1)
    ap.add_argument("--delta-c", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--all-turns", action="store_true", help="store every turn of group candidates (needed for --rescore)")
    ap.add_argument("--allow-kaggle-tasks", type=str, help="JSON list of explicitly authorized training task IDs")
    args = ap.parse_args()

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer)
    rng = random.Random(args.seed)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    trajs = [json.loads(l) for l in open(args.trajectories) if l.strip()]
    allowed = set(json.loads(Path(args.allow_kaggle_tasks).read_text())) if args.allow_kaggle_tasks else set()
    for t in trajs:
        if t["task_id"] in allowed: t["is_kaggle"] = False
        t["counts"] = counts(t)
    train = [t for t in trajs if not t["is_kaggle"] and any(x["kind"] == "assistant" for x in t["turns"])]
    evalset = [t for t in trajs if t["is_kaggle"]]
    base_train = [t for t in train if variant(t) == "base"]
    cal = calibrate(base_train or train)
    for t in trajs:
        t["cost"] = cost(t["counts"], t["task_id"], cal)
    json.dump({k: v for k, v in cal.items() if k != "nbar"} | {"n_tasks_calibrated": len(cal["nbar"])},
              open(out / "cost.json", "w"), indent=1)

    extra = {"pos": Path(args.pos_text).read_text().strip() if args.pos_text else None,
             "neg": Path(args.neg_text).read_text().strip() if args.neg_text else None}

    def stripped(t):
        """System prompt of a p+/p- run with the appended RLCD text removed (context distillation)."""
        x = extra.get(variant(t))
        if not x or x not in t["system"]:
            return None
        return t["system"].replace(x, "").rstrip()
    by_task = defaultdict(list)
    for t in train:
        by_task[t["task_id"]].append(t)

    skips = defaultdict(int)

    def add_skips(s):
        for k, v in s.items():
            skips[k] += v

    # --- SFT (RFT-lite): best success per task by R2, base or p+ (p+ gets the standard prompt) ---
    sft = []
    for tid, rs in by_task.items():
        succ = [t for t in rs if t["solved"] and variant(t) in ("base", "pos")]
        if not succ:
            continue
        best = max(succ, key=lambda t: r2(True, t["cost"]))
        so = stripped(best) if variant(best) == "pos" else None
        if so is None and variant(best) == "pos":
            continue  # cannot strip the p+ prompt
        c, s = candidate(tok, best, rng, args.k_sft, args.max_len, so); add_skips(s)
        if c["turns"]:
            sft.append(c)

    # --- listwise groups and sibling pairs from base rollouts ---
    groups, pairs = [], []
    compatible_groups = defaultdict(list)
    for tid, rs in by_task.items():
        for t in rs:
            compatible_groups[(tid, t.get("compatibility_sha256", "legacy-unverified"))].append(t)
    for (tid, compatibility), rs in compatible_groups.items():
        base = [t for t in rs if variant(t) == "base"]
        if len(base) < 2 or not any(t["solved"] for t in base):
            continue
        cands = []
        for t in base:
            c, s = candidate(tok, t, rng, args.k_pref, args.max_len, all_turns=args.all_turns); add_skips(s)
            if c["turns"]:
                cands.append(c)
        if len(cands) >= 2 and any(c["solved"] for c in cands):
            groups.append({"task_id": tid, "kind": "sibling", "candidates": cands})
            succ = sorted([c for c in cands if c["solved"]], key=lambda c: c["cost"])
            fail = [c for c in cands if not c["solved"]]
            if fail:
                pairs.append({"task_id": tid, "kind": "competence", "candidates": [succ[0], fail[0]]})
            if len(succ) >= 2 and succ[-1]["cost"] - succ[0]["cost"] > args.delta_c:
                pairs.append({"task_id": tid, "kind": "efficiency", "candidates": [succ[0], succ[-1]]})

    # --- RLCD pairs: proposals from p+/p- prompts, labels from verified outcomes ---
    rlcd, leak_drop = [], 0
    for tid, rs in by_task.items():
        pos = [t for t in rs if variant(t) == "pos"]
        neg = [t for t in rs if variant(t) == "neg"]
        for tp in pos:
            for tn in neg:
                ok = (tp["solved"] and not tn["solved"]) or \
                     (tp["solved"] and tn["solved"] and tp["cost"] < tn["cost"] - args.delta_c)
                if not ok:
                    continue
                if any(LEAK_RE.search(x.get("text", "") + x.get("reasoning", "")) for x in tp["turns"]
                       if x["kind"] == "assistant"):
                    leak_drop += 1
                    continue
                sp_, sn_ = stripped(tp), stripped(tn)
                if sp_ is None or sn_ is None:
                    skips["rlcd_prompt_not_found"] += 1
                    continue
                cp, s1 = candidate(tok, tp, rng, args.k_pref, args.max_len, sp_)
                cn, s2 = candidate(tok, tn, rng, args.k_pref, args.max_len, sn_)
                add_skips(s1); add_skips(s2)
                if cp["turns"] and cn["turns"]:
                    rlcd.append({"task_id": tid, "kind": "rlcd", "candidates": [cp, cn]})

    # --- hard rule: no Kaggle task anywhere in training data ---
    kag = {t["task_id"] for t in evalset} | {t["task_id"] for t in trajs if t["is_kaggle"]}
    for name, ds in (("sft", [{"task_id": c["task_id"]} for c in sft]), ("groups", groups),
                     ("pairs", pairs), ("rlcd", rlcd)):
        assert not ({d["task_id"] for d in ds} & kag), f"Kaggle task leaked into {name}"

    torch.save(sft, out / "sft.pt"); torch.save(groups, out / "groups.pt")
    torch.save(pairs, out / "pairs.pt"); torch.save(rlcd, out / "rlcd.pt")

    rpt = [
        "# Data report", "",
        f"- trajectories: {len(trajs)} (train {len(train)}, kaggle eval {len(evalset)})",
        f"- training tasks: {len(by_task)}; rollouts per task: min {min(map(len, by_task.values()), default=0)}, "
        f"max {max(map(len, by_task.values()), default=0)}",
        f"- training successes: {sum(t['solved'] for t in train)} / {len(train)}",
        f"- kaggle eval solved: {sum(t['solved'] for t in evalset)} / {len(evalset)}",
        f"- variants: " + ", ".join(f"{v}={sum(variant(t) == v for t in train)}" for v in ("base", "pos", "neg")),
        f"- cost calibration: c_max={cal['cmax']:.2f}, tasks with a success baseline={len(cal['nbar'])}",
        f"- SFT (RFT-lite) trajectories: {len(sft)}, turns: {sum(len(c['turns']) for c in sft)}",
        f"- listwise groups: {len(groups)} (candidates {sum(len(g['candidates']) for g in groups)})",
        f"- sibling pairs: {len(pairs)} (competence {sum(p['kind'] == 'competence' for p in pairs)}, "
        f"efficiency {sum(p['kind'] == 'efficiency' for p in pairs)})",
        f"- RLCD pairs: {len(rlcd)} (dropped for prompt leakage: {leak_drop})",
        f"- skipped turns: {dict(skips)}",
        "- all inputs are reconstructed from traces (approx=True); compaction approximated by dropping oldest history",
    ]
    (out / "data_report.md").write_text("\n".join(rpt) + "\n")
    print("\n".join(rpt))


if __name__ == "__main__":
    main()
