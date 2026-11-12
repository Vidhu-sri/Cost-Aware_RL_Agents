import asyncio
import importlib.util
import json
from pathlib import Path

import httpx

SPEC = importlib.util.spec_from_file_location("phase_router", Path(__file__).resolve().parents[1] / "scripts/phase_router.py")
router_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(router_module)


def payload(calls=(), model="main_lora"):
    return {"model": model, "messages": [{"role": "system", "content": "Original prompt"},
            {"role": "assistant", "tool_calls": list(calls)}],
            "tools": [{"type": "function", "function": {"name": n}} for n in
                      ["run_command", "read_file", "edit_file", "submit_patch", "get_status"]],
            "max_completion_tokens": 16384, "temperature": 0.2, "seed": 42}


def call(ident, name):
    return {"id": ident, "function": {"name": name, "arguments": "{}"}}


def test_phase_progress_and_compacted_history():
    now = [0]
    router = router_module.PhaseRouter(clock=lambda: now[0])
    original = payload()
    body, decision = router.route(original)
    assert decision["phase"] == "localize"
    assert original["max_completion_tokens"] == 16384
    assert "max_completion_tokens" not in body
    calls = [call("r1", "read_file"), call("r2", "read_file")]
    assert router.route(payload(calls))[1]["phase"] == "edit"
    assert router.route(payload(calls + [call("e1", "edit_file")]))[1]["phase"] == "verify"
    # Old observations remain in controller state even if the harness compacts.
    assert router.route(payload())[1]["edits"] == 1
    now[0] = 241
    body, decision = router.route(payload())
    assert decision["phase"] == "submit"
    assert decision["allowed_tools"] == ["submit_patch", "get_status"]
    assert body["seed"] == 42 and body["temperature"] == 0.2


def test_analyzer_is_unchanged():
    original = payload(model="tool_lora")
    body, decision = router_module.PhaseRouter().route(original)
    assert body is original and decision is None


def test_fallback_preserves_available_tools_if_phase_filter_is_empty():
    original = payload()
    original["tools"] = [{"type": "function", "function": {"name": "edit_file"}}]
    body, decision = router_module.PhaseRouter().route(original)
    assert body["tools"] == original["tools"]
    assert decision["fallback"] == "full_original_tool_list"
    assert decision["allowed_tools"] == ["edit_file"]
    assert original["max_completion_tokens"] == 16384


def test_toolless_requests_pass_through_without_fabricated_tools():
    for value in (None, []):
        original = payload()
        if value is None:
            original.pop("tools")
        else:
            original["tools"] = value
        body, decision = router_module.PhaseRouter().route(original)
        assert body == original
        assert decision["fallback"] == "no_tools_supplied"
        assert decision["allowed_tools"] == []


def test_toolless_request_reaches_http_transport(tmp_path, monkeypatch):
    old_send = httpx.AsyncClient.send
    router_module.install(tmp_path)
    routed_send = httpx.AsyncClient.send
    httpx.AsyncClient.send = old_send
    monkeypatch.setattr(httpx.AsyncClient, "send", routed_send)
    request_body = payload()
    request_body.pop("tools")
    received = []

    def handle(request):
        received.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": []})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            await client.post("http://127.0.0.1:8001/v1/chat/completions", json=request_body)

    asyncio.run(run())
    assert received == [request_body]
    assert json.loads((tmp_path / "router_decisions.jsonl").read_text())["fallback"] == "no_tools_supplied"


def test_actual_http_body_and_log(tmp_path, monkeypatch):
    old_send = httpx.AsyncClient.send
    router_module.install(tmp_path)
    routed_send = httpx.AsyncClient.send
    httpx.AsyncClient.send = old_send
    monkeypatch.setattr(httpx.AsyncClient, "send", routed_send)
    seen = []

    def handle(request):
        data = json.loads(request.content)
        seen.append(data)
        assert int(request.headers["content-length"]) == len(request.content)
        return httpx.Response(200, json={"choices": []})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            await client.post("http://127.0.0.1:8001/v1/chat/completions", json=payload())
    asyncio.run(run())
    assert seen[0]["max_tokens"] == 2048
    assert seen[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "Original prompt" in seen[0]["messages"][0]["content"]
    assert "edit_file" not in [t["function"]["name"] for t in seen[0]["tools"]]
    assert json.loads((tmp_path / "router_decisions.jsonl").read_text())["phase"] == "localize"
