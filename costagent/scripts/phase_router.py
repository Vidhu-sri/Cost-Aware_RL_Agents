"""Research-only deterministic controller for the existing DPO agent.

The output cap limits all generated tokens, not reasoning tokens alone.
Tool declarations guide tool selection; run_command remains unrestricted shell
inside the existing sandbox, so these masks are not filesystem enforcement.
"""
import copy
import hashlib
import json
import re
import time
from pathlib import Path

VERSION = "phase-v2-empty-tools-fallback"
PHASES = {
    "localize": (False, 2048, {"read_file", "run_command", "get_code_neighbors", "search_similar_code", "get_code_subgraph", "get_status", "submit_patch", "code_analyzer_agent"}),
    "edit": (True, 8192, {"read_file", "run_command", "edit_file", "write_file", "get_status", "submit_patch"}),
    "verify": (True, 4096, {"read_file", "run_command", "get_status", "submit_patch"}),
    "submit": (False, 1024, {"get_status", "submit_patch"}),
}


class PhaseRouter:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.started = None
        self.seen = set()
        self.observed = []
        self.turn = 0
        self.verify_turn_used = False

    def route(self, payload):
        if payload.get("model", "").removeprefix("openai/") not in {"main_lora", "costlora"}:
            return payload, None
        now = self.clock()
        if self.started is None:
            self.started = now
        self.turn += 1
        new_edit = False
        for message in payload.get("messages", []):
            for call in message.get("tool_calls") or []:
                ident = call.get("id") or hashlib.sha256(json.dumps(call, sort_keys=True).encode()).hexdigest()
                if ident in self.seen:
                    continue
                self.seen.add(ident)
                fn = call.get("function", {})
                name = fn.get("name", "")
                raw = fn.get("arguments", "{}")
                try:
                    arguments = json.loads(raw) if isinstance(raw, str) else raw
                except ValueError:
                    arguments = {}
                command = str(arguments.get("command", ""))
                kind = "other"
                if name in {"edit_file", "write_file"}:
                    kind = "edit"
                elif name == "run_command" and re.search(r"\b(pytest|unittest|tox)\b", command):
                    kind = "test"
                elif name in {"read_file", "get_code_neighbors", "get_code_subgraph", "search_similar_code"}:
                    kind = "inspect"
                elif name == "run_command" and re.search(r"\b(ls|rg|grep|find|cat|sed|head|tail)\b", command):
                    kind = "inspect"
                new_edit |= kind == "edit"
                self.observed.append({"name": name, "kind": kind, "command": command})
        if new_edit:
            self.verify_turn_used = False
        elapsed = now - self.started
        calls = sum(c["name"] not in {"get_status", "submit_patch"} for c in self.observed)
        inspections = sum(c["kind"] == "inspect" for c in self.observed)
        edits = sum(c["kind"] == "edit" for c in self.observed)
        last = self.observed[-1] if self.observed else {}
        repeated = (len(self.observed) >= 2 and bool(last.get("command"))
                    and last.get("command") == self.observed[-2].get("command"))
        if elapsed >= 240 or calls >= 85:
            phase, reason = "submit", "reserve time for patch submission"
        elif edits and last.get("kind") == "edit" and not self.verify_turn_used:
            phase, reason = "verify", "request a check after an edit"
            self.verify_turn_used = True
        elif inspections >= 2 or self.turn >= 4 or repeated or edits:
            phase, reason = "edit", "context gathered or inspection-turn limit reached"
        else:
            phase, reason = "localize", "initial repository inspection"
        thinking, cap, names = PHASES[phase]
        result = copy.deepcopy(payload)
        original_tools = result.get("tools") or []
        selected_tools = [t for t in original_tools if t.get("function", {}).get("name") in names]
        fallback = None
        if not original_tools:
            # Some harness requests deliberately have no tool declarations.
            # Do not fabricate a submit_patch schema or alter the request.
            return result, {"version": VERSION, "turn": self.turn,
                            "elapsed_seconds": elapsed, "phase": phase,
                            "reason": reason, "fallback": "no_tools_supplied",
                            "allowed_tools": [], "model": result.get("model"),
                            "time": time.time()}
        if not selected_tools:
            # Preserve the actual caller-provided schemas and retain all tools.
            selected_tools = original_tools
            fallback = "full_original_tool_list"
        result["tools"] = selected_tools
        # Remove ADK's alternative output-limit field before setting the cap.
        original_cap = result.pop("max_completion_tokens", result.get("max_tokens", 16384))
        result["max_tokens"] = min(int(original_cap or 16384), cap)
        result.setdefault("chat_template_kwargs", {})["enable_thinking"] = thinking
        instruction = (f"Controller phase: {phase}. {reason}. "
                       "Use the available tools to advance the fix. "
                       + ("Submit your current patch now if the submission tool is available; the time budget is nearly used." if phase == "submit" else
                          "Run a focused check, then revise if needed." if phase == "verify" else
                          "Avoid repeating the same inspection; proceed to a targeted edit when justified." if phase == "edit" else
                          "Locate the relevant files and read a focused span."))
        messages = result.setdefault("messages", [])
        if messages and messages[0].get("role") in {"system", "developer"} and isinstance(messages[0].get("content"), str):
            messages[0]["content"] += "\n\n" + instruction
        else:
            messages.insert(0, {"role": "system", "content": instruction})
        record = {"version": VERSION, "turn": self.turn, "elapsed_seconds": elapsed,
                  "phase": phase, "reason": reason, "inspections": inspections,
                  "edits": edits, "observed_calls": calls, "repeat_command": repeated,
                  "ready_to_edit_heuristic": inspections >= 2 or self.turn >= 4,
                  "enable_thinking": thinking, "max_tokens": result["max_tokens"],
                  "allowed_tools": [t.get("function", {}).get("name") for t in result["tools"]],
                  "fallback": fallback,
                  "model": result.get("model"), "time": time.time()}
        return result, record


def install(out):
    import httpx
    out = Path(out)
    router = PhaseRouter()
    original = httpx.AsyncClient.send

    async def send(client, request, *args, **kwargs):
        if (request.url.host == "127.0.0.1" and request.url.port == 8001
                and request.url.path.endswith("/chat/completions")):
            body, record = router.route(json.loads(request.content))
            if record is not None:
                headers = dict(request.headers)
                headers.pop("content-length", None)
                request = httpx.Request(request.method, request.url, headers=headers,
                                        content=json.dumps(body).encode(), extensions=request.extensions)
                with (out / "router_decisions.jsonl").open("a") as stream:
                    stream.write(json.dumps(record) + "\n")
        return await original(client, request, *args, **kwargs)

    httpx.AsyncClient.send = send
