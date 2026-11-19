#!/usr/bin/env python3
"""Resumable, sequential fresh-A0 vs DPO confirmatory v2 run."""
from __future__ import annotations

import csv
import argparse
import datetime
import fcntl
import hashlib
import json
import os
import random
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "costagent"
BASELINE = ROOT / "baseline-kit"
OUT = ROOT / "results/dpo_live_v2"
PYTHON = "/home/mahesh/miniconda3/envs/gemma-harness/bin/python"
URL = "http://127.0.0.1:8001/v1"
DPO = PKG / "artifacts/mixed-temperature-v1/dpo/epoch-005"
WANT_WEIGHT = "0c5fe9518135b51ee846bad843a356f2026c99d5793082c93b8bba90e1a498a1"
WANT_CONFIG = "2d24af75f2f30c2207966e7dedef68b18eccc20203c68a8907fe351883cebde8"
WANT_ZIP = "8520c647932ce0d483202739ef3ce270583cf221312b17078917b395f1a0e148"
ORIGINAL_PREREG_SHA256 = "f06aadea2b0e39c6cc8cc1f3a275375362994a22d4b599343ae62e8a535fa85b"
FIXED_STOP_UTC = datetime(2026, 11, 20, 8, 30, tzinfo=timezone.utc).timestamp()
STOP = False
TOKENIZER = None

sys.path.insert(0, str(BASELINE))
sys.path.insert(0, str(PKG))
from run_docker_agent_all import gpu_free_mib, resource_concern, stop_server
from costagent.eval_status import interpret_outcome


class AttachedOwnedServer:
    """Popen-like handle for a previously launched, identity-checked server."""
    def __init__(self, pid):
        self.pid = int(pid)

    def poll(self):
        return None if psutil.pid_exists(self.pid) else 0

    def wait(self, timeout=None):
        return psutil.Process(self.pid).wait(timeout=timeout)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n")
    os.replace(tmp, path)


def event(name, **fields):
    row = {"time": time.time(), "event": name, **fields}
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "progress.jsonl").open("a") as f:
        f.write(json.dumps(row) + "\n")
        f.flush()
        os.fsync(f.fileno())
    print(json.dumps(row), flush=True)


def on_signal(*_):
    global STOP
    STOP = True


def adapter_identity():
    provenance = json.loads((ROOT / "submissions/dpo-20261108-provenance.json").read_text())
    archive = ROOT / "submission.zip"
    if provenance["archive_sha256"] != WANT_ZIP or sha(archive) != WANT_ZIP:
        raise RuntimeError("DPO submission archive SHA-256 mismatch")
    with zipfile.ZipFile(archive) as zf:
        blob = zf.read("adapters/main_lora/adapter_model.safetensors")
        cfg = zf.read("adapters/main_lora/adapter_config.json")
    if hashlib.sha256(blob).hexdigest() != WANT_WEIGHT:
        raise RuntimeError("DPO archive weight hash mismatch")
    if hashlib.sha256(cfg).hexdigest() != WANT_CONFIG:
        raise RuntimeError("DPO archive config hash mismatch")
    if sha(DPO / "adapter_model.safetensors") != WANT_WEIGHT:
        raise RuntimeError("DPO checkpoint weight hash mismatch")
    if sha(DPO / "adapter_config.json") != WANT_CONFIG:
        raise RuntimeError("DPO checkpoint config hash mismatch")
    return {"path": str(DPO.resolve()), "weight_sha256": WANT_WEIGHT,
            "config_sha256": WANT_CONFIG, "archive": str(archive),
            "archive_sha256": WANT_ZIP,
            "pilot_served_path": "/tmp/costagent-pipeline-20261102/artifacts/mixed-temperature-v1/dpo/epoch-005"}


def frozen_schedule():
    plan = json.loads((ROOT / "prereg/frozen.json").read_text())
    tasks = list(plan["tasks"])
    if len(tasks) != 84 or len(set(tasks)) != 84:
        raise RuntimeError(f"Frozen task list invalid: {len(tasks)} IDs")
    rng = random.Random(20261119)
    rng.shuffle(tasks)
    order = []
    for tid in tasks:
        arms = ["A0", "DPO"] if rng.getrandbits(1) == 0 else ["DPO", "A0"]
        order.append({"task_id": tid, "arms": arms})
    return plan, order


def save_csv():
    rows = []
    turn_rows = []
    snapshot_rows = []
    for marker in sorted((OUT / "attempts").glob("*/**/done.json")):
        try:
            attempt = json.loads(marker.read_text())
            rows.append(attempt)
            result_dir = Path(attempt["result_dir"])
            for field, target in (("turn_telemetry.jsonl", turn_rows),
                                  ("snapshot_manifest.jsonl", snapshot_rows)):
                source = result_dir / field
                if source.exists():
                    for line in source.read_text().splitlines():
                        if line:
                            target.append({"task_id": attempt["task_id"],
                                           "arm": attempt["arm"],
                                           "smoke": attempt.get("smoke"),
                                           **json.loads(line)})
        except Exception:
            continue
    path = OUT / "per_attempt.csv"
    fields = ["task_id", "arm", "smoke", "resolved", "verification_status",
              "agent_timeout", "patch_bytes", "tool_calls", "total_llm_calls",
              "prompt_tokens", "completion_tokens", "cleanup_ok", "result_dir"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows({k: row.get(k) for k in fields} for row in rows)
    for filename, records in (("per_turn.csv", turn_rows),
                              ("per_snapshot.csv", snapshot_rows)):
        cols = sorted({key for row in records for key in row})
        with (OUT / filename).open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols or ["task_id", "arm"])
            w.writeheader()
            w.writerows(records)


