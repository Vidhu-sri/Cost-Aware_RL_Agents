"""Regression checks for the configured-clone and deadline v2 fixes."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from adk_submission.resolvers.generation import apply_thinking_config_to_model
from costagent.scripts.dpo_live_v2_instrumentation import LiveRecorder
from costagent.scripts import capture_http


class FakeModel:
    def __init__(self):
        self.model = "openai/main_lora"
        self._additional_args = {}
        self.sent = []

    async def generate_content_async(self, request, stream=False):
        self.sent.append({"model": self.model,
                          **self._additional_args.get("extra_body", {})})
        yield object()


class DpoLiveV2Tests(unittest.IsolatedAsyncioTestCase):
    async def test_instrumented_configured_clone_sends_thinking_fields(self):
        with tempfile.TemporaryDirectory() as td:
            recorder = LiveRecorder(Path(td))
            restore = recorder.install_configured_model_hook()
            try:
                from adk_submission.builders import llm as builder
                original = FakeModel()
                configured = builder.apply_thinking_config_to_model(
                    original, {"seed": 42, "thinking_config": {
                        "include_thoughts": True, "thinking_budget": 4096}})
                # The resolver shallow-copies models; give the two instances
                # separate observation lists to identify the invoked receiver.
                configured.sent = []
                # Disable network telemetry; this test exercises the actual
                # method wrapped on the configured clone.
                with patch("costagent.scripts.dpo_live_v2_instrumentation._server_load",
                           return_value={}):
                    async for _ in configured.generate_content_async(object()):
                        pass
                self.assertIsNot(configured, original)
                self.assertEqual(original.sent, [])
                self.assertEqual(configured.sent[0]["chat_template_kwargs"],
                                 {"enable_thinking": True})
                self.assertEqual(configured.sent[0]["thinking_token_budget"], 4096)
            finally:
                restore()

    async def test_http_guard_rejects_request_without_thinking(self):
        with tempfile.TemporaryDirectory() as td:
            original_send = httpx.AsyncClient.send

            async def fake_send(client, request, *args, **kwargs):
                return httpx.Response(200, request=request,
                                      json={"usage": {"prompt_tokens": 1,
                                                      "completion_tokens": 1},
                                            "choices": [{"message": {}}]})

            httpx.AsyncClient.send = fake_send
            try:
                with patch.dict(os.environ, {"COSTAGENT_DPO_LIVE_V2": "1"}):
                    capture_http.install(td)
                    async with httpx.AsyncClient() as client:
                        url = "http://127.0.0.1:8001/v1/chat/completions"
                        good = client.build_request("POST", url, json={
                            "model": "main_lora",
                            "chat_template_kwargs": {"enable_thinking": True},
                            "thinking_token_budget": 4096})
                        self.assertEqual((await client.send(good)).status_code, 200)
                        bad = client.build_request("POST", url, json={"model": "main_lora"})
                        with self.assertRaisesRegex(RuntimeError, "must enable thinking"):
                            await client.send(bad)
                violation = Path(td) / "runtime_guard_violation.jsonl"
                self.assertEqual(json.loads(violation.read_text().splitlines()[0])["number"], 2)
            finally:
                httpx.AsyncClient.send = original_send

    async def test_snapshot_time_extends_agent_runner_hard_deadline(self):
        from swegemma.harness import agent_runner
        with tempfile.TemporaryDirectory() as td:
            recorder = LiveRecorder(Path(td))
            restore = recorder.patch_timeout_context(agent_runner)
            try:
                class Context:
                    agent_start_time = 10.0
                ctx = Context()
                async with agent_runner.asyncio.timeout(300):
                    before = recorder.timeout_obj.when()
                    recorder.exclude_from_budget(0.25, ctx)
                    self.assertAlmostEqual(recorder.timeout_obj.when() - before, 0.25)
                    self.assertAlmostEqual(ctx.agent_start_time, 10.25)
                row = json.loads((Path(td) / "deadline_adjustments.jsonl").read_text().splitlines()[0])
                self.assertAlmostEqual(row["excluded_seconds"], 0.25)
            finally:
                restore()

    async def test_post_expiry_telemetry_does_not_raise_guard_violation(self):
        with tempfile.TemporaryDirectory() as td:
            recorder = LiveRecorder(Path(td))
            class Expired:
                def expired(self):
                    return True
                def reschedule(self, when):
                    raise AssertionError("Must not reschedule an expired deadline")
            recorder.timeout_obj = Expired()
            recorder.exclude_from_budget(0.007)
            self.assertFalse((Path(td) / "deadline_guard_violation.jsonl").exists())
            row = json.loads((Path(td) / "deadline_adjustments.jsonl").read_text().splitlines()[0])
            self.assertEqual(row["status"], "already_expired")

    async def test_post_submission_telemetry_does_not_extend_finished_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            recorder = LiveRecorder(Path(td))
            async with asyncio.timeout(300) as timeout:
                pass
            recorder.timeout_obj = timeout
            recorder.exclude_from_budget(0.007)
            self.assertFalse((Path(td) / "deadline_guard_violation.jsonl").exists())
            row = json.loads((Path(td) / "deadline_adjustments.jsonl").read_text().splitlines()[0])
            self.assertEqual(row["status"], "already_finished")
            self.assertEqual(row["excluded_seconds"], 0.0)


if __name__ == "__main__":
    unittest.main()
