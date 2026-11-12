"""Listwise preference math (THEORY.md section 4). Pure torch, no model needed."""
from __future__ import annotations

import torch


def targets(r2: torch.Tensor, mode: str = "soft", T: float = 0.1) -> torch.Tensor:
    """Target distribution over a group.

    soft: softmax(R2 / T) over all candidates (finite optimum, success gate kept).
    hard: one-hot on the best candidate by R2 (pairs reduce exactly to DPO).
    """
    if mode == "soft":
        return torch.softmax(r2 / T, dim=0)
    if mode == "hard":
        w = torch.zeros_like(r2)
        w[int(torch.argmax(r2))] = 1.0
        return w
    raise ValueError(mode)


def listwise_loss(r: torch.Tensor, w: torch.Tensor, beta: float) -> torch.Tensor:
    """-sum_i w_i log softmax(beta r)_i"""
    return -(w * torch.log_softmax(beta * r, dim=0)).sum()


def coefficients(r: torch.Tensor, w: torch.Tensor, beta: float, alpha: float, n_best: int) -> torch.Tensor:
    """d L / d log P_theta(tau_i), including the per-token NLL anchor on the best candidate."""
    p = torch.softmax(beta * r, dim=0)
    c = beta * (p - w)
    b = int(torch.argmax(w))
    c[b] = c[b] - alpha / max(n_best, 1)
    return c


def dpo_loss(r_pos: torch.Tensor, r_neg: torch.Tensor, beta: float) -> torch.Tensor:
    return -torch.nn.functional.logsigmoid(beta * (r_pos - r_neg))
