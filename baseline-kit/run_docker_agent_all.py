"""Run each published Gemma task once, sequentially, on one owned vLLM server."""

import argparse
from collections import Counter, defaultdict
import csv
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
import uuid
import urllib.request

import docker
import psutil

from run_docker import DATA, KIT, clean_owned, owned_containers, sha256
from run_docker_reference_batch import IMAGES


OUTER_SECONDS = 900
MIN_START_GPU_FREE_MIB = 62000
MIN_RUNNING_GPU_FREE_MIB = 8000
MIN_HOST_MEMORY_BYTES = 16 * 1024**3
MIN_DISK_BYTES = 12 * 1024**3
MAX_OBSERVED_CONTAINER_RSS_BYTES = 8 * 1024**3
MODEL_URL = "http://127.0.0.1:8001/v1"
STOP_REQUESTED = False


def request_stop(_signum, _frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def gpu_free_mib():
    run = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=15, check=True,
    )
    values = [int(line.strip()) for line in run.stdout.splitlines() if line.strip()]
    if len(values) != 1:
        raise RuntimeError(f"Expected one GPU, found {len(values)}")
    return values[0]


def server_is_owned(server, created_at):
    try:
        return (psutil.Process(server.pid).create_time() == created_at
                and os.getpgid(server.pid) == server.pid)
    except (psutil.Error, ProcessLookupError):
        return False


def stop_server(server, created_at):
    if server is None:
        return None
    if server.poll() is None and server_is_owned(server, created_at):
        os.killpg(server.pid, signal.SIGTERM)
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            if server_is_owned(server, created_at):
                os.killpg(server.pid, signal.SIGKILL)
            server.wait(timeout=15)
    with socket.socket() as check:
        port_closed = check.connect_ex(("127.0.0.1", 8001)) != 0
    return {"pid": server.pid, "process_exited": server.poll() is not None,
            "port_8001_closed": port_closed}


def test_counts(output):
    counts = {}
    for count, kind in re.findall(
        r"(\d+) (passed|failed|error|errors|skipped|xfailed|xpassed)", output
    ):
        counts[kind] = int(count)
    return counts


def classify_agent(outcome, monitor, patch_path):
    timed_out = bool((monitor and monitor.get("timed_out"))
                     or (outcome and outcome.get("agent_timeout")))
    if timed_out:
        return "timed_out"
    if not patch_path.is_file() or not patch_path.read_text(errors="replace").strip():
        return "no_patch"
    return "resolved" if outcome and outcome.get("resolved") is True else "unresolved"


def classify_verification(outcome, output):
    if outcome is None or outcome.get("test_exit_code") in (None, -1) or not output.strip():
        return "could_not_be_interpreted"
    if outcome.get("resolved") is True and outcome.get("test_exit_code") == 0:
        return "passed"
    return "failed"


