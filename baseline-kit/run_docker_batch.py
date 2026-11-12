"""Three sequential Requests attempts against one locally owned vLLM server."""

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import uuid
import urllib.request

import docker
import psutil

from run_docker import KIT, LABEL_KEY, MODEL_URL, clean_owned, owned_containers, sha256


IMAGE = "gemma-requests-sandbox:20261015c"
SEEDS = (750501, 750502, 750503)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def server_is_owned(server, create_time):
    try:
        return (psutil.Process(server.pid).create_time() == create_time
                and os.getpgid(server.pid) == server.pid)
    except (psutil.Error, ProcessLookupError):
        return False


def stop_server(server, create_time):
    if server is None:
        return None
    if server_is_owned(server, create_time):
        os.killpg(server.pid, signal.SIGTERM)
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if server_is_owned(server, create_time):
                os.killpg(server.pid, signal.SIGKILL)
            server.wait(timeout=10)
    with socket.socket() as check:
        port_closed = check.connect_ex(("127.0.0.1", 8001)) != 0
    return {"pid": server.pid, "process_exited": server.poll() is not None,
            "port_8001_closed": port_closed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-label", required=True)
    args = parser.parse_args()
    label = args.batch_label
    if not label.isascii() or not label.replace("-", "").replace("_", "").isalnum():
        parser.error("batch label must contain only ASCII letters, digits, hyphens, or underscores")

    batch_dir = KIT / "results" / f"docker-{label}-batch"
    labels = [f"{label}-a{index}" for index in range(1, 4)]
    attempt_dirs = [KIT / "results" / f"docker-{item}-agent" for item in labels]
    for path in [batch_dir, *attempt_dirs]:
        if path.exists():
            parser.error(f"result directory already exists: {path}")
    with socket.socket() as check:
        if check.connect_ex(("127.0.0.1", 8001)) == 0:
            parser.error("port 8001 is already in use; cannot own that server")

    client = docker.from_env(timeout=10)
    image_id = client.images.get(IMAGE).id
    batch_dir.mkdir(parents=True)
    batch = {"image": IMAGE, "image_id": image_id, "concurrency": 1,
             "gpu_memory_fraction": "0.60", "max_num_seqs": 1,
             "agent_budget_minutes": 5, "max_tool_calls": 100,
             "outer_deadline_seconds_per_attempt": 900,
             "labels": labels, "seeds": list(SEEDS), "attempts": []}
    write_json(batch_dir / "batch_manifest.json", batch)

    server = None
    server_create_time = None
    active_attempt = None
    active_run_id = None
    launched_run_ids = []
    stop_reason = None
    try:
        env = os.environ.copy()
        env["BASELINE_GPU_FRACTION"] = "0.60"
        env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
        with (batch_dir / "vllm.log").open("w") as log:
            server = subprocess.Popen(["bash", str(KIT / "serve.sh")], cwd=KIT,
                                      env=env, stdout=log, stderr=subprocess.STDOUT,
                                      start_new_session=True)
        server_create_time = psutil.Process(server.pid).create_time()
        write_json(batch_dir / "server_record.json", {
            "pid": server.pid, "create_time": server_create_time,
            "process_group": os.getpgid(server.pid),
            "serve_script_sha256": sha256(KIT / "serve.sh"),
            "gpu_memory_fraction": "0.60", "max_num_seqs": 1,
        })
        startup_deadline = time.monotonic() + 600
        while True:
            if server.poll() is not None:
                raise RuntimeError(f"vLLM exited during startup: {server.returncode}")
            if time.monotonic() >= startup_deadline:
                raise TimeoutError("vLLM startup exceeded 600 seconds")
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

        for label_item, result_dir, seed in zip(labels, attempt_dirs, SEEDS):
            if server.poll() is not None:
                stop_reason = "vLLM exited before an attempt"
                break
            active_run_id = f"{label_item}-{uuid.uuid4().hex}"
            launched_run_ids.append(active_run_id)
            command = [sys.executable, str(KIT / "run_docker.py"),
                       "--mode", "agent", "--external-server",
                       "--label", label_item, "--run-id", active_run_id,
                       "--image", IMAGE, "--seconds", "900",
                       "--seed", str(seed)]
            with (batch_dir / f"{label_item}.supervisor.log").open("w") as log:
                active_attempt = subprocess.Popen(command, cwd=KIT, stdout=log,
                                                  stderr=subprocess.STDOUT,
                                                  start_new_session=True)
                try:
                    return_code = active_attempt.wait(timeout=930)
                except subprocess.TimeoutExpired:
                    os.killpg(active_attempt.pid, signal.SIGINT)
                    try:
                        active_attempt.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(active_attempt.pid, signal.SIGKILL)
                        active_attempt.wait()
                    clean_owned(client, active_run_id)
                    stop_reason = f"attempt {label_item} supervisor watchdog expired"
                    return_code = active_attempt.returncode
            active_attempt = None
            remaining = [c.id for c in owned_containers(client, active_run_id)]
            monitor_path = result_dir / "monitor.json"
            outcome_path = result_dir / "outcome.json"
            monitor = json.loads(monitor_path.read_text()) if monitor_path.exists() else None
            outcome = json.loads(outcome_path.read_text()) if outcome_path.exists() else None
            attempt = {"label": label_item, "run_id": active_run_id,
                       "seed": seed, "result_dir": str(result_dir),
                       "supervisor_exit_code": return_code,
                       "monitor": str(monitor_path) if monitor else None,
                       "outcome": outcome,
                       "remaining_owned_ids": remaining}
            batch["attempts"].append(attempt)
            write_json(batch_dir / "batch_summary.json", batch)
            if (stop_reason or remaining or monitor is None or outcome is None
                    or return_code not in (0, 1) or monitor.get("timed_out")
                    or monitor.get("interrupted")
                    or monitor.get("monitor_started_at") is None
                    or monitor.get("worker_started_at") is None
                    or monitor["monitor_started_at"] > monitor["worker_started_at"]):
                stop_reason = stop_reason or f"infrastructure or cleanup failure in {label_item}"
                if remaining:
                    clean_owned(client, active_run_id)
                break
            active_run_id = None
    except KeyboardInterrupt:
        stop_reason = "batch interrupted"
    except Exception as exc:
        stop_reason = f"infrastructure failure: {type(exc).__name__}: {exc}"
    finally:
        if active_attempt is not None and active_attempt.poll() is None:
            os.killpg(active_attempt.pid, signal.SIGINT)
            try:
                active_attempt.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(active_attempt.pid, signal.SIGKILL)
                active_attempt.wait()
        cleanup_errors = []
        if active_run_id is not None:
            try:
                clean_owned(client, active_run_id)
            except Exception as exc:
                cleanup_errors.append(f"container cleanup: {type(exc).__name__}: {exc}")
        batch["stop_reason"] = stop_reason
        try:
            batch["server_cleanup"] = stop_server(server, server_create_time)
        except Exception as exc:
            batch["server_cleanup"] = None
            cleanup_errors.append(f"server cleanup: {type(exc).__name__}: {exc}")
        batch["remaining_owned_ids"] = {}
        for run_id in launched_run_ids:
            try:
                batch["remaining_owned_ids"][run_id] = [
                    c.id for c in owned_containers(client, run_id)]
            except Exception as exc:
                batch["remaining_owned_ids"][run_id] = None
                cleanup_errors.append(f"container verification {run_id}: {type(exc).__name__}: {exc}")
        batch["cleanup_errors"] = cleanup_errors
        write_json(batch_dir / "batch_summary.json", batch)
    clean = batch["server_cleanup"] and all(batch["server_cleanup"].values())
    clean = clean and not any(batch["remaining_owned_ids"].values()) and not batch["cleanup_errors"]
    return 0 if len(batch["attempts"]) == 3 and not stop_reason and clean else 1


if __name__ == "__main__":
    sys.exit(main())
