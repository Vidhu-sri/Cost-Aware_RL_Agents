#!/usr/bin/env python3
"""Finish the owned contrast run, cancel its queued ablations, then evaluate 40 tasks.

This script is intended to run detached on the execution host. The SDPO Bash
launcher must already be SIGSTOPed while its direct Python training child runs.
No other process or container is signaled by this controller.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil


ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "costagent"
BASE = PKG / "artifacts/mixed-temperature-v1"
EVAL = BASE / "evaluation"
CONTRAST = BASE / "sdpo/contrast"
HARNESS_PY = Path("/home/mahesh/miniconda3/envs/gemma-harness/bin/python")
TRAIN_PY = Path("/home/mahesh/miniconda3/envs/gdac/bin/python")


def identity(pid, created, required):
    try:
        process = psutil.Process(pid)
        if abs(process.create_time() - created) > 0.02:
            raise RuntimeError(f"PID {pid} was reused")
        if process.status() == psutil.STATUS_ZOMBIE:
            return process  # cmdline is unavailable for a zombie; creation time still identifies it.
        command = " ".join(process.cmdline())
        if required not in command:
            raise RuntimeError(f"PID {pid} command changed: {command[:300]}")
        return process
    except psutil.NoSuchProcess:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--launcher-pid", type=int, required=True)
    parser.add_argument("--launcher-created", type=float, required=True)
    parser.add_argument("--trainer-pid", type=int, required=True)
    parser.add_argument("--trainer-created", type=float, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    if not args.label.replace("-", "").isalnum():
        parser.error("label must contain letters, digits and hyphens only")
    batch = EVAL / args.label
    if batch.exists():
        parser.error(f"Batch already exists: {batch}")
    task_ids = json.loads((EVAL / "test_tasks.json").read_text())
    training_ids = set(json.loads((BASE / "training_tasks.json").read_text()))
    if len(task_ids) != 40 or len(set(task_ids)) != 40 or training_ids.intersection(task_ids):
        raise RuntimeError("The frozen 40-task split is missing, duplicated, or contaminated")
    arms = [
        ("A0", ROOT / "data/sample_submission", None),
        ("A1", PKG / "results/subs/A1", None),
        ("A2", ROOT / "data/sample_submission", PKG / "artifacts/adapters/A2"),
        ("DPO", ROOT / "data/sample_submission", BASE / "dpo/epoch-005"),
        ("A9-contrast", ROOT / "data/sample_submission", CONTRAST / "epoch-005"),
    ]
    for name, submission, adapter in arms:
        if not (submission / "agent.yaml").is_file():
            raise RuntimeError(f"{name}: missing agent.yaml in {submission}")
        if name != "A9-contrast" and adapter and not (adapter / "adapter_model.safetensors").is_file():
            raise RuntimeError(f"{name}: missing adapter: {adapter}")
        if (EVAL / f"{args.label}-{name}-test-seed-42").exists():
            raise RuntimeError(f"{name}: result directory already exists")
    launcher = identity(args.launcher_pid, args.launcher_created, "run_sdpo_offline.sh")
    trainer = identity(args.trainer_pid, args.trainer_created, "--out artifacts/mixed-temperature-v1/sdpo/contrast")
    if launcher is None or launcher.status() != psutil.STATUS_STOPPED:
        raise RuntimeError("Owned SDPO launcher is missing or not paused; queued arms are not controlled")
    if trainer is None or trainer.ppid() != args.launcher_pid:
        raise RuntimeError("Owned contrast trainer is missing or no longer the launcher's child")
    if args.plan_only:
        print(json.dumps({"label": args.label, "task_count": len(task_ids),
                          "arms": [name for name, _, _ in arms],
                          "seed": 42, "launcher_status": launcher.status(),
                          "trainer_status": trainer.status()}, indent=2))
        return

    batch.mkdir(parents=True)
    progress = batch / "progress.jsonl"

    def log(event, **fields):
        row = {"time": time.time(), "event": event, **fields}
        with progress.open("a") as stream:
            stream.write(json.dumps(row) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps(row), flush=True)

    log("waiting_for_contrast", launcher_pid=args.launcher_pid, trainer_pid=args.trainer_pid)
    while True:
        trainer = identity(args.trainer_pid, args.trainer_created,
                           "--out artifacts/mixed-temperature-v1/sdpo/contrast")
        if trainer is None or trainer.status() == psutil.STATUS_ZOMBIE:
            break
        launcher = identity(args.launcher_pid, args.launcher_created, "run_sdpo_offline.sh")
        if launcher is None or launcher.status() != psutil.STATUS_STOPPED:
            raise RuntimeError("SDPO launcher unexpectedly resumed; refusing to continue")
        time.sleep(15)

    launcher = identity(args.launcher_pid, args.launcher_created, "run_sdpo_offline.sh")
    if launcher is None or launcher.status() != psutil.STATUS_STOPPED:
        raise RuntimeError("Owned SDPO launcher identity/status changed at completion")
    launcher.kill()  # Direct Bash PID only; trainer has already exited.
    launcher.wait(timeout=10)
    log("queued_ablations_cancelled", launcher_pid=args.launcher_pid)

    epoch_metrics = CONTRAST / "epoch-005/epoch_metrics.json"
    adapter_file = CONTRAST / "epoch-005/adapter_model.safetensors"
    ok = (epoch_metrics.is_file() and adapter_file.is_file()
          and adapter_file.stat().st_size > 1_000_000
          and json.loads(epoch_metrics.read_text()).get("epoch") == 5)
    (BASE / "sdpo/runner.status").write_text(
        "contrast_complete_queue_cancelled\n" if ok else "contrast_failed_queue_cancelled\n")
    if not ok:
        raise RuntimeError("Contrast trainer exited without a complete epoch-five checkpoint")
    log("contrast_complete", adapter_bytes=adapter_file.stat().st_size)

    selected = set(task_ids)
    source_lines = [line for line in (ROOT / "data/tasks.jsonl").read_text().splitlines()
                    if json.loads(line)["instance_id"] in selected]
    if len(source_lines) != 40:
        raise RuntimeError("Could not build exact 40-task statistics input")
    (batch / "tasks.jsonl").write_text("\n".join(source_lines) + "\n")
    (batch / "plan.json").write_text(json.dumps({
        "tasks": task_ids, "training_excluded": sorted(training_ids), "seed": 42,
        "arms": [{"name": n, "submission": str(s), "adapter": str(a) if a else None}
                 for n, s, a in arms],
        "agent_minutes": 5, "max_tool_calls": 100, "sampling_temperature": 0.2,
        "split": "frozen_test_40", "evaluation_is_sequential": True,
    }, indent=2) + "\n")

    import shutil
    for name, submission, adapter in arms:
        free_gib = shutil.disk_usage(batch).free / 2**30
        if free_gib < 10:
            raise RuntimeError(f"Free disk below 10 GiB before {name}: {free_gib:.1f} GiB")
        cmd = [str(HARNESS_PY), str(PKG / "scripts/evaluate_checkpoint.py"),
               "--arm", f"{args.label}-{name}", "--split", "test", "--seeds", "42",
               "--submission", str(submission)]
        if adapter:
            cmd += ["--adapter", str(adapter)]
        log("arm_started", arm=name, free_disk_gib=round(free_gib, 1), command=cmd)
        result = subprocess.run(cmd, cwd=PKG)
        if result.returncode:
            raise RuntimeError(f"Evaluation of {name} failed with exit code {result.returncode}")
        run = EVAL / f"{args.label}-{name}-test-seed-42"
        manifest = json.loads((run / "manifest.json").read_text())["attempts"]
        if len(manifest) != 40 or {x["task_id"] for x in manifest} != selected:
            raise RuntimeError(f"{name}: incomplete or mismatched manifest")
        errors = []
        for row in manifest:
            directory = Path(row["result_dir"])
            monitor = json.loads((directory / "monitor.json").read_text())
            if monitor.get("remaining_owned_ids"):
                raise RuntimeError(f"{name}/{row['task_id']}: owned container cleanup failed")
            if monitor.get("monitor_started_at", float("inf")) > monitor.get("worker_started_at", 0):
                raise RuntimeError(f"{name}/{row['task_id']}: monitor started late")
            if row["resolved"] is None:
                errors.append(row["task_id"])
        log("arm_complete", arm=name, resolved=sum(x["resolved"] is True for x in manifest),
            unresolved=sum(x["resolved"] is False for x in manifest),
            infrastructure_errors=errors)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PKG)
    env["MPLCONFIGDIR"] = str(batch / "matplotlib-cache")
    cmd = [str(TRAIN_PY), "-m", "costagent.stats", "--kaggle-tasks", str(batch / "tasks.jsonl"),
           "--baseline", "A0"]
    for name, _, _ in arms:
        cmd += ["--arm", f"{name}={EVAL / f'{args.label}-{name}-test-seed-42'}"]
    cmd += ["--out", str(batch / "stats")]
    log("stats_started", command=cmd)
    subprocess.run(cmd, cwd=PKG, env=env, check=True)
    log("batch_complete", results_table=str(batch / "stats/results_table.md"))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"time": time.time(), "event": "batch_error",
                          "error": f"{type(exc).__name__}: {exc}"}), flush=True)
        raise
