import importlib.util
from pathlib import Path

import pytest
import torch


SPEC = importlib.util.spec_from_file_location(
    "blend_lora", Path(__file__).resolve().parents[1] / "scripts/blend_lora.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_rank_concatenation_equals_weighted_update():
    torch.manual_seed(4)
    a1, a2 = torch.randn(2, 3), torch.randn(2, 3)
    b1, b2 = torch.randn(4, 2), torch.randn(4, 2)
    a, b = MODULE.blend_pair(a1, b1, a2, b2, 0.4, 2.0, 1.0)
    expected = 0.4 * 2 * (b1 @ a1) + 0.6 * 2 * (b2 @ a2)
    assert a.shape == (4, 3)
    assert b.shape == (4, 4)
    assert torch.allclose(b @ a, expected, atol=1e-6)


def test_rejects_incompatible_shapes():
    with pytest.raises(ValueError, match="different shapes"):
        MODULE.blend_pair(torch.zeros(2, 3), torch.zeros(4, 2),
                          torch.zeros(3, 3), torch.zeros(4, 3), 0.5, 2, 1)
