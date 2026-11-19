#!/usr/bin/env python3
"""Independent read-only status watcher for the DPO live v2 nohup batch."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time

import psutil

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/dpo_live_v2"
PROGRESS = OUT / "progress.jsonl"
HEALTH = OUT / "health.json"


def owned_processes(script: str) -> list[int]:
    found = []
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = proc.info["cmdline"] or []
            if any(arg.endswith("/" + script) or arg == script for arg in cmd):
                found.append(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def snapshot() -> dict:
    rows = []
    if PROGRESS.exists():
        for line in PROGRESS.read_text().splitlines():
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    terminal = list((OUT / "attempts").glob("*/**/done.json"))
    terminal = [p for p in terminal if not p.parent.parent.name.startswith("smoke-")]
    last = rows[-1] if rows else {}
    last_done = next((r for r in reversed(rows) if r.get("event") in
                      ("attempt_done", "attempt_recovered_terminal")), None)
    last_stop = next((r for r in reversed(rows) if r.get("event") == "batch_stopped"), None)
    last_complete = next((r for r in reversed(rows) if r.get("event") == "batch_complete"), None)
    controllers = owned_processes("run_dpo_live_v2.py")
    verifiers = owned_processes("verify_live_snapshots_v2.py")
    now = time.time()
    if last_complete and len(terminal) == 168:
        state = "complete"
    elif not controllers:
        state = "stopped"
    elif now - last.get("time", 0) > 1200:
        state = "stalled"
    else:
        state = "running"
    return {
        "checked_at": now, "state": state, "terminal_attempts": len(terminal),
        "target_attempts": 168, "controller_pids": controllers,
        "verifier_pids": verifiers, "last_event": last,
        "last_terminal_event": last_done,
        "last_stop_event": last_stop,
        "verifier_failure": (OUT / "snapshot_verifier_failure.json").exists(),
    }


def main() -> None:
    previous = None
    while True:
        row = snapshot()
        temp = HEALTH.with_suffix(".tmp")
        temp.write_text(json.dumps(row, indent=2) + "\n")
        os.replace(temp, HEALTH)
        if row["state"] != previous:
            print(json.dumps({"state": row["state"], "terminal_attempts": row["terminal_attempts"],
                              "last_event": row["last_event"].get("event")}), flush=True)
            previous = row["state"]
        if row["state"] in ("complete", "stopped", "stalled"):
            return
        time.sleep(30)


if __name__ == "__main__":
    main()
