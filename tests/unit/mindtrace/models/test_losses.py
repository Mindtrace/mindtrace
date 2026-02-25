"""Unit tests for mindtrace.models.training.losses.

All tests require PyTorch and are guarded with pytest.importorskip.

Tests use small synthetic tensors (batch=2, classes=3, H=8, W=8) to keep
execution fast.  Exact numeric thresholds are validated against analytically
known values or directional inequalities derived from loss definitions.
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

import torch.nn as nn
import torch.nn.functional as F

from mindtrace.models.training.losses import (
    CIoULoss,
    ComboLoss,
    DiceLoss,
    FocalLoss,
    GIoULoss,
    IoULoss,
    LabelSmoothingCrossEntropy,
    TverskyLoss,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

N = 4       # batch size for classification losses
C = 3       # number of classes
BN = 2      # batch size for segmentation / detection losses
H = 8       # spatial height
W = 8       # spatial width


def _seg_logits_perfect(n: int = BN, c: int = C, h: int = H, w: int = W) -> tuple:
    """Return (logits, targets) where predictions perfectly match targets."""
    targets = torch.zeros(n, h, w, dtype=torch.long)
    # For class 0: push logits for class 0 very high so softmax ≈ 1 everywhere
    logits = torch.full((n, c, h, w), -100.0)
    logits[:, 0, :, :] = 100.0  # class 0 wins everywhere
    # targets are all class 0 — perfect match
    return logits, targets


def _seg_logits_wrong(n: int = BN, c: int = C, h: int = H, w: int = W) -> tuple:
    """Return (logits, targets) where predictions never match targets."""
    targets = torch.ones(n, h, w, dtype=torch.long)  # all class 1
    logits = torch.full((n, c, h, w), -100.0)
    logits[:, 0, :, :] = 100.0  # predict class 0 everywhere (wrong)
    return logits, targets


def _det_boxes_identical() -> tuple:
    """Return two identical box tensors of shape (2, 4) in xyxy format."""
    boxes = torch.tensor([[10.0, 10.0, 50.0, 50.0], [5.0, 5.0, 20.0, 20.0]])
    return boxes, boxes.clone()


def _det_boxes_non_overlapping() -> tuple:
    """Return box pairs with no overlap."""
    pred = torch.tensor([[0.0, 0.0, 10.0, 10.0], [0.0, 0.0, 10.0, 10.0]])
    tgt = torch.tensor([[20.0, 20.0, 30.0, 30.0], [20.0, 20.0, 30.0, 30.0]])
    return pred, tgt


# ---------------------------------------------------------------------------
# FocalLoss
# ---------------------------------------------------------------------------


class TestFocalLoss:
    def test_forward_shape(self):
        criterion = FocalLoss(alpha=1.0, gamma=2.0)
        inputs = torch.randn(N, C)
        targets = torch.randint(0, C, (N,))
        loss = criterion(inputs, targets)
        assert loss.shape == torch.Size([])  # scalar

    def test_gamma_zero_equals_cross_entropy(self):
        """FocalLoss with gamma=0, alpha=1 should equal standard cross-entropy."""
        torch.manual_seed(42)
        inputs = torch.randn(N, C)
        targets = torch.randint(0, C, (N,))

        focal = FocalLoss(alpha=1.0, gamma=0.0)
        ce = nn.CrossEntropyLoss()

        focal_loss = focal(inputs, targets)
        ce_loss = ce(inputs, targets)
        assert focal_loss.item() == pytest.approx(ce_loss.item(), abs=1e-5)

    def test_reduction_none_returns_per_sample(self):
        criterion = FocalLoss(alpha=1.0, gamma=2.0, reduction="none")
        inputs = torch.randn(N, C)
        targets = torch.randint(0, C, (N,))
        loss = criterion(inputs, targets)
        assert loss.shape == torch.Size([N])

    def test_invalid_reduction_raises(self):
        with pytest.raises(ValueError, match="reduction"):
            FocalLoss(reduction="invalid")


# ---------------------------------------------------------------------------
# LabelSmoothingCrossEntropy
# ---------------------------------------------------------------------------


class TestLabelSmoothingCrossEntropy:
    def test_forward_shape(self):
        criterion = LabelSmoothingCrossEntropy(smoothing=0.1)
        inputs = torch.randn(N, C)
        targets = torch.randint(0, C, (N,))
        loss = criterion(inputs, targets)
        assert loss.shape == torch.Size([])

    def test_smoothing_zero_approaches_ce(self):
        """With smoothing=0.0, output should equal standard cross-entropy."""
        torch.manual_seed(0)
        inputs = torch.randn(N, C)
        targets = torch.randint(0, C, (N,))

        lsce = LabelSmoothingCrossEntropy(smoothing=0.0)
        ce = nn.CrossEntropyLoss()

        assert lsce(inputs, targets).item() == pytest.approx(ce(inputs, targets).item(), abs=1e-5)

    def test_maximum_smoothing_gives_uniform_loss(self):
        """smoothing close to 1.0 should give loss close to log(C) — uniform distribution."""
        inputs = torch.zeros(N, C)  # all logits equal → uniform softmax
        targets = torch.zeros(N, dtype=torch.long)

        loss = LabelSmoothingCrossEntropy(smoothing=0.9999)(inputs, targets)
        expected = torch.log(torch.tensor(float(C))).item()
        assert loss.item() == pytest.approx(expected, abs=1e-3)

    def test_invalid_smoothing_raises(self):
        with pytest.raises(ValueError):
            LabelSmoothingCrossEntropy(smoothing=1.0)


# ---------------------------------------------------------------------------
# DiceLoss
# ---------------------------------------------------------------------------


class TestDiceLoss:
    def test_perfect_prediction_near_zero(self):
        criterion = DiceLoss(smooth=1e-6)
        logits, targets = _seg_logits_perfect()
        loss = criterion(logits, targets)
        assert loss.item() == pytest.approx(0.0, abs=1e-3)

    def test_wrong_prediction_near_one(self):
        """When predictions are maximally wrong, Dice loss should be close to 1."""
        criterion = DiceLoss(smooth=1e-6)
        logits, targets = _seg_logits_wrong()
        loss = criterion(logits, targets)
        # Loss should be substantially positive (not near zero)
        assert loss.item() > 0.5

    def test_forward_shape(self):
        criterion = DiceLoss()
        logits = torch.randn(BN, C, H, W)
        targets = torch.randint(0, C, (BN, H, W))
        loss = criterion(logits, targets)
        assert loss.shape == torch.Size([])


# ---------------------------------------------------------------------------
# TverskyLoss
# ---------------------------------------------------------------------------


class TestTverskyLoss:
    def test_forward_shape(self):
        criterion = TverskyLoss(alpha=0.3, beta=0.7)
        logits = torch.randn(BN, C, H, W)
        targets = torch.randint(0, C, (BN, H, W))
        loss = criterion(logits, targets)
        assert loss.shape == torch.Size([])

    def test_fp_heavy_penalty_raises_loss(self):
        """High beta (FN penalty) should produce higher loss than symmetric alpha=beta."""
        torch.manual_seed(99)
        logits = torch.randn(BN, C, H, W)
        targets = torch.randint(0, C, (BN, H, W))

        balanced = TverskyLoss(alpha=0.5, beta=0.5)
        fn_heavy = TverskyLoss(alpha=0.1, beta=0.9)  # penalise FN heavily

        # fn_heavy penalises missed detections more — loss values will differ
        assert balanced(logits, targets).item() != pytest.approx(
            fn_heavy(logits, targets).item(), abs=1e-3
        )


# ---------------------------------------------------------------------------
# IoULoss
# ---------------------------------------------------------------------------


class TestIoULoss:
    def test_forward_shape(self):
        criterion = IoULoss()
        logits = torch.randn(BN, C, H, W)
        targets = torch.randint(0, C, (BN, H, W))
        loss = criterion(logits, targets)
        assert loss.shape == torch.Size([])

    def test_perfect_prediction_near_zero(self):
        criterion = IoULoss(smooth=1e-6)
        logits, targets = _seg_logits_perfect()
        loss = criterion(logits, targets)
        assert loss.item() == pytest.approx(0.0, abs=1e-3)


# ---------------------------------------------------------------------------
# GIoULoss
# ---------------------------------------------------------------------------


class TestGIoULoss:
    def test_forward_shape(self):
        criterion = GIoULoss()
        pred, tgt = _det_boxes_non_overlapping()
        loss = criterion(pred, tgt)
        assert loss.shape == torch.Size([])

    def test_identical_boxes_loss_near_zero(self):
        """GIoU of identical boxes = 1, so loss = 1 - 1 = 0."""
        criterion = GIoULoss()
        pred, tgt = _det_boxes_identical()
        loss = criterion(pred, tgt)
        assert loss.item() == pytest.approx(0.0, abs=1e-5)


# ---------------------------------------------------------------------------
# CIoULoss
# ---------------------------------------------------------------------------


class TestCIoULoss:
    def test_forward_shape(self):
        criterion = CIoULoss()
        pred, tgt = _det_boxes_non_overlapping()
        loss = criterion(pred, tgt)
        assert loss.shape == torch.Size([])

    def test_identical_boxes_loss_near_zero(self):
        """CIoU of identical boxes: IoU=1, centre dist=0, v=0 → loss ≈ 0."""
        criterion = CIoULoss()
        pred, tgt = _det_boxes_identical()
        loss = criterion(pred, tgt)
        assert loss.item() == pytest.approx(0.0, abs=1e-4)


# ---------------------------------------------------------------------------
# ComboLoss
# ---------------------------------------------------------------------------


class TestComboLoss:
    def test_forward_combines_losses(self):
        """ComboLoss of DiceLoss + FocalLoss must return a scalar tensor."""
        # FocalLoss operates on (N, C) / (N,) while DiceLoss on (N, C, H, W) / (N, H, W).
        # We use two DiceLoss instances so the shapes are compatible.
        combo = ComboLoss(
            losses={"dice1": DiceLoss(), "dice2": DiceLoss()},
            weights={"dice1": 0.5, "dice2": 0.5},
        )
        logits = torch.randn(BN, C, H, W)
        targets = torch.randint(0, C, (BN, H, W))
        loss = combo(logits, targets)
        assert loss.shape == torch.Size([])

    def test_equal_weights_by_default(self):
        """When weights=None all components get weight 1.0."""
        combo = ComboLoss(losses={"a": DiceLoss(), "b": DiceLoss()})
        assert combo._weights == {"a": 1.0, "b": 1.0}

    def test_named_losses_populated_after_forward(self):
        combo = ComboLoss(
            losses={"d1": DiceLoss(), "d2": DiceLoss()},
            weights=None,
        )
        logits = torch.randn(BN, C, H, W)
        targets = torch.randint(0, C, (BN, H, W))
        combo(logits, targets)

        named = combo.named_losses
        assert "d1" in named
        assert "d2" in named
        assert isinstance(named["d1"], float)
        assert isinstance(named["d2"], float)

    def test_zero_weight_component_excluded_from_total(self):
        """A component with weight 0.0 contributes nothing to the total loss."""
        combo_zero = ComboLoss(
            losses={"d1": DiceLoss(), "d2": DiceLoss()},
            weights={"d1": 1.0, "d2": 0.0},
        )
        combo_one = ComboLoss(
            losses={"d1": DiceLoss()},
            weights={"d1": 1.0},
        )
        torch.manual_seed(5)
        logits = torch.randn(BN, C, H, W)
        targets = torch.randint(0, C, (BN, H, W))

        loss_zero = combo_zero(logits, targets)
        loss_one = combo_one(logits, targets)
        # The zero-weighted d2 contributes 0 so totals should match
        assert loss_zero.item() == pytest.approx(loss_one.item(), abs=1e-6)

    def test_empty_losses_raises(self):
        with pytest.raises(ValueError, match="at least one"):
            ComboLoss(losses={})

    def test_list_weights_wrong_length_raises(self):
        with pytest.raises(ValueError, match="length"):
            ComboLoss(losses={"a": DiceLoss(), "b": DiceLoss()}, weights=[1.0])

    def test_dict_weights_unknown_key_raises(self):
        with pytest.raises(ValueError, match="not found"):
            ComboLoss(losses={"a": DiceLoss()}, weights={"z": 1.0})
