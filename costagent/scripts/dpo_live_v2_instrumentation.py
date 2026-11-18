"""Configured-model telemetry and out-of-budget snapshots for DPO live v2.

Loaded only when COSTAGENT_DPO_LIVE=1. Snapshots use a temporary Git index so
the agent's real index and working tree remain untouched.
"""
from __future__ import annotations

import asyncio
import base64
from functools import wraps
import hashlib
import json
import os
import re
import shlex
import subprocess
import time
import urllib.request
from pathlib import Path


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _usage(response):
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return {"prompt_tokens": None, "completion_tokens": None,
                "reasoning_tokens": None, "usage_present": False}
    def val(*names):
        for name in names:
            x = getattr(usage, name, None)
            if x is not None:
                return int(x)
        return None
    return {"prompt_tokens": val("prompt_token_count"),
            "completion_tokens": val("candidates_token_count", "completion_tokens"),
            "reasoning_tokens": val("thoughts_token_count", "reasoning_tokens"),
            "usage_present": True}


def _server_load(metrics_url: str):
    counts = {"running_requests": None, "waiting_requests": None,
              "metrics_scrape_time": time.time(), "metrics_error": None}
    try:
        with urllib.request.urlopen(metrics_url, timeout=1.5) as r:
            body = r.read().decode("utf-8", "replace")
        for key, patterns in {
            "running_requests": (r"vllm:num_requests_running(?:\{[^}]*\})?\s+([0-9.eE+-]+)",
                                  r"vllm_num_requests_running(?:\{[^}]*\})?\s+([0-9.eE+-]+)"),
            "waiting_requests": (r"vllm:num_requests_waiting(?:\{[^}]*\})?\s+([0-9.eE+-]+)",
                                  r"vllm_num_requests_waiting(?:\{[^}]*\})?\s+([0-9.eE+-]+)"),
        }.items():
            for pattern in patterns:
                m = re.search(pattern, body)
                if m:
                    counts[key] = float(m.group(1))
                    break
    except Exception as e:  # recorded, never allowed to change model behavior
        counts["metrics_error"] = f"{type(e).__name__}: {e}"
    return counts


