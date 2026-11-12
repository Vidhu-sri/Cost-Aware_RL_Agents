"""Turn a trajectory into per-turn training examples: (input_ids, assistant mask).

Without capture-proxy logs, each turn's context is rebuilt from the trace:
system prompt + first user message + the history before the turn, rendered
with the model's own chat template and the 9 tool schemas. When the rebuilt
context is longer than the harness would have kept (it compacts at ~14k
tokens), the oldest assistant/tool blocks are dropped until it fits. This is
an approximation; every example carries approx=True.
"""
from __future__ import annotations

import json

from .tools_schema import TOOLS

TEMPLATE_KW = {"enable_thinking": True}


def _assistant_msg(turn: dict) -> dict:
    msg = {"role": "assistant", "content": turn.get("text", "") or ""}
    if turn.get("reasoning"):
        msg["reasoning_content"] = turn["reasoning"]
        msg["thinking"] = turn["reasoning"]
    if turn["calls"]:
        msg["tool_calls"] = [{"id": c["id"] or f"call_{i}", "type": "function",
                              "function": {"name": c["name"], "arguments": c["args"]}}
                             for i, c in enumerate(turn["calls"])]
    return msg


def _tool_msgs(turn: dict) -> list[dict]:
    out = []
    names = {c["id"]: c["name"] for c in turn["calls"]}
    for i, r in enumerate(turn.get("results", [])):
        cid = r.get("id") or (turn["calls"][i]["id"] if i < len(turn["calls"]) else "")
        out.append({"role": "tool", "tool_call_id": cid or f"call_{i}",
                    "name": names.get(cid, turn["calls"][i]["name"] if i < len(turn["calls"]) else "tool"),
                    "content": r.get("content", "")})
    return out


def blocks(traj: dict, system_override: str | None = None):
    """Header messages and one block per turn: (assistant_index or None, [messages])."""
    system = system_override if system_override is not None else traj["system"]
    head = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": traj["first_user"]}]
    out = []
    for t in traj["turns"]:
        if t["kind"] == "user":
            out.append((None, [{"role": "user", "content": t["text"]}]))
        else:
            out.append((t, [_assistant_msg(t)] + _tool_msgs(t)))
    return head, out


def _render(tok, msgs, gen):
    return tok.apply_chat_template(msgs, tools=TOOLS, tokenize=False, add_generation_prompt=gen, **TEMPLATE_KW)


def turn_examples(tok, traj: dict, max_len: int = 16384, system_override: str | None = None,
                  only: set[int] | None = None) -> list[dict]:
    """One example per assistant turn (or only those whose index is in `only`)."""
    head, blks = blocks(traj, system_override)
    exs, a_idx = [], -1
    for bi, (turn, msgs) in enumerate(blks):
        if turn is None:
            continue
        a_idx += 1
        if only is not None and a_idx not in only:
            continue
        hist = [m for _, ms in blks[:bi] for m in ms]
        start = 0
        ex = None
        while True:
            # never start the kept history on a dangling tool message
            while start < len(hist) and hist[start]["role"] == "tool":
                start += 1
            ctx = head + hist[start:]
            prefix = _render(tok, ctx, True)
            full = _render(tok, ctx + [msgs[0]], False)
            if not full.startswith(prefix):
                ex = {"skip": "template_prefix_mismatch"}
                break
            p_ids = tok(prefix, add_special_tokens=False)["input_ids"]
            c_ids = tok(full[len(prefix):], add_special_tokens=False)["input_ids"]
            if len(c_ids) == 0:
                ex = {"skip": "empty_completion"}
                break
            if len(p_ids) + len(c_ids) <= max_len:
                ex = {"input_ids": p_ids + c_ids, "mask": [0] * len(p_ids) + [1] * len(c_ids),
                      "n_assistant": len(c_ids), "dropped_msgs": start, "approx": True}
                break
            if start >= len(hist):
                ex = {"skip": "too_long"}
                break
            start += max(1, (len(hist) - start) // 8)  # drop oldest history, coarse steps
        ex.update(rollout_id=traj["rollout_id"], turn=a_idx)
        exs.append(ex)
    return exs


def assistant_turn_meta(traj: dict) -> list[dict]:
    """Per assistant turn: tools called and files touched (for stratum A selection)."""
    meta = []
    for t in traj["turns"]:
        if t["kind"] != "assistant":
            continue
        names = [c["name"] for c in t["calls"]]
        files = [c["args"].get("filepath", "") for c in t["calls"] if isinstance(c["args"], dict)]
        meta.append({"names": names, "files": [f.lstrip("/").removeprefix("workspace/") for f in files if f],
                     "cmd": json.dumps([c["args"] for c in t["calls"]])[:2000]})
    return meta
