"""Sequential published-reference preflight with owned-container cleanup."""

import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

import docker
import psutil

from run_docker import DATA, KIT, clean_owned, owned_containers


IMAGES = {
    "psf/requests": "gemma-requests-sandbox:20261015c",
    "encode/httpx": "gemma-httpx-sandbox:20261015a",
    "Textualize/rich": "gemma-rich-sandbox:20261015a",
    "fastapi/fastapi": "gemma-fastapi-sandbox:20261015a",
}
MIN_DISK_BYTES = 12 * 1024**3
MIN_MEMORY_BYTES = 16 * 1024**3
MAX_OBSERVED_RSS_BYTES = 8 * 1024**3


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def test_counts(output):
    counts = {}
    for count, kind in re.findall(
        r"(\d+) (passed|failed|error|errors|skipped|xfailed|xpassed)", output
    ):
        counts[kind] = int(count)
    return counts


def classify(result, monitor, supervisor_code, output=""):
    if monitor is None:
        return "infrastructure_error"
    if monitor.get("timed_out"):
        return "timeout"
    if monitor.get("interrupted"):
        return "interrupted"
    if result is None:
        return "setup_error"
    if result.get("error"):
        error = result["error"].lower()
        if "required test node did not pass" in error:
            return "required_test_not_passed"
        if "patch" in error:
            return "patch_apply_error"
        return "setup_or_verification_error"
    if (result.get("test_exit_code") == 2
            and "error during collection" in output.lower()):
        return "test_collection_error"
    if result.get("resolved") and supervisor_code == 0:
        return "passed"
    return "failed_reference_tests"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-label", required=True)
    parser.add_argument("--seconds-per-task", type=int, default=900)
    parser.add_argument("--retry-unresolved-from", type=Path)
    args = parser.parse_args()
    label = args.batch_label
    if not label.isascii() or not label.replace("-", "").replace("_", "").isalnum():
        parser.error("batch label must contain only ASCII letters, digits, hyphens, or underscores")
    if not 1 <= args.seconds_per_task <= 1800:
        parser.error("seconds-per-task must be between 1 and 1800")

    tasks = [json.loads(line) for line in (DATA / "tasks.jsonl").open()]
    if len(tasks) != 129 or len({task["instance_id"] for task in tasks}) != 129:
        parser.error("published task inventory is not the expected 129 unique IDs")
    if args.retry_unresolved_from:
        prior = json.loads(args.retry_unresolved_from.read_text())
        selected = {item["task_id"] for item in prior["investigation"]}
        if not selected or not selected <= {task["instance_id"] for task in tasks}:
            parser.error("retry selection is empty or contains an unpublished task ID")
        tasks = [task for task in tasks if task["instance_id"] in selected]
    if not {task["repo"] for task in tasks} <= set(IMAGES):
        parser.error("image map does not cover every published repository")
    for task in tasks:
        if not (DATA / "snapshots" / f"{task['instance_id']}.tgz").is_file():
            parser.error(f"missing snapshot: {task['instance_id']}")
        if not task.get("patch") or not task.get("test_patch"):
            parser.error(f"missing reference or test patch: {task['instance_id']}")

    client = docker.from_env(timeout=10)
    image_ids = {repo: client.images.get(image).id for repo, image in IMAGES.items()}
    batch_dir = KIT / "results" / f"docker-{label}-reference-batch"
    if batch_dir.exists():
        parser.error(f"batch result directory already exists: {batch_dir}")
    for task in tasks:
        run_label = f"{label}-{task['instance_id']}"
        if (KIT / "results" / f"docker-{run_label}-reference").exists():
            parser.error(f"task result directory already exists: {run_label}")
    batch_dir.mkdir(parents=True)
    batch = {"batch_label": label, "task_count": len(tasks), "image_ids": image_ids,
             "seconds_per_task": args.seconds_per_task, "concurrency": 1,
             "tasks": [], "stop_reason": None}
    save(batch_dir / "batch_manifest.json", batch)

    active = None
    active_run_id = None
    try:
        for index, task in enumerate(tasks, 1):
            task_id, repo = task["instance_id"], task["repo"]
            disk_free = os.statvfs(KIT).f_bavail * os.statvfs(KIT).f_frsize
            memory_free = psutil.virtual_memory().available
            if disk_free < MIN_DISK_BYTES or memory_free < MIN_MEMORY_BYTES:
                batch["stop_reason"] = (f"shared-server resource concern before {task_id}: "
                                        f"disk_free={disk_free}, memory_available={memory_free}")
                break

            run_label = f"{label}-{task_id}"
            active_run_id = f"{run_label}-{uuid.uuid4().hex}"
            result_dir = KIT / "results" / f"docker-{run_label}-reference"
            command = [sys.executable, str(KIT / "run_docker.py"),
                       "--mode", "reference", "--task-id", task_id,
                       "--label", run_label, "--run-id", active_run_id,
                       "--image", IMAGES[repo], "--seconds", str(args.seconds_per_task)]
            print(f"[{index}/{len(tasks)}] {task_id} ({repo})", flush=True)
            with (batch_dir / f"{task_id}.supervisor.log").open("w") as log:
                active = subprocess.Popen(command, cwd=KIT, stdout=log,
                                          stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    supervisor_code = active.wait(timeout=args.seconds_per_task + 45)
                except subprocess.TimeoutExpired:
                    os.killpg(active.pid, signal.SIGINT)
                    try:
                        active.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(active.pid, signal.SIGKILL)
                        active.wait()
                    supervisor_code = active.returncode
                    batch["stop_reason"] = f"supervisor watchdog expired at {task_id}"
            active = None

            monitor_path = result_dir / "monitor.json"
            result_path = result_dir / "result.json"
            manifest_path = result_dir / "run_manifest.json"
            output_path = result_dir / "test_outputs" / f"{task_id}.log"
            monitor = json.loads(monitor_path.read_text()) if monitor_path.exists() else None
            result = json.loads(result_path.read_text()) if result_path.exists() else None
            manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
            output = output_path.read_text(errors="replace") if output_path.exists() else ""
            remaining = [c.id for c in owned_containers(client, active_run_id)]
            versions_path = next(result_dir.glob("container_packages_*.json"), None)
            versions = json.loads(versions_path.read_text()) if versions_path else None
            peak_rss = max((sample.get("observed_pid_namespace_rss_bytes") or 0
                            for sample in monitor.get("samples", [])), default=0) if monitor else 0
            entry = {
                "task_id": task_id, "repository": repo, "run_id": active_run_id,
                "result_dir": str(result_dir), "image_id": image_ids[repo],
                "image_id_recorded": manifest.get("image_id") if manifest else None,
                "dependency_versions": versions,
                "reference_patch_sha256": manifest.get("reference_patch_sha256") if manifest else None,
                "reference_patch_status": ("applied" if result and result.get("test_exit_code") is not None
                                           else "unconfirmed"),
                "test_exit_code": result.get("test_exit_code") if result else None,
                "resolved": result.get("resolved") if result else None,
                "verification_error": result.get("error") if result else None,
                "test_counts": test_counts(output),
                "test_summary": next((line for line in reversed(output.splitlines())
                                      if " passed" in line or " failed" in line), None),
                "supervisor_exit_code": supervisor_code,
                "timed_out": monitor.get("timed_out") if monitor else None,
                "interrupted": monitor.get("interrupted") if monitor else None,
                "peak_observed_rss_bytes": peak_rss,
                "cleanup_ok": bool(monitor is not None and not monitor.get("remaining_owned_ids")
                                   and not remaining),
                "remaining_owned_ids": remaining,
                "category": classify(result, monitor, supervisor_code, output),
            }
            batch["tasks"].append(entry)
            save(batch_dir / "batch_summary.json", batch)
            print(f"  {entry['category']}: {entry['test_summary']}; cleanup={entry['cleanup_ok']}",
                  flush=True)
            if not entry["cleanup_ok"] or remaining:
                batch["stop_reason"] = f"container cleanup failure at {task_id}"
                break
            if monitor.get("monitor_started_at") is None or monitor.get("worker_started_at") is None:
                batch["stop_reason"] = f"monitoring failure at {task_id}"
                break
            if monitor["monitor_started_at"] > monitor["worker_started_at"]:
                batch["stop_reason"] = f"monitor started after worker at {task_id}"
                break
            if peak_rss > MAX_OBSERVED_RSS_BYTES:
                batch["stop_reason"] = f"shared-server resource concern after {task_id}: peak RSS={peak_rss}"
                break
            if batch["stop_reason"]:
                break
            active_run_id = None
    except KeyboardInterrupt:
        batch["stop_reason"] = "batch interrupted"
    except Exception as exc:
        batch["stop_reason"] = f"batch infrastructure error: {type(exc).__name__}: {exc}"
    finally:
        if active is not None and active.poll() is None:
            os.killpg(active.pid, signal.SIGINT)
            try:
                active.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(active.pid, signal.SIGKILL)
                active.wait()
        if active_run_id is not None:
            try:
                clean_owned(client, active_run_id)
            except Exception as exc:
                batch["stop_reason"] = (batch["stop_reason"] or "") + f"; cleanup error: {exc}"
        counts = defaultdict(Counter)
        for entry in batch["tasks"]:
            counts[entry["repository"]][entry["category"]] += 1
        batch["counts_by_repository"] = {repo: dict(items) for repo, items in counts.items()}
        batch["investigate_ids"] = [e["task_id"] for e in batch["tasks"] if e["category"] != "passed"]
        batch["completed_count"] = len(batch["tasks"])
        save(batch_dir / "batch_summary.json", batch)
    return 0 if len(batch["tasks"]) == len(tasks) and not batch["stop_reason"] else 1


if __name__ == "__main__":
    sys.exit(main())
