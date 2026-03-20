"""Segmentation loss functions for the MindTrace training pillar.

Provides region-overlap losses commonly used for semantic and instance
segmentation:

- ``DiceLoss``: Differentiable Dice coefficient loss.
- ``TverskyLoss``: Generalisation of Dice with asymmetric FP/FN weighting.
- ``IoULoss``: Jaccard / Intersection-over-Union loss.
"""

from __future__ import annotations

import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor


def _one_hot_encode(targets: Tensor, num_classes: int) -> Tensor:
    """One-hot encode integer class maps.

    Args:
        targets: Integer class indices of shape ``(N, H, W)``.
        num_classes: Total number of classes *C*.

    Returns:
        Float tensor of shape ``(N, C, H, W)`` with values in ``{0, 1}``.
    """
    # F.one_hot works on the last dim; we need to permute after
    one_hot = F.one_hot(targets.long(), num_classes=num_classes)  # (N, H, W, C)
    return one_hot.permute(0, 3, 1, 2).float()  # (N, C, H, W)


class DiceLoss(nn.Module):
    """Differentiable Dice loss for multi-class segmentation.

    Applies softmax to the raw logits, one-hot encodes the targets, then
    computes per-class Dice coefficients and averages them.  The Dice
    coefficient for class *c* is:

    .. math::

        \\text{Dice}_c
        = \\frac{2 \\sum_i p_{ic} \\, g_{ic} + \\varepsilon}
                {\\sum_i p_{ic} + \\sum_i g_{ic} + \\varepsilon}

    where :math:`p_{ic}` is the predicted probability and :math:`g_{ic}` is
    the one-hot ground-truth for pixel *i* and class *c*.

    Args:
        smooth: Laplace smoothing constant added to both numerator and
            denominator to prevent division by zero and improve gradient
            stability.
        reduction: How to reduce over classes: ``"mean"`` (default) or
            ``"none"`` (returns per-class losses).

    Example::

        criterion = DiceLoss(smooth=1.0)
        loss = criterion(logits, targets)  # logits: (N,C,H,W), targets: (N,H,W)
    """

    def __init__(self, smooth: float = 1.0, reduction: str = "mean") -> None:
        super().__init__()
        if reduction not in ("mean", "none"):
            raise ValueError(f"reduction must be 'mean' or 'none', got '{reduction}'")
        self.smooth = smooth
        self.reduction = reduction

    def forward(self, inputs: Tensor, targets: Tensor) -> Tensor:
        """Compute Dice loss.

        Args:
            inputs: Raw logits of shape ``(N, C, H, W)``.
            targets: Integer class indices of shape ``(N, H, W)``.

        Returns:
            Scalar mean Dice loss (when ``reduction="mean"``) or per-class
            losses of shape ``(C,)`` (when ``reduction="none"``).
        """
        num_classes = inputs.size(1)
        probs = F.softmax(inputs, dim=1)  # (N, C, H, W)
        targets_oh = _one_hot_encode(targets, num_classes)  # (N, C, H, W)

        # Flatten spatial and batch dims for each class: (N*H*W, C) → sum over N*H*W
        # We sum over N, H, W independently per class
        dims = (0, 2, 3)  # batch + spatial
        intersection = (probs * targets_oh).sum(dim=dims)  # (C,)
        denom = probs.sum(dim=dims) + targets_oh.sum(dim=dims)  # (C,)

        dice_per_class = (2.0 * intersection + self.smooth) / (denom + self.smooth)  # (C,)
        loss_per_class = 1.0 - dice_per_class

        if self.reduction == "mean":
            return loss_per_class.mean()
        return loss_per_class

    def extra_repr(self) -> str:
        return f"smooth={self.smooth}, reduction={self.reduction!r}"


