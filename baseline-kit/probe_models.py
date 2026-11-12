"""Check the host's existing vLLM endpoint before a single Docker agent run."""

import argparse
import json
from pathlib import Path
import time
import urllib.request


BASE = "http://127.0.0.1:8001/v1"
MODELS = ("gemma-4-31b-it-qat-w4a16-ct", "main_lora", "tool_lora")


def request(path, body=None, timeout=60):
    payload = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json", "Authorization": "Bearer EMPTY"}
    req = urllib.request.Request(BASE + path, data=payload, headers=headers,
                                 method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    served = request("/models", timeout=10)
    ids = {entry["id"] for entry in served["data"]}
    if not set(MODELS) <= ids:
        raise RuntimeError(f"Model server missing: {sorted(set(MODELS) - ids)}")
    responses = {}
    for name in MODELS:
        start = time.monotonic()
        data = request("/chat/completions", {
            "model": name,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "max_tokens": 32,
            "temperature": 0,
        }, timeout=120)
        choices = data.get("choices", [])
        if not choices or not isinstance(choices[0].get("message"), dict):
            raise RuntimeError(f"No chat response from {name}")
        responses[name] = {
            "response_model": data.get("model"),
            "finish_reason": choices[0].get("finish_reason"),
            "message": choices[0]["message"],
            "seconds": time.monotonic() - start,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"served_ids": sorted(ids),
                                       "responses": responses}, indent=2) + "\n")
    print(json.dumps({"served_ids": sorted(ids),
                      "responded": sorted(responses)}, indent=2))


if __name__ == "__main__":
    main()
