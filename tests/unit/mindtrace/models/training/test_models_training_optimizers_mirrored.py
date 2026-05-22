"""Additional mirrored tests for `mindtrace.models.training.optimizers`."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
import torch.nn as nn  # noqa: E402
from torch.optim import RMSprop  # noqa: E402
from torch.optim.lr_scheduler import OneCycleLR  # noqa: E402

from mindtrace.models.training.optimizers import build_optimizer, build_scheduler  # noqa: E402


class TinyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = nn.Linear(4, 4)
        self.head = nn.Linear(4, 2)

    def forward(self, x):
        return self.head(self.backbone(x))


@pytest.fixture()
def model():
    return TinyModel()


@pytest.fixture()
def optimizer(model):
    return torch.optim.SGD(model.parameters(), lr=0.01)


class TestBuildOptimizerMirrored:
    def test_rmsprop_supported(self, model):
        opt = build_optimizer("rmsprop", model, lr=1e-3)

        assert isinstance(opt, RMSprop)

    def test_explicit_param_groups_list_passthrough(self, model):
        param_groups = [
            {"params": model.backbone.parameters(), "lr": 1e-4},
            {"params": model.head.parameters(), "lr": 1e-3},
        ]

        opt = build_optimizer("adamw", param_groups, weight_decay=1e-2)

        assert len(opt.param_groups) == 2
        assert opt.param_groups[0]["lr"] == pytest.approx(1e-4)
        assert opt.param_groups[1]["lr"] == pytest.approx(1e-3)

    def test_backbone_lr_multiplier_requires_backbone_and_head(self):
        plain_model = nn.Linear(4, 2)

        with pytest.raises(ValueError, match=r"\.backbone'.*\.head"):
            build_optimizer("adamw", plain_model, lr=1e-3, backbone_lr_multiplier=0.1)

    def test_backbone_lr_multiplier_requires_lr_kwarg(self, model):
        with pytest.raises(ValueError, match="requires 'lr'"):
            build_optimizer("adamw", model, backbone_lr_multiplier=0.1)

    def test_backbone_lr_multiplier_builds_differential_groups(self, model):
        opt = build_optimizer("adamw", model, lr=1e-3, backbone_lr_multiplier=0.1)

        assert len(opt.param_groups) == 2
        assert opt.param_groups[0]["lr"] == pytest.approx(1e-4)
        assert opt.param_groups[1]["lr"] == pytest.approx(1e-3)


class TestBuildSchedulerMirrored:
    def test_plateau_missing_args_raises(self, optimizer):
        with pytest.raises(TypeError, match="patience.*factor"):
            build_scheduler("plateau", optimizer, patience=1)

    def test_onecycle_returns_scheduler(self, optimizer):
        scheduler = build_scheduler("onecycle", optimizer, max_lr=0.1, total_steps=5)

        assert isinstance(scheduler, OneCycleLR)

    def test_onecycle_missing_args_raises(self, optimizer):
        with pytest.raises(TypeError, match="max_lr.*total_steps"):
            build_scheduler("onecycle", optimizer, max_lr=0.1)