def summarize_attempt(tid, arm, path, smoke):
    outcome_path = path / "outcome.json"
    monitor_path = path / "monitor.json"
    if not outcome_path.exists() or not monitor_path.exists():
        raise RuntimeError(f"No terminal outcome/monitor for {tid}/{arm}: {path}")
    outcome = json.loads(outcome_path.read_text())
    monitor = json.loads(monitor_path.read_text())
    if arm == "DPO":
        actual = json.loads((path / "dpo_adapter_identity.json").read_text())
        if (actual.get("adapter_model_sha256") != WANT_WEIGHT or
                actual.get("adapter_config_sha256") != WANT_CONFIG or
                Path(actual.get("path", "")).resolve() != DPO.resolve()):
            raise RuntimeError(f"Per-attempt DPO identity drift: {actual}")
    resolved, verification_status = interpret_outcome(
        outcome, monitor, monitor.get("worker_exit_code"))
    telemetry = []
    turn_path = path / "turn_telemetry.jsonl"
    if turn_path.exists():
        telemetry = [json.loads(x) for x in turn_path.read_text().splitlines() if x]
    cleanup_ok = not monitor.get("remaining_owned_ids")
    if not cleanup_ok:
        raise RuntimeError(f"Container cleanup failed for {tid}/{arm}")
    final = {
        "task_id": tid, "arm": arm, "smoke": smoke,
        "resolved": resolved,
        "verification_status": verification_status,
        "agent_timeout": outcome.get("agent_timeout"),
        "patch_bytes": outcome.get("patch_bytes"),
        "tool_calls": outcome.get("tool_calls"),
        "total_llm_calls": outcome.get("total_llm_calls"),
        "prompt_tokens": sum(x.get("prompt_tokens") or 0 for x in telemetry),
        "completion_tokens": sum(x.get("completion_tokens") or 0 for x in telemetry),
        "turns_with_missing_usage": sum(not x.get("usage_present") for x in telemetry),
        "turns_with_missing_reasoning": sum(x.get("reasoning_tokens") is None for x in telemetry),
        "cleanup_ok": cleanup_ok, "result_dir": str(path),
        "outer_timed_out": monitor.get("timed_out"),
        "monitor": str(monitor_path),
    }
    return final


