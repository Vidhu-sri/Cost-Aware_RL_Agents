"""Bounded Docker evaluation using the installed swegemma API.

The parent owns the wall deadline and cleans containers identified by a unique
Docker label. The child calls the official Evaluator or verify_task.
"""

import argparse
import asyncio
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
import urllib.request
from types import SimpleNamespace

import docker
import psutil


KIT = Path(__file__).resolve().parent
ROOT = KIT.parent
DATA = ROOT / "data"
PATCH = KIT / "results/requests-agent-20261012-095650-baseline/patches/requests_7505.patch"
LABEL_KEY = "gemma.local.verification.run"
MODEL_ALIAS = "gemma-4-31b-it-qat-w4a16-ct"
MODEL_URL = "http://127.0.0.1:8001/v1"

for key, value in {
    "LITELLM_LOCAL_MODEL_COST_MAP": "True", "OTEL_SDK_DISABLED": "true",
    "LITELLM_TELEMETRY": "False", "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
}.items():
    os.environ[key] = value


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def owned_containers(client, run_id):
    return client.containers.list(all=True, filters={"label": f"{LABEL_KEY}={run_id}"})


def clean_owned(client, run_id):
    removed = []
    for container in owned_containers(client, run_id):
        cid = container.id
        try:
            container.stop(timeout=2)
        except docker.errors.DockerException:
            pass
        try:
            container.remove(force=True)
        except docker.errors.NotFound:
            pass
        removed.append(cid)
    return removed


