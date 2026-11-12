"""Cost counts, calibration, normalized cost C and rewards (THEORY.md section 2)."""
from __future__ import annotations

import re
from collections import defaultdict
from statistics import median

import numpy as np

from .tools_schema import EDIT_TOOLS, FREE_TOOLS

KEYS = ("calls", "tokens", "files", "tests", "dups")
DEFAULT_W = {"calls": 0.35, "tokens": 0.35, "files": 0.10, "tests": 0.15, "dups": 0.05}
TEST_RE = re.compile(r"\b(pytest|py\.test|unittest|tox|nox)\b|python\S*\s+\S*tests?/\S+\.py")
READ_CMD_RE = re.compile(r"^\s*(cat|head|tail|nl|less|sed\s+-n)\b[^|;&]*?\s(\S+\.\w+)")


def counts(traj: dict) -> dict:
    n = dict.fromkeys(KEYS, 0)
    files = set()
    read_ranges: dict[str, list[tuple[int, int]]] = defaultdict(list)
    last_cmd = None
    for t in traj["turns"]:
        if t["kind"] != "assistant":
            continue
        tok = t.get("prompt_tokens", 0) + t.get("completion_tokens", 0)
        if not tok:  # no metrics in the trace: approximate 4 chars per token
            tok = (len(t.get("text", "")) + len(t.get("reasoning", ""))
                   + sum(len(r.get("content", "")) for r in t.get("results", []))) // 4
        n["tokens"] += tok
        for c in t["calls"]:
            name, a = c["name"], c["args"] if isinstance(c["args"], dict) else {}
            if name not in FREE_TOOLS:
                n["calls"] += 1
            fp = a.get("filepath")
            if fp:
                files.add(fp.lstrip("/").removeprefix("workspace/"))
            if name in EDIT_TOOLS and fp:
                read_ranges.pop(fp, None)  # an edit resets duplicate tracking for that file
            if name == "read_file" and fp:
                s = int(a.get("start_line") or 1)
                e = int(a.get("end_line") or s + 149)
                if any(s <= e2 and s2 <= e for s2, e2 in read_ranges[fp]):
                    n["dups"] += 1
                read_ranges[fp].append((s, e))
            if name == "run_command":
                cmd = str(a.get("command", ""))
                if TEST_RE.search(cmd):
                    n["tests"] += 1
                m = READ_CMD_RE.search(cmd)
                if m:
                    files.add(m.group(2).lstrip("./"))
                if cmd == last_cmd:  # identical consecutive command ("spin")
                    n["dups"] += 1
                last_cmd = cmd
            else:
                last_cmd = None
    n["files"] = len(files)
    return n


def calibrate(train_trajs: list[dict], cmax_pct: float = 95.0) -> dict:
    """n-bar per task from successful training rollouts; c_max from the ratio distribution."""
    per_task = defaultdict(list)
    for r in train_trajs:
        if r["solved"]:
            per_task[r["task_id"]].append(r["counts"])
    pool = [c for v in per_task.values() for c in v] or [r["counts"] for r in train_trajs]
    glob = {k: max(1.0, float(median([c[k] for c in pool]))) for k in KEYS}
    nbar = {t: {k: max(1.0, float(median([c[k] for c in v]))) for k in KEYS} for t, v in per_task.items()}
    ratios = [r["counts"][k] / nbar.get(r["task_id"], glob)[k] for r in train_trajs for k in KEYS]
    cmax = max(1.5, float(np.percentile(ratios, cmax_pct))) if ratios else 3.0
    return {"nbar": nbar, "global": glob, "cmax": cmax, "w": dict(DEFAULT_W)}


def cost(c: dict, task_id: str, cal: dict) -> float:
    nb = cal["nbar"].get(task_id, cal["global"])
    cm = cal["cmax"]
    val = sum(cal["w"][k] * min(c[k] / max(nb[k], 1.0), cm) / cm for k in KEYS)
    return float(min(max(val, 0.0), 1.0))


def r2(solved: bool, c: float, lam: float = 0.5) -> float:
    assert 0.0 <= lam < 1.0
    return float(solved) * (1.0 - lam * c)
