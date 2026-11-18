"""Capture local model HTTP calls without blocking agent requests.

When DPO-live instrumentation is enabled this is the authoritative per-request
telemetry source. It sees root and sub-agent requests alike, including requests
that fail before returning a response. A daemon sampler records server load
asynchronously so metrics collection does not delay model calls.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from urllib.request import urlopen

import httpx


def _append(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(value, ensure_ascii=False) + "\n")
        f.flush()


def _usage(data: bytes) -> dict:
    try:
        text = data.decode("utf-8", "replace")
        # Normal OpenAI-compatible JSON response.
        obj = json.loads(text)
    except Exception:
        # Streaming responses use SSE; retain the last usage-bearing payload.
        obj = None
        for line in data.decode("utf-8", "replace").splitlines():
            if not line.startswith("data:") or line.strip() == "data: [DONE]":
                continue
            try:
                candidate = json.loads(line[5:].strip())
            except Exception:
                continue
            if candidate.get("usage"):
                obj = candidate
    if not isinstance(obj, dict):
        return {"prompt_tokens": None, "completion_tokens": None,
                "reasoning_tokens": None, "usage_present": False,
                "reasoning_text": None}
    usage = obj.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    message = ((obj.get("choices") or [{}])[0].get("message") or {})
    reasoning_text = message.get("reasoning") or message.get("reasoning_content")
    return {"prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": details.get("reasoning_tokens"),
            "usage_present": usage.get("prompt_tokens") is not None and
                             usage.get("completion_tokens") is not None,
            "reasoning_text": reasoning_text}


def install(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    original = httpx.AsyncClient.send
    counter = 0
    lock = threading.Lock()
    latest_metrics = {"time": None, "running": None, "waiting": None,
                      "error": "metrics sampler starting"}
    live = __import__("os").environ.get("COSTAGENT_DPO_LIVE") == "1"

    def sample_metrics():
        nonlocal latest_metrics
        while True:
            sampled_at = time.time()
            row = {"time": sampled_at, "running": None, "waiting": None,
                   "error": None}
            try:
                with urlopen("http://127.0.0.1:8001/metrics", timeout=0.5) as r:
                    body = r.read().decode("utf-8", "replace")
                for key, patterns in {
                    "running": (r"vllm:num_requests_running(?:\{[^}]*\})?\s+([0-9.eE+-]+)",
                                r"vllm_num_requests_running(?:\{[^}]*\})?\s+([0-9.eE+-]+)"),
                    "waiting": (r"vllm:num_requests_waiting(?:\{[^}]*\})?\s+([0-9.eE+-]+)",
                                r"vllm_num_requests_waiting(?:\{[^}]*\})?\s+([0-9.eE+-]+)"),
                }.items():
                    for pattern in patterns:
                        match = re.search(pattern, body)
                        if match:
                            row[key] = float(match.group(1))
                            break
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"
            with lock:
                latest_metrics = row
            time.sleep(0.1)

    if live:
        threading.Thread(target=sample_metrics, name="dpo-live-metrics", daemon=True).start()

    async def send(client, request, *args, **kwargs):
        nonlocal counter
        capture = (request.url.host == "127.0.0.1" and request.url.port == 8001
                   and "/chat/completions" in request.url.path)
        if not capture:
            return await original(client, request, *args, **kwargs)
        with lock:
            counter += 1
            number = counter
            metrics = dict(latest_metrics)
        request_body = json.loads(request.content)
        request_row = {"number": number, "body": request_body}
        with (out / "model_requests.jsonl").open("a") as f:
            f.write(json.dumps(request_row) + "\n")
        request_started = time.time()
        monotonic_started = time.perf_counter()
        metrics_age = (request_started - metrics["time"]
                       if metrics.get("time") is not None else None)
        response_path = out / f"model_response_{number:04d}.bin"

        def finish(data=b"", error=None, status=None):
            if not live:
                return
            usage = _usage(data)
            row = {"request_index": number,
                   "model_alias": request_body.get("model"),
                   "request_start_time": request_started,
                   "request_end_time": time.time(),
                   "generation_wall_seconds": time.perf_counter() - monotonic_started,
                   "running_requests": metrics.get("running"),
                   "waiting_requests": metrics.get("waiting"),
                   "metrics_scrape_time": metrics.get("time"),
                   "metrics_sample_age_seconds": metrics_age,
                   "metrics_error": metrics.get("error"),
                   "response_status": status,
                   "response_file": response_path.name if response_path.exists() else None,
                   **usage, "error": error,
                   "telemetry_source": "http_capture"}
            _append(out / "http_request_telemetry.jsonl", row)

        try:
            response = await original(client, request, *args, **kwargs)
        except BaseException as e:
            finish(error=f"{type(e).__name__}: {e}")
            raise
        if response.is_stream_consumed:
            data = response.content
            response_path.write_bytes(data)
            finish(data=data, status=response.status_code)
        else:
            stream = response.stream

            class Capture(httpx.AsyncByteStream):
                def __init__(self):
                    self.parts = []
                    self.finished = False

                async def __aiter__(self):
                    try:
                        async for chunk in stream:
                            self.parts.append(chunk)
                            yield chunk
                    finally:
                        data = b"".join(self.parts)
                        response_path.write_bytes(data)
                        if not self.finished:
                            self.finished = True
                            finish(data=data, status=response.status_code)

                async def aclose(self):
                    try:
                        await stream.aclose()
                    finally:
                        if not self.finished:
                            self.finished = True
                            data = b"".join(self.parts)
                            response_path.write_bytes(data)
                            finish(data=data, status=response.status_code)

            response.stream = Capture()
        return response

    httpx.AsyncClient.send = send
