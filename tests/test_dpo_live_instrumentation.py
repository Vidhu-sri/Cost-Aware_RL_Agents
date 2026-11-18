import asyncio
import base64
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "costagent/scripts"))
import dpo_live_instrumentation as instrumentation
import run_dpo_live
import capture_http
from dpo_live_instrumentation import LiveRecorder


def test_tool_snapshot_preserves_tool_result_and_budget(tmp_path):
    patch = b"diff --git a/x.py b/x.py\n+new\n"
    docker = SimpleNamespace(exec=lambda *_args, **_kwargs: SimpleNamespace(
        exit_code=0, stdout=base64.b64encode(patch).decode(), stderr=""))
    ctx = SimpleNamespace(docker=docker, container_id="owned", agent_start_time=100.0,
                          tool_calls_used=4)
    recorder = LiveRecorder(tmp_path)
    original = lambda command: {"stdout": command, "exit_code": 0}
    wrapped = recorder.tool_wrapper(ctx, "run_command", original)

    result = wrapped("echo hi")

    assert result == {"stdout": "echo hi", "exit_code": 0}
    assert ctx.tool_calls_used == 4
    assert ctx.agent_start_time > 100.0
    snap = tmp_path / "snapshots/snapshot_0001.patch"
    assert snap.read_bytes() == patch
    manifest = json.loads((tmp_path / "snapshot_manifest.jsonl").read_text())
    assert manifest["status"] == "ok"
    assert manifest["tool"] == "run_command"


def test_model_telemetry_records_usage_and_yields_identical_response(tmp_path, monkeypatch):
    recorder = LiveRecorder(tmp_path)
    monkeypatch.setattr(instrumentation, "_server_load", lambda _url: {"running_requests": 0,
        "waiting_requests": 0, "metrics_scrape_time": 1.0, "metrics_error": None}
    )

    response = SimpleNamespace(usage_metadata=SimpleNamespace(
        prompt_token_count=11, candidates_token_count=7, thoughts_token_count=3))
    class Model:
        async def generate_content_async(self, request, stream=False):
            yield response

    model = recorder.wrap_model(Model(), "base")
    async def collect():
        return [x async for x in model.generate_content_async("request")]
    assert asyncio.run(collect()) == [response]
    row = json.loads((tmp_path / "turn_telemetry.jsonl").read_text())
    assert row["prompt_tokens"] == 11
    assert row["completion_tokens"] == 7
    assert row["reasoning_tokens"] == 3
    assert row["running_requests"] == 0
    assert row["waiting_requests"] == 0
    assert row["generation_wall_seconds"] >= 0


def test_atomic_json_creates_parent_not_destination_directory(tmp_path):
    target = tmp_path / "nested" / "state.json"
    run_dpo_live.atomic(target, {"ok": True})
    assert target.is_file()
    assert json.loads(target.read_text()) == {"ok": True}


def test_http_capture_records_every_response_and_usage_without_changing_body(tmp_path, monkeypatch):
    import httpx
    original = httpx.AsyncClient.send
    monkeypatch.setenv("COSTAGENT_DPO_LIVE", "1")
    try:
        capture_http.install(tmp_path)

        def handler(request):
            return httpx.Response(200, json={"model": "dpo_lora", "choices": [
                {"message": {"content": "ok", "reasoning_content": "think"}}],
                "usage": {"prompt_tokens": 13, "completion_tokens": 4,
                          "completion_tokens_details": {"reasoning_tokens": 2}}})

        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                response = await client.post("http://127.0.0.1:8001/v1/chat/completions",
                    json={"model": "dpo_lora", "messages": []})
                return response.json()

        assert asyncio.run(run())["choices"][0]["message"]["content"] == "ok"
        row = json.loads((tmp_path / "http_request_telemetry.jsonl").read_text())
        assert row["model_alias"] == "dpo_lora"
        assert row["prompt_tokens"] == 13
        assert row["completion_tokens"] == 4
        assert row["reasoning_tokens"] == 2
        assert row["generation_wall_seconds"] >= 0
        assert row["request_index"] == 1
    finally:
        httpx.AsyncClient.send = original
