#!/usr/bin/env python3
"""Replay recorded SWE-gemma tool calls in owned offline Docker sandboxes.

This re-executes the recorded action sequence; it never sends prompts to a model.
Verification uses the installed swegemma verifier on the host and its normal
task test patch inside a separate offline container. Gold patches are not copied
into replay workspaces.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import random
import shlex
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DEFAULT_OUT = ROOT / "results/found_lost/replay"
LABEL_KEY = "gemma.local.verification.run"


def _offline_env() -> None:
    for key, value in {
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "OTEL_SDK_DISABLED": "true",
        "LITELLM_TELEMETRY": "False",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }.items():
        os.environ[key] = value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, help="Replay one trace")
    parser.add_argument("--source-root", type=Path, default=ROOT / "results",
                        help="Search for unique trace files under this directory")
    parser.add_argument("--limit", type=int, default=0,
                        help="Replay a seeded sample; zero means every discovered trace")
    parser.add_argument("--seed", type=int, default=20261118)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--verify-snapshots", action="store_true",
                        help="Run the official hidden-test verifier on each unique diff")
    parser.add_argument("--max-snapshots", type=int, default=0,
                        help="Optional per-attempt limit for snapshot verifications")
    parser.add_argument("--command-timeout", type=int, default=60)
    parser.add_argument("--run-id", help="Docker ownership label value")
    return parser.parse_args()


def find_attempt_root(trace_path: Path) -> Path:
    for parent in trace_path.resolve().parents:
        if (parent / "agent_phase.json").is_file():
            return parent
    return trace_path.parent


def task_id_from_trace(trace_path: Path, trace: dict) -> str:
    for step in trace.get("steps", []):
        if step.get("source") == "user":
            marker = "You are evaluating a software engineering task for repository "
            msg = step.get("message", "")
            if marker in msg:
                repo_and_id = msg.split(marker, 1)[1].split(".", 1)[0]
                if repo_and_id:
                    # The canonical ID is the trace filename, while task records
                    # remain authoritative if a nonstandard filename is used.
                    break
    return trace_path.stem.removeprefix("trace_")


def parse_observation(step: dict) -> dict | None:
    observation = step.get("observation")
    if not isinstance(observation, dict):
        return None
    content = observation.get("content")
    if not isinstance(content, str):
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def discover_traces(root: Path) -> list[Path]:
    candidates = sorted(root.rglob("trace_*.json"))
    unique: dict[str, Path] = {}
    for path in candidates:
        try:
            digest = sha256_bytes(path.read_bytes())
        except OSError:
            continue
        unique.setdefault(digest, path)
    return sorted(unique.values())


def _image_for(trace_path: Path, task_id: str, task_repo: str) -> tuple[str, str | None]:
    for parent in trace_path.resolve().parents:
        manifest_path = parent / "run_manifest.json"
        if manifest_path.is_file():
            try:
                manifest = read_json(manifest_path)
            except Exception:
                continue
            if manifest.get("task_id") == task_id and manifest.get("image"):
                return str(manifest["image"]), manifest.get("image_id")
    repo = task_repo.split("/", 1)[0]
    image = {
        "fastapi": "gemma-fastapi-sandbox:20261015a",
        "rich": "gemma-rich-sandbox:20261015a",
        "httpx": "gemma-httpx-sandbox:20261015a",
        "requests": "gemma-requests-sandbox:20261015c",
    }.get(repo)
    if not image:
        raise RuntimeError(f"No known local image mapping for {task_id} ({task_repo})")
    return image, None


class ReplayContext:
    def __init__(self, manager, container_id: str, command_timeout: int):
        from types import SimpleNamespace

        self.docker = manager
        self.container_id = container_id
        self.harness = SimpleNamespace(
            command_timeout_seconds=command_timeout,
            max_stdout_chars=5000,
            max_file_lines=150,
            max_file_chars=10000,
        )
        self.budget = SimpleNamespace(tool_calls=None, time_minutes=None)
        self.tool_calls_used = 0
        self.remaining_time_seconds = None
        self.submitted_patch = None
        self.patch_submitted = False

    def check_budget(self, **_kwargs):
        return None


class OwnedContainerManager:
    """Small ContainerManager subclass that labels every container we create."""

    def __init__(self, image: str, run_id: str, timeout: int):
        from swegemma.sandbox.docker import ContainerConfig, ContainerManager

        self.run_id = run_id
        self.label = LABEL_KEY

        class Manager(ContainerManager):
            def start(inner_self):
                container = inner_self.client.containers.run(
                    image,
                    command="sleep infinity",
                    detach=True,
                    network_mode="none",
                    cap_add=["NET_ADMIN"],
                    working_dir="/workspace",
                    environment={"TEST_TMPDIR": "/tmp"},
                    labels={LABEL_KEY: run_id},
                )
                cid = str(container.id)
                inner_self._active_containers.add(cid)
                setup = inner_self.exec(
                    cid,
                    "ip link set lo up && ip link add test_a type veth peer name test_b "
                    "&& ip addr add 10.255.255.2/24 dev test_a "
                    "&& ip link set test_a up && ip link set test_b up "
                    "&& test -z \"$(ip -4 route show default)\"",
                    timeout=10,
                )
                if setup.exit_code != 0:
                    raise RuntimeError(f"offline private-veth setup failed: {setup.stderr}")
                marker = (
                    "python3 -c \"import pathlib; pathlib.Path("
                    "'/usr/local/lib/python3.13/site-packages/.swegemma_base_injected'"
                    ").touch()\""
                )
                marked = inner_self.exec(cid, marker, timeout=10)
                if marked.exit_code != 0:
                    raise RuntimeError(f"image dependency marker failed: {marked.stderr}")
                return cid

        self.manager = Manager(ContainerConfig(
            image=image,
            network_mode="none",
            working_dir="/workspace",
            timeout_seconds=timeout,
            environment={"TEST_TMPDIR": "/tmp"},
        ))
        self.client = self.manager.client

    def cleanup(self) -> list[str]:
        removed = []
        for container in self.client.containers.list(
            all=True, filters={"label": f"{self.label}={self.run_id}"}
        ):
            cid = container.id
            try:
                container.stop(timeout=2)
            except Exception:
                pass
            try:
                container.remove(force=True)
                removed.append(cid)
            except Exception:
                pass
        return removed


def get_diff(manager, container_id: str) -> bytes:
    response = manager.exec(
        container_id,
        "cd /workspace && git add -N . 2>/dev/null || true; "
        "cd /workspace && git diff --binary _swegemma_baseline 2>/dev/null "
        "|| git diff --binary HEAD",
        timeout=30,
    )
    if response.exit_code != 0:
        raise RuntimeError(f"git diff failed: {response.stderr or response.stdout}")
    return response.stdout.encode("utf-8", errors="replace")


def start_replay_workspace(owned, task, config, snapshot: Path) -> str:
    from swegemma.harness.container_setup import (
        extract_snapshot,
        install_editable_package,
        install_test_dependencies,
        setup_baseline_commit,
        setup_container_wheels,
        setup_git_exclude,
        setup_workspace_test_config,
    )

    manager = owned.manager
    cid = manager.start()
    setup_container_wheels(manager, cid, config)
    extract_snapshot(manager, cid, snapshot)
    setup_git_exclude(manager, cid)
    install_editable_package(manager, cid)
    install_test_dependencies(manager, cid, task.repo, config=config)
    setup_workspace_test_config(manager, cid, repo=task.repo)
    setup_baseline_commit(manager, cid, "found_lost_replay_baseline")
    return cid


def tool_map(ctx):
    from swegemma.tools.execution import make_run_command, make_submit_patch
    from swegemma.tools.workspace import make_edit_file, make_read_file, make_write_file

    return {
        "run_command": make_run_command(ctx),
        "read_file": make_read_file(ctx),
        "edit_file": make_edit_file(ctx),
        "write_file": make_write_file(ctx),
        "submit_patch": make_submit_patch(ctx),
    }


def invoke_recorded_call(call: dict, tools: dict) -> tuple[dict, bool]:
    name = call.get("function_name")
    args = call.get("arguments", {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return {"status": "skipped", "reason": "arguments are not valid JSON"}, False
    if not isinstance(args, dict):
        return {"status": "skipped", "reason": "arguments are not an object"}, False
    tool = tools.get(name)
    if tool is None:
        # The graph and status tools are read-only and cannot change the diff.
        return {"status": "skipped", "reason": "not a mutating workspace tool"}, False
    try:
        result = tool(**args)
        if not isinstance(result, dict):
            result = {"status": "ok", "result": str(result)}
    except Exception as exc:
        result = {"status": "replay_exception", "error": f"{type(exc).__name__}: {exc}"}
    return result, name in {"run_command", "edit_file", "write_file"}


def verifier_config(task_id: str, image: str, out_dir: Path):
    from adk_submission import ModelRegistry
    from swegemma.config import EvalConfig

    limits, constraints = __import__("swegemma.config", fromlist=["build_submission_limits"]).build_submission_limits()
    task_prefix = task_id.split("_", 1)[0]
    return EvalConfig(
        tasks_path=DATA / "tasks.jsonl",
        snapshots_dir=DATA / "snapshots",
        results_dir=out_dir,
        submission_dir=ROOT / "submission",
        models=ModelRegistry(),
        image=image,
        sandbox="docker",
        wheels_dir=ROOT / f"baseline-kit/docker-context/{task_prefix}/wheels",
        graph_dir=str(DATA / "graphs"),
        embeddings_dir=str(DATA / "embeddings"),
        timeout_seconds=60,
        max_time_minutes=5,
        max_tool_calls=100,
        max_turns=50,
        task_ids=[task_id],
        limits=limits,
        generation_constraints=constraints,
        concurrency=1,
        display_mode="quiet",
    )


async def verify_diff(owned, config, task, snapshot: Path, patch: str, start_time: float):
    from swegemma.harness.verification import verify_task

    return await verify_task(
        owned.manager,
        config,
        task,
        snapshot,
        agent_patch=patch,
        trace=None,
        start_time=start_time,
    )


def replay_one(trace_path: Path, out_root: Path, args: argparse.Namespace) -> dict:
    _offline_env()
    import docker
    from swegemma.config import EvalConfig
    from swegemma.models import load_tasks

    trace_path = trace_path.resolve()
    trace = read_json(trace_path)
    task_id = task_id_from_trace(trace_path, trace)
    tasks = {t.instance_id: t for t in load_tasks(DATA / "tasks.jsonl")}
    task = tasks.get(task_id)
    if task is None:
        raise RuntimeError(f"trace task ID not present in data/tasks.jsonl: {task_id}")
    snapshot = DATA / "snapshots" / f"{task_id}.tgz"
    if not snapshot.is_file():
        raise RuntimeError(f"task snapshot not found: {snapshot}")
    image, recorded_image_id = _image_for(trace_path, task_id, task.repo)

    attempt_root = find_attempt_root(trace_path)
    phase_path = attempt_root / "agent_phase.json"
    expected = read_json(phase_path) if phase_path.is_file() else {}
    expected_hash = expected.get("patch_sha256")
    if expected_hash is None:
        expected_hash = expected.get("agent_patch_sha256")

    content_hash = sha256_bytes(trace_path.read_bytes())[:12]
    attempt_name = f"{task_id}-{content_hash}"
    out_dir = out_root / attempt_name
    out_dir.mkdir(parents=True, exist_ok=False)
    snap_dir = out_dir / "snapshots"
    snap_dir.mkdir()
    run_id = args.run_id or f"found-lost-{uuid.uuid4().hex}"
    owned = OwnedContainerManager(image, run_id, args.command_timeout)
    started = time.monotonic()
    record = {
        "task_id": task_id,
        "trace_path": str(trace_path),
        "trace_sha256": sha256_bytes(trace_path.read_bytes()),
        "attempt_root": str(attempt_root),
        "recorded_patch_sha256": expected_hash,
        "image": image,
        "recorded_image_id": recorded_image_id,
        "run_id": run_id,
        "container_ids": [],
        "tool_calls_replayed": 0,
        "mutating_calls": 0,
        "skipped_tools": {},
        "snapshots": [],
        "verification": [],
    }
    try:
        config = verifier_config(task_id, image, out_dir)
        cid = start_replay_workspace(owned, task, config, snapshot)
        record["container_ids"].append(cid)
        ctx = ReplayContext(owned.manager, cid, args.command_timeout)
        tools = tool_map(ctx)
        step_index = 0
        verify_hashes: set[str] = set()
        for step in trace.get("steps", []):
            for call_index, call in enumerate(step.get("tool_calls", [])):
                step_index += 1
                result, mutating = invoke_recorded_call(call, tools)
                if call.get("function_name") in tools:
                    record["tool_calls_replayed"] += 1
                else:
                    name = str(call.get("function_name", "unknown"))
                    record["skipped_tools"][name] = record["skipped_tools"].get(name, 0) + 1
                if mutating:
                    record["mutating_calls"] += 1
                    patch_bytes = get_diff(owned.manager, cid)
                    patch_hash = sha256_bytes(patch_bytes)
                    patch_path = snap_dir / f"step-{step_index:04d}-{patch_hash[:12]}.patch"
                    patch_path.write_bytes(patch_bytes)
                    snapshot_record = {
                        "task_id": task_id,
                        "tool_step_id": step.get("step_id"),
                        "call_index": call_index,
                        "tool": call.get("function_name"),
                        "patch_sha256": patch_hash,
                        "patch_path": str(patch_path),
                        "patch_bytes": len(patch_bytes),
                        "tool_result": result,
                    }
                    if args.verify_snapshots and patch_hash not in verify_hashes:
                        verify_hashes.add(patch_hash)
                        if args.max_snapshots and len(verify_hashes) > args.max_snapshots:
                            snapshot_record["verification_status"] = "skipped_max_snapshots"
                        else:
                            verify_out = out_dir / "verification" / patch_hash[:16]
                            verify_out.mkdir(parents=True, exist_ok=True)
                            verify_run_id = f"{run_id}-v-{patch_hash[:8]}"
                            verify_owned = OwnedContainerManager(
                                image, verify_run_id, args.command_timeout
                            )
                            try:
                                verified = asyncio.run(verify_diff(
                                    verify_owned,
                                    verifier_config(task_id, image, verify_out),
                                    task,
                                    snapshot,
                                    patch_bytes.decode("utf-8", errors="replace"),
                                    time.perf_counter(),
                                ))
                                snapshot_record["verification_status"] = "pass" if verified.resolved else "fail"
                                snapshot_record["test_exit_code"] = verified.test_exit_code
                                snapshot_record["test_error"] = verified.error
                                snapshot_record["test_output_path"] = str(verify_out / "snapshot_test_output.txt")
                                (verify_out / "snapshot_test_output.txt").write_text(verified.test_output or "")
                            finally:
                                removed = verify_owned.cleanup()
                                snapshot_record["verification_container_cleanup"] = removed
                                record["container_ids"].extend(removed)
                    elif args.verify_snapshots:
                        snapshot_record["verification_status"] = "deduplicated"
                    record["snapshots"].append(snapshot_record)
                    with (out_dir / "snapshots.jsonl").open("a", encoding="utf-8") as f:
                        f.write(json.dumps(snapshot_record, ensure_ascii=False) + "\n")
                with (out_dir / "replay_calls.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "step_id": step.get("step_id"),
                        "function_name": call.get("function_name"),
                        "arguments": call.get("arguments"),
                        "replay_result": result,
                        "mutating": mutating,
                    }, ensure_ascii=False) + "\n")
        final_bytes = get_diff(owned.manager, cid)
        final_hash = sha256_bytes(final_bytes)
        (out_dir / "final.patch").write_bytes(final_bytes)
        record["replayed_final_patch_sha256"] = final_hash
        record["final_patch_matches_recorded"] = (
            expected_hash is not None and final_hash == expected_hash
        )
        record["elapsed_seconds"] = time.monotonic() - started
        record["verifier_available_cpu"] = True
        return record
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["elapsed_seconds"] = time.monotonic() - started
        return record
    finally:
        record["removed_container_ids"] = owned.cleanup()
        (out_dir / "replay_record.json").write_text(json.dumps(record, indent=2) + "\n")


def main() -> int:
    args = parse_args()
    _offline_env()
    if args.trace:
        traces = [args.trace]
    else:
        traces = discover_traces(args.source_root)
    if args.limit and len(traces) > args.limit:
        traces = random.Random(args.seed).sample(traces, args.limit)
    args.out.mkdir(parents=True, exist_ok=True)
    index_path = args.out / "replay_index.jsonl"
    for trace in traces:
        print(f"REPLAY_START {trace}", flush=True)
        try:
            record = replay_one(trace, args.out, args)
        except Exception as exc:
            record = {"trace_path": str(trace), "error": f"{type(exc).__name__}: {exc}"}
        with index_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(json.dumps({
            "task_id": record.get("task_id"),
            "fidelity": record.get("final_patch_matches_recorded"),
            "snapshots": len(record.get("snapshots", [])),
            "elapsed_seconds": record.get("elapsed_seconds"),
            "error": record.get("error"),
            "cleanup_count": len(record.get("removed_container_ids", [])),
        }), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
