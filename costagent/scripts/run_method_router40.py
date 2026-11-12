#!/usr/bin/env python3
"""Run the matched 40 tasks with RFT/DPO/sticky-SDPO plus phase controls."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

import psutil

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "costagent"
EVAL = PKG / "artifacts/mixed-temperature-v1/evaluation"
SOURCE_CSV = EVAL / "router40-20261108a-analysis/per_task_outcomes_6arms.csv"
ADAPTER = PKG / "artifacts/mixed-temperature-v1/dpo/epoch-005"
PYTHON = "/home/mahesh/miniconda3/envs/gemma-harness/bin/python"
sys.path.insert(0, str(ROOT / "baseline-kit"))
from run_docker_agent_all import gpu_free_mib, resource_concern, stop_server
from run_docker import owned_containers

STOP = False


def request_stop(_signal, _frame):
    global STOP
    STOP = True


def selected_tasks():
    tasks = json.loads((EVAL / 'test_tasks.json').read_text())
    original = [json.loads(line)['instance_id'] for line in
                (EVAL / 'paper40-20261106a/tasks.jsonl').read_text().splitlines()]
    if len(tasks) != 40 or len(set(tasks)) != 40 or set(tasks) != set(original):
        raise RuntimeError('Task list differs from original 40')
    return sorted(tasks)


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume-from", type=Path)
    args = parser.parse_args()
    if not args.label.isascii() or not args.label.replace("-", "").isalnum():
        parser.error("Invalid label")
    all_tasks = selected_tasks()
    previous = []
    if args.resume_from:
        prior = json.loads((args.resume_from / 'summary.json').read_text())
        if prior['state'] not in {'stopped', 'complete'}:
            raise RuntimeError('Prior batch is not terminal')
        for row in prior['attempts']:
            directory = Path(row['result_dir'])
            outcome = json.loads((directory / 'outcome.json').read_text())
            monitor = json.loads((directory / 'monitor.json').read_text())
            if not row['cleanup_ok'] or monitor['remaining_owned_ids']:
                raise RuntimeError('Prior cleanup not confirmed')
            if outcome.get('agent_timeout') != row['agent_timeout']:
                raise RuntimeError('Prior outcome inconsistent')
            previous.append(row)
        ids = [r['task_id'] for r in previous]
        if len(set(ids)) != len(ids) or not set(ids) <= set(all_tasks):
            raise RuntimeError('Invalid prior task IDs')
        for name in ['method_router.py', 'phase_router.py']:
            if (args.resume_from / name).read_bytes() != (PKG / 'scripts' / name).read_bytes():
                raise RuntimeError('Routing policy changed; cannot combine previous outcomes')
    tasks = [t for t in all_tasks if t not in {r['task_id'] for r in previous}]
    smoke = []
    plan = {"label": args.label, "smoke_tasks": smoke, "rerun_tasks": tasks,
            "resume_from": str(args.resume_from) if args.resume_from else None,
            "preserved_task_ids": [r["task_id"] for r in previous],
            "seed": 42, "temperature": 0.2, "agent_minutes": 5,
            "max_tool_calls": 100, "outer_seconds": 900, "concurrency": 1,
            "adapter": str(ADAPTER), "router": "method-v1-sticky+phase-v2", "gpu_memory_fraction": 0.60,
            "max_observed_container_rss_gib": 12,
            "router_fallback": "full original tool list when filter is empty; unchanged request if caller supplies no tools"}
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return
    batch = EVAL / args.label
    batch.mkdir(exist_ok=False)
    (batch / "task_lists").mkdir()
    router = batch / "method_router.py"
    shutil.copy2(PKG / "scripts/method_router.py", router)
    shutil.copy2(PKG / "scripts/phase_router.py", batch / 'phase_router.py')
    adapters = {'rft_lora': PKG / 'artifacts/adapters/A2',
                'dpo_lora': ADAPTER,
                'sdpo_lora': PKG / 'artifacts/mixed-temperature-v1/sdpo/contrast/epoch-005'}
    plan['adapters'] = {name: {'path': str(path.resolve()), 'files': {
        filename: hashlib.sha256((path / filename).read_bytes()).hexdigest()
        for filename in ('adapter_config.json', 'adapter_model.safetensors')}}
        for name, path in adapters.items()}
    plan['phase_sha256'] = hashlib.sha256((batch / 'phase_router.py').read_bytes()).hexdigest()
    plan['trigger_priority'] = ['sticky', 'wall_seconds>=240', 'identical_command_and_output_twice', 'recognized_test_exit_0', 'two_completed_exchanges']
    plan['monitor_sha256'] = hashlib.sha256((PKG / 'scripts/container_monitor.py').read_bytes()).hexdigest()
    plan['worker_sha256'] = hashlib.sha256((PKG / 'scripts/docker_eval_worker.py').read_bytes()).hexdigest()
    plan["router_sha256"] = hashlib.sha256(router.read_bytes()).hexdigest()
    atomic_json(batch / "plan.json", plan)
    summary = {"plan": plan, "attempts": previous, "state": "starting", "server_cleanup": None}

    def save(event, **fields):
        row = {"time": time.time(), "event": event, **fields}
        with (batch / "progress.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()
            os.fsync(f.fileno())
        summary['counts'] = {'completed': len(summary['attempts']),
            'resolved': sum(r['resolved'] is True for r in summary['attempts']),
            'unresolved': sum(r['resolved'] is False for r in summary['attempts']),
            'ungraded': sum(r['resolved'] is None for r in summary['attempts']),
            'timeout': sum(bool(r['agent_timeout']) for r in summary['attempts'])}
        atomic_json(batch / "summary.json", summary)
        print(json.dumps(row), flush=True)

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    server = active = client = None
    created = None
    try:
        if gpu_free_mib() < 62000:
            raise RuntimeError("GPU free memory below 62000 MiB before server startup")
        concern = resource_concern()
        if concern:
            raise RuntimeError(concern)
        with socket.socket() as port:
            if port.connect_ex(("127.0.0.1", 8001)) == 0:
                raise RuntimeError("Port 8001 is already in use; will not take ownership")
        env = os.environ.copy()
        env["MAIN_ADAPTER"] = str(ADAPTER)
        env["COSTAGENT_ROUTER"] = "method-v1"
        env["COSTAGENT_METHOD_ROUTER"] = "1"
        env["COSTAGENT_ROUTER_SOURCE"] = str(router)
        with (batch / "vllm.log").open("w") as log:
            server = subprocess.Popen(["bash", str(PKG / "scripts/serve_local.sh")],
                                      cwd=PKG, env=env, stdout=log, stderr=subprocess.STDOUT,
                                      start_new_session=True)
        created = psutil.Process(server.pid).create_time()
        atomic_json(batch / "server_record.json", {"pid": server.pid, "create_time": created,
                                                     "process_group": os.getpgid(server.pid)})
        save("server_starting", pid=server.pid)
        deadline = time.monotonic() + 1200
        while True:
            if STOP or server.poll() is not None:
                raise RuntimeError(f"Server stopped before readiness: {server.poll()}")
            if time.monotonic() > deadline:
                raise TimeoutError("vLLM startup exceeded 1200 seconds")
            concern = resource_concern()
            if concern:
                raise RuntimeError(concern)
            try:
                with urllib.request.urlopen("http://127.0.0.1:8001/v1/models", timeout=2) as r:
                    json.load(r)
                break
            except (OSError, ValueError):
                time.sleep(3)
        save("server_ready")
        with (batch / "model_probe.log").open("w") as log:
            subprocess.run([PYTHON, str(ROOT / "baseline-kit/probe_models.py"),
                            "--output", str(batch / "model_probe.json")],
                           cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=390)
        save("model_probe_passed")
        with urllib.request.urlopen('http://127.0.0.1:8001/v1/models', timeout=10) as response:
            served = {m['id']: m for m in json.load(response)['data']}
        probes = []
        for name, path in adapters.items():
            if name not in served or Path(served[name]['root']).resolve() != path.resolve():
                raise RuntimeError(f'Adapter identity mismatch: {name}')
            body = {'model': name, 'messages': [{'role': 'user', 'content': 'Reply OK.'}],
                    'max_tokens': 16, 'temperature': 0, 'chat_template_kwargs': {'enable_thinking': False}}
            req = urllib.request.Request('http://127.0.0.1:8001/v1/chat/completions',
                data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=90) as response:
                result = json.load(response)
            if not result.get('choices'):
                raise RuntimeError(f'No response from {name}')
            probes.append({'model': name, 'response': result})
            atomic_json(batch / 'method_model_probes.json', probes)
            save('method_adapter_ready', model=name)
        import docker
        env.setdefault("DOCKER_HOST", subprocess.check_output(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"], text=True).strip())
        client = docker.DockerClient(base_url=env["DOCKER_HOST"], timeout=10)
        sequence = [("smoke", t) for t in smoke] + [("rerun", t) for t in tasks]
        for stage, task in sequence:
            if STOP:
                raise InterruptedError("Stop requested")
            if server.poll() is not None:
                raise RuntimeError("Owned vLLM server exited")
            concern = resource_concern()
            if concern:
                raise RuntimeError(concern)
            task_list = batch / "task_lists" / f"{stage}-{task}.json"
            atomic_json(task_list, [task])
            out = batch / stage / task
            command = [PYTHON, "-u", str(PKG / "scripts/eval_existing_docker.py"),
                       "--submission", str(ROOT / "data/sample_submission"), "--out", str(out),
                       "--task-list", str(task_list), "--seed", "42", "--temperature", "0.2"]
            summary["state"] = f"{stage}:{task}"
            save("task_started", stage=stage, task_id=task, command=command,
                 reruns_completed=sum(x["stage"] == "rerun" for x in summary["attempts"]))
            with (batch / f"{stage}-{task}.log").open("w") as log:
                active = subprocess.Popen(command, cwd=PKG, env=env, stdout=log,
                                          stderr=subprocess.STDOUT, start_new_session=True)
                watchdog = time.monotonic() + 960
                while active.poll() is None:
                    concern = resource_concern()
                    if STOP or concern or server.poll() is not None or time.monotonic() > watchdog:
                        os.killpg(active.pid, signal.SIGINT)
                        try:
                            active.wait(timeout=45)
                        except subprocess.TimeoutExpired:
                            os.killpg(active.pid, signal.SIGTERM)
                            active.wait(timeout=15)
                        raise RuntimeError(f"Stopped {task}: {concern or 'interruption, server exit, or watchdog'}")
                    time.sleep(5)
                rc = active.returncode
                active = None
            taskdir = out / "tasks" / task
            monitor_path, outcome_path = taskdir / "monitor.json", taskdir / "outcome.json"
            if rc or not monitor_path.is_file() or not outcome_path.is_file():
                raise RuntimeError(f"Task {task} infrastructure failure: rc={rc}, result={taskdir}")
            monitor = json.loads(monitor_path.read_text())
            run = json.loads((taskdir / "run_manifest.json").read_text())
            remaining = [c.id for c in owned_containers(client, run["run_id"])]
            samples = monitor.get("samples", [])
            peak = max((s.get("observed_pid_namespace_rss_bytes") or 0 for s in samples), default=0)
            if (remaining or monitor.get("remaining_owned_ids") or not monitor.get("monitor_started_at")
                    or monitor["monitor_started_at"] > monitor.get("worker_started_at", 0)
                    or not any(s.get("host_pid") for s in samples)):
                raise RuntimeError(f"Cleanup/monitor check failed for {task}; remaining={remaining}")
            outcome = json.loads(outcome_path.read_text())
            manifest = json.loads((out / "manifest.json").read_text())["attempts"]
            if len(manifest) != 1 or manifest[0]["task_id"] != task:
                raise RuntimeError(f"Task result manifest mismatch: {task}")
            if "Router would expose no tools" in (taskdir / "worker.log").read_text(errors="replace"):
                raise RuntimeError(f"Router empty-tool exception recurred: {task}")
            row = {"stage": stage, "task_id": task, "resolved": manifest[0]["resolved"],
                   "verification_status": manifest[0]["verification_status"],
                   "agent_timeout": outcome.get("agent_timeout"), "agent_error": outcome.get("agent_error"),
                   "patch_bytes": outcome.get("patch_bytes"), "test_exit_code": outcome.get("test_exit_code"),
                   "peak_observed_container_rss_bytes": peak, "cleanup_ok": True,
                   "result_dir": str(taskdir), "trace": manifest[0].get("trace_path"),
                   "submission_elapsed_seconds": outcome.get('patch_submission_seconds'),
                   "token_usage": outcome.get('token_usage'),
                   "tool_calls": outcome.get("tool_calls"), "llm_calls": outcome.get("total_llm_calls"),
                   "duration_seconds": outcome.get("duration_seconds"),
                   "method_request_counts": {}, "method_switches": 0}
            for line in (taskdir / 'router_decisions.jsonl').read_text().splitlines():
                decision = json.loads(line)
                method = decision['method']
                row['method_request_counts'][method] = row['method_request_counts'].get(method, 0) + 1
                row['method_switches'] = max(row['method_switches'], decision['switches'])
            if row['method_switches'] > 2:
                raise RuntimeError('Method router switched more than twice')
            summary["attempts"].append(row)
            save("task_finished", **row, reruns_completed=sum(x["stage"] == "rerun" for x in summary["attempts"]))
            if peak > 12 * 1024**3:
                raise RuntimeError(f"Observed container namespace RSS exceeded 12 GiB on {task}")
        summary["state"] = "complete"
        save("batch_complete", reruns_completed=40, smoke_completed=0)
    except BaseException as exc:
        summary["state"] = "stopped"
        summary["stop_reason"] = f"{type(exc).__name__}: {exc}"
        save("batch_stopped", reason=summary["stop_reason"])
        raise
    finally:
        if active is not None and active.poll() is None:
            os.killpg(active.pid, signal.SIGINT)
            try:
                active.wait(timeout=45)
            except subprocess.TimeoutExpired:
                os.killpg(active.pid, signal.SIGTERM)
                active.wait(timeout=15)
        try:
            if client is not None:
                cleanup = []
                for path in batch.glob('**/run_manifest.json'):
                    run_id = json.loads(path.read_text())['run_id']
                    for container in owned_containers(client, run_id):
                        container.reload()
                        if container.labels.get('gemma.local.verification.run') != run_id:
                            raise RuntimeError('Container ownership changed')
                        container.remove(force=True)
                        cleanup.append(container.id)
                    if owned_containers(client, run_id):
                        raise RuntimeError(f'Owned containers remain: {run_id}')
                save('final_container_cleanup', removed_ids=cleanup)
        finally:
            if server is not None:
                summary["server_cleanup"] = stop_server(server, created)
                save("server_cleanup", **(summary["server_cleanup"] or {}))



if __name__ == "__main__":
    main()
