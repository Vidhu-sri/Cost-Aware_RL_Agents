"""Read original Gemma results and export a separate rollout audit."""

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path


KIT = Path(__file__).resolve().parent
ROOT = KIT.parent
RESULTS = KIT / "results"
FIRST = RESULTS / "docker-gemma129-20261016a-agent-batch"
RESUME = RESULTS / "docker-gemma129-20261017b-agent-batch"
AUDIT = RESULTS / "docker-gemma129-all129-rollout-audit"


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def export_rollout(path, entry, trace):
    lines = [f"Task: {entry['task_id']}", f"Run: {entry['run_id']}",
             f"Result: resolved={entry['agent_resolved']}, verification={entry['verification_status']}",
             f"Agent timeout: {entry['agent_timed_out']}",
             f"Patch: {entry['patch_bytes']} bytes; {entry['patch_path'] or 'none'}",
             f"Test exit code: {entry['test_exit_code']}; {entry['test_output_path'] or 'no output'}",
             f"Original trace: {entry['trace_path']}", ""]
    for step in trace["steps"]:
        lines.append(f"{'=' * 20} Step {step['step_id']} [{step['source']}] {'=' * 20}")
        if step.get("model_name"):
            lines.append(f"Model: {step['model_name']}")
        if step.get("message") is not None:
            lines.extend(["Message:", str(step["message"])])
        for call in step.get("tool_calls") or []:
            lines.extend([f"Tool: {call.get('function_name')}",
                          "Arguments: " + json.dumps(call.get("arguments"), ensure_ascii=False, indent=2)])
        if step.get("observation") is not None:
            lines.extend(["Observation:", json.dumps(step["observation"], ensure_ascii=False, indent=2)])
        if step.get("metrics"):
            lines.append("Step metrics: " + json.dumps(step["metrics"], ensure_ascii=False))
        lines.append("")
    lines.append("Final metrics: " + json.dumps(trace.get("final_metrics", {}), ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n")


def main():
    first = read_json(FIRST / "batch_summary.json")
    resume = read_json(RESUME / "batch_summary.json")
    combined = read_json(RESUME / "all129_per_task.json")
    summary = read_json(RESUME / "all129_summary.json")
    published = [json.loads(line)["instance_id"] for line in (ROOT / "data/tasks.jsonl").read_text().splitlines() if line.strip()]
    manifest_entries = first["tasks"] + resume["tasks"]
    manifest_ids = Counter(entry["task_id"] for entry in manifest_entries)
    combined_ids = Counter(entry["task_id"] for entry in combined)
    duplicates = sorted({task_id for task_id, count in (manifest_ids + combined_ids).items()
                         if manifest_ids[task_id] > 1 or combined_ids[task_id] > 1})
    missing = sorted(set(published) - set(manifest_ids) | set(published) - set(combined_ids))
    extra = sorted((set(manifest_ids) | set(combined_ids)) - set(published))
    manifest_by_id = {entry["task_id"]: entry for entry in manifest_entries}
    disagreements = sorted(entry["task_id"] for entry in combined
                           if manifest_by_id.get(entry["task_id"]) != entry)

    trace_problems = []
    unexpected_traces = []
    trace_data = {}
    seen_trace_paths = set()
    index = []
    cross = Counter()
    terminal_missing = []
    for entry in combined:
        task_id = entry["task_id"]
        result_dir = Path(entry["result_dir"])
        try:
            run = read_json(result_dir / "run_manifest.json")
            outcome = read_json(result_dir / "outcome.json")
            if (run.get("run_id"), run.get("task_id"), run.get("mode")) != (entry["run_id"], task_id, "agent"):
                trace_problems.append(f"{task_id}: run manifest mismatch")
            if run.get("image_id") != entry["image_id"]:
                trace_problems.append(f"{task_id}: image identity mismatch")
            if (outcome.get("resolved"), bool(outcome.get("agent_timeout")), outcome.get("patch_bytes")) != (
                    entry["agent_resolved"], bool(entry["agent_timed_out"]), entry["patch_bytes"]):
                trace_problems.append(f"{task_id}: outcome mismatch")
        except (OSError, ValueError) as exc:
            terminal_missing.append(f"{task_id}: {type(exc).__name__}: {exc}")
        if entry.get("agent_resolved") is None or not entry.get("cleanup_ok"):
            terminal_missing.append(f"{task_id}: nonterminal per-task record")

        trace_path = Path(entry["trace_path"]) if entry.get("trace_path") else None
        if trace_path:
            seen_trace_paths.add(trace_path.resolve())
        try:
            if trace_path is None or trace_path.parent != result_dir / "traces" or trace_path.name != f"trace_{task_id}.json":
                raise ValueError("trace path does not match task result directory")
            trace = read_json(trace_path)
            if trace.get("schema_version") != "ATIF-v1.7" or not isinstance(trace.get("steps"), list) or not trace["steps"]:
                raise ValueError("invalid trace schema or empty steps")
            step_ids = [step.get("step_id") for step in trace["steps"]]
            if len(step_ids) != len(set(step_ids)) or not isinstance(trace.get("final_metrics"), dict):
                raise ValueError("duplicate step IDs or missing final metrics")
            trace_data[task_id] = trace
        except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
            trace_problems.append(f"{task_id}: {type(exc).__name__}: {exc}")
        for candidate in (result_dir / "traces").glob("trace_*.json"):
            if candidate.resolve() not in seen_trace_paths and candidate.resolve() != (trace_path.resolve() if trace_path else None):
                unexpected_traces.append(str(candidate))

        patch_present = bool(entry.get("patch_bytes"))
        cross[(entry["verification_status"], bool(entry["agent_timed_out"]),
               patch_present, entry["reference_preflight_status"])] += 1
        usage = entry.get("token_usage") or {}
        index.append({
            "task_id": task_id, "run_id": entry["run_id"], "repository": entry["repository"],
            "agent_resolved": entry["agent_resolved"], "verification_status": entry["verification_status"],
            "agent_timeout": bool(entry["agent_timed_out"]), "tool_calls": entry.get("tool_calls"),
            "llm_calls": entry.get("llm_calls"), "prompt_tokens": usage.get("total_prompt_tokens"),
            "completion_tokens": usage.get("total_completion_tokens"), "total_tokens": usage.get("total_tokens"),
            "patch_present": patch_present, "patch_bytes": entry.get("patch_bytes"),
            "patch_path": entry.get("patch_path"), "test_exit_code": entry.get("test_exit_code"),
            "test_passed": entry.get("test_passed"), "test_failed": entry.get("test_failed"),
            "reference_preflight_status": entry["reference_preflight_status"],
            "trace_path": entry.get("trace_path"), "result_dir": entry["result_dir"],
        })

    resolved = sum(entry["agent_resolved"] is True for entry in combined)
    unresolved = sum(entry["agent_resolved"] is False for entry in combined)
    passed = sum(entry["agent_resolved"] is True and entry["verification_status"] == "passed" for entry in combined)
    count_comparison = {
        "recomputed_resolved": resolved, "recomputed_unresolved": unresolved,
        "recomputed_resolved_with_passing_verification": passed,
        "combined_summary_resolved": summary["agent_resolved"],
        "combined_summary_unresolved": summary["agent_unresolved"],
        "combined_summary_verified_passes": summary["verified_passes"],
        "first_batch_resolved": sum(entry["agent_resolved"] is True for entry in first["tasks"]),
        "resume_batch_resolved": sum(entry["agent_resolved"] is True for entry in resume["tasks"]),
        "matches": (resolved, unresolved, passed) == (summary["agent_resolved"],
                  summary["agent_unresolved"], summary["verified_passes"]),
    }
    audit = {
        "published_count": len(published), "manifest_record_count": len(manifest_entries),
        "combined_record_count": len(combined), "manifest_unique_count": len(manifest_ids),
        "combined_unique_count": len(combined_ids), "duplicate_ids": duplicates,
        "missing_ids": missing, "extra_ids": extra, "manifest_combined_disagreements": disagreements,
        "without_final_outcome": terminal_missing, "expected_trace_count": len(combined),
        "valid_trace_count": len(trace_data), "trace_problems": trace_problems,
        "unexpected_traces": sorted(set(unexpected_traces)), "count_comparison": count_comparison,
        "resolved_with_timeout_ids": [entry["task_id"] for entry in combined
                                      if entry["agent_resolved"] is True and entry["agent_timed_out"]],
        "no_patch_verification_counts": dict(Counter(entry["verification_status"] for entry in combined
                                                     if not entry.get("patch_bytes"))),
    }
    AUDIT.mkdir(exist_ok=True)
    write_json(AUDIT / "audit.json", audit)
    write_json(AUDIT / "rollout_index.json", index)
    with (AUDIT / "rollout_index.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(index[0]))
        writer.writeheader()
        writer.writerows(index)
    rows = [{"verification_status": key[0], "agent_timeout": key[1], "patch_present": key[2],
             "reference_preflight_status": key[3], "count": count}
            for key, count in sorted(cross.items())]
    write_json(AUDIT / "cross_tab.json", rows)
    with (AUDIT / "cross_tab.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    examples = {
        "resolved": next(entry for entry in combined if entry["agent_resolved"] and not entry["agent_timed_out"]),
        "resolved_with_timeout": next(entry for entry in combined if entry["agent_resolved"] and entry["agent_timed_out"]),
        "timeout_no_patch": next(entry for entry in combined if entry["agent_timed_out"] and not entry.get("patch_bytes")),
        "verification_failure": next(entry for entry in combined if entry["verification_status"] == "failed" and entry.get("patch_bytes")),
    }
    for category, entry in examples.items():
        if entry["task_id"] in trace_data:
            export_rollout(AUDIT / f"example_{category}_{entry['task_id']}.txt", entry,
                           trace_data[entry["task_id"]])
    print(json.dumps({"audit": audit, "cross_tab": rows,
                      "examples": {key: entry["task_id"] for key, entry in examples.items()}}, indent=2))


if __name__ == "__main__":
    main()
