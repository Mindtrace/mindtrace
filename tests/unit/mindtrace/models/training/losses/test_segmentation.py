"""Unit tests for `mindtrace.models.training.losses.segmentation`."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from mindtrace.models.training.losses.segmentation import DiceLoss, IoULoss, TverskyLoss  # noqa: E402


def _segmentation_batch():
    logits = torch.randn(2, 3, 4, 4)
    targets = torch.randint(0, 3, (2, 4, 4))
    return logits, targets


class TestDiceLoss:
    def test_invalid_reduction_raises(self):
        with pytest.raises(ValueError, match="reduction"):
            DiceLoss(reduction="sum")

    def test_none_reduction_returns_per_class_values(self):
        logits, targets = _segmentation_batch()

        loss = DiceLoss(reduction="none")(logits, targets)

        assert loss.shape == torch.Size([3])

    def test_extra_repr_reports_configuration(self):
        assert DiceLoss(smooth=0.5, reduction="none").extra_repr() == "smooth=0.5, reduction='none'"


class TestTverskyLoss:
    def test_invalid_reduction_raises(self):
        with pytest.raises(ValueError, match="reduction"):
            TverskyLoss(reduction="sum")

    def test_none_reduction_returns_per_class_values(self):
        logits, targets = _segmentation_batch()

        loss = TverskyLoss(alpha=0.2, beta=0.8, reduction="none")(logits, targets)

        assert loss.shape == torch.Size([3])

    def test_extra_repr_reports_configuration(self):
        expected = "alpha=0.2, beta=0.8, smooth=0.5, reduction='none'"
        assert TverskyLoss(alpha=0.2, beta=0.8, smooth=0.5, reduction="none").extra_repr() == expected


class TestIoULoss:
    def test_invalid_reduction_raises(self):
        with pytest.raises(ValueError, match="reduction"):
            IoULoss(reduction="sum")

    def test_none_reduction_returns_per_class_values(self):
        logits, targets = _segmentation_batch()

        loss = IoULoss(reduction="none")(logits, targets)

        assert loss.shape == torch.Size([3])

    def test_extra_repr_reports_configuration(self):
        assert IoULoss(smooth=0.25, reduction="none").extra_repr() == "smooth=0.25, reduction='none'"