class LiveRecorder:
    def __init__(self, result_dir: Path, metrics_url="http://127.0.0.1:8001/metrics"):
        self.result_dir = Path(result_dir)
        self.turn_file = self.result_dir / "turn_telemetry.jsonl"
        self.snapshot_dir = self.result_dir / "snapshots"
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_file = self.result_dir / "snapshot_manifest.jsonl"
        self.metrics_url = metrics_url
        self.turn = 0
        self.snapshot = 0
        self.timeout_obj = None
        self.context = None

    def exclude_from_budget(self, elapsed, ctx=None):
        ctx = ctx or self.context
        if ctx is not None and getattr(ctx, "agent_start_time", None) is not None:
            ctx.agent_start_time += elapsed
        if self.timeout_obj is None:
            # The agent_runner module owns the hard 300-second deadline. A
            # missing handle would charge snapshot work against that budget.
            if ctx is not None and getattr(ctx, "agent_start_time", None) is not None:
                _append(self.result_dir / "deadline_guard_violation.jsonl", {
                    "time": time.time(), "error": "hard deadline not captured",
                    "excluded_seconds": elapsed})
                raise RuntimeError("DPO live v2 hard deadline not captured")
            return
        try:
            before = self.timeout_obj.when()
            if before is None:
                raise RuntimeError("hard deadline has no scheduled expiry")
            self.timeout_obj.reschedule(before + elapsed)
            _append(self.result_dir / "deadline_adjustments.jsonl", {
                "time": time.time(), "excluded_seconds": elapsed,
                "deadline_before": before, "deadline_after": self.timeout_obj.when()})
        except (RuntimeError, AttributeError) as e:
            _append(self.result_dir / "deadline_guard_violation.jsonl", {
                "time": time.time(), "error": f"{type(e).__name__}: {e}",
                "excluded_seconds": elapsed})
            raise

    def install_configured_model_hook(self):
        """Instrument the ADK-configured clone, after thinking args are added."""
        import adk_submission.builders.llm as builder
        original = builder.apply_thinking_config_to_model
        recorder = self

        def configured_then_wrapped(model, gen_config):
            configured = original(model, gen_config)
            alias = getattr(configured, "model", "unknown")
            return recorder.wrap_model(configured, alias)

        builder.apply_thinking_config_to_model = configured_then_wrapped
        return lambda: setattr(builder, "apply_thinking_config_to_model", original)

    def wrap_model(self, model, alias):
        original = model.generate_content_async
        recorder = self

        async def wrapped(llm_request, stream=False):
            recorder.turn += 1
            n = recorder.turn
            overhead_started = time.perf_counter()
            load = _server_load(recorder.metrics_url)
            started_wall = time.time()
            started = time.perf_counter()
            last = None
            error = None
            try:
                async for item in original(llm_request, stream=stream):
                    last = item
                    yield item
            except BaseException as e:
                error = f"{type(e).__name__}: {e}"
                raise
            finally:
                ended_wall = time.time()
                row = {"request_index": n, "model_alias": alias,
                       "request_start_time": started_wall,
                       "request_end_time": ended_wall,
                       "generation_wall_seconds": time.perf_counter() - started,
                       **load, **_usage(last), "error": error}
                log_started = time.perf_counter()
                try:
                    _append(recorder.turn_file, row)
                except Exception as e:
                    try:
                        _append(recorder.result_dir / "telemetry_errors.jsonl", {
                            "time": time.time(), "request_index": n,
                            "error": f"{type(e).__name__}: {e}"})
                    except Exception:
                        pass
                log_elapsed = time.perf_counter() - log_started
                recorder.exclude_from_budget((started - overhead_started) + log_elapsed)

        # Called only after the resolver clones and configures the model. The
        # bound method closed over here therefore belongs to that exact clone.
        model.__dict__["generate_content_async"] = wrapped
        return model

    def tool_wrapper(self, ctx, name, fn):
        recorder = self
        recorder.context = ctx

        @wraps(fn)
        def wrapped(*args, **kwargs):
            result = fn(*args, **kwargs)
            if name in {"edit_file", "write_file", "run_command"}:
                snapshot_started = time.perf_counter()
                try:
                    recorder.take_snapshot(ctx, name)
                except Exception as e:
                    try:
                        _append(recorder.snapshot_file, {"sequence": recorder.snapshot + 1,
                                "tool": name, "time": time.time(),
                                "status": "snapshot_error",
                                "error": f"{type(e).__name__}: {e}"})
                    except Exception:
                        pass
                finally:
                    recorder.exclude_from_budget(time.perf_counter() - snapshot_started, ctx)
            return result
        wrapped.__name__ = name
        wrapped.__doc__ = getattr(fn, "__doc__", None)
        return wrapped

    def take_snapshot(self, ctx, tool_name):
        self.snapshot += 1
        seq = self.snapshot
        started = time.perf_counter()
        # A private index avoids changing the index observed by the agent.
        code = r'''import base64, os, subprocess, tempfile
root='/workspace'
fd,index=tempfile.mkstemp(prefix='dpo-live-index-',dir='/tmp'); os.close(fd); os.unlink(index)
env=os.environ.copy(); env['GIT_INDEX_FILE']=index
def run(args, check=True):
 p=subprocess.run(['git',*args],cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if check and p.returncode: raise RuntimeError(p.stderr.decode('utf-8','replace'))
 return p
try:
 run(['read-tree','HEAD'])
 run(['add','-N','.'])
 d=run(['diff','--binary','_swegemma_baseline','--'],check=False)
 if d.returncode not in (0,): d=run(['diff','--binary','HEAD','--'])
 sysbytes=d.stdout
 print(base64.b64encode(sysbytes).decode('ascii'))
finally:
 try: os.unlink(index)
 except FileNotFoundError: pass
'''
        # sys is deliberately injected through the command's Python prelude.
        cmd = "cd /workspace && python3 -c " + shlex.quote("import sys; " + code)
        response = ctx.docker.exec(ctx.container_id, cmd, timeout=45)
        elapsed = time.perf_counter() - started
        if response.exit_code != 0:
            _append(self.snapshot_file, {"sequence": seq, "tool": tool_name,
                    "time": time.time(), "duration_seconds": elapsed,
                    "tool_calls_used": getattr(ctx, "tool_calls_used", None),
                    "status": "snapshot_error", "stderr": response.stderr,
                    "exit_code": response.exit_code})
            return
        try:
            patch = base64.b64decode(response.stdout.strip(), validate=True)
        except Exception as e:
            _append(self.snapshot_file, {"sequence": seq, "tool": tool_name,
                    "time": time.time(), "duration_seconds": elapsed,
                    "tool_calls_used": getattr(ctx, "tool_calls_used", None),
                    "status": "snapshot_decode_error", "error": str(e)})
            return
        target = self.snapshot_dir / f"snapshot_{seq:04d}.patch"
        target.write_bytes(patch)
        elapsed = time.perf_counter() - started
        _append(self.snapshot_file, {"sequence": seq, "tool": tool_name,
                "time": time.time(), "duration_seconds": elapsed,
                "tool_calls_used": getattr(ctx, "tool_calls_used", None),
                "status": "ok", "patch_path": str(target),
                "patch_sha256": hashlib.sha256(patch).hexdigest(),
                "patch_bytes": len(patch)})

    def patch_timeout_context(self, agent_runner_module):
        """Keep snapshots outside the harness's five-minute asyncio deadline."""
        recorder = self
        original_module = agent_runner_module.asyncio
        class Proxy:
            def __getattr__(self, name):
                return getattr(original_module, name)
            def timeout(self, delay):
                obj = original_module.timeout(delay)
                if delay == 300:
                    recorder.timeout_obj = obj
                return obj
        agent_runner_module.asyncio = Proxy()
        return lambda: setattr(agent_runner_module, "asyncio", original_module)