def finalize_reasoning_tokens(path):
    """Use raw vLLM reasoning spans when usage lacks a reasoning-token count."""
    global TOKENIZER
    import transformers
    model_path = (ROOT / "gemma-4-31b-it-qat-w4a16-ct").resolve()
    if TOKENIZER is None:
        TOKENIZER = transformers.AutoTokenizer.from_pretrained(
            model_path, local_files_only=True, trust_remote_code=True)
    turn_path = path / "turn_telemetry.jsonl"
    http_path = path / "http_request_telemetry.jsonl"
    if http_path.exists():
        # HTTP capture sees calls made by sub-agents too; LiteLLM wrapper rows
        # alone omit those calls. Use one row per actual request, including
        # transport failures, rather than assuming the two counters coincide.
        rows = [json.loads(x) for x in http_path.read_text().splitlines() if x]
        rows.sort(key=lambda row: row.get("request_index", 0))
        for row in rows:
            reasoning = row.pop("reasoning_text", None)
            if row.get("reasoning_tokens") is None:
                if row.get("usage_present"):
                    row["reasoning_tokens"] = len(TOKENIZER.encode(
                        reasoning or "", add_special_tokens=False))
                    row["reasoning_tokens_source"] = (
                        "gemma_tokenizer_raw_reasoning_span" if reasoning
                        else "no_reasoning_span")
                else:
                    row["reasoning_tokens_source"] = "unavailable_no_response_usage"
            else:
                row["reasoning_tokens_source"] = "vllm_usage"
            row["raw_response_file"] = row.get("response_file")
    else:
        # Backward-compatible recovery for attempts made before HTTP-level
        # telemetry was added. Missing root-model rows are kept explicit below.
        rows = [json.loads(x) for x in turn_path.read_text().splitlines() if x]
        responses = []
        for f in sorted(path.glob("model_response_*.bin")):
            try:
                obj = json.loads(f.read_bytes())
                choice = obj.get("choices", [{}])[0]
                message = choice.get("message", {})
                reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
                usage = obj.get("usage") or {}
                details = usage.get("completion_tokens_details") or {}
                responses.append((f.name, reasoning, usage, details))
            except Exception:
                responses.append((f.name, None, {}, {}))
        for row, (filename, reasoning, usage, details) in zip(rows, responses):
            row["raw_response_file"] = filename
            if usage.get("prompt_tokens") is not None:
                row["prompt_tokens"] = int(usage["prompt_tokens"])
            if usage.get("completion_tokens") is not None:
                row["completion_tokens"] = int(usage["completion_tokens"])
            if details.get("reasoning_tokens") is not None:
                row["reasoning_tokens"] = int(details["reasoning_tokens"])
                row["reasoning_tokens_source"] = "vllm_usage"
            if row.get("reasoning_tokens") is None and reasoning is not None:
                row["reasoning_tokens"] = len(TOKENIZER.encode(reasoning, add_special_tokens=False))
                row["reasoning_tokens_source"] = "gemma_tokenizer_raw_reasoning_span" if reasoning else "no_reasoning_span"
            elif row.get("reasoning_tokens") is None:
                row["reasoning_tokens_source"] = "unavailable_no_response_usage"
        if len(rows) < len(responses):
            for idx, (filename, reasoning, usage, details) in enumerate(
                    responses[len(rows):], start=len(rows) + 1):
                reasoning_tokens = details.get("reasoning_tokens")
                source = "vllm_usage"
                if reasoning_tokens is None and reasoning is not None:
                    reasoning_tokens = len(TOKENIZER.encode(reasoning, add_special_tokens=False))
                    source = "gemma_tokenizer_raw_reasoning_span" if reasoning else "no_reasoning_span"
                rows.append({"request_index": idx, "model_alias": None,
                             "prompt_tokens": usage.get("prompt_tokens"),
                             "completion_tokens": usage.get("completion_tokens"),
                             "reasoning_tokens": reasoning_tokens,
                             "reasoning_tokens_source": source,
                             "usage_present": bool(usage),
                             "generation_wall_seconds": None,
                             "running_requests": None, "waiting_requests": None,
                             "action_type": "model_only",
                             "tool_call_count": 0, "tool_execution_seconds": 0.0,
                             "observation_chars": 0, "repeats_previous_call": False,
                             "repeated_tool_calls": 0,
                             "trace_mapping_status": "recovered_http_only",
                             "raw_response_file": filename})
    trace_path = next(iter((path / "traces").glob("trace_*.json")), None)
    if trace_path is None:
        raise RuntimeError("Trace missing; cannot map turn telemetry to actions")
    trace = json.loads(trace_path.read_text())
    agent_steps = [s for s in trace.get("steps", []) if s.get("source") == "agent"]
    steps_by_usage = {}
    for step in agent_steps:
        calls = step.get("tool_calls") or []
        if not calls:
            continue
        usage = ((calls[0].get("extra") or {}).get("usage") or {}) if calls else {}
        key = (usage.get("prompt_tokens"), usage.get("completion_tokens"))
        steps_by_usage.setdefault(key, []).append(step)
    previous_call = None
    for row in rows:
        key = (row.get("prompt_tokens"), row.get("completion_tokens"))
        matches = steps_by_usage.get(key) or []
        step = matches.pop(0) if matches else None
        if step is None:
            row.update({"trace_step_id": None, "action_type": "model_only",
                        "tool_call_count": 0, "tool_execution_seconds": 0.0,
                        "observation_chars": 0, "repeats_previous_call": False,
                        "repeated_tool_calls": 0,
                        "trace_mapping_status": "model_only_no_tool_step"})
            continue
        calls = step.get("tool_calls") or []
        action_types = []
        tool_seconds = 0.0
        repeat_count = 0
        for call in calls:
            name = call.get("function_name", "")
            try:
                args = call.get("arguments") or {}
                canonical = json.dumps(args, sort_keys=True, separators=(",", ":"))
            except TypeError:
                canonical = str(call.get("arguments"))
            signature = (name, canonical)
            repeated = signature == previous_call
            repeat_count += int(repeated)
            previous_call = signature
            elapsed = (call.get("extra") or {}).get("elapsed_s")
            if isinstance(elapsed, (int, float)):
                tool_seconds += float(elapsed)
            if name in {"edit_file", "write_file"}:
                action = "edit"
            elif name in {"get_code_neighbors", "search_similar_code", "get_code_subgraph"}:
                action = "graph"
            elif name == "submit_patch":
                action = "submit"
            elif name == "get_status":
                action = "status"
            elif name == "read_file":
                action = "read"
            elif name == "run_command":
                command = str((call.get("arguments") or {}).get("command", "")).strip().lower()
                import re
                if re.search(r"(^|[;&| ])pytest(?:\s|$)|python(?:3)?\s+-m\s+(pytest|unittest)|tox(?:\s|$)|unittest discover", command) or re.search(r"python(?:3)?\s+[^ ]*tests/", command):
                    action = "test"
                elif re.search(r"(^|[;&| ])(rg|grep|find|ls)(?:\s|$)", command):
                    action = "search"
                elif re.search(r"(^|[;&| ])(cat|sed|head|tail|nl)(?:\s|$)", command):
                    action = "read"
                else:
                    action = "shell"
            else:
                action = "other"
            action_types.append(action)
        observation = step.get("observation")
        observation_text = (observation if isinstance(observation, str) else
                            json.dumps(observation, ensure_ascii=False, sort_keys=True)
                            if observation is not None else "")
        row.update({"trace_step_id": step.get("step_id"),
                    "action_type": "+".join(action_types) if action_types else "response",
                    "tool_call_count": len(calls), "tool_execution_seconds": tool_seconds,
                    "observation_chars": len(observation_text),
                    "repeats_previous_call": repeat_count > 0,
                    "repeated_tool_calls": repeat_count,
                    "trace_mapping_status": "matched"})
    remaining = sum(len(items) for items in steps_by_usage.values())
    atomic(path / "trace_mapping_audit.json", {
        "telemetry_rows": len(rows), "unmatched_trace_tool_steps": remaining,
        "unmatched_step_ids": [step.get("step_id") for items in steps_by_usage.values()
                               for step in items],
        "source": "http_request_telemetry" if http_path.exists()
                  else "legacy_model_wrapper_and_response_files"})
    turn_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def validate_smokes():
    expected = 4
    found = []
    for marker in sorted((OUT / "attempts").glob("smoke-*/**/done.json")):
        row = json.loads(marker.read_text())
        found.append(row)
    if len(found) != expected:
        raise RuntimeError(f"Expected {expected} smoke attempts, found {len(found)}")
    first_completion = []
    termination_counts = {"wall_clock": 0, "turn_cap": 0, "explicit_submit": 0, "other": 0}
    request_counts = []
    cancelled_without_usage = 0
    for row in found:
        path = Path(row["result_dir"])
        requests = [json.loads(x)["body"] for x in
                    (path / "model_requests.jsonl").read_text().splitlines() if x]
        if not requests:
            raise RuntimeError(f"Smoke has no model requests: {row['task_id']}/{row['arm']}")
        for request in requests:
            if ((request.get("chat_template_kwargs") or {}).get("enable_thinking") is not True
                    or request.get("thinking_token_budget") != 4096):
                raise RuntimeError(f"Smoke request missing thinking config: {row['task_id']}/{row['arm']}")
        request_counts.append(len(requests))
        response = json.loads((path / "model_response_0001.bin").read_bytes())
        first_completion.append(int(response["usage"]["completion_tokens"]))
        outcome = json.loads((path / "outcome.json").read_text())
        error = outcome.get("agent_error") or ""
        reason = ("wall_clock" if "session timeout" in error else
                  "turn_cap" if "turns budget" in error else
                  "explicit_submit" if outcome.get("patch_submission_seconds") is not None else
                  "other")
        termination_counts[reason] += 1
        for t in [json.loads(x) for x in (path / "turn_telemetry.jsonl").read_text().splitlines() if x]:
            cancelled_at_deadline = (bool(outcome.get("agent_timeout"))
                                     and str(t.get("error") or "").startswith("CancelledError")
                                     and t.get("response_file") is None
                                     and t.get("response_status") is None)
            if not t.get("usage_present"):
                if not cancelled_at_deadline:
                    raise RuntimeError(f"Smoke has missing usage on a non-cancelled request: {row['task_id']}/{row['arm']}: {t}")
                cancelled_without_usage += 1
            required = ["generation_wall_seconds", "running_requests", "waiting_requests",
                        "action_type", "tool_execution_seconds", "observation_chars",
                        "repeats_previous_call", "trace_mapping_status"]
            if not cancelled_at_deadline:
                required.extend(["prompt_tokens", "completion_tokens", "reasoning_tokens"])
            if any(t.get(k) is None for k in required):
                raise RuntimeError(f"Smoke telemetry missing fields: {row['task_id']}/{row['arm']}: {t}")
        check = path / "snapshot_patch_check.json"
        if not check.exists() or not json.loads(check.read_text()).get("last_snapshot_matches_extracted_patch"):
            raise RuntimeError(f"Smoke final snapshot differs from patch: {row['task_id']}/{row['arm']}")
        if (path / "runtime_guard_violation.jsonl").exists() or (path / "deadline_guard_violation.jsonl").exists():
            raise RuntimeError(f"Smoke guard violation: {row['task_id']}/{row['arm']}")
    import statistics
    median_first = statistics.median(first_completion)
    if median_first < 80:
        raise RuntimeError(f"Smoke first-response completion median {median_first} resembles thinking-off runs")
    if termination_counts["turn_cap"] > termination_counts["wall_clock"]:
        raise RuntimeError(f"Smoke remains turn-cap dominated: {termination_counts}")
    atomic(OUT / "smoke_validation.json", {"passed": True, "attempts": expected,
           "at": time.time(), "smoke_ids": ["fastapi_14246", "rich_4070"],
           "first_response_completion_tokens": first_completion,
           "first_response_completion_median": median_first,
           "termination_counts": termination_counts,
           "model_request_counts": request_counts,
           "cancelled_deadline_requests_without_usage": cancelled_without_usage,
           "thinking_on_for_every_request": True,
           "final_snapshot_matches_patch_for_every_smoke": True})


