"""Bounding-box detection loss functions for the MindTrace training pillar.

Provides:
- ``GIoULoss``: Generalised Intersection-over-Union loss.
- ``CIoULoss``: Complete Intersection-over-Union loss with aspect-ratio term.

Both losses expect boxes in ``(x1, y1, x2, y2)`` absolute-coordinate format
and return ``1 - IoU_variant`` so that minimising the loss maximises overlap.
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn
from torch import Tensor


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _box_iou(boxes1: Tensor, boxes2: Tensor) -> tuple[Tensor, Tensor, Tensor, Tensor]:
    """Compute pairwise IoU between two sets of axis-aligned boxes.

    Boxes are expected in ``(x1, y1, x2, y2)`` format where ``x1 < x2`` and
    ``y1 < y2``.  Inputs are clamped internally so that degenerate boxes
    (zero area) produce an IoU of 0 rather than NaN.

    Args:
        boxes1: Tensor of shape ``(N, 4)``.
        boxes2: Tensor of shape ``(N, 4)``, paired element-wise with *boxes1*.

    Returns:
        A 4-tuple ``(iou, inter_area, area1, area2)`` where each element is a
        1-D tensor of length *N*.

        - ``iou``: Intersection-over-Union for each pair.
        - ``inter_area``: Intersection area for each pair.
        - ``area1``: Area of each box in *boxes1*.
        - ``area2``: Area of each box in *boxes2*.
    """
    # Intersection
    inter_x1 = torch.max(boxes1[:, 0], boxes2[:, 0])
    inter_y1 = torch.max(boxes1[:, 1], boxes2[:, 1])
    inter_x2 = torch.min(boxes1[:, 2], boxes2[:, 2])
    inter_y2 = torch.min(boxes1[:, 3], boxes2[:, 3])

    inter_w = (inter_x2 - inter_x1).clamp(min=0.0)
    inter_h = (inter_y2 - inter_y1).clamp(min=0.0)
    inter_area = inter_w * inter_h

    # Individual areas (clamped to 0 for degenerate boxes)
    area1 = ((boxes1[:, 2] - boxes1[:, 0]).clamp(min=0.0)
             * (boxes1[:, 3] - boxes1[:, 1]).clamp(min=0.0))
    area2 = ((boxes2[:, 2] - boxes2[:, 0]).clamp(min=0.0)
             * (boxes2[:, 3] - boxes2[:, 1]).clamp(min=0.0))

    union_area = area1 + area2 - inter_area
    iou = inter_area / (union_area + 1e-7)

    return iou, inter_area, area1, area2


# ---------------------------------------------------------------------------
# GIoU
# ---------------------------------------------------------------------------


class GIoULoss(nn.Module):
    """Generalised Intersection-over-Union (GIoU) loss.

    GIoU extends IoU with a penalty term based on the area of the smallest
    enclosing box, providing a meaningful gradient even for non-overlapping
    boxes:

    .. math::

        \\mathcal{L}_{GIoU} = 1 - IoU + \\frac{|C \\setminus (A \\cup B)|}{|C|}

    where *C* is the smallest axis-aligned enclosing box of *A* and *B*.

    Args:
        reduction: ``"mean"`` (default), ``"sum"``, or ``"none"``.

    Reference:
        Rezatofighi et al. "Generalized Intersection over Union: A Metric and
        A Loss for Bounding Box Regression." CVPR 2019.

    Example::

        criterion = GIoULoss()
        loss = criterion(pred_boxes, target_boxes)  # boxes: (N, 4) xyxy
    """

    def __init__(self, reduction: str = "mean") -> None:
        super().__init__()
        if reduction not in ("mean", "sum", "none"):
            raise ValueError(
                f"reduction must be 'mean', 'sum', or 'none', got '{reduction}'"
            )
        self.reduction = reduction

    def forward(self, pred_boxes: Tensor, target_boxes: Tensor) -> Tensor:
        """Compute GIoU loss.

        Args:
            pred_boxes: Predicted boxes of shape ``(N, 4)`` in
                ``(x1, y1, x2, y2)`` format.
            target_boxes: Ground-truth boxes of shape ``(N, 4)`` in the same
                format.

        Returns:
            Scalar loss (when ``reduction`` is ``"mean"`` or ``"sum"``) or
            per-pair losses of shape ``(N,)`` when ``reduction="none"``.
        """
        iou, inter_area, area1, area2 = _box_iou(pred_boxes, target_boxes)

        union_area = area1 + area2 - inter_area

        # Smallest enclosing box
        enc_x1 = torch.min(pred_boxes[:, 0], target_boxes[:, 0])
        enc_y1 = torch.min(pred_boxes[:, 1], target_boxes[:, 1])
        enc_x2 = torch.max(pred_boxes[:, 2], target_boxes[:, 2])
        enc_y2 = torch.max(pred_boxes[:, 3], target_boxes[:, 3])

        enc_area = (
            (enc_x2 - enc_x1).clamp(min=0.0)
            * (enc_y2 - enc_y1).clamp(min=0.0)
        )

        giou = iou - (enc_area - union_area) / (enc_area + 1e-7)
        per_pair_loss = 1.0 - giou

        if self.reduction == "mean":
            return per_pair_loss.mean()
        if self.reduction == "sum":
            return per_pair_loss.sum()
        return per_pair_loss

    def extra_repr(self) -> str:
        return f"reduction={self.reduction!r}"


# ---------------------------------------------------------------------------
# CIoU
# ---------------------------------------------------------------------------


class CIoULoss(nn.Module):
    """Complete Intersection-over-Union (CIoU) loss.

    CIoU augments GIoU with:
    - An overlap factor (IoU).
    - A centre-distance penalty term.
    - An aspect-ratio consistency term :math:`v` weighted by a trade-off
      factor :math:`\\alpha`.

    .. math::

        \\mathcal{L}_{CIoU} = 1 - IoU + \\frac{\\rho^2(b, b^{gt})}{c^2} + \\alpha v

    where :math:`\\rho` is the Euclidean centre distance, *c* is the diagonal
    length of the enclosing box, and
    :math:`v = \\frac{4}{\\pi^2}(\\arctan(w^{gt}/h^{gt}) - \\arctan(w/h))^2`.

    Args:
        reduction: ``"mean"`` (default), ``"sum"``, or ``"none"``.

    Reference:
        Zheng et al. "Distance-IoU Loss: Faster and Better Learning for
        Bounding Box Regression." AAAI 2020.

    Example::

        criterion = CIoULoss()
        loss = criterion(pred_boxes, target_boxes)
    """

    def __init__(self, reduction: str = "mean") -> None:
        super().__init__()
        if reduction not in ("mean", "sum", "none"):
            raise ValueError(
                f"reduction must be 'mean', 'sum', or 'none', got '{reduction}'"
            )
        self.reduction = reduction

    def forward(self, pred_boxes: Tensor, target_boxes: Tensor) -> Tensor:
        """Compute CIoU loss.

        Args:
            pred_boxes: Predicted boxes of shape ``(N, 4)`` in
                ``(x1, y1, x2, y2)`` format.
            target_boxes: Ground-truth boxes of shape ``(N, 4)`` in the same
                format.

        Returns:
            Scalar loss or per-pair losses of shape ``(N,)``, depending on
            ``self.reduction``.
        """
        iou, _inter_area, _area1, _area2 = _box_iou(pred_boxes, target_boxes)

        # Centres of predicted and target boxes
        pred_cx = (pred_boxes[:, 0] + pred_boxes[:, 2]) / 2.0
        pred_cy = (pred_boxes[:, 1] + pred_boxes[:, 3]) / 2.0
        gt_cx = (target_boxes[:, 0] + target_boxes[:, 2]) / 2.0
        gt_cy = (target_boxes[:, 1] + target_boxes[:, 3]) / 2.0

        # Squared Euclidean distance between centres
        rho2 = (pred_cx - gt_cx) ** 2 + (pred_cy - gt_cy) ** 2

        # Smallest enclosing box diagonal squared
        enc_x1 = torch.min(pred_boxes[:, 0], target_boxes[:, 0])
        enc_y1 = torch.min(pred_boxes[:, 1], target_boxes[:, 1])
        enc_x2 = torch.max(pred_boxes[:, 2], target_boxes[:, 2])
        enc_y2 = torch.max(pred_boxes[:, 3], target_boxes[:, 3])

        c2 = (enc_x2 - enc_x1) ** 2 + (enc_y2 - enc_y1) ** 2

        # Aspect-ratio consistency term v
        pred_w = (pred_boxes[:, 2] - pred_boxes[:, 0]).clamp(min=1e-7)
        pred_h = (pred_boxes[:, 3] - pred_boxes[:, 1]).clamp(min=1e-7)
        gt_w = (target_boxes[:, 2] - target_boxes[:, 0]).clamp(min=1e-7)
        gt_h = (target_boxes[:, 3] - target_boxes[:, 1]).clamp(min=1e-7)

        v = (4.0 / (math.pi ** 2)) * (
            torch.atan(gt_w / gt_h) - torch.atan(pred_w / pred_h)
        ) ** 2

        # Trade-off factor alpha (non-negative gradient stop on v)
        with torch.no_grad():
            alpha_w = v / (1.0 - iou + v + 1e-7)

        ciou = iou - rho2 / (c2 + 1e-7) - alpha_w * v
        per_pair_loss = 1.0 - ciou

        if self.reduction == "mean":
            return per_pair_loss.mean()
        if self.reduction == "sum":
            return per_pair_loss.sum()
        return per_pair_loss

    def extra_repr(self) -> str:
        return f"reduction={self.reduction!r}"
