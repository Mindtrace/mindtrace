"""Unit tests for mindtrace.models.optimization.prune.

Covers:
- ChannelPruner: parameter/FLOP reduction, output-shape preservation,
  ignore-prefix protection, summary() consistency
- magnitude_prune: global unstructured sparsity level, mask removal, forward
- PruningSchedule: end-to-end with the real Trainer over a few short epochs
- to_sparse_24: exact 2:4 pattern per group of four, forward still works
- sparsity: measurement helper
"""

from __future__ import annotations

import pytest
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

# ---------------------------------------------------------------------------
# Environment fixtures (must exist before any Mindtrace import)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/test_logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/test_pids")


# ---------------------------------------------------------------------------
# Imports (after env fixture is declared so collection order is correct)
# ---------------------------------------------------------------------------

from mindtrace.models.optimization.prune import (  # noqa: E402
    ChannelPruner,
    PruningSchedule,
    magnitude_prune,
    sparsity,
    to_sparse_24,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NUM_CLASSES = 10


class TinyCNN(nn.Module):
    """Small CNN with a named ``head`` submodule for ignore-prefix tests."""

    def __init__(self, num_classes: int = NUM_CLASSES) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 16, 3, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(),
            nn.Conv2d(16, 32, 3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d(1),
        )
        self.head = nn.Linear(32, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.features(x).flatten(1))


def _param_count(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())


def _example_input() -> torch.Tensor:
    return torch.randn(2, 3, 16, 16)


# ===================================================================
# 1. ChannelPruner
# ===================================================================


class TestChannelPruner:
    def test_reduces_params_and_preserves_output_shape(self):
        torch.manual_seed(0)
        model = TinyCNN()
        params_before = _param_count(model)

        pruner = ChannelPruner(criterion="l1", sparsity=0.5, example_input=_example_input())
        model = pruner.run(model)

        params_after = _param_count(model)
        assert params_after < 0.8 * params_before  # meaningful reduction

        out = model(_example_input())
        assert out.shape == (2, NUM_CLASSES)

    def test_ignore_head_keeps_head_weight_shapes(self):
        torch.manual_seed(0)
        model = TinyCNN()
        head_weight_shape = tuple(model.head.weight.shape)
        head_bias_shape = tuple(model.head.bias.shape)
        params_before = _param_count(model)

        pruner = ChannelPruner(sparsity=0.5, ignore=["head"], example_input=_example_input())
        model = pruner.run(model)

        assert tuple(model.head.weight.shape) == head_weight_shape
        assert tuple(model.head.bias.shape) == head_bias_shape
        assert _param_count(model) < params_before
        assert model(_example_input()).shape == (2, NUM_CLASSES)

    def test_summary_consistent(self):
        torch.manual_seed(0)
        model = TinyCNN()

        pruner = ChannelPruner(sparsity=0.5, example_input=_example_input())

        with pytest.raises(RuntimeError):
            pruner.summary()

        model = pruner.run(model)
        stats = pruner.summary()

        assert set(stats) == {"params_before", "params_after", "flops_before", "flops_after"}
        assert stats["params_after"] < stats["params_before"]
        assert stats["flops_after"] < stats["flops_before"]
        assert stats["params_after"] == _param_count(model)

    def test_invalid_arguments(self):
        with pytest.raises(ValueError):
            ChannelPruner(criterion="bogus")
        with pytest.raises(ValueError):
            ChannelPruner(sparsity=1.5)
        with pytest.raises(ValueError):
            ChannelPruner().run(TinyCNN())  # no example_input


# ===================================================================
# 2. magnitude_prune + sparsity
# ===================================================================


class TestMagnitudePrune:
    def test_reaches_target_sparsity_and_forward_works(self):
        torch.manual_seed(0)
        model = TinyCNN()
        assert sparsity(model) < 0.01

        model = magnitude_prune(model, sparsity=0.6)

        assert sparsity(model) == pytest.approx(0.6, abs=0.02)
        # Masks must be removed: weights are plain parameters again.
        for module in model.modules():
            assert not hasattr(module, "weight_orig")
        assert model(_example_input()).shape == (2, NUM_CLASSES)

    def test_ignore_prefix_leaves_head_dense(self):
        torch.manual_seed(0)
        model = TinyCNN()
        model = magnitude_prune(model, sparsity=0.5, ignore=["head"])
        assert int((model.head.weight == 0).sum()) == 0
        assert sparsity(model) > 0.3

    def test_invalid_sparsity(self):
        with pytest.raises(ValueError):
            magnitude_prune(TinyCNN(), sparsity=1.2)


# ===================================================================
# 3. PruningSchedule with the real Trainer
# ===================================================================


class TestPruningSchedule:
    def test_schedule_reaches_final_sparsity_with_trainer(self):
        from mindtrace.models.training.trainer import Trainer

        torch.manual_seed(0)
        model = TinyCNN()

        x = torch.randn(16, 3, 8, 8)
        y = torch.randint(0, NUM_CLASSES, (16,))
        loader = DataLoader(TensorDataset(x, y), batch_size=8)

        schedule = PruningSchedule(final_sparsity=0.5, start_epoch=1, end_epoch=3, interval=1)
        trainer = Trainer(
            model=model,
            loss_fn=nn.CrossEntropyLoss(),
            optimizer=torch.optim.SGD(model.parameters(), lr=0.01),
            callbacks=[schedule],
            device="cpu",
        )
        trainer.fit(loader, epochs=4)

        # Masks removed at train end; weights are plain zeros near the target.
        for module in model.modules():
            assert not hasattr(module, "weight_orig")
        assert sparsity(model) == pytest.approx(0.5, abs=0.02)
        assert model(_example_input()).shape == (2, NUM_CLASSES)

    def test_invalid_arguments(self):
        with pytest.raises(ValueError):
            PruningSchedule(final_sparsity=1.0)
        with pytest.raises(ValueError):
            PruningSchedule(start_epoch=5, end_epoch=2)
        with pytest.raises(ValueError):
            PruningSchedule(interval=0)
        with pytest.raises(ValueError):
            PruningSchedule(criterion="l7")


# ===================================================================
# 4. to_sparse_24
# ===================================================================


class TestToSparse24:
    def test_exact_two_of_four_zeros_per_group(self):
        torch.manual_seed(0)
        model = TinyCNN()  # conv in-dims: 3*9=27 (tail of 3 skipped), 16*9=144; head in: 32
        model = to_sparse_24(model)

        for module in model.modules():
            if not isinstance(module, (nn.Conv2d, nn.Linear)):
                continue
            flat = module.weight.data.reshape(module.weight.shape[0], -1)
            num_groups = flat.shape[1] // 4
            groups = flat[:, : num_groups * 4].reshape(flat.shape[0], num_groups, 4)
            zeros_per_group = (groups == 0).sum(dim=-1)
            assert torch.all(zeros_per_group == 2), f"{module}: expected exactly 2 zeros per group of 4"

        assert model(_example_input()).shape == (2, NUM_CLASSES)

    def test_overall_sparsity_near_half(self):
        torch.manual_seed(0)
        model = nn.Sequential(nn.Linear(32, 64), nn.ReLU(), nn.Linear(64, 8))
        model = to_sparse_24(model)
        assert sparsity(model) == pytest.approx(0.5, abs=0.001)
        assert model(torch.randn(4, 32)).shape == (4, 8)
