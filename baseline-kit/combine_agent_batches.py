"""Combine completed sequential agent batches without changing their records."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--resume", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    args = parser.parse_args()
    first = json.loads(args.first.read_text())
    resume = json.loads(args.resume.read_text())
    published = [json.loads(line)["instance_id"] for line in args.tasks.read_text().splitlines() if line.strip()]
    entries = first["tasks"] + resume["tasks"]
    by_id = {entry["task_id"]: entry for entry in entries}
    if len(entries) != 129 or len(by_id) != 129 or set(by_id) != set(published):
        raise ValueError("Batches do not cover exactly the 129 published tasks")
    ordered = [by_id[task_id] for task_id in published]
    if resume.get("stop_reason") or resume.get("completed_count") != 17:
        raise ValueError("Resume batch did not complete cleanly")
    if not all(entry["cleanup_ok"] for entry in ordered):
        raise ValueError("At least one task has incomplete cleanup")
    cleanup = resume.get("server_cleanup") or {}
    if not cleanup.get("process_exited") or not cleanup.get("port_8001_closed"):
        raise ValueError("Resume server did not shut down cleanly")

    summary = {
        "published_tasks": 129,
        "attempted_tasks": len(ordered),
        "verified_passes": sum(entry["verification_status"] == "passed" for entry in ordered),
        "verification_failed": sum(entry["verification_status"] == "failed" for entry in ordered),
        "verification_could_not_be_interpreted": sum(entry["verification_status"] == "could_not_be_interpreted" for entry in ordered),
        "agent_resolved": sum(entry["agent_resolved"] is True for entry in ordered),
        "agent_unresolved": sum(entry["agent_resolved"] is False for entry in ordered),
        "agent_timeouts": sum(bool(entry["agent_timed_out"]) for entry in ordered),
        "resolved_with_timeout": sum(entry["agent_resolved"] is True and entry["agent_timed_out"] for entry in ordered),
        "no_patch": sum(not entry.get("patch_bytes") for entry in ordered),
        "reference_preflight": dict(Counter(entry["reference_preflight_status"] for entry in ordered)),
        "reference_environment_problems": sum(entry["reference_preflight_status"] != "passed" for entry in ordered),
        "all_task_cleanup_ok": True,
        "first_batch_stop_reason": first.get("stop_reason"),
        "resume_batch_stop_reason": resume.get("stop_reason"),
        "resume_server_cleanup": cleanup,
        "resume_rss_stop_threshold_bytes": resume["max_observed_container_rss_bytes"],
        "first_batch_summary": str(args.first),
        "resume_batch_summary": str(args.resume),
    }
    output_dir = args.resume.parent
    (output_dir / "all129_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output_dir / "all129_per_task.json").write_text(json.dumps(ordered, indent=2) + "\n")
    fields = ["task_id", "repository", "agent_resolved", "agent_timed_out", "patch_bytes",
              "verification_status", "test_exit_code", "test_passed", "test_failed",
              "reference_preflight_status", "cleanup_ok", "image_id", "result_dir",
              "trace_path", "patch_path", "test_output_path", "effective_settings_path"]
    with (output_dir / "all129_per_task.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: entry.get(field) for field in fields} for entry in ordered)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
