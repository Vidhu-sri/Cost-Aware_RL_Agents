"""Parse swegemma results directories into trajectory records.

A results directory (from `swegemma eval --results-dir X`) contains
task_results.jsonl, patches/<id>.patch and traces/trace_<id>.json (ATIF).
The ATIF reader below accepts the common key spellings. Run
`python -m costagent.traces inspect <results_dir>` first: it prints the raw
structure of one trace and how it was parsed, so a mismatch is visible before
any training.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

KAGGLE_REPOS = {"fastapi/fastapi", "psf/requests", "Textualize/rich", "encode/httpx"}


def _first(d: dict, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return d[k]
    return default


def _as_text(x) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return "\n".join(_as_text(i) for i in x)
    if isinstance(x, dict):
        for k in ("text", "content", "output", "result"):
            if k in x:
                return _as_text(x[k])
        return json.dumps(x)
    return str(x)


def _args(x):
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return {"_raw": x}
    return x or {}


def _norm_call(c: dict) -> dict:
    fn = c.get("function") if isinstance(c.get("function"), dict) else {}
    return {
        "id": _first(c, "tool_call_id", "id", "call_id", default=""),
        "name": _first(c, "function_name", "name", "tool_name", default=fn.get("name", "")),
        "args": _args(_first(c, "arguments", "args", "input", default=fn.get("arguments"))),
    }


def parse_trace(obj: dict) -> dict:
    """Return {system, first_user, turns:[...]} from one ATIF-like trace."""
    steps = _first(obj, "steps", "events", "trajectory", default=[])
    system, first_user, turns = "", None, []
    for s in steps:
        src = str(_first(s, "source", "role", "author", default="")).lower()
        msg = _as_text(_first(s, "message", "content", "text"))
        calls = [_norm_call(c) for c in (_first(s, "tool_calls", "function_calls", default=[]) or [])]
        obs = _first(s, "observation", "observations", "tool_results")
        results = []
        if isinstance(obs, dict):
            for r in _first(obs, "results", default=[]) or []:
                results.append({"id": _first(r, "source_call_id", "tool_call_id", "id", default=""),
                                "content": _as_text(_first(r, "content", "output", "result"))})
            if not results and "content" in obs and calls:
                if len(calls) != 1:
                    raise ValueError("Direct observation requires exactly one matching tool call")
                results.append({"id": calls[0]["id"], "content": _as_text(obs["content"])})
        elif isinstance(obs, list):
            for r in obs:
                results.append({"id": _first(r, "source_call_id", "tool_call_id", "id", default="")
                                if isinstance(r, dict) else "", "content": _as_text(r)})
        metrics = _first(s, "metrics", "usage", default={}) or {}
        if src == "system":
            system = system + ("\n" if system else "") + msg
        elif src in ("user", "human") and not calls:
            if first_user is None:
                first_user = msg
            else:
                turns.append({"kind": "user", "text": msg})
        elif src in ("tool", "function") and turns:
            turns[-1].setdefault("results", []).append({"id": _first(s, "tool_call_id", default=""), "content": msg})
        else:  # agent / assistant / model
            turns.append({
                "kind": "assistant",
                "text": msg,
                "reasoning": _as_text(_first(s, "reasoning_content", "thought", "thoughts", "reasoning")),
                "calls": calls,
                "results": results,
                "prompt_tokens": int(_first(metrics, "prompt_tokens", "input_tokens", default=0) or 0),
                "completion_tokens": int(_first(metrics, "completion_tokens", "output_tokens", default=0) or 0),
            })
    return {"system": system, "first_user": first_user or "", "turns": turns}


def load_run(run_dir: Path, kaggle_ids: set[str]) -> list[dict]:
    run_dir = Path(run_dir)
    for index in (run_dir / "effective_manifest.json", run_dir / "manifest.json", run_dir / "all129_per_task.json"):
        if index.exists():
            data = json.loads(index.read_text())
            entries = data.get("attempts", []) if isinstance(data, dict) else data
            if not entries: continue
            out = []
            for entry in entries:
                solved = entry.get("resolved", entry.get("agent_resolved"))
                if type(solved) is not bool:
                    print(f"[traces] exclude unknown outcome: {entry.get('task_id')}", file=sys.stderr)
                    continue
                directory = Path(entry["result_dir"])
                tp = Path(entry.get("trace_path", directory / "trace.json"))
                try:
                    parsed = parse_trace(json.loads(tp.read_text()))
                except ValueError as exc:
                    print(f"[traces] exclude ambiguous trace {tp}: {exc}", file=sys.stderr)
                    continue
                tid = entry["task_id"]
                safe = directory / "safe_task_input.json"
                repo = json.loads(safe.read_text()).get("repo", "") if safe.exists() else entry.get("repo", "")
                patch = directory / "agent.patch"
                out.append(dict(task_id=tid, rollout_id=str(tp.resolve()), run=run_dir.name,
                                repo=repo, is_kaggle=tid in kaggle_ids or repo in KAGGLE_REPOS,
                                solved=solved, has_result=True, seed=entry.get("seed"),
                                patch=patch.read_text(errors="replace") if patch.exists() else "", **parsed))
            return out
    results = {}
    tr = run_dir / "task_results.jsonl"
    if tr.exists():
        for line in tr.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                tid = _first(r, "instance_id", "task_id", "id")
                results[tid] = r
    out = []
    for tp in sorted((run_dir / "traces").glob("trace_*.json")):
        tid = tp.stem[len("trace_"):]
        try:
            parsed = parse_trace(json.loads(tp.read_text()))
        except Exception as e:  # keep going, report later
            print(f"[traces] could not parse {tp}: {e}", file=sys.stderr)
            continue
        r = results.get(tid, {})
        repo = _first(r, "repo", default="")
        patch_p = run_dir / "patches" / f"{tid}.patch"
        out.append({
            "task_id": tid,
            "rollout_id": f"{run_dir.name}:{tid}",
            "run": run_dir.name,
            "repo": repo,
            "is_kaggle": tid in kaggle_ids or repo in KAGGLE_REPOS,
            "solved": bool(_first(r, "resolved", "success", "passed", default=False)),
            "has_result": bool(r),
            "patch": patch_p.read_text(errors="replace") if patch_p.exists() else "",
            **parsed,
        })
    return out


def kaggle_ids(tasks_jsonl: Path) -> set[str]:
    ids = set()
    if tasks_jsonl and Path(tasks_jsonl).exists():
        for line in Path(tasks_jsonl).read_text().splitlines():
            if line.strip():
                ids.add(json.loads(line)["instance_id"])
    return ids


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("inspect"); i.add_argument("run_dir")
    a = sub.add_parser("collect")
    a.add_argument("--runs", nargs="+", required=True, help="results dirs (train and eval)")
    a.add_argument("--kaggle-tasks", required=True, help="data/tasks.jsonl")
    a.add_argument("--out", default="artifacts/trajectories.jsonl")
    args = ap.parse_args()
    if args.cmd == "inspect":
        directory = Path(args.run_dir)
        indexed = load_run(directory, set())
        if not indexed: raise SystemExit("No labeled trajectories found")
        candidates = sorted((directory / "traces").glob("trace_*.json"))
        tp = candidates[0] if candidates else Path(indexed[0]["rollout_id"])
        print("labeled trajectories:", len(indexed), "solved:", sum(r["solved"] for r in indexed))
        obj = json.loads(tp.read_text())
        print("file:", tp)
        print("top-level keys:", list(obj)[:30])
        steps = _first(obj, "steps", "events", "trajectory", default=[])
        print("n steps:", len(steps))
        for s in steps[:4]:
            print(json.dumps(s, default=str)[:800])
        p = parse_trace(obj)
        print("\nPARSED: system chars", len(p["system"]), "| first_user chars", len(p["first_user"]),
              "| assistant turns", sum(t["kind"] == "assistant" for t in p["turns"]))
        for t in p["turns"][:3]:
            print({k: (str(v)[:200]) for k, v in t.items()})
        return
    kid = kaggle_ids(Path(args.kaggle_tasks))
    allr = []
    for rd in args.runs:
        rs = load_run(Path(rd), kid)
        print(f"{rd}: {len(rs)} trajectories, {sum(r['solved'] for r in rs)} solved, "
              f"{sum(r['is_kaggle'] for r in rs)} kaggle")
        allr += rs
    bad = [r["rollout_id"] for r in allr if not any(t["kind"] == "assistant" for t in r["turns"])]
    if bad:
        print(f"WARNING: {len(bad)} trajectories have no assistant turns (parser mismatch?): {bad[:5]}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        for r in allr:
            f.write(json.dumps(r) + "\n")
    print("wrote", args.out, len(allr))


if __name__ == "__main__":
    main()
