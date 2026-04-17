"""Unit tests for mindtrace.models.training.optimizers.

All tests require PyTorch and are guarded with pytest.importorskip.

Tests use a tiny nn.Linear(2, 2) model for all optimizer instantiation checks
so that they complete in milliseconds.
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
import torch.nn as nn  # noqa: E402
from torch.optim import SGD, Adam, AdamW, Optimizer, RAdam  # noqa: E402
from torch.optim.lr_scheduler import (  # noqa: E402
    CosineAnnealingLR,
    LambdaLR,
    LRScheduler,
    ReduceLROnPlateau,
    StepLR,
)

from mindtrace.models.training.optimizers import (  # noqa: E402
    WarmupCosineScheduler,
    build_optimizer,
    build_scheduler,
)

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def tiny_model() -> nn.Module:
    """A tiny nn.Linear(2, 2) used as a stand-in for any trainable module."""
    return nn.Linear(2, 2)


@pytest.fixture()
def tiny_optimizer(tiny_model: nn.Module) -> Optimizer:
    """AdamW optimizer wrapping the tiny model."""
    return torch.optim.AdamW(tiny_model.parameters(), lr=1e-3)


# ===========================================================================
# build_optimizer
# ===========================================================================


class TestBuildOptimizer:
    def test_adamw(self, tiny_model):
        opt = build_optimizer("adamw", tiny_model, lr=1e-3)
        assert isinstance(opt, AdamW)

    def test_adam(self, tiny_model):
        opt = build_optimizer("adam", tiny_model, lr=1e-4)
        assert isinstance(opt, Adam)

    def test_sgd(self, tiny_model):
        opt = build_optimizer("sgd", tiny_model, lr=0.01, momentum=0.9)
        assert isinstance(opt, SGD)

    def test_radam(self, tiny_model):
        opt = build_optimizer("radam", tiny_model, lr=1e-3)
        assert isinstance(opt, RAdam)

    def test_case_insensitive(self, tiny_model):
        """Name lookup must be case-insensitive."""
        opt = build_optimizer("AdamW", tiny_model, lr=1e-3)
        assert isinstance(opt, AdamW)

    def test_unknown_name_raises_value_error(self, tiny_model):
        with pytest.raises(ValueError, match="Unknown optimizer"):
            build_optimizer("lion", tiny_model)


# ===========================================================================
# build_scheduler
# ===========================================================================


class TestBuildScheduler:
    def test_cosine(self, tiny_optimizer):
        scheduler = build_scheduler("cosine", tiny_optimizer, T_max=100)
        assert isinstance(scheduler, CosineAnnealingLR)

    def test_cosine_total_steps_alias(self, tiny_optimizer):
        """'total_steps' is an accepted alias for T_max in the cosine scheduler."""
        scheduler = build_scheduler("cosine", tiny_optimizer, total_steps=50)
        assert isinstance(scheduler, CosineAnnealingLR)

    def test_cosine_missing_t_max_raises(self, tiny_optimizer):
        with pytest.raises(TypeError, match="total_steps.*T_max"):
            build_scheduler("cosine", tiny_optimizer)

    def test_step(self, tiny_optimizer):
        scheduler = build_scheduler("step", tiny_optimizer, step_size=10, gamma=0.5)
        assert isinstance(scheduler, StepLR)

    def test_step_missing_args_raises(self, tiny_optimizer):
        with pytest.raises(TypeError, match="step_size"):
            build_scheduler("step", tiny_optimizer)

    def test_plateau(self, tiny_optimizer):
        scheduler = build_scheduler("plateau", tiny_optimizer, patience=5, factor=0.5)
        assert isinstance(scheduler, ReduceLROnPlateau)

    def test_constant_returns_lambda_lr(self, tiny_optimizer):
        scheduler = build_scheduler("constant", tiny_optimizer)
        assert isinstance(scheduler, LambdaLR)

    def test_cosine_warmup_returns_scheduler(self, tiny_optimizer):
        scheduler = build_scheduler(
            "cosine_warmup",
            tiny_optimizer,
            warmup_steps=10,
            total_steps=100,
        )
        assert isinstance(scheduler, LRScheduler)
        assert isinstance(scheduler, WarmupCosineScheduler)

    def test_cosine_warmup_missing_args_raises(self, tiny_optimizer):
        with pytest.raises(TypeError, match="warmup_steps"):
            build_scheduler("cosine_warmup", tiny_optimizer, total_steps=100)

    def test_unknown_name_raises_value_error(self, tiny_optimizer):
        with pytest.raises(ValueError, match="Unknown scheduler"):
            build_scheduler("transformer_lr", tiny_optimizer)


# ===========================================================================
# WarmupCosineScheduler
# ===========================================================================


class TestWarmupCosineScheduler:
    def test_warmup_phase_increases_lr(self, tiny_optimizer):
        """During warm-up steps the LR should increase from near-zero."""
        scheduler = WarmupCosineScheduler(tiny_optimizer, warmup_steps=5, total_steps=20)
        lrs = []
        for _ in range(5):
            lrs.append(scheduler.get_lr()[0])
            tiny_optimizer.step()
            scheduler.step()
        # LR should be monotonically non-decreasing during warm-up
        for i in range(1, len(lrs)):
            assert lrs[i] >= lrs[i - 1] - 1e-9

    def test_cosine_phase_decreases_lr(self, tiny_optimizer):
        """After warm-up the LR should decrease towards eta_min."""
        scheduler = WarmupCosineScheduler(tiny_optimizer, warmup_steps=2, total_steps=10, eta_min=0.0)
        # Advance past warm-up
        for _ in range(2):
            tiny_optimizer.step()
            scheduler.step()
        lr_after_warmup = scheduler.get_lr()[0]

        for _ in range(7):
            tiny_optimizer.step()
            scheduler.step()
        lr_near_end = scheduler.get_lr()[0]

        assert lr_near_end <= lr_after_warmup + 1e-9

    def test_negative_warmup_steps_raises(self, tiny_optimizer):
        with pytest.raises(ValueError, match="warmup_steps"):
            WarmupCosineScheduler(tiny_optimizer, warmup_steps=-1, total_steps=10)

    def test_warmup_gt_total_raises(self, tiny_optimizer):
        with pytest.raises(ValueError, match="warmup_steps"):
            WarmupCosineScheduler(tiny_optimizer, warmup_steps=20, total_steps=10)

    def test_zero_total_steps_raises(self, tiny_optimizer):
        with pytest.raises(ValueError, match="total_steps"):
            WarmupCosineScheduler(tiny_optimizer, warmup_steps=0, total_steps=0)
