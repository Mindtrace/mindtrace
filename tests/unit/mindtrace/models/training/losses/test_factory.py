"""Unit tests for the loss factory and multi-task composition."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
nn = pytest.importorskip("torch.nn")

import torch.nn.functional as F  # noqa: E402

from mindtrace.models.training.losses.factory import MultiTaskLoss, TaskSpec, build_loss  # noqa: E402


class TestBuildLoss:
    @pytest.mark.parametrize("name, cls", [
        ("cross_entropy", nn.CrossEntropyLoss),
        ("ce", nn.CrossEntropyLoss),
        ("mse", nn.MSELoss),
        ("l1", nn.L1Loss),
        ("mae", nn.L1Loss),
        ("huber", nn.HuberLoss),
        ("bce_with_logits", nn.BCEWithLogitsLoss),
    ])
    def test_torch_losses_by_name(self, name, cls):
        assert isinstance(build_loss(name), cls)

    def test_case_insensitive(self):
        assert isinstance(build_loss("MSE"), nn.MSELoss)

    def test_mindtrace_loss(self):
        loss = build_loss("focal", gamma=2.0)
        assert type(loss).__name__ == "FocalLoss"

    def test_kwargs_forwarded(self):
        loss = build_loss("cross_entropy", label_smoothing=0.1)
        assert loss.label_smoothing == 0.1

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="unknown loss"):
            build_loss("nonexistent")


class TestMultiTaskLoss:
    def _make(self):
        return MultiTaskLoss({
            "cls": TaskSpec(build_loss("cross_entropy"), output=0, target="cls"),
            "reg": TaskSpec(build_loss("mse"), output=1, target="reg", weight=0.5),
        })

    def test_routes_each_loss_to_its_head_and_target(self):
        loss = self._make()
        logits = torch.randn(4, 3)
        reg = torch.randn(4)
        targets = {"cls": torch.randint(0, 3, (4,)), "reg": torch.randn(4)}
        outputs = (logits, reg)

        total = loss(outputs, targets)
        # Matches the explicit weighted sum of the two routed sub-losses.
        expected = F.cross_entropy(logits, targets["cls"]) + 0.5 * F.mse_loss(reg, targets["reg"])
        assert torch.allclose(total, expected)

    def test_named_losses_cached_for_logging(self):
        loss = self._make()
        loss((torch.randn(4, 3), torch.randn(4)), {"cls": torch.randint(0, 3, (4,)), "reg": torch.randn(4)})
        named = loss.named_losses
        assert set(named) == {"cls", "reg"} and all(isinstance(v, float) for v in named.values())

    def test_supports_dict_outputs(self):
        loss = MultiTaskLoss({"a": TaskSpec(build_loss("mse"), output="a", target="a")})
        out = loss({"a": torch.zeros(3)}, {"a": torch.zeros(3)})
        assert float(out) == 0.0

    def test_backward_flows(self):
        model_out = (torch.randn(4, 3, requires_grad=True), torch.randn(4, requires_grad=True))
        loss = self._make()
        loss(model_out, {"cls": torch.randint(0, 3, (4,)), "reg": torch.randn(4)}).backward()
        assert all(o.grad is not None for o in model_out)

    def test_empty_tasks_rejected(self):
        with pytest.raises(ValueError, match="at least one task"):
            MultiTaskLoss({})
