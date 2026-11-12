"""Build a tiny model, tokenizer and fake swegemma results dirs for an end-to-end CPU smoke run."""
import json
import random
import sys
from pathlib import Path

import torch
from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers
from transformers import LlamaConfig, LlamaForCausalLM, PreTrainedTokenizerFast

TEMPLATE = (
    "{%- for m in messages -%}"
    "<|{{ m.role }}|>"
    "{%- if m.role == 'assistant' and m.thinking %}<think>{{ m.thinking }}</think>{% endif %}"
    "{{ m.content }}"
    "{%- if m.tool_calls %}{% for c in m.tool_calls %}<call>{{ c.function.name }} "
    "{{ c.function.arguments | tojson }}</call>{% endfor %}{% endif %}<|end|>\n"
    "{%- endfor -%}"
    "{%- if add_generation_prompt %}<|assistant|>{% endif -%}"
)


def build(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    corpus = ["read_file run_command edit_file submit_patch pytest src/app.py def fix bug test passed "
              "<think> </think> <call> </call> system user assistant tool {\"filepath\": 1 2 3}"] * 50
    tk = Tokenizer(models.BPE(unk_token="<unk>"))
    tk.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tk.decoder = decoders.ByteLevel()
    tk.train_from_iterator(corpus, trainers.BpeTrainer(
        vocab_size=400, special_tokens=["<unk>", "<s>", "<|end|>"],
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet()))
    tok = PreTrainedTokenizerFast(tokenizer_object=tk, unk_token="<unk>", bos_token="<s>", eos_token="<|end|>")
    tok.chat_template = TEMPLATE
    mdir = root / "tiny_model"
    tok.save_pretrained(mdir)
    torch.manual_seed(0)
    cfg = LlamaConfig(vocab_size=len(tok), hidden_size=32, intermediate_size=64, num_hidden_layers=2,
                      num_attention_heads=4, num_key_value_heads=2, max_position_embeddings=4096,
                      bos_token_id=1, eos_token_id=2)
    LlamaForCausalLM(cfg).save_pretrained(mdir)

    rng = random.Random(0)

    def trace(n_calls):
        steps = [{"step_id": 0, "source": "system", "message": "You are a coding agent."},
                 {"step_id": 1, "source": "user", "message": "Problem Statement: fix the bug in src/app.py"}]
        for i in range(n_calls):
            if i == n_calls - 1:
                call = {"tool_call_id": f"c{i}", "function_name": "submit_patch", "arguments": {}}
            elif i == n_calls - 2:
                call = {"tool_call_id": f"c{i}", "function_name": "edit_file",
                        "arguments": {"filepath": "src/app.py", "old_string": "a", "new_string": "b"}}
            elif i % 3 == 0:
                call = {"tool_call_id": f"c{i}", "function_name": "read_file",
                        "arguments": {"filepath": "src/app.py", "start_line": 1, "end_line": 50}}
            else:
                call = {"tool_call_id": f"c{i}", "function_name": "run_command", "arguments": {"command": f"pytest -k t{i}"}}
            steps.append({"step_id": i + 2, "source": "agent", "message": "",
                          "reasoning_content": f"think step {i}", "tool_calls": [call],
                          "observation": {"results": [{"source_call_id": f"c{i}", "content": "ok " * 5}]},
                          "metrics": {"prompt_tokens": 100 + 10 * i, "completion_tokens": 20}})
        return {"schema_version": "ATIF-v1.7", "steps": steps}

    def run(name, tasks, solve_p, repo):
        d = root / "runs" / name
        (d / "traces").mkdir(parents=True, exist_ok=True); (d / "patches").mkdir(exist_ok=True)
        with open(d / "task_results.jsonl", "w") as f:
            for t in tasks:
                n = rng.randint(4, 14)
                (d / "traces" / f"trace_{t}.json").write_text(json.dumps(trace(n)))
                (d / "patches" / f"{t}.patch").write_text("--- a/src/app.py\n+++ b/src/app.py\n@@\n-a\n+b\n")
                f.write(json.dumps({"instance_id": t, "repo": repo, "resolved": rng.random() < solve_p}) + "\n")
        return d

    train_tasks = [f"org__lib-{i}" for i in range(6)]
    kag = [f"fastapi__fastapi-{i}" for i in range(8)]
    (root / "tasks.jsonl").write_text("\n".join(json.dumps({"instance_id": k}) for k in kag) + "\n")
    for s in range(3):
        run(f"train_s{s}", train_tasks, 0.6, "org/lib")
    run("rlcd_pos", train_tasks, 0.7, "org/lib")
    run("rlcd_neg", train_tasks, 0.3, "org/lib")
    run("a0", kag, 0.4, "fastapi/fastapi")
    run("a1", kag, 0.4, "fastapi/fastapi")
    (root / "system.md").write_text("You are a coding agent.")
    print(root)


if __name__ == "__main__":
    build(Path(sys.argv[1]))