def run_attempt(server, tid, arm, smoke=False):
    verifier_failure = OUT / "snapshot_verifier_failure.json"
    if verifier_failure.exists():
        raise RuntimeError(f"CPU snapshot verifier failed: {verifier_failure.read_text()}")
    name = f"smoke-v2-retry1-{tid}" if smoke else tid
    path = OUT / "attempts" / name / arm
    done = path / "done.json"
    if done.exists():
        row = json.loads(done.read_text())
        if not row.get("cleanup_ok"):
            raise RuntimeError(f"Saved attempt has cleanup failure: {done}")
        return row
    if path.exists():
        outcome_path = path / "evaluation/outcome.json"
        monitor_path = path / "evaluation/monitor.json"
        if not smoke and outcome_path.is_file() and monitor_path.is_file():
            monitor = json.loads(monitor_path.read_text())
            if monitor.get("remaining_owned_ids"):
                raise RuntimeError(f"Terminal attempt has owned containers remaining: {path}")
            guard_note = None
            guard_path = path / "evaluation/deadline_guard_violation.jsonl"
            if guard_path.exists():
                violations = [json.loads(line) for line in guard_path.read_text().splitlines() if line]
                outcome = json.loads(outcome_path.read_text())
                known_post_completion = (violations and all(
                    v.get("error") == "RuntimeError: Cannot change state of finished Timeout"
                    for v in violations))
                if not (known_post_completion and outcome.get("patch_submission_seconds") is not None
                        and not outcome.get("agent_error")):
                    raise RuntimeError(f"Unresolved deadline guard violation: {guard_path}")
                requests = [json.loads(line)["body"] for line in
                            (path / "evaluation/model_requests.jsonl").read_text().splitlines() if line]
                if not requests or any(
                        (body.get("chat_template_kwargs") or {}).get("enable_thinking") is not True
                        or body.get("thinking_token_budget") != 4096 for body in requests):
                    raise RuntimeError(f"Thinking guard failed during recovery: {path}")
                guard_note = "telemetry attempted reschedule after successful agent timeout context exit"
                event("recovered_finished_timeout_guard", task_id=tid, arm=arm,
                      guard_path=str(guard_path), violations=len(violations))
            if (path / "evaluation/runtime_guard_violation.jsonl").exists():
                raise RuntimeError(f"Model request guard violation: {path}")
            # The prior controller stopped during post-processing, after the
            # harness wrote a terminal outcome and cleaned its container. Recover
            # that record; never spend another model run on this task/arm.
            result_dir = path / "evaluation"
            finalize_reasoning_tokens(result_dir)
            row = summarize_attempt(tid, arm, result_dir, smoke=False)
            row.update({"runner_returncode": monitor.get("worker_exit_code"),
                        "sampling_seed": 42, "outer_deadline_seconds": 900,
                        "elapsed_controller_seconds": None,
                        "recovered_terminal_record": True,
                        "telemetry_source_anomaly": "recovered after controller post-processing failure"})
            if guard_note:
                row["deadline_guard_false_positive"] = guard_note
                row["original_guard_record"] = str(guard_path)
            atomic(done, row)
            event("attempt_recovered_terminal", **row)
            save_csv()
            return row
        # Replacement is allowed only for a crash with no terminal record.
        # Keep the entire partial slot as evidence and ensure neither its worker
        # nor any of its labeled containers remains before starting a fresh one.
        if not smoke and not outcome_path.exists() and not monitor_path.exists():
            if any((path / "evaluation" / guard).exists() for guard in
                   ("runtime_guard_violation.jsonl", "deadline_guard_violation.jsonl")):
                raise RuntimeError(f"Guard violation in incomplete slot: {path}")
            owner_path = path / "ownership.json"
            if not owner_path.exists():
                raise RuntimeError(f"Incomplete slot lacks worker ownership: {path}")
            owner = json.loads(owner_path.read_text())
            try:
                worker = psutil.Process(int(owner["pid"]))
                if abs(worker.create_time() - float(owner["create_time"])) < 0.02 and worker.is_running():
                    raise RuntimeError(f"Owned worker still running: {owner['pid']}")
            except psutil.NoSuchProcess:
                pass
            import docker
            client = docker.from_env()
            label_prefix = f"dpolivev2-{tid}-{arm}".replace("_", "-") + "-"
            owned = [c.id for c in client.containers.list(
                all=True, filters={"label": "gemma.local.verification.run"})
                if c.labels.get("gemma.local.verification.run", "").startswith(label_prefix)]
            if owned:
                raise RuntimeError(f"Interrupted slot still owns containers: {owned}")
            archive = (OUT / "interrupted_attempts" / tid / arm /
                       datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
            archive.parent.mkdir(parents=True, exist_ok=True)
            path.rename(archive)
            event("replacement_after_crash_no_terminal", task_id=tid, arm=arm,
                  preserved_partial=str(archive))
        else:
            raise RuntimeError(f"Incomplete attempt slot preserved; inspect before resume: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir()
    result_dir = path / "evaluation"
    env = os.environ.copy()
    for name in ("COSTAGENT_ROUTER", "COSTAGENT_METHOD_ROUTER",
                 "COSTAGENT_ROUTER_SOURCE", "COSTAGENT_PHASE_ROUTER"):
        env.pop(name, None)
    env.update({"COSTAGENT_RESULT": str(result_dir),
                "COSTAGENT_SUBMISSION": str(ROOT / "data/sample_submission"),
                "COSTAGENT_DPO_LIVE_V2": "1", "COSTAGENT_DPO_LIVE_V2_ARM": arm,
                "COSTAGENT_TEMPERATURE": "0.2", "PYTHONUNBUFFERED": "1"})
    label = f"dpolivev2-{('smoke-' if smoke else '')}{tid}-{arm}".replace("_", "-")
    task = next(json.loads(x) for x in (ROOT / "data/tasks.jsonl").read_text().splitlines()
                if json.loads(x)["instance_id"] == tid)
    image = {"fastapi/fastapi": "gemma-fastapi-sandbox:20261015a",
             "Textualize/rich": "gemma-rich-sandbox:20261015a",
             "psf/requests": "gemma-requests-sandbox:20261015c",
             "encode/httpx": "gemma-httpx-sandbox:20261015a"}[task["repo"]]
    command = [PYTHON, str(PKG / "scripts/docker_eval_worker.py"), "--mode", "agent",
               "--label", label, "--task-id", tid, "--image", image,
               "--seconds", "900", "--seed", "42", "--external-server"]
    event("attempt_started", task_id=tid, arm=arm, smoke=smoke, image=image)
    started_at = time.time()
    log_file = (path / "controller.log").open("w")
    proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log_file,
                            stderr=subprocess.STDOUT, start_new_session=True)
    atomic(path / "ownership.json", {"pid": proc.pid,
           "create_time": psutil.Process(proc.pid).create_time(),
           "process_group": proc.pid, "task_id": tid, "arm": arm,
           "started_at": started_at})
    deadline = time.monotonic() + 960
    last_live = 0
    last_resource_check = 0
    try:
        while proc.poll() is None:
            if verifier_failure.exists():
                raise RuntimeError(f"CPU snapshot verifier failed: {verifier_failure.read_text()}")
            if STOP or time.monotonic() > deadline:
                try:
                    os.killpg(proc.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    raise RuntimeError("Owned runner did not exit cleanly after SIGINT")
                break
            if time.time() - last_live > 60:
                responses = len(list(result_dir.glob("model_response_*.bin")))
                trace_path = result_dir / f"traces/trace_{tid}.json"
                calls = None
                latest_action = "agent running; latest saved trace state"
                if trace_path.exists():
                    try:
                        trace = json.loads(trace_path.read_text())
                        calls = sum(len(s.get("tool_calls", [])) for s in trace.get("steps", []))
                        for step in reversed(trace.get("steps", [])):
                            if step.get("tool_calls"):
                                call = step["tool_calls"][-1]
                                latest_action = f"{call.get('function_name')}: {str(call.get('arguments'))[:180]}"
                                break
                    except (ValueError, OSError):
                        pass
                event("attempt_live", task_id=tid, arm=arm,
                      elapsed_seconds=int(time.time() - started_at),
                      llm_calls=responses, tool_calls=calls,
                      latest_action=latest_action,
                      disk_free_bytes=__import__("shutil").disk_usage(ROOT).free)
                last_live = time.time()
            if time.time() - last_resource_check >= 30:
                concern = resource_concern()
                if concern:
                    raise RuntimeError(f"Resource guard: {concern}")
                last_resource_check = time.time()
            time.sleep(2)
    except BaseException:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                raise RuntimeError("Owned runner cleanup timed out after interruption")
        raise
    finally:
        log_file.close()
    rc = proc.wait()
    for guard_name in ("runtime_guard_violation.jsonl", "deadline_guard_violation.jsonl"):
        if (result_dir / guard_name).exists():
            raise RuntimeError(f"Fatal v2 guard violation in {result_dir / guard_name}")
    if not (result_dir / "outcome.json").exists():
        raise RuntimeError(f"No terminal attempt record for {tid}/{arm}; runner rc={rc}")
    finalize_reasoning_tokens(result_dir)
    row = summarize_attempt(tid, arm, result_dir, smoke)
    row["runner_returncode"] = rc
    row["sampling_seed"] = 42
    row["outer_deadline_seconds"] = 900
    row["elapsed_controller_seconds"] = time.time() - started_at
    atomic(done, row)
    event("attempt_done", **row)
    save_csv()
    return row


def start_server(identity):
    if gpu_free_mib() < 62000:
        raise RuntimeError(f"GPU preflight failed: free {gpu_free_mib()} MiB < 62000 MiB")
    concern = resource_concern()
    if concern:
        raise RuntimeError(concern)
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", 8001)) == 0:
            raise RuntimeError("Port 8001 is occupied; will not claim or stop that server")
    env = os.environ.copy()
    for name in ("COSTAGENT_ROUTER", "COSTAGENT_METHOD_ROUTER",
                 "COSTAGENT_ROUTER_SOURCE", "COSTAGENT_PHASE_ROUTER"):
        env.pop(name, None)
    env.update({"COSTAGENT_DPO_LIVE_V2": "1",
                "MAIN_ADAPTER": str(ROOT / "data/sample_submission/adapters/main_lora")})
    server_dir = OUT / "server"
    server_dir.mkdir(exist_ok=True)
    gpu_state = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=name,memory.free,memory.used,utilization.gpu",
         "--format=csv,noheader"], text=True)
    gpu_processes = subprocess.check_output(
        ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader"],
        text=True)
    (server_dir / "gpu_preflight.txt").write_text(
        "GPU state before our server:\n" + gpu_state +
        "Compute processes (PID, memory; left untouched):\n" + gpu_processes)
    log = (server_dir / "vllm.log").open("a")
    proc = subprocess.Popen(["bash", str(PKG / "scripts/serve_local.sh")], cwd=PKG,
                            env=env, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)
    created = psutil.Process(proc.pid).create_time()
    ownership = {"pid": proc.pid, "create_time": created,
                 "process_group": os.getpgid(proc.pid), "gpu_fraction": 0.60,
                 "max_num_seqs": 1, "identity": identity}
    atomic(server_dir / "ownership.json", ownership)
    try:
        deadline = time.monotonic() + 1200
        while True:
            if STOP or proc.poll() is not None:
                raise RuntimeError(f"Owned vLLM stopped during startup: rc={proc.poll()}")
            if time.monotonic() > deadline:
                raise TimeoutError("vLLM readiness deadline of 1200s expired")
            concern = resource_concern()
            if concern:
                raise RuntimeError(concern)
            try:
                with urllib.request.urlopen(URL + "/models", timeout=2) as r:
                    served = json.load(r)
                break
            except (OSError, ValueError):
                time.sleep(3)
        models = {m["id"]: m for m in served.get("data", [])}
        expected = {"gemma-4-31b-it-qat-w4a16-ct", "main_lora", "tool_lora", "dpo_lora"}
        if not expected <= models.keys():
            raise RuntimeError(f"vLLM missing models: {sorted(expected - models.keys())}")
        roots = {
            "main_lora": (ROOT / "data/sample_submission/adapters/main_lora").resolve(),
            "tool_lora": (ROOT / "data/sample_submission/adapters/tool_lora").resolve(),
            "dpo_lora": DPO.resolve(),
        }
        for name, expected_root in roots.items():
            if Path(models[name]["root"]).resolve() != expected_root:
                raise RuntimeError(f"Adapter alias {name} points to {models[name]['root']}, expected {expected_root}")
        (server_dir / "served_models.json").write_text(json.dumps(served, indent=2) + "\n")
        for mid in ("gemma-4-31b-it-qat-w4a16-ct", "main_lora", "tool_lora", "dpo_lora"):
            body = {"model": mid, "messages": [{"role": "user", "content": "Reply OK."}],
                    "max_tokens": 12, "temperature": 0,
                    "chat_template_kwargs": {"enable_thinking": False}}
            req = urllib.request.Request(URL + "/chat/completions", data=json.dumps(body).encode(),
                                        headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                response = json.load(r)
            if not response.get("choices"):
                raise RuntimeError(f"Model readiness probe returned no choices: {mid}")
            atomic(server_dir / f"probe-{mid}.json", response)
        event("vllm_ready", pid=proc.pid, adapters=sorted(expected), gpu_free_mib=gpu_free_mib())
        return proc, created
    except BaseException:
        record = stop_server(proc, created)
        atomic(server_dir / "cleanup.json", record)
        raise


def attach_owned_server(identity):
    """Reuse only this batch's still-running server after controller recovery."""
    owner_path = OUT / "server" / "ownership.json"
    owner = json.loads(owner_path.read_text())
    pid = int(owner["pid"])
    proc = psutil.Process(pid)
    if abs(proc.create_time() - float(owner["create_time"])) > 0.02:
        raise RuntimeError("Recorded vLLM PID was reused; refusing to attach")
    if os.getpgid(pid) != int(owner["process_group"]) or int(owner["process_group"]) != pid:
        raise RuntimeError("Recorded vLLM process-group identity changed; refusing to attach")
    if owner.get("identity", {}).get("weight_sha256") != identity["weight_sha256"]:
        raise RuntimeError("Owned vLLM serves a different DPO adapter; refusing to attach")
    cmd = " ".join(proc.cmdline())
    for required in ("--port 8001", "--gpu-memory-utilization 0.60",
                     "--max-num-seqs 1", "dpo_lora="):
        if required not in cmd:
            raise RuntimeError(f"Owned vLLM command is missing {required!r}")
    with urllib.request.urlopen(URL + "/models", timeout=5) as response:
        served = json.load(response)
    models = {m["id"]: m for m in served.get("data", [])}
    expected = {
        "gemma-4-31b-it-qat-w4a16-ct",
        "main_lora", "tool_lora", "dpo_lora",
    }
    if not expected <= models.keys():
        raise RuntimeError(f"Owned vLLM missing expected models: {sorted(expected-models.keys())}")
    roots = {
        "main_lora": (ROOT / "data/sample_submission/adapters/main_lora").resolve(),
        "tool_lora": (ROOT / "data/sample_submission/adapters/tool_lora").resolve(),
        "dpo_lora": DPO.resolve(),
    }
    for name, expected_root in roots.items():
        if Path(models[name]["root"]).resolve() != expected_root:
            raise RuntimeError(f"Owned vLLM alias {name} points to unexpected root")
    atomic(OUT / "server" / "served_models.json", served)
    event("vllm_reused_owned", pid=pid, process_group=owner["process_group"],
          gpu_free_mib=gpu_free_mib())
    return AttachedOwnedServer(pid), float(owner["create_time"])


def completed_smoke(task_id, arm):
    for marker in sorted((OUT / "attempts").glob("smoke-*/**/done.json")):
        try:
            row = json.loads(marker.read_text())
            result_dir = Path(row["result_dir"])
            if (row.get("smoke") is True and row.get("task_id") == task_id
                    and row.get("arm") == arm and row.get("cleanup_ok")
                    and (result_dir / "turn_telemetry.jsonl").is_file()
                    and (result_dir / "snapshot_patch_check.json").is_file()):
                return row
        except (OSError, KeyError, ValueError):
            continue
    return None


def main():
    global STOP
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reuse-owned-server", action="store_true",
                        help="resume with the batch's identity-verified existing vLLM")
    parser.add_argument("--smoke-only", action="store_true",
                        help="run and report the four smoke attempts, then pause")
    parser.add_argument("--keep-server", action="store_true",
                        help="with --smoke-only, retain the owned server for batch resume")
    args = parser.parse_args()
    if args.keep_server and not args.smoke_only:
        parser.error("--keep-server requires --smoke-only")
    identity = adapter_identity()
    plan, schedule = frozen_schedule()
    if args.dry_run:
        print(json.dumps({"adapter": identity, "tasks": len(schedule),
                          "attempts": 168, "smoke_ids": ["fastapi_14246", "rich_4070"],
                          "first_slots": schedule[:3], "phase2_enabled": True}, indent=2))
        return
    OUT.mkdir(parents=True, exist_ok=True)
    lock = (OUT / "runner.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, on_signal)
    schedule_path = OUT / "schedule.json"
    serialized = json.dumps(schedule, separators=(",", ":")).encode()
    schedule_hash = hashlib.sha256(serialized).hexdigest()
    if schedule_path.exists():
        saved = json.loads(schedule_path.read_text())
        if saved["sha256"] != schedule_hash:
            raise RuntimeError("Saved schedule differs from preregistered schedule")
    else:
        atomic(schedule_path, {"seed": 20261119, "rows": schedule, "sha256": schedule_hash})
    manifest_path = OUT / "run_manifest.json"
    manifest = {
        "prereg_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "prereg_file_sha256": sha(ROOT / "prereg/DPO_LIVE_V2.md"),
        "source_commit": plan["source_commit"], "adapter": identity,
        "schedule_sha256": schedule_hash, "attempt_target": 168,
        "smoke_task_ids": ["fastapi_14246", "rich_4070"],
        "effective_settings": plan["effective_settings"],
        "server_script_sha256": sha(PKG / "scripts/serve_local.sh"),
        "worker_sha256": sha(PKG / "scripts/docker_eval_worker.py"),
        "instrumentation_sha256": sha(PKG / "scripts/dpo_live_instrumentation.py"),
        "http_capture_sha256": sha(PKG / "scripts/capture_http.py"),
        "runner_sha256": sha(Path(__file__)),
    }
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        if (previous.get("prereg_file_sha256") not in
                (ORIGINAL_PREREG_SHA256, manifest["prereg_file_sha256"])
                or previous.get("schedule_sha256") != schedule_hash
                or previous.get("adapter", {}).get("weight_sha256") != identity["weight_sha256"]):
            raise RuntimeError("Existing run manifest does not match preregistration, schedule, or adapter")
        if previous.get("prereg_file_sha256") == ORIGINAL_PREREG_SHA256:
            previous["fixed_stop_amendment_sha256"] = manifest["prereg_file_sha256"]
            previous["fixed_stop_utc"] = FIXED_STOP_UTC
        previous.setdefault("resume_history", []).append({
            "time": time.time(), "controller_commit": manifest["prereg_commit"],
            "runner_sha256": manifest["runner_sha256"],
            "reuse_owned_server": args.reuse_owned_server,
        })
        manifest = previous
    atomic(manifest_path, manifest)
    event("preflight_passed", adapter=identity, schedule_sha256=schedule_hash,
          tasks=len(schedule), attempts=168)
    server = None
    created = None
    smoke_passed = False
    try:
        server, created = (attach_owned_server(identity) if args.reuse_owned_server
                           else start_server(identity))
        # Discarded smokes, both arms on both pre-registered smoke IDs.
        for tid in ("fastapi_14246", "rich_4070"):
            for arm in ("A0", "DPO"):
                prior = completed_smoke(tid, arm)
                if prior:
                    event("smoke_reused", task_id=tid, arm=arm,
                          result_dir=prior["result_dir"])
                else:
                    run_attempt(server, tid, arm, smoke=True)
        validate_smokes()
        smoke_passed = True
        event("smoke_gate_passed", confirmatory_attempts_started=0)
        if args.smoke_only:
            return
        done = 0
        for slot in schedule:
            # Finish a task already underway, then stop before starting another.
            markers = [OUT / "attempts" / slot["task_id"] / arm / "done.json"
                       for arm in slot["arms"]]
            if time.time() >= FIXED_STOP_UTC and not any(p.exists() for p in markers):
                event("fixed_stop", deadline_utc=FIXED_STOP_UTC,
                      terminal_records=sum(1 for p in (OUT / "attempts").glob("*/**/done.json")
                                           if not p.parent.parent.name.startswith("smoke-")))
                return
            for arm in slot["arms"]:
                if STOP:
                    raise KeyboardInterrupt
                run_attempt(server, slot["task_id"], arm, smoke=False)
                done += 1
                prior_rows = [json.loads(p.read_text()) for p in
                              (OUT / "attempts").glob("*/**/done.json")
                              if not p.parent.parent.name.startswith("smoke-")]
                event("batch_progress", completed=done, total=168,
                      distinct_tasks=len({x["task_id"] for x in schedule[:(done + 1) // 2]}),
                      resolved=sum(x.get("resolved") is True for x in prior_rows),
                      unresolved=sum(x.get("resolved") is False for x in prior_rows),
                      grading_errors=sum(x.get("resolved") is None for x in prior_rows),
                      timeouts=sum(bool(x.get("agent_timeout")) for x in prior_rows),
                      disk_free_bytes=__import__("shutil").disk_usage(ROOT).free)
        event("batch_complete", completed=168)
    except BaseException as e:
        event("batch_stopped", error=f"{type(e).__name__}: {e}")
        raise
    finally:
        if server is not None and not (args.smoke_only and args.keep_server and smoke_passed):
            record = stop_server(server, created)
            atomic(OUT / "server" / "cleanup.json", record)
            event("vllm_cleanup", **record)
            if not record["process_exited"] or not record["port_8001_closed"]:
                raise RuntimeError("Owned vLLM cleanup failed")
        elif server is not None:
            event("vllm_retained_after_smoke", pid=server.pid,
                  next_command="--reuse-owned-server")


if __name__ == "__main__":
    main()