class TverskyLoss(nn.Module):
    """Tversky loss — an asymmetric generalisation of Dice loss.

    Independently weights false positives and false negatives:

    .. math::

        \\text{Tversky}_c
        = \\frac{\\sum_i p_{ic} g_{ic} + \\varepsilon}
                {\\sum_i p_{ic} g_{ic}
                 + \\alpha \\sum_i p_{ic}(1-g_{ic})
                 + \\beta \\sum_i (1-p_{ic}) g_{ic}
                 + \\varepsilon}

    Setting ``alpha=0.5, beta=0.5`` recovers Dice loss.  Increasing ``beta``
    penalises false negatives more heavily — useful for small-structure
    segmentation where recall matters more than precision.

    Args:
        alpha: False-positive penalty weight.
        beta: False-negative penalty weight.
        smooth: Laplace smoothing constant.
        reduction: ``"mean"`` (default) or ``"none"``.

    Example::

        criterion = TverskyLoss(alpha=0.3, beta=0.7)
        loss = criterion(logits, targets)
    """

    def __init__(
        self,
        alpha: float = 0.3,
        beta: float = 0.7,
        smooth: float = 1.0,
        reduction: str = "mean",
    ) -> None:
        super().__init__()
        if reduction not in ("mean", "none"):
            raise ValueError(f"reduction must be 'mean' or 'none', got '{reduction}'")
        self.alpha = alpha
        self.beta = beta
        self.smooth = smooth
        self.reduction = reduction

    def forward(self, inputs: Tensor, targets: Tensor) -> Tensor:
        """Compute Tversky loss.

        Args:
            inputs: Raw logits of shape ``(N, C, H, W)``.
            targets: Integer class indices of shape ``(N, H, W)``.

        Returns:
            Scalar mean loss or per-class losses of shape ``(C,)``.
        """
        num_classes = inputs.size(1)
        probs = F.softmax(inputs, dim=1)  # (N, C, H, W)
        targets_oh = _one_hot_encode(targets, num_classes)  # (N, C, H, W)

        dims = (0, 2, 3)
        tp = (probs * targets_oh).sum(dim=dims)  # true positives
        fp = (probs * (1.0 - targets_oh)).sum(dim=dims)  # false positives
        fn = ((1.0 - probs) * targets_oh).sum(dim=dims)  # false negatives

        tversky = (tp + self.smooth) / (tp + self.alpha * fp + self.beta * fn + self.smooth)
        loss_per_class = 1.0 - tversky

        if self.reduction == "mean":
            return loss_per_class.mean()
        return loss_per_class

    def extra_repr(self) -> str:
        return f"alpha={self.alpha}, beta={self.beta}, smooth={self.smooth}, reduction={self.reduction!r}"


class IoULoss(nn.Module):
    """Jaccard / Intersection-over-Union loss for multi-class segmentation.

    Computes the IoU (Jaccard index) per class and returns ``1 - IoU`` as the
    loss:

    .. math::

        \\text{IoU}_c
        = \\frac{\\sum_i p_{ic} g_{ic} + \\varepsilon}
                {\\sum_i p_{ic} + \\sum_i g_{ic}
                 - \\sum_i p_{ic} g_{ic} + \\varepsilon}

    Args:
        smooth: Laplace smoothing constant.
        reduction: ``"mean"`` (default) or ``"none"``.

    Example::

        criterion = IoULoss()
        loss = criterion(logits, targets)
    """

    def __init__(self, smooth: float = 1.0, reduction: str = "mean") -> None:
        super().__init__()
        if reduction not in ("mean", "none"):
            raise ValueError(f"reduction must be 'mean' or 'none', got '{reduction}'")
        self.smooth = smooth
        self.reduction = reduction

    def forward(self, inputs: Tensor, targets: Tensor) -> Tensor:
        """Compute IoU (Jaccard) loss.

        Args:
            inputs: Raw logits of shape ``(N, C, H, W)``.
            targets: Integer class indices of shape ``(N, H, W)``.

        Returns:
            Scalar mean loss or per-class losses of shape ``(C,)``.
        """
        num_classes = inputs.size(1)
        probs = F.softmax(inputs, dim=1)  # (N, C, H, W)
        targets_oh = _one_hot_encode(targets, num_classes)  # (N, C, H, W)

        dims = (0, 2, 3)
        intersection = (probs * targets_oh).sum(dim=dims)  # (C,)
        sum_pred = probs.sum(dim=dims)
        sum_tgt = targets_oh.sum(dim=dims)
        union = sum_pred + sum_tgt - intersection

        iou_per_class = (intersection + self.smooth) / (union + self.smooth)
        loss_per_class = 1.0 - iou_per_class

        if self.reduction == "mean":
            return loss_per_class.mean()
        return loss_per_class

    def extra_repr(self) -> str:
        return f"smooth={self.smooth}, reduction={self.reduction!r}"
