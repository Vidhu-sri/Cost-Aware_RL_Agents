"""CPU-only checks for the first-request gate in DPO live v2."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "costagent/scripts"))
from capture_http import request_differences


def test_only_adapter_differs():
    a0 = {"model": "main_lora", "messages": [{"role": "user", "content": "issue"}],
          "tools": [{"function": {"name": "run_command"}}], "temperature": 0.2}
    dpo = {**a0, "model": "dpo_lora"}
    assert request_differences(dpo, a0) == ["$.model"]


def test_nested_prompt_or_tool_change_is_rejected():
    a0 = {"model": "main_lora", "messages": [{"role": "user", "content": "issue"}],
          "tools": [{"function": {"name": "run_command"}}]}
    dpo = {"model": "dpo_lora", "messages": [{"role": "user", "content": "changed"}],
           "tools": [{"function": {"name": "submit_patch"}}]}
    assert request_differences(dpo, a0) == [
        "$.messages[0].content", "$.model", "$.tools[0].function.name"]


def test_missing_field_is_rejected():
    assert request_differences({"model": "dpo_lora"},
                               {"model": "main_lora", "seed": 42}) == ["$.model", "$.seed"]
