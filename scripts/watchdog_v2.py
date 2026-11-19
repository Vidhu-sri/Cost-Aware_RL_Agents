#!/usr/bin/env python3
"""Watch only the identity-checked DPO live v2 controller and owned vLLM."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/dpo_live_v2"
STATE = OUT / "watchdog_state.json"
LOG = OUT / "WATCHDOG.log"
ALERT = OUT / "ALERT.txt"
DEADLINE = 1795164300.0  # 2026-11-20 14:15 Asia/Kolkata
PYTHON = "/home/mahesh/miniconda3/envs/gemma-harness/bin/python"
SCRIPT = "costagent/scripts/run_dpo_live_v2.py"


def log(kind: str, message: str) -> None:
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {kind} {message}\n")
        f.flush()
        os.fsync(f.fileno())


def atomic(path: Path, data: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(temp, path)


def terminals() -> tuple[int, float]:
    paths = [p for p in (OUT / "attempts").glob("*/DPO/done.json")
             if not p.parent.parent.name.startswith("smoke-")]
    return len(paths), max((p.stat().st_mtime for p in paths), default=0.0)


def exact_controller(proc: psutil.Process) -> bool:
    try:
        return (proc.uids().real == os.getuid()
                and Path(proc.cwd()).resolve() == ROOT.resolve()
                and SCRIPT in proc.cmdline())
    except (psutil.Error, OSError):
        return False


def discover_controller() -> dict | None:
    matches = [p for p in psutil.process_iter() if exact_controller(p)]
    if len(matches) > 1:
        raise RuntimeError(f"multiple matching controllers: {[p.pid for p in matches]}")
    if not matches:
        return None
    p = matches[0]
    return {"pid": p.pid, "create_time": p.create_time()}


def same_controller(identity: dict | None) -> bool:
    if not identity:
        return False
    try:
        proc = psutil.Process(int(identity["pid"]))
        return (abs(proc.create_time() - float(identity["create_time"])) < 0.02
                and exact_controller(proc))
    except (psutil.Error, OSError, ValueError):
        return False


def owned_server() -> bool:
    owner = OUT / "server/ownership.json"
    if not owner.exists():
        return False
    try:
        data = json.loads(owner.read_text())
        p = psutil.Process(int(data["pid"]))
        cmd = " ".join(p.cmdline())
        return (p.uids().real == os.getuid()
                and abs(p.create_time() - float(data["create_time"])) < 0.02
                and os.getpgid(p.pid) == int(data["process_group"]) == p.pid
                and "vllm serve" in cmd and "--port 8001" in cmd
                and "--gpu-memory-utilization 0.60" in cmd
                and "dpo_lora=" in cmd)
    except (psutil.Error, OSError, ValueError, KeyError):
        return False


def port_open() -> bool:
    with socket.socket() as s:
        s.settimeout(2)
        return s.connect_ex(("127.0.0.1", 8001)) == 0


def stop_controller(identity: dict | None) -> bool:
    if not same_controller(identity):
        return True
    pid = int(identity["pid"])
    log("STOP", f"SIGINT owned controller pid={pid}")
    os.kill(pid, signal.SIGINT)
    end = time.monotonic() + 950  # allow the running outer-deadline task to finish
    while time.monotonic() < end:
        if not same_controller(identity):
            return True
        time.sleep(5)
    return False


def stop_owned_server() -> bool:
    if not owned_server():
        return not port_open()
    sys.path.insert(0, str(ROOT / "costagent/scripts"))
    sys.path.insert(0, str(ROOT / "baseline-kit"))
    from run_dpo_live_v2 import AttachedOwnedServer, adapter_identity, attach_owned_server
    from run_docker_agent_all import stop_server
    server, created = attach_owned_server(adapter_identity())
    result = stop_server(server, created)
    log("SERVER_CLEANUP", json.dumps(result, sort_keys=True))
    return bool(result["process_exited"] and result["port_8001_closed"])


def alert(reason: str, state: dict) -> None:
    log("ALERT", reason)
    controller = state.get("controller")
    if same_controller(controller):
        if not stop_controller(controller):
            log("ALERT", "owned controller did not exit after SIGINT; no other process touched")
    if not same_controller(controller):
        try:
            if not stop_owned_server():
                log("ALERT", "owned server cleanup could not be confirmed")
        except Exception as exc:
            log("ALERT", f"owned server cleanup failed: {type(exc).__name__}: {exc}")
    tail = LOG.read_text(errors="replace").splitlines()[-50:]
    ALERT.write_text(reason + "\n\nLast 50 watchdog log lines:\n" + "\n".join(tail) + "\n")


def launch(state: dict, count: int, reason: str) -> None:
    if port_open() and not owned_server():
        raise RuntimeError("port 8001 belongs to an unverified process; refusing restart")
    command = [PYTHON, "-u", SCRIPT]
    if owned_server():
        command.append("--reuse-owned-server")
    with (OUT / "controller-watchdog-nohup.log").open("a") as output:
        proc = subprocess.Popen(command, cwd=ROOT, stdout=output,
                                stderr=subprocess.STDOUT, start_new_session=True)
    state["controller"] = {"pid": proc.pid, "create_time": psutil.Process(proc.pid).create_time()}
    now = time.time()
    state["restart_times"] = [t for t in state.get("restart_times", []) if now - t < 3600] + [now]
    state["last_count"] = count
    state["last_growth"] = now
    atomic(STATE, state)
    log("RESTART", f"pid={proc.pid} reason={reason} recent_60m={len(state['restart_times'])} command={' '.join(command)}")
    if len(state["restart_times"]) >= 3:
        alert("Three restarts occurred within 60 minutes; no further restarts", state)
        raise SystemExit(2)


def check(state: dict) -> dict:
    count, latest = terminals()
    now = time.time()
    if count >= 84:
        log("COMPLETE", "84 DPO terminal records")
        raise SystemExit(0)
    if ALERT.exists():
        raise SystemExit(2)
    if now >= DEADLINE:
        # The controller finishes any task already begun, then exits at its next boundary.
        log("FIXED_STOP", "deadline reached; waiting for controller task-boundary exit")
        identity = state.get("controller")
        if same_controller(identity):
            return state
        if owned_server():
            stop_owned_server()
        raise SystemExit(0)
    if count > state.get("last_count", 0):
        state["last_count"] = count
        state["last_growth"] = latest or now
    elif not state.get("last_growth"):
        state["last_growth"] = latest or now
    identity = state.get("controller")
    if not same_controller(identity):
        found = discover_controller()
        if found and not identity:
            state["controller"] = found
            log("ATTACH", f"existing owned controller pid={found['pid']}")
        elif found:
            raise RuntimeError("recorded controller gone but another matching controller exists")
        else:
            launch(state, count, "controller_not_alive")
    elif now - state["last_growth"] >= 25 * 60:
        log("STALL", f"terminal records unchanged for {int(now - state['last_growth'])}s count={count}")
        if not stop_controller(identity):
            raise RuntimeError("owned controller did not exit cleanly; refusing concurrent restart")
        launch(state, count, "no_terminal_growth_25m")
    atomic(STATE, state)
    return state


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lock = (OUT / "watchdog.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if state.get("design") != "DPO-only-v2":
        count, latest = terminals()
        state.update({"design": "DPO-only-v2", "last_count": count,
                      "last_growth": latest or time.time()})
        atomic(STATE, state)
    log("START", f"watchdog pid={os.getpid()} interval=300s stall=1500s")
    while True:
        try:
            state = check(state)
        except SystemExit:
            raise
        except Exception as exc:
            alert(f"Watchdog cannot safely restart: {type(exc).__name__}: {exc}", state)
            raise SystemExit(2)
        if "--once" in sys.argv[1:]:
            return
        time.sleep(300)


if __name__ == "__main__":
    main()
