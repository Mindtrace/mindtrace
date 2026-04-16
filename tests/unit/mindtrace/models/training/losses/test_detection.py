"""Unit tests for `mindtrace.models.training.losses.detection`."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from mindtrace.models.training.losses.detection import CIoULoss, GIoULoss  # noqa: E402


def _boxes():
    pred = torch.tensor([[0.0, 0.0, 2.0, 2.0], [1.0, 1.0, 3.0, 3.0]])
    tgt = torch.tensor([[0.0, 0.0, 2.0, 2.0], [0.0, 0.0, 4.0, 4.0]])
    return pred, tgt


class TestGIoULoss:
    def test_invalid_reduction_raises(self):
        with pytest.raises(ValueError, match="reduction"):
            GIoULoss(reduction="bad")

    def test_sum_reduction_matches_none_sum(self):
        pred, tgt = _boxes()
        sum_loss = GIoULoss(reduction="sum")(pred, tgt)
        none_loss = GIoULoss(reduction="none")(pred, tgt)

        assert none_loss.shape == torch.Size([2])
        assert sum_loss.item() == pytest.approx(none_loss.sum().item())

    def test_extra_repr_reports_reduction(self):
        assert GIoULoss(reduction="sum").extra_repr() == "reduction='sum'"


class TestCIoULoss:
    def test_invalid_reduction_raises(self):
        with pytest.raises(ValueError, match="reduction"):
            CIoULoss(reduction="bad")

    def test_sum_reduction_matches_none_sum(self):
        pred, tgt = _boxes()
        sum_loss = CIoULoss(reduction="sum")(pred, tgt)
        none_loss = CIoULoss(reduction="none")(pred, tgt)

        assert none_loss.shape == torch.Size([2])
        assert sum_loss.item() == pytest.approx(none_loss.sum().item())

    def test_extra_repr_reports_reduction(self):
        assert CIoULoss(reduction="none").extra_repr() == "reduction='none'"