def worker(args, result_dir):
    ready = result_dir / "monitor.ready"
    while not ready.exists():
        time.sleep(0.1)
    from adk_submission import ModelRegistry
    from swegemma.config import EvalConfig
    from swegemma.deduplication import resolve_task_snapshot_paths
    from swegemma.harness.verification import verify_task
    from swegemma.harness.container_setup import (
        extract_snapshot, install_editable_package, install_test_dependencies,
        setup_container_wheels,
    )
    from swegemma.models import load_tasks
    from swegemma.sandbox.docker import ContainerConfig, ContainerManager

    class OwnedContainerManager(ContainerManager):
        def exec(self, container_id, command, *, timeout=None):
            response = super().exec(container_id, command, timeout=timeout)
            if (args.mode in ("reference", "agent") and response.exit_code == 0
                    and command.startswith("python3 /tmp/setup.py ")):
                packages = ["pytest", "pytest-cov", "pytest-timeout", "pygments",
                            "markdown-it-py", "mdurl", "typing-extensions",
                            "certifi", "idna", "httpx", "rich", "starlette",
                            "pydantic", "pydantic-core", "inline-snapshot",
                            "dirty-equals", "sqlmodel", "strawberry-graphql"]
                code = ("import importlib.metadata as m, importlib.util as u, json, sys, os, fcntl, pygments; "
                        f"names={packages!r}; "
                        "pipe_read,pipe_write=os.pipe(); "
                        "versions={n:(m.version(n) if any(x.name.lower().replace('_','-')==n "
                        "for x in m.distributions()) else None) for n in names}; "
                        "print(json.dumps({'python':sys.version.split()[0], "
                        "'pipe_capacity_bytes':fcntl.fcntl(pipe_write,fcntl.F_GETPIPE_SZ), "
                        "'TERM':os.environ.get('TERM'), 'COLUMNS':os.environ.get('COLUMNS'), "
                        "'PYTHONUNBUFFERED':os.environ.get('PYTHONUNBUFFERED'), "
                        "'versions':versions, 'pygments_imported_version':pygments.__version__, "
                        "'pygments_path':pygments.__file__, "
                        "'httpx_path':str(u.find_spec('httpx').origin) "
                        "if u.find_spec('httpx') else None, 'rich_path':str(u.find_spec('rich').origin) "
                        "if u.find_spec('rich') else None, "
                        "'fastapi_path':str(u.find_spec('fastapi').origin) "
                        "if u.find_spec('fastapi') else None}))")
                import shlex
                captured = super().exec(container_id, "python3 -c " + shlex.quote(code), timeout=20)
                if captured.exit_code == 0:
                    observed = json.loads(captured.stdout)
                    (result_dir / f"container_packages_{container_id[:12]}.json").write_text(
                        json.dumps(observed, indent=2) + "\n")
                    if args.task_id.startswith("rich_"):
                        expected = {"pygments": "2.19.2", "markdown-it-py": "3.0.0",
                                    "mdurl": "0.1.2", "typing-extensions": "4.13.2",
                                    "pytest": "7.4.4", "pytest-cov": "3.0.0"}
                        mismatch = {name: (observed["versions"].get(name), version)
                                    for name, version in expected.items()
                                    if observed["versions"].get(name) != version}
                        if observed["pygments_imported_version"] != expected["pygments"]:
                            mismatch["pygments import"] = (
                                observed["pygments_imported_version"], expected["pygments"])
                        if mismatch:
                            raise RuntimeError(f"Rich image dependency mismatch after setup: {mismatch}")
                    if args.task_id.startswith("fastapi_"):
                        expected = {"starlette": "0.47.3", "pydantic": "2.14.1",
                                    "pytest": "9.1.1", "httpx": "0.28.1"}
                        mismatch = {name: (observed["versions"].get(name), version)
                                    for name, version in expected.items()
                                    if observed["versions"].get(name) != version}
                        if mismatch or observed["fastapi_path"] != "/workspace/fastapi/__init__.py":
                            raise RuntimeError(f"FastAPI image dependency/import mismatch after setup: "
                                               f"{mismatch}, path={observed['fastapi_path']}")
                elif args.task_id.startswith(("rich_", "fastapi_")):
                    raise RuntimeError(f"Package inspection failed: {captured.stderr}")
            return response

        def start(self):
            # No cgroup limits are passed: this rootless daemon cannot enforce
            # them. No host bind mounts or network attachment are requested.
            container = self.client.containers.run(
                self.config.image,
                command="sleep infinity",
                detach=True,
                network_mode="none",
                cap_add=["NET_ADMIN"],
                working_dir="/workspace",
                environment={"TEST_TMPDIR": "/tmp"},
                labels={LABEL_KEY: args.run_id},
            )
            cid = str(container.id)
            with self._lock:
                self._active_containers.add(cid)
            with (result_dir / "container_ids.jsonl").open("a") as records:
                records.write(json.dumps({"id": cid}) + "\n")
            setup = self.exec(cid,
                "ip link set lo up && ip link add test_a type veth peer name test_b "
                "&& ip addr add 10.255.255.2/24 dev test_a "
                "&& ip link set test_a up && ip link set test_b up "
                "&& test -z \"$(ip -4 route show default)\"",
                timeout=10)
            if setup.exit_code != 0:
                self.stop(cid)
                raise RuntimeError(f"Private disconnected veth setup failed: {setup.stderr}")
            if args.mode in ("reference", "agent") and args.task_id.startswith(("rich_", "fastapi_")):
                # This image already installed the complete small-wheel set.
                # The harness's global sp_base.tar cache is not keyed by wheel
                # contents, so extracting it can overwrite the image pins.
                import shlex
                preflight = ("import pygments; assert pygments.__version__ == '2.19.2'; "
                             "assert m.version('pytest-cov') == '3.0.0'; ") if args.task_id.startswith("rich_") else (
                             "import pydantic, starlette; "
                             "assert pydantic.__version__ == '2.14.1'; "
                             "assert starlette.__version__ == '0.47.3'; ")
                code = ("import importlib.metadata as m, pathlib; " + preflight +
                        "pathlib.Path('/usr/local/lib/python3.13/site-packages/"
                        ".swegemma_base_injected').touch()")
                prepared = self.exec(cid, "python3 -c " + shlex.quote(code), timeout=20)
                if prepared.exit_code != 0:
                    raise RuntimeError(f"Image package preflight failed: {prepared.stderr}")
            return cid

    task = next(t for t in load_tasks(DATA / "tasks.jsonl") if t.instance_id == args.task_id)
    if args.mode in ("saved-patch", "output-diagnostic") and args.task_id != "requests_7505":
        raise RuntimeError(f"{args.mode} is Requests-only")
    effective_patch = (task.patch if args.mode == "reference" else
                       PATCH.read_text() if args.mode == "saved-patch" else "")
    if args.mode in ("reference", "saved-patch") and not effective_patch.strip():
        raise RuntimeError("Verification patch is empty")
    snapshot, base_snapshot, snapshot_patch = resolve_task_snapshot_paths(
        DATA / "snapshots", task.instance_id, task.repo
    )
    config = EvalConfig(
        tasks_path=DATA / "tasks.jsonl",
        snapshots_dir=DATA / "snapshots",
        results_dir=result_dir,
        submission_dir=DATA / "sample_submission",
        models=ModelRegistry(),
        image=args.image,
        sandbox="docker",
        wheels_dir=KIT / f"docker-context/{args.task_id.split('_')[0]}/wheels",
        task_ids=[task.instance_id],
        concurrency=1,
    )
    manager = OwnedContainerManager(ContainerConfig(image=args.image, network_mode="none"))
    try:
        if args.mode == "output-diagnostic":
            from swegemma.tools.execution import make_run_command

            cid = manager.start()
            extract_snapshot(manager, cid, snapshot,
                             base_snapshot_path=base_snapshot, patch_path=snapshot_patch)

            class DiagnosticContext:
                docker = manager
                container_id = cid
                harness = SimpleNamespace(command_timeout_seconds=10,
                                          max_stdout_chars=5000)
                budget = SimpleNamespace(time_minutes=None, tool_calls=None)
                tool_calls_used = 0

                def check_budget(self, **_kwargs):
                    return None

            run_command = make_run_command(DiagnosticContext())
            commands = [
                "printf 'LINE1\\nLINE2\\nLINE3\\n'",
                "grep -n '_SupportsRead' src/requests/models.py",
                "ls -1",
            ]
            comparisons = []
            container = manager.client.containers.get(cid)
            for command_text in commands:
                agent_result = run_command(command_text)
                direct = container.exec_run(
                    ["/bin/bash", "-c", "cd /workspace && " + command_text],
                    stdout=True, stderr=True, demux=True,
                )
                direct_stdout, direct_stderr = direct.output
                direct_result = {
                    "stdout": (direct_stdout or b"").decode("utf-8", errors="replace"),
                    "stderr": (direct_stderr or b"").decode("utf-8", errors="replace"),
                    "exit_code": direct.exit_code,
                }
                matched = all(agent_result.get(key) == direct_result[key]
                              for key in ("stdout", "stderr", "exit_code"))
                comparisons.append({"command": command_text,
                                    "agent_path": agent_result,
                                    "docker_exec": direct_result,
                                    "matched": matched})
            passed = all(item["matched"] for item in comparisons)
            passed &= comparisons[0]["agent_path"]["stdout"] == "LINE1\nLINE2\nLINE3\n"
            passed &= comparisons[1]["agent_path"]["stdout"].count("\n") == 4
            (result_dir / "output_comparison.json").write_text(
                json.dumps({"passed": passed, "comparisons": comparisons}, indent=2) + "\n")
            return 0 if passed else 1
        if args.mode == "agent":
            import litellm
            import yaml
            from adk_submission import ModelRegistry
            from google.adk.models.lite_llm import LiteLlm
            from google.adk.agents.context_cache_config import ContextCacheConfig
            from google.adk.apps._configs import EventsCompactionConfig
            from swegemma.config import build_submission_limits
            from swegemma.evaluate import Evaluator

            with urllib.request.urlopen(MODEL_URL + "/models", timeout=10) as response:
                served = json.load(response)
            served_ids = {model["id"] for model in served["data"]}
            expected_ids = {MODEL_ALIAS, "main_lora", "tool_lora"}
            if not expected_ids <= served_ids:
                raise RuntimeError(f"Model server missing: {sorted(expected_ids - served_ids)}")
            (result_dir / "served_models.json").write_text(json.dumps(served, indent=2) + "\n")

            agent_dir = result_dir / "agent_snapshot"
            shutil.copytree(DATA / "sample_submission", agent_dir)
            sampling_path = agent_dir / "configs/sampling.yaml"
            original_sampling_sha256 = sha256(sampling_path)
            if args.seed is not None:
                sampling = yaml.safe_load(sampling_path.read_text())
                if "seed" in sampling:
                    raise RuntimeError("Sample sampling config already sets a seed")
                with sampling_path.open("a") as sampling_file:
                    sampling_file.write(f"\nseed: {args.seed}\n")
            original = yaml.safe_load((agent_dir / "eval_config.yaml").read_text())["evaluation"]
            effective = dict(original)
            effective.update(max_time_minutes=5, max_tool_calls=100)
            model_dir = (KIT / (ROOT / "model-path.txt").read_text().strip()).resolve()
            (result_dir / "effective_settings.json").write_text(json.dumps({
                "original_sample_evaluation": original,
                "local_evaluation": effective,
                "overrides": {"max_time_minutes": [original["max_time_minutes"], 5],
                              "max_tool_calls": [original["max_tool_calls"], 100]},
                "sampling_seed": args.seed,
                "original_sampling_sha256": original_sampling_sha256,
                "effective_sampling_sha256": sha256(sampling_path),
                "agent_sha256": {
                    str(path.relative_to(agent_dir)): sha256(path)
                    for path in agent_dir.rglob("*") if path.is_file()
                },
                "image_id": manager.client.images.get(args.image).id,
                "model_alias": MODEL_ALIAS,
                "model_config_sha256": sha256(model_dir / "config.json"),
                "model_source_sha256": sha256(ROOT / "model-source.json"),
                "packages": {name: metadata.version(name) for name in (
                    "swegemma", "adk-submission", "adk-eval-core", "google-adk",
                    "vllm", "transformers", "torch", "litellm")},
            }, indent=2) + "\n")

            litellm.drop_params = True
            litellm.telemetry = False
            models = ModelRegistry()
            models.register(MODEL_ALIAS, LiteLlm(
                model="openai/" + MODEL_ALIAS, api_base=MODEL_URL,
                api_key="EMPTY", num_retries=5))
            for adapter in ("main_lora", "tool_lora"):
                models.register("adapter:" + adapter, LiteLlm(
                    model="openai/" + adapter, api_base=MODEL_URL,
                    api_key="EMPTY", num_retries=5))
            limits, constraints = build_submission_limits()
            config = EvalConfig(
                tasks_path=DATA / "tasks.jsonl",
                snapshots_dir=DATA / "snapshots",
                results_dir=result_dir,
                submission_dir=agent_dir,
                models=models,
                image=args.image,
                sandbox="docker",
                wheels_dir=KIT / f"docker-context/{args.task_id.split('_')[0]}/wheels",
                graph_dir=str(DATA / "graphs"),
                embeddings_dir=str(DATA / "embeddings"),
                task_ids=[task.instance_id], concurrency=1, display_mode="single",
                timeout_seconds=int(effective["timeout_seconds"]),
                max_time_minutes=5, max_tool_calls=100,
                max_turns=effective.get("max_turns"),
                limits=limits, generation_constraints=constraints,
                context_cache_config=ContextCacheConfig(
                    min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
                events_compaction_config=EventsCompactionConfig(
                    compaction_interval=15, overlap_size=2,
                    token_threshold=14336, event_retention_size=5),
            )
            evaluator = Evaluator(config)
            evaluator.sandbox = manager
            evaluator.docker = manager
            original_runner = evaluator._run_agent_sandbox

            async def capture_agent_phase(*run_args, **run_kwargs):
                # Observe the harness result; the harness still performs every
                # agent call, patch extraction, and verification step itself.
                patch, agent_error, trace = await original_runner(*run_args, **run_kwargs)
                (result_dir / "agent_phase.json").write_text(json.dumps({
                    "agent_error": agent_error,
                    "agent_timeout": bool(agent_error and "timeout" in agent_error.lower()),
                    "patch_bytes": len(patch.encode()),
                    "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
                }, indent=2) + "\n")
                return patch, agent_error, trace

            evaluator._run_agent_sandbox = capture_agent_phase
            evaluation = asyncio.run(evaluator.run())
            if len(evaluation.task_results) != 1:
                raise RuntimeError("Expected exactly one task result")
            result = evaluation.task_results[0]
            trace_path = result_dir / f"traces/trace_{task.instance_id}.json"
            submitted_at = None
            if trace_path.exists():
                trace_data = json.loads(trace_path.read_text())
                for step in trace_data.get("steps", []):
                    for call in step.get("tool_calls", []):
                        if call.get("function_name") == "submit_patch":
                            submitted_at = call.get("extra", {}).get("elapsed_s")
                            break
                    if submitted_at is not None:
                        break
            token_usage = trace_data.get("final_metrics", {}) if trace_path.exists() else {}
            phase_path = result_dir / "agent_phase.json"
            phase = json.loads(phase_path.read_text()) if phase_path.exists() else {}
            (result_dir / "outcome.json").write_text(json.dumps({
                "resolved": result.resolved,
                "test_exit_code": result.test_exit_code,
                "verification_error": result.error,
                "agent_error": phase.get("agent_error"),
                "agent_timeout": phase.get("agent_timeout"),
                "patch_submission_seconds": submitted_at,
                "patch_bytes": phase.get("patch_bytes"),
                "tool_calls": result.tool_calls,
                "total_llm_calls": result.total_llm_calls,
                "token_usage": token_usage,
                "duration_seconds": result.duration_seconds,
            }, indent=2) + "\n")
            return 0 if result.resolved else 1
        if args.mode in ("diagnostic", "timeout-probe"):
            cid = manager.start()
            container = manager.client.containers.get(cid)
            container.reload()
            (result_dir / "container_security.json").write_text(json.dumps({
                "id": cid,
                "privileged": container.attrs["HostConfig"]["Privileged"],
                "network_mode": container.attrs["HostConfig"]["NetworkMode"],
                "mounts": container.attrs.get("Mounts", []),
                "binds": container.attrs["HostConfig"].get("Binds"),
                "cap_add": container.attrs["HostConfig"].get("CapAdd"),
                "labels": container.attrs["Config"].get("Labels", {}),
            }, indent=2) + "\n")
            if args.mode == "timeout-probe":
                manager.exec(cid, "sleep 30", timeout=35)
                return 0
            probes = {}
            for name, command, seconds in [
                ("python", "python3 -V", 5),
                ("network", "ip -br link && ip -4 route", 5),
                ("offline", "python3 -c 'import socket; s=socket.socket(); s.settimeout(1); s.connect((\"1.1.1.1\",443))'", 5),
                ("onlink_timeout", "python3 -c 'import socket; s=socket.socket(); s.settimeout(.5); s.connect((\"10.255.255.1\",80))'", 5),
                ("command_timeout", "sleep 10", 1),
            ]:
                response = manager.exec(cid, command, timeout=seconds)
                probes[name] = {"exit_code": response.exit_code,
                                "status": response.status,
                                "stdout": response.stdout[-500:],
                                "stderr": response.stderr[-500:]}
            setup_container_wheels(manager, cid, config)
            extract_snapshot(manager, cid, snapshot,
                             base_snapshot_path=base_snapshot, patch_path=snapshot_patch)
            install_editable_package(manager, cid)
            install_test_dependencies(manager, cid, task.repo, config=config)
            response = manager.exec(cid,
                "cd /workspace && PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 python3 -s -c 'import requests,pytest,httpbin,pytest_httpbin; print(requests.__file__); print(pytest.__version__); print(httpbin.__file__); print(pytest_httpbin.__file__)'",
                timeout=30)
            probes["imports"] = {"exit_code": response.exit_code,
                                 "stdout": response.stdout, "stderr": response.stderr}
            (result_dir / "diagnostic.json").write_text(json.dumps(probes, indent=2) + "\n")
            return 0 if (probes["python"]["exit_code"] == 0
                         and probes["offline"]["exit_code"] != 0
                         and "TimeoutError" in probes["onlink_timeout"]["stderr"]
                         and probes["command_timeout"]["exit_code"] == 124
                         and probes["imports"]["exit_code"] == 0) else 1
        result = asyncio.run(verify_task(
            manager, config, task, snapshot,
            base_snapshot_path=base_snapshot,
            patch_path=snapshot_patch,
            agent_patch=effective_patch,
            trace=None,
            start_time=time.perf_counter(),
        ))
        (result_dir / "test_outputs").mkdir()
        (result_dir / f"test_outputs/{task.instance_id}.log").write_text(result.test_output)
        summary = {
            "instance_id": task.instance_id,
            "mode": args.mode,
            "resolved": result.resolved,
            "test_exit_code": result.test_exit_code,
            "error": result.error,
            "duration_seconds": result.duration_seconds,
            "patch_sha256": hashlib.sha256(effective_patch.encode()).hexdigest(),
        }
        (result_dir / "result.json").write_text(json.dumps(summary, indent=2) + "\n")
        return 0 if result.resolved else 1
    finally:
        manager.cleanup_all()


def supervise(args, result_dir):
    client = docker.from_env(timeout=10)
    image = client.images.get(args.image)
    result_dir.mkdir(parents=True, exist_ok=False)
    task_record = next(t for t in map(json.loads, (DATA / "tasks.jsonl").open())
                       if t["instance_id"] == args.task_id)
    wheel_dir = KIT / f"docker-context/{args.task_id.split('_')[0]}/wheels"
    manifest = {
        "run_id": args.run_id,
        "mode": args.mode,
        "task_id": args.task_id,
        "image": args.image,
        "image_id": image.id,
        "snapshot_sha256": sha256(DATA / f"snapshots/{args.task_id}.tgz"),
        "tasks_sha256": sha256(DATA / "tasks.jsonl"),
        "reference_patch_sha256": hashlib.sha256(task_record["patch"].encode()).hexdigest(),
        "test_patch_sha256": hashlib.sha256(task_record["test_patch"].encode()).hexdigest(),
        "wheel_sha256": {p.name: sha256(p) for p in sorted(wheel_dir.glob("*.whl"))},
        "dockerfile_sha256": sha256(wheel_dir.parent / "Dockerfile.public"),
        "saved_patch_sha256": sha256(PATCH) if args.mode == "saved-patch" else None,
        "outer_deadline_seconds": args.seconds,
        "network": "none",
        "cgroup_limits_enforced": False,
        "sampling_seed": args.seed,
        "external_server": args.external_server,
    }
    (result_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    command = [sys.executable, str(Path(__file__).resolve()), "--worker",
               "--mode", args.mode, "--label", args.label,
               "--image", args.image, "--seconds", str(args.seconds),
               "--run-id", args.run_id, "--task-id", args.task_id]
    if args.seed is not None:
        command.extend(["--seed", str(args.seed)])
    samples = []
    timed_out = False
    interrupted = False
    process = None
    server = None
    server_create_time = None
    deadline = time.monotonic() + args.seconds
    monitor_started_at = None
    worker_started_at = None
    server_stopped = None
    try:
        if args.mode == "agent" and not args.external_server:
            # Refuse to take ownership of a server started by someone else.
            with socket.socket() as port_check:
                if port_check.connect_ex(("127.0.0.1", 8001)) == 0:
                    raise RuntimeError("Port 8001 is in use; refusing to start another server")
            server_env = os.environ.copy()
            server_env["BASELINE_GPU_FRACTION"] = "0.60"
            server_env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + server_env.get("PATH", "")
            with (result_dir / "vllm.log").open("w") as log:
                server = subprocess.Popen(["bash", str(KIT / "serve.sh")], cwd=KIT,
                                          env=server_env, stdout=log,
                                          stderr=subprocess.STDOUT, start_new_session=True)
            server_create_time = psutil.Process(server.pid).create_time()
            (result_dir / "server_record.json").write_text(json.dumps({
                "pid": server.pid, "create_time": server_create_time,
                "process_group": os.getpgid(server.pid), "script_sha256": sha256(KIT / "serve.sh"),
                "gpu_memory_fraction": "0.60", "max_num_seqs": 1,
            }, indent=2) + "\n")
            while True:
                if server.poll() is not None:
                    raise RuntimeError(f"vLLM exited before readiness: {server.returncode}")
                if time.monotonic() >= deadline:
                    timed_out = True
                    raise TimeoutError("Outer deadline expired during vLLM startup")
                try:
                    with urllib.request.urlopen(MODEL_URL + "/models", timeout=2) as response:
                        if response.status == 200:
                            break
                except Exception:
                    time.sleep(2)
            probe_timeout = max(1, min(390, int(deadline - time.monotonic())))
            with (result_dir / "model_probe.log").open("w") as log:
                subprocess.run([sys.executable, str(KIT / "probe_models.py"),
                                "--output", str(result_dir / "model_probe.json")],
                               cwd=KIT, stdout=log, stderr=subprocess.STDOUT,
                               timeout=probe_timeout, check=True)
        # The worker waits on monitor.ready, so no Evaluator container can
        # start until the supervisor has successfully queried its run label.
        owned_containers(client, args.run_id)
        monitor_started_at = time.time()
        with (result_dir / "worker.log").open("w") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        worker_started_at = time.time()
        (result_dir / "monitor.ready").write_text(str(monitor_started_at) + "\n")
        while process.poll() is None:
            if time.monotonic() >= deadline:
                timed_out = True
                break
            try:
                for container in owned_containers(client, args.run_id):
                    container.reload()
                    pid = container.attrs.get("State", {}).get("Pid", 0)
                    rss = None
                    process_count = None
                    if pid:
                        try:
                            namespace = os.readlink(f"/proc/{pid}/ns/pid")
                            members = []
                            for candidate in psutil.process_iter(["pid"]):
                                try:
                                    if os.readlink(f"/proc/{candidate.pid}/ns/pid") == namespace:
                                        members.append(candidate)
                                except (psutil.Error, OSError):
                                    continue
                            process_count = len(members)
                            rss = sum(p.memory_info().rss for p in members)
                        except (psutil.Error, OSError):
                            pass
                    samples.append({"time": time.time(), "container_id": container.id,
                                    "host_pid": pid, "pid_namespace_processes": process_count,
                                    "observed_pid_namespace_rss_bytes": rss})
            except docker.errors.DockerException:
                pass
            time.sleep(1)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        if process is not None:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        removed = clean_owned(client, args.run_id)
        if server is not None:
            try:
                identity_ok = (psutil.Process(server.pid).create_time() == server_create_time
                               and os.getpgid(server.pid) == server.pid)
            except (psutil.Error, ProcessLookupError):
                identity_ok = False
            if identity_ok:
                os.killpg(server.pid, signal.SIGTERM)
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(server.pid, signal.SIGKILL)
                    server.wait()
                server_stopped = True
            else:
                server_stopped = server.poll() is not None
        (result_dir / "monitor.json").write_text(json.dumps({
            "samples": samples, "cleanup_ids": removed,
            "remaining_owned_ids": [c.id for c in owned_containers(client, args.run_id)],
            "timed_out": timed_out, "interrupted": interrupted,
            "worker_exit_code": process.returncode if process else None,
            "monitor_started_at": monitor_started_at,
            "worker_started_at": worker_started_at,
            "server_pid": server.pid if server else None,
            "server_stopped": server_stopped,
        }, indent=2) + "\n")
    return 124 if timed_out else (130 if interrupted else (process.returncode if process else 1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("diagnostic", "output-diagnostic", "timeout-probe", "reference", "saved-patch", "agent"), required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--image", default="gemma-requests-sandbox:20261015c")
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--run-id")
    published_ids = {json.loads(line)["instance_id"] for line in (DATA / "tasks.jsonl").open()}
    parser.add_argument("--task-id", choices=sorted(published_ids), default="requests_7505")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--external-server", action="store_true")
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if not args.label.isascii() or not args.label.replace("-", "").replace("_", "").isalnum():
        parser.error("label must contain only ASCII letters, digits, hyphens, or underscores")
    if args.seconds < 1 or args.seconds > 1800:
        parser.error("seconds must be between 1 and 1800")
    args.run_id = args.run_id or f"{args.label}-{uuid.uuid4().hex}"
    result_dir = KIT / "results" / f"docker-{args.label}-{args.mode}"
    if args.worker:
        return worker(args, result_dir)
    if result_dir.exists():
        parser.error(f"result directory already exists: {result_dir}")
    return supervise(args, result_dir)


if __name__ == "__main__":
    sys.exit(main())
