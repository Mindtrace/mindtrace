"""Unit tests for `mindtrace.models.training.losses.classification`."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
F = pytest.importorskip("torch.nn.functional")

from mindtrace.models.training.losses.classification import (  # noqa: E402
    FocalLoss,
    LabelSmoothingCrossEntropy,
    SupConLoss,
)


class TestFocalLoss:
    def test_invalid_alpha_type_raises(self):
        with pytest.raises(TypeError, match="alpha must be a positive float"):
            FocalLoss(alpha=None)  # type: ignore[arg-type]

    def test_invalid_alpha_value_raises(self):
        with pytest.raises(ValueError, match="alpha must be > 0"):
            FocalLoss(alpha=0.0)

    def test_invalid_gamma_raises(self):
        with pytest.raises(ValueError, match="gamma must be >= 0"):
            FocalLoss(gamma=-1.0)

    def test_sum_reduction_matches_none_sum(self):
        inputs = torch.tensor([[2.0, 0.5], [0.2, 1.0]], dtype=torch.float32)
        targets = torch.tensor([0, 1])

        sum_loss = FocalLoss(alpha=1.0, gamma=2.0, reduction="sum")(inputs, targets)
        none_loss = FocalLoss(alpha=1.0, gamma=2.0, reduction="none")(inputs, targets)

        assert none_loss.shape == torch.Size([2])
        assert sum_loss.item() == pytest.approx(none_loss.sum().item())

    def test_extra_repr_reports_configuration(self):
        assert FocalLoss(alpha=0.5, gamma=1.5, reduction="sum").extra_repr() == "alpha=0.5, gamma=1.5, reduction='sum'"


class TestLabelSmoothingCrossEntropy:
    def test_invalid_reduction_raises(self):
        with pytest.raises(ValueError, match="reduction"):
            LabelSmoothingCrossEntropy(reduction="bad")

    def test_sum_reduction_matches_none_sum(self):
        inputs = torch.tensor([[2.0, 0.5], [0.2, 1.0]], dtype=torch.float32)
        targets = torch.tensor([0, 1])

        sum_loss = LabelSmoothingCrossEntropy(smoothing=0.1, reduction="sum")(inputs, targets)
        none_loss = LabelSmoothingCrossEntropy(smoothing=0.1, reduction="none")(inputs, targets)

        assert none_loss.shape == torch.Size([2])
        assert sum_loss.item() == pytest.approx(none_loss.sum().item())

    def test_extra_repr_reports_configuration(self):
        expected = "smoothing=0.2, reduction='none'"
        assert LabelSmoothingCrossEntropy(smoothing=0.2, reduction="none").extra_repr() == expected


class TestSupConLoss:
    def test_invalid_temperatures_raise(self):
        with pytest.raises(ValueError, match="temperature"):
            SupConLoss(temperature=0.0)
        with pytest.raises(ValueError, match="base_temperature"):
            SupConLoss(base_temperature=0.0)

    def test_mismatched_batch_sizes_raise(self):
        criterion = SupConLoss()
        features = F.normalize(torch.tensor([[1.0, 0.0], [0.0, 1.0]]), dim=1)
        labels = torch.tensor([0])

        with pytest.raises(ValueError, match="same batch size"):
            criterion(features, labels)

    def test_returns_zero_when_no_positive_pairs_exist(self):
        criterion = SupConLoss()
        features = F.normalize(
            torch.tensor(
                [
                    [1.0, 0.0],
                    [0.0, 1.0],
                    [1.0, 1.0],
                ]
            ),
            dim=1,
        )
        labels = torch.tensor([0, 1, 2])

        loss = criterion(features, labels)

        assert loss.shape == torch.Size([])
        assert loss.item() == pytest.approx(0.0)

    def test_identical_positive_pairs_produce_finite_positive_loss(self):
        criterion = SupConLoss(temperature=0.07, base_temperature=0.07)
        features = F.normalize(
            torch.tensor(
                [
                    [1.0, 0.0],
                    [1.0, 0.0],
                    [0.0, 1.0],
                    [0.0, 1.0],
                ]
            ),
            dim=1,
        )
        labels = torch.tensor([0, 0, 1, 1])

        loss = criterion(features, labels)

        assert loss.shape == torch.Size([])
        assert torch.isfinite(loss)
        assert loss.item() > 0.0

    def test_extra_repr_includes_configuration(self):
        criterion = SupConLoss(temperature=0.2, base_temperature=0.5)

        assert criterion.extra_repr() == "temperature=0.2, base_temperature=0.5"
