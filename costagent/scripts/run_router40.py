"""Detached, resource-gated research evaluation of DPO plus phase-v1 routing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

import psutil

PKG = Path(__file__).resolve().parents[1]
BASE = PKG / "artifacts/mixed-temperature-v1"
PYTHON = "/home/mahesh/miniconda3/envs/gemma-harness/bin/python"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if not args.label.replace("-", "").isalnum():
        parser.error("Invalid label")
    batch = BASE / "evaluation" / args.label
    batch.mkdir(exist_ok=False)
    tasks = json.loads((BASE / "evaluation/test_tasks.json").read_text())
    original = [json.loads(line)["instance_id"] for line in
                (BASE / "evaluation/paper40-20261106a/tasks.jsonl").read_text().splitlines()]
    if len(tasks) != 40 or len(set(tasks)) != 40 or set(tasks) != set(original):
        raise RuntimeError("Task list differs from the original matched 40 tasks")
    source = batch / "phase_router.py"
    shutil.copy2(PKG / "scripts/phase_router.py", source)
    child = None

    def log(event, **fields):
        row = dict(time=time.time(), event=event, **fields)
        with (batch / "progress.jsonl").open("a") as stream:
            stream.write(json.dumps(row) + "\n")
        print(json.dumps(row), flush=True)

    def interrupt(signum, frame):
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGINT)
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    plan = dict(task_ids=tasks, seed=42, adapter=str(BASE / "dpo/epoch-005"),
                router="phase-v1", router_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                minutes=5, tool_calls=100, outer_seconds=900, concurrency=1,
                policy="DPO epoch 5", kind="heuristic controller, not trained router")
    (batch / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    try:
        stable = 0
        while stable < 3:
            free, util = map(int, subprocess.check_output([
                "nvidia-smi", "--query-gpu=memory.free,utilization.gpu",
                "--format=csv,noheader,nounits"], text=True).strip().split(","))
            processes = subprocess.check_output([
                "nvidia-smi", "--query-compute-apps=process_name",
                "--format=csv,noheader"], text=True)
            ram = psutil.virtual_memory().available / 2**30
            disk = shutil.disk_usage(batch).free / 2**30
            ready = free >= 62000 and util <= 10 and ram >= 24 and disk >= 10 and "vllm" not in processes.lower()
            stable = stable + 1 if ready else 0
            log("resource_gate", gpu_free_mib=free, gpu_utilization=util,
                available_ram_gib=round(ram, 1), disk_free_gib=round(disk, 1),
                stable_samples=stable, ready=ready)
            if stable < 3:
                time.sleep(30)
        env = os.environ.copy()
        env.update(COSTAGENT_ROUTER="phase-v1", COSTAGENT_ROUTER_SOURCE=str(source))
        command = [PYTHON, "-u", str(PKG / "scripts/evaluate_checkpoint.py"),
                   "--arm", args.label, "--split", "test", "--seeds", "42",
                   "--adapter", str(BASE / "dpo/epoch-005")]
        log("evaluation_started", command=command)
        child = subprocess.Popen(command, cwd=PKG, env=env, start_new_session=True)
        (batch / "owned_process.json").write_text(json.dumps({"pid": child.pid,
            "created": psutil.Process(child.pid).create_time()}) + "\n")
        rc = child.wait()
        if rc:
            raise RuntimeError(f"Evaluation exited {rc}; see task and server logs")
        manifest = json.loads((BASE / f"evaluation/{args.label}-test-manifest.json").read_text())
        rows = manifest["attempts"]
        summary = dict(attempts=len(rows), resolved=sum(r.get("resolved") is True for r in rows),
                       unresolved=sum(r.get("resolved") is False for r in rows),
                       ungraded=sum(r.get("resolved") is None for r in rows),
                       agent_timeout=sum(bool(r.get("agent_timeout")) for r in rows))
        (batch / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        log("complete", **summary)
    except BaseException as exc:
        log("stopped", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGINT)
            child.wait(timeout=120)


if __name__ == "__main__":
    main()
