#!/usr/bin/env python3
"""Verify unique live-run working-tree snapshots outside the agent budget.

Polls completed non-smoke attempts, considers only attempts whose final
verification failed, deduplicates by (task ID, patch SHA), and evaluates each
diff with the installed timeout-aware Docker verifier. No model requests occur.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/dpo_live"
BASELINE = ROOT / "baseline-kit/run_docker.py"
PYTHON = "/home/mahesh/miniconda3/envs/gemma-harness/bin/python"
IMAGES = {"fastapi/fastapi": "gemma-fastapi-sandbox:20261015a",
          "Textualize/rich": "gemma-rich-sandbox:20261015a",
          "psf/requests": "gemma-requests-sandbox:20261015c",
          "encode/httpx": "gemma-httpx-sandbox:20261015a"}


def append(path: Path, obj: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def load_terminal_attempts():
    rows = []
    for marker in sorted((OUT / "attempts").glob("*/**/done.json")):
        try:
            row = json.loads(marker.read_text())
            if row.get("smoke") is True or row.get("resolved") is not False:
                continue
            result_dir = Path(row["result_dir"])
            manifest = result_dir / "snapshot_manifest.jsonl"
            if not manifest.exists():
                continue
            for line in manifest.read_text().splitlines():
                if not line:
                    continue
                snap = json.loads(line)
                if snap.get("status") != "ok" or not snap.get("patch_path"):
                    continue
                patch = Path(snap["patch_path"])
                if not patch.is_file():
                    continue
                blob = patch.read_bytes()
                digest = hashlib.sha256(blob).hexdigest()
                if digest != snap.get("patch_sha256"):
                    continue
                rows.append({"task_id": row["task_id"], "arm": row["arm"],
                             "attempt_result_dir": str(result_dir),
                             "sequence": snap.get("sequence"),
                             "tool": snap.get("tool"), "patch_path": str(patch),
                             "patch_sha256": digest, "patch_bytes": len(blob),
                             "snapshot_duration_seconds": snap.get("duration_seconds")})
        except (OSError, ValueError, KeyError):
            continue
    return rows


def existing_keys(index: Path):
    result = set()
    if index.exists():
        for line in index.read_text().splitlines():
            try:
                row = json.loads(line)
                output = row.get("captured_output", "")
                retryable_collision = (row.get("status") == "infrastructure_error"
                                       and "result directory already exists" in output)
                if (row.get("status") in {"complete", "could_not_interpret", "infrastructure_error"}
                        and not retryable_collision):
                    result.add((row["task_id"], row["patch_sha256"]))
            except (ValueError, KeyError):
                continue
    return result


def verify(item: dict) -> dict:
    task_records = [json.loads(line) for line in (ROOT / "data/tasks.jsonl").read_text().splitlines()]
    task = next(t for t in task_records if t["instance_id"] == item["task_id"])
    image = IMAGES[task["repo"]]
    slug = f"{item['task_id']}-{item['patch_sha256'][:16]}"
    result_dir = OUT / "snapshot_verification" / slug
    label = f"dpolive-snap-{slug}"
    if result_dir.exists():
        # A previous verifier may have completed the test but failed before
        # writing its monitor/index row. Keep that evidence intact and give
        # the retry its own output directory and owned-container label.
        retry = uuid.uuid4().hex[:8]
        result_dir = result_dir.with_name(f"{slug}-retry-{retry}")
        label = f"{label}-retry-{retry}"
    env = os.environ.copy()
    env["COSTAGENT_RESULT"] = str(result_dir)
    env["COSTAGENT_SUBMISSION"] = str(ROOT / "data/sample_submission")
    command = [PYTHON, "-u", str(BASELINE), "--mode", "patch-file",
               "--patch-path", item["patch_path"], "--label", label,
               "--task-id", item["task_id"], "--image", image, "--seconds", "900"]
    started = time.time()
    try:
        proc = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, timeout=930)
        output = proc.stdout
        try:
            result = json.loads((result_dir / "result.json").read_text())
        except Exception:
            result = {}
        monitor = {}
        try:
            monitor = json.loads((result_dir / "monitor.json").read_text())
        except Exception:
            pass
        cleanup_ok = bool(monitor) and not monitor.get("remaining_owned_ids")
        if not result or not cleanup_ok:
            status = "infrastructure_error"
        elif result.get("test_exit_code") in (None, -1, 124) or result.get("error"):
            status = "could_not_interpret"
        else:
            status = "complete"
        return {**item, "status": status, "resolved": result.get("resolved"),
                "test_exit_code": result.get("test_exit_code"),
                "test_error": result.get("error"), "runner_returncode": proc.returncode,
                "cleanup_ok": cleanup_ok, "result_dir": str(result_dir),
                "elapsed_seconds": time.time() - started,
                "captured_output": output[-4000:]}
    except subprocess.TimeoutExpired as exc:
        return {**item, "status": "infrastructure_error", "resolved": None,
                "test_exit_code": None, "test_error": "outer verification process timeout",
                "runner_returncode": None, "cleanup_ok": False,
                "result_dir": str(result_dir), "elapsed_seconds": time.time() - started,
                "captured_output": str(exc)[:4000]}


def save_csv(records):
    path = OUT / "snapshot_verification.csv"
    latest = {}
    for row in records:
        latest[(row["task_id"], row["patch_sha256"])] = row
    records = list(latest.values())
    columns = sorted({k for row in records for k in row})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")
    if args.poll_seconds < 5:
        parser.error("--poll-seconds must be at least 5")
    index = OUT / "snapshot_verification.jsonl"
    active_keys = set()
    all_records = []
    if index.exists():
        all_records = [json.loads(x) for x in index.read_text().splitlines() if x]
    executor = ThreadPoolExecutor(max_workers=args.workers)
    active = {}
    try:
        while True:
            for future in [f for f in active if f.done()]:
                item = active.pop(future)
                row = future.result()
                append(index, row)
                all_records.append(row)
                active_keys.discard((item["task_id"], item["patch_sha256"]))
                print(json.dumps({"event": "snapshot_verified", **{
                    k: row.get(k) for k in ("task_id", "patch_sha256", "status",
                                            "resolved", "test_exit_code", "cleanup_ok")}}), flush=True)
                if not row.get("cleanup_ok"):
                    raise RuntimeError(f"Snapshot verifier cleanup failed: {row}")
            done_keys = existing_keys(index)
            candidates = load_terminal_attempts()
            groups = {}
            for row in candidates:
                groups.setdefault((row["task_id"], row["patch_sha256"]), row)
            for key, item in sorted(groups.items()):
                if key in done_keys or key in active_keys or len(active) >= args.workers:
                    continue
                future = executor.submit(verify, item)
                active[future] = item
                active_keys.add(key)
                print(json.dumps({"event": "snapshot_verification_started",
                                  "task_id": item["task_id"],
                                  "patch_sha256": item["patch_sha256"],
                                  "active_workers": len(active)}), flush=True)
            save_csv(all_records)
            progress = [json.loads(x) for x in (OUT / "progress.jsonl").read_text().splitlines()]
            complete = any(e.get("event") == "batch_complete" for e in progress)
            if args.once or (complete and not active):
                break
            time.sleep(args.poll_seconds)
    finally:
        executor.shutdown(wait=True, cancel_futures=False)
        save_csv(all_records)


if __name__ == "__main__":
    main()