def save_batch(batch_dir, batch):
    counts = Counter(item["agent_status"] for item in batch["tasks"])
    checks = Counter(item["verification_status"] for item in batch["tasks"])
    by_repo = defaultdict(Counter)
    for item in batch["tasks"]:
        by_repo[item["repository"]][item["agent_status"]] += 1
    batch["agent_counts"] = dict(counts)
    batch["verification_counts"] = dict(checks)
    batch["agent_counts_by_repository"] = {repo: dict(c) for repo, c in by_repo.items()}
    batch["completed_count"] = len(batch["tasks"])
    write_json(batch_dir / "batch_summary.json", batch)
    fields = ["task_id", "repository", "agent_status", "agent_resolved",
              "agent_timed_out", "patch_bytes", "verification_status",
              "test_exit_code", "test_passed", "test_failed", "test_errors",
              "reference_preflight_status", "cleanup_ok", "image_id",
              "result_dir", "trace_path", "patch_path", "test_output_path",
              "effective_settings_path"]
    with (batch_dir / "per_task.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in batch["tasks"]:
            writer.writerow({field: item.get(field) for field in fields})
    write_json(batch_dir / "per_task.json", batch["tasks"])


def resource_concern():
    stat = os.statvfs(KIT)
    disk_free = stat.f_bavail * stat.f_frsize
    memory_free = psutil.virtual_memory().available
    gpu_free = gpu_free_mib()
    if disk_free < MIN_DISK_BYTES:
        return f"disk free below 12 GiB: {disk_free} bytes"
    if memory_free < MIN_HOST_MEMORY_BYTES:
        return f"host memory available below 16 GiB: {memory_free} bytes"
    if gpu_free < MIN_RUNNING_GPU_FREE_MIB:
        return f"GPU free below 8,000 MiB: {gpu_free} MiB"
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-label", required=True)
    parser.add_argument("--resume-from", type=Path,
                        help="Completed batch summary; run only its unattempted published tasks")
    parser.add_argument("--max-observed-container-rss-gib", type=float, default=8.0)
    args = parser.parse_args()
    label = args.batch_label
    if not label.isascii() or not label.replace("-", "").replace("_", "").isalnum():
        parser.error("batch label must use ASCII letters, digits, hyphens, or underscores")

    tasks = [json.loads(line) for line in (DATA / "tasks.jsonl").open()]
    if len(tasks) != 129 or len({t["instance_id"] for t in tasks}) != 129:
        parser.error("Expected 129 unique published tasks")
    source_batch = None
    if args.resume_from:
        source_batch = json.loads(args.resume_from.read_text())
        completed = {entry["task_id"] for entry in source_batch["tasks"]}
        published = {task["instance_id"] for task in tasks}
        if source_batch.get("task_count") != 129 or not completed <= published:
            parser.error("Resume source does not match the published 129-task set")
        tasks = [task for task in tasks if task["instance_id"] not in completed]
        if not tasks:
            parser.error("No unattempted tasks remain")
    if args.max_observed_container_rss_gib <= 0:
        parser.error("RSS threshold must be positive")
    rss_limit_bytes = int(args.max_observed_container_rss_gib * 1024**3)
    audit = json.loads((KIT / "results/docker-ref129-20261015a-reference-batch/batch_audit.json").read_text())
    preflight = {task_id: status for status, task_ids in audit["ids_by_category"].items()
                 for task_id in task_ids}
    if len(preflight) != 129:
        parser.error("Reference preflight does not cover 129 tasks")

    batch_dir = KIT / "results" / f"docker-{label}-agent-batch"
    if batch_dir.exists():
        parser.error(f"Batch result already exists: {batch_dir}")
    for task in tasks:
        run_label = f"{label}-{task['instance_id']}"
        if (KIT / "results" / f"docker-{run_label}-agent").exists():
            parser.error(f"Task result already exists: {run_label}")
    with socket.socket() as check:
        if check.connect_ex(("127.0.0.1", 8001)) == 0:
            parser.error("Port 8001 is occupied; refusing to take over a server")
    initial_gpu_free = gpu_free_mib()
    if initial_gpu_free < MIN_START_GPU_FREE_MIB:
        parser.error(f"Insufficient GPU memory before server: {initial_gpu_free} MiB free")

    client = docker.from_env(timeout=10)
    image_ids = {repo: client.images.get(image).id for repo, image in IMAGES.items()}
    batch_dir.mkdir(parents=True)
    batch = {"label": label, "task_count": len(tasks), "published_task_count": 129,
             "resume_source": str(args.resume_from) if args.resume_from else None,
             "max_observed_container_rss_bytes": rss_limit_bytes, "concurrency": 1,
             "agent_time_minutes": 5, "max_tool_calls": 100,
             "outer_deadline_seconds_per_task": OUTER_SECONDS,
             "gpu_memory_fraction": "0.60", "max_num_seqs": 1,
             "sampling_seed": None, "image_ids": image_ids,
             "reference_audit": str(KIT / "results/docker-ref129-20261015a-reference-batch/batch_audit.json"),
             "gpu_free_mib_before_server": initial_gpu_free,
             "tasks": [], "stop_reason": None}
    write_json(batch_dir / "batch_manifest.json", {k: v for k, v in batch.items() if k != "tasks"})

    server = None
    server_created_at = None
    active = None
    active_run_id = None
    try:
        env = os.environ.copy()
        env["BASELINE_GPU_FRACTION"] = "0.60"
        env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
        with (batch_dir / "vllm.log").open("w") as log:
            server = subprocess.Popen(["bash", str(KIT / "serve.sh")], cwd=KIT,
                                      env=env, stdout=log, stderr=subprocess.STDOUT,
                                      start_new_session=True)
        server_created_at = psutil.Process(server.pid).create_time()
        write_json(batch_dir / "server_record.json", {
            "pid": server.pid, "create_time": server_created_at,
            "process_group": os.getpgid(server.pid),
            "serve_script_sha256": sha256(KIT / "serve.sh"),
            "gpu_memory_fraction": "0.60", "max_num_seqs": 1,
        })
        startup_deadline = time.monotonic() + 600
        while True:
            if STOP_REQUESTED:
                raise KeyboardInterrupt
            if server.poll() is not None:
                raise RuntimeError(f"vLLM exited during startup: {server.returncode}")
            if time.monotonic() >= startup_deadline:
                raise TimeoutError("vLLM startup exceeded 600 seconds")
            if gpu_free_mib() < MIN_RUNNING_GPU_FREE_MIB:
                raise RuntimeError("GPU free memory fell below 8,000 MiB during server startup")
            try:
                with urllib.request.urlopen(MODEL_URL + "/models", timeout=2) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(2)
        with (batch_dir / "model_probe.log").open("w") as log:
            subprocess.run([sys.executable, str(KIT / "probe_models.py"),
                            "--output", str(batch_dir / "model_probe.json")],
                           cwd=KIT, stdout=log, stderr=subprocess.STDOUT,
                           timeout=390, check=True)

        for index, task in enumerate(tasks, 1):
            if STOP_REQUESTED:
                batch["stop_reason"] = "batch interrupted"
                break
            if server.poll() is not None:
                batch["stop_reason"] = "vLLM server exited before next task"
                break
            concern = resource_concern()
            if concern:
                batch["stop_reason"] = f"shared-server resource concern before {task['instance_id']}: {concern}"
                break

            task_id, repo = task["instance_id"], task["repo"]
            run_label = f"{label}-{task_id}"
            active_run_id = f"{run_label}-{uuid.uuid4().hex}"
            result_dir = KIT / "results" / f"docker-{run_label}-agent"
            command = [sys.executable, str(KIT / "run_docker.py"), "--mode", "agent",
                       "--external-server", "--task-id", task_id,
                       "--label", run_label, "--run-id", active_run_id,
                       "--image", IMAGES[repo], "--seconds", str(OUTER_SECONDS)]
            print(f"[{index}/{len(tasks)}] {task_id} ({repo})", flush=True)
            with (batch_dir / f"{task_id}.supervisor.log").open("w") as log:
                active = subprocess.Popen(command, cwd=KIT, stdout=log,
                                          stderr=subprocess.STDOUT, start_new_session=True)
                watchdog = time.monotonic() + OUTER_SECONDS + 45
                while active.poll() is None:
                    if STOP_REQUESTED or server.poll() is not None:
                        os.killpg(active.pid, signal.SIGINT)
                        break
                    if time.monotonic() >= watchdog:
                        os.killpg(active.pid, signal.SIGINT)
                        batch["stop_reason"] = f"supervisor watchdog expired at {task_id}"
                        break
                    concern = resource_concern()
                    if concern:
                        os.killpg(active.pid, signal.SIGINT)
                        batch["stop_reason"] = f"shared-server resource concern during {task_id}: {concern}"
                        break
                    time.sleep(5)
                try:
                    active.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(active.pid, signal.SIGKILL)
                    active.wait()
                    batch["stop_reason"] = batch["stop_reason"] or f"supervisor did not stop at {task_id}"
                supervisor_code = active.returncode
            active = None

            monitor_path = result_dir / "monitor.json"
            outcome_path = result_dir / "outcome.json"
            phase_path = result_dir / "agent_phase.json"
            settings_path = result_dir / "effective_settings.json"
            patch_path = result_dir / "patches" / f"{task_id}.patch"
            trace_path = result_dir / "traces" / f"trace_{task_id}.json"
            test_path = result_dir / "test_outputs" / f"{task_id}.log"
            monitor = json.loads(monitor_path.read_text()) if monitor_path.exists() else None
            outcome = json.loads(outcome_path.read_text()) if outcome_path.exists() else None
            phase = json.loads(phase_path.read_text()) if phase_path.exists() else None
            test_output = test_path.read_text(errors="replace") if test_path.exists() else ""
            remaining = [c.id for c in owned_containers(client, active_run_id)]
            peak_rss = max((sample.get("observed_pid_namespace_rss_bytes") or 0
                            for sample in monitor.get("samples", [])), default=0) if monitor else 0
            category = classify_agent(outcome, monitor, patch_path)
            verification = classify_verification(outcome, test_output)
            counts = test_counts(test_output)
            entry = {
                "task_id": task_id, "repository": repo, "run_id": active_run_id,
                "image_id": image_ids[repo], "result_dir": str(result_dir),
                "reference_preflight_status": preflight[task_id],
                "agent_status": category,
                "agent_resolved": outcome.get("resolved") if outcome else None,
                "agent_timed_out": bool((monitor and monitor.get("timed_out"))
                                        or (outcome and outcome.get("agent_timeout"))),
                "agent_error": outcome.get("agent_error") if outcome else None,
                "verification_status": verification,
                "verification_error": outcome.get("verification_error") if outcome else None,
                "test_exit_code": outcome.get("test_exit_code") if outcome else None,
                "test_counts": counts, "test_passed": counts.get("passed", 0),
                "test_failed": counts.get("failed", 0),
                "test_errors": counts.get("error", counts.get("errors", 0)),
                "patch_bytes": phase.get("patch_bytes") if phase else None,
                "patch_submission_seconds": outcome.get("patch_submission_seconds") if outcome else None,
                "tool_calls": outcome.get("tool_calls") if outcome else None,
                "llm_calls": outcome.get("total_llm_calls") if outcome else None,
                "token_usage": outcome.get("token_usage") if outcome else None,
                "supervisor_exit_code": supervisor_code,
                "monitor_started_before_worker": bool(monitor and monitor.get("monitor_started_at")
                    and monitor.get("worker_started_at") and
                    monitor["monitor_started_at"] <= monitor["worker_started_at"]),
                "peak_observed_container_rss_bytes": peak_rss,
                "cleanup_ok": bool(monitor and not monitor.get("remaining_owned_ids") and not remaining),
                "remaining_owned_ids": remaining,
                "trace_path": str(trace_path) if trace_path.exists() else None,
                "patch_path": str(patch_path) if patch_path.exists() else None,
                "test_output_path": str(test_path) if test_path.exists() else None,
                "effective_settings_path": str(settings_path) if settings_path.exists() else None,
            }
            batch["tasks"].append(entry)
            save_batch(batch_dir, batch)
            print(f"  agent={category}; verification={verification}; "
                  f"resolved={entry['agent_resolved']}; cleanup={entry['cleanup_ok']}", flush=True)

            if not entry["cleanup_ok"]:
                batch["stop_reason"] = batch["stop_reason"] or f"container cleanup failure at {task_id}"
            if not entry["monitor_started_before_worker"]:
                batch["stop_reason"] = batch["stop_reason"] or f"monitoring failure at {task_id}"
            if peak_rss > rss_limit_bytes:
                batch["stop_reason"] = batch["stop_reason"] or f"container RSS resource concern at {task_id}"
            if not settings_path.exists():
                batch["stop_reason"] = batch["stop_reason"] or f"missing effective settings at {task_id}"
            if outcome is None:
                batch["stop_reason"] = batch["stop_reason"] or f"missing agent outcome at {task_id}"
            if supervisor_code not in (0, 1, 124, 130):
                batch["stop_reason"] = batch["stop_reason"] or f"supervisor error at {task_id}: {supervisor_code}"
            if STOP_REQUESTED and not batch["stop_reason"]:
                batch["stop_reason"] = "batch interrupted"
            if batch["stop_reason"]:
                break
            active_run_id = None
    except KeyboardInterrupt:
        batch["stop_reason"] = batch["stop_reason"] or "batch interrupted"
    except Exception as exc:
        batch["stop_reason"] = batch["stop_reason"] or f"infrastructure error: {type(exc).__name__}: {exc}"
    finally:
        if active is not None and active.poll() is None:
            os.killpg(active.pid, signal.SIGINT)
            try:
                active.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(active.pid, signal.SIGKILL)
                active.wait()
        if active_run_id is not None:
            try:
                clean_owned(client, active_run_id)
            except Exception as exc:
                batch["stop_reason"] = (batch["stop_reason"] or "") + f"; cleanup error: {exc}"
        try:
            batch["server_cleanup"] = stop_server(server, server_created_at)
        except Exception as exc:
            batch["server_cleanup"] = None
            batch["stop_reason"] = (batch["stop_reason"] or "") + f"; server cleanup error: {exc}"
        save_batch(batch_dir, batch)
    clean_server = batch["server_cleanup"] and all(batch["server_cleanup"].values())
    return 0 if len(batch["tasks"]) == len(tasks) and not batch["stop_reason"] and clean_server else 1


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    sys.exit(main())
