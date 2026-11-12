"""CPU tests: THEORY.md section 12, tests 1-5, plus the chat-template mask."""
import math
import random

import pytest
import torch

from costagent.costs import calibrate, cost, counts, r2
from costagent.listwise import coefficients, dpo_loss, listwise_loss, targets


def test_reduces_to_dpo():
    r = torch.tensor([0.7, -0.4])
    w = torch.tensor([1.0, 0.0])
    assert torch.allclose(listwise_loss(r, w, 0.1), dpo_loss(r[0], r[1], 0.1), atol=1e-6)


def test_coefficients_match_autograd():
    torch.manual_seed(0)
    r = torch.randn(5, requires_grad=True)
    w = targets(torch.tensor([0.9, 0.0, 0.7, 0.0, 0.8]), "soft", 0.1)
    listwise_loss(r, w, 0.1).backward()
    c = coefficients(r.detach(), w, 0.1, alpha=0.0, n_best=1)
    assert torch.allclose(r.grad, c, atol=1e-6)


def test_gate_soft_vs_hard():
    r2v = torch.tensor([r2(True, 0.2), r2(True, 0.6), r2(False, 0.1)])
    w = targets(r2v, "soft", 0.1)
    assert w[0] > w[1] > w[2] and w[1] / w[2] > 1e3  # every success far above every failure
    h = targets(r2v, "hard", 0.1)
    assert h.tolist() == [1.0, 0.0, 0.0]               # costlier success treated like a failure


def test_r2_worked_examples():
    assert r2(True, 0.2, 0.5) == pytest.approx(0.9)
    assert r2(True, 0.6, 0.5) == pytest.approx(0.7)
    assert r2(False, 0.1, 0.5) == 0.0


def _traj(task, calls, solved):
    turns = [{"kind": "assistant", "text": "", "reasoning": "", "calls": calls, "results": [],
              "prompt_tokens": 100, "completion_tokens": 10}]
    return {"task_id": task, "turns": turns, "solved": solved}


def test_cost_range_monotone_and_dups():
    rng = random.Random(0)
    trajs = []
    for i in range(40):
        calls = [{"id": str(j), "name": "run_command", "args": {"command": f"ls {j}"}} for j in range(rng.randint(1, 30))]
        t = _traj(f"t{i % 5}", calls, rng.random() < 0.5)
        t["counts"] = counts(t)
        trajs.append(t)
    cal = calibrate(trajs)
    for t in trajs:
        c = cost(t["counts"], t["task_id"], cal)
        assert 0.0 <= c <= 1.0
        more = dict(t["counts"]); more["calls"] += 5
        assert cost(more, t["task_id"], cal) >= c
    rd = lambda s, e: {"id": "", "name": "read_file", "args": {"filepath": "a.py", "start_line": s, "end_line": e}}
    ed = {"id": "", "name": "edit_file", "args": {"filepath": "a.py", "old_string": "x", "new_string": "y"}}
    assert counts(_traj("x", [rd(1, 50), rd(40, 80)], True))["dups"] == 1   # overlap
    assert counts(_traj("x", [rd(1, 50), rd(60, 80)], True))["dups"] == 0   # no overlap
    assert counts(_traj("x", [rd(1, 50), ed, rd(1, 50)], True))["dups"] == 0  # edit resets
    free = [{"id": "", "name": "submit_patch", "args": {}}, {"id": "", "name": "get_status", "args": {}}]
    assert counts(_traj("x", free, True))["calls"] == 0


def _tiny_lm():
    from transformers import LlamaConfig, LlamaForCausalLM
    torch.manual_seed(0)
    cfg = LlamaConfig(vocab_size=64, hidden_size=32, intermediate_size=64, num_hidden_layers=2,
                      num_attention_heads=4, num_key_value_heads=2, max_position_embeddings=128)
    return LlamaForCausalLM(cfg).eval()


def test_surrogate_gradient_equals_autograd():
    from costagent.modeling import turn_logprob
    model = _tiny_lm()
    g = torch.Generator().manual_seed(1)
    cands = []
    for _ in range(3):
        turns = []
        for _ in range(2):
            ids = torch.randint(0, 64, (12,), generator=g).tolist()
            turns.append({"input_ids": ids, "mask": [0] * 6 + [1] * 6})
        cands.append(turns)
    w = targets(torch.tensor([0.9, 0.0, 0.7]), "soft", 0.1)
    beta, alpha = 0.5, 0.3
    params = [p for p in model.parameters()]

    # reference = a frozen copy with different weights so r != 0
    ref = _tiny_lm()
    with torch.no_grad():
        for p in ref.parameters():
            p.add_(0.05 * torch.randn_like(p))
    def seq(m, turns):
        tot, n = 0.0, 0
        for t in turns:
            lp, k = turn_logprob(m, t["input_ids"], t["mask"]); tot = tot + lp; n += k
        return tot, n
    with torch.no_grad():
        ref_lp = torch.stack([seq(ref, t)[0] for t in cands])
    # full autograd
    pol = [seq(model, t) for t in cands]
    lp = torch.stack([p for p, _ in pol])
    b = int(torch.argmax(w)); n_b = pol[b][1]
    loss = listwise_loss(lp - ref_lp, w, beta) - alpha * lp[b] / n_b
    full = torch.autograd.grad(loss, params)
    # two-pass surrogate
    c = coefficients((lp - ref_lp).detach(), w, beta, alpha, n_b)
    sur = sum(c[i] * seq(model, cands[i])[0] for i in range(3))
    two = torch.autograd.grad(sur, params)
    for a, bb in zip(full, two):
        assert torch.allclose(a, bb, rtol=1e-4, atol=1e-6)


def test_turn_sampling_unbiased():
    torch.manual_seed(0)
    g_turns = torch.randn(10, 3)          # per-turn gradient vectors
    A, B, k = [0, 9], list(range(1, 9)), 2
    full = g_turns.sum(0)
    rng = random.Random(0)
    draws = []
    for _ in range(20000):
        pick = rng.sample(B, k)
        draws.append(g_turns[A].sum(0) + len(B) / k * g_turns[pick].sum(0))
    d = torch.stack(draws)
    se = d.std(0) / math.sqrt(len(draws))
    assert torch.all((d.mean(0) - full).abs() < 4 * se)
