"""First-class precision casting with overflow validation."""

from __future__ import annotations

import pytest
import torch
import torch.nn as nn

from mindtrace.models.optimization import NumericalInstabilityError, to_precision


class Small(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.fc = nn.Linear(8, 4)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc(x)


class Overflow(nn.Module):
    """Produces values above fp16's 65504 ceiling — NaN/Inf in fp16, fine in bf16."""

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x * 1e4 * 1e4  # ~1e8


class TestToPrecision:
    def test_casts_to_bf16(self):
        model = to_precision(Small(), "bf16")
        assert next(model.parameters()).dtype == torch.bfloat16

    def test_accepts_torch_dtype(self):
        model = to_precision(Small(), torch.float16)
        assert next(model.parameters()).dtype == torch.float16

    def test_unknown_precision_raises(self):
        with pytest.raises(ValueError, match="Unknown precision"):
            to_precision(Small(), "int4")

    def test_fp16_overflow_is_caught(self):
        x = torch.full((2, 8), 8.0)
        with pytest.raises(NumericalInstabilityError, match="bf16"):
            to_precision(Overflow(), "fp16", example_input=x, validate=True)

    def test_bf16_does_not_overflow(self):
        x = torch.full((2, 8), 8.0)
        model = to_precision(Overflow(), "bf16", example_input=x, validate=True)  # must not raise
        assert model is not None

    def test_validation_can_be_skipped(self):
        x = torch.full((2, 8), 8.0)
        # validate=False => no forward pass, no raise even though fp16 would overflow
        to_precision(Overflow(), "fp16", example_input=x, validate=False)

    def test_valid_cast_passes_finiteness_check(self):
        model = to_precision(Small(), "bf16", example_input=torch.randn(4, 8))
        assert next(model.parameters()).dtype == torch.bfloat16
