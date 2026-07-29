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
    area1 = (boxes1[:, 2] - boxes1[:, 0]).clamp(min=0.0) * (boxes1[:, 3] - boxes1[:, 1]).clamp(min=0.0)
    area2 = (boxes2[:, 2] - boxes2[:, 0]).clamp(min=0.0) * (boxes2[:, 3] - boxes2[:, 1]).clamp(min=0.0)

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
            raise ValueError(f"reduction must be 'mean', 'sum', or 'none', got '{reduction}'")
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

        enc_area = (enc_x2 - enc_x1).clamp(min=0.0) * (enc_y2 - enc_y1).clamp(min=0.0)

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
            raise ValueError(f"reduction must be 'mean', 'sum', or 'none', got '{reduction}'")
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

        v = (4.0 / (math.pi**2)) * (torch.atan(gt_w / gt_h) - torch.atan(pred_w / pred_h)) ** 2

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


# ---------------------------------------------------------------------------
# Set-prediction detection: box helpers, Hungarian matcher, set criterion.
#
# These train a query-based detector such as ``QueryDetectionHead``: a fixed set
# of queries is matched one-to-one to the ground-truth boxes, matched queries are
# supervised on class + box, and the rest are pushed to a no-object class.
# ---------------------------------------------------------------------------


def box_cxcywh_to_xyxy(boxes: Tensor) -> Tensor:
    """Convert ``(cx, cy, w, h)`` boxes to ``(x1, y1, x2, y2)``."""
    cx, cy, w, h = boxes.unbind(-1)
    return torch.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], dim=-1)


def generalized_box_iou_pairwise(boxes1: Tensor, boxes2: Tensor) -> Tensor:
    """Pairwise generalised IoU between two sets of ``(x1, y1, x2, y2)`` boxes.

    Args:
        boxes1: ``[N, 4]`` xyxy boxes.
        boxes2: ``[M, 4]`` xyxy boxes.

    Returns:
        ``[N, M]`` GIoU matrix in ``[-1, 1]``.
    """
    area1 = (boxes1[:, 2] - boxes1[:, 0]).clamp(min=0) * (boxes1[:, 3] - boxes1[:, 1]).clamp(min=0)
    area2 = (boxes2[:, 2] - boxes2[:, 0]).clamp(min=0) * (boxes2[:, 3] - boxes2[:, 1]).clamp(min=0)
    lt = torch.max(boxes1[:, None, :2], boxes2[None, :, :2])
    rb = torch.min(boxes1[:, None, 2:], boxes2[None, :, 2:])
    wh = (rb - lt).clamp(min=0)
    inter = wh[..., 0] * wh[..., 1]
    union = area1[:, None] + area2[None, :] - inter
    iou = inter / union.clamp(min=1e-7)
    lt_c = torch.min(boxes1[:, None, :2], boxes2[None, :, :2])
    rb_c = torch.max(boxes1[:, None, 2:], boxes2[None, :, 2:])
    wh_c = (rb_c - lt_c).clamp(min=0)
    enclosing = wh_c[..., 0] * wh_c[..., 1]
    return iou - (enclosing - union) / enclosing.clamp(min=1e-7)


class HungarianMatcher(nn.Module):
    """Optimal one-to-one assignment between queries and ground-truth boxes.

    The assignment minimises a cost that combines negative class probability,
    L1 box distance, and negative pairwise GIoU (all in normalized ``cxcywh``
    box space). Requires ``scipy`` (imported lazily on first use).

    Args:
        w_class: Weight on the classification cost.
        w_bbox: Weight on the L1 box cost.
        w_giou: Weight on the GIoU cost.
    """

    def __init__(self, w_class: float = 1.0, w_bbox: float = 5.0, w_giou: float = 2.0) -> None:
        super().__init__()
        self.w_class, self.w_bbox, self.w_giou = w_class, w_bbox, w_giou

    @torch.no_grad()
    def forward(self, logits: Tensor, boxes: Tensor, targets: list[dict]) -> list[tuple[Tensor, Tensor]]:
        """Match per image.

        Args:
            logits: ``[B, Q, C + 1]`` class logits (last column is no-object).
            boxes: ``[B, Q, 4]`` predicted ``cxcywh`` boxes in ``[0, 1]``.
            targets: Length-``B`` list of ``{"boxes": [M, 4] cxcywh, "labels": [M]}``.

        Returns:
            Length-``B`` list of ``(query_index, target_index)`` LongTensor pairs.
        """
        from scipy.optimize import linear_sum_assignment

        prob = logits.softmax(-1)
        matches: list[tuple[Tensor, Tensor]] = []
        for b in range(logits.size(0)):
            tgt_boxes = targets[b]["boxes"].to(logits.device)
            tgt_labels = targets[b]["labels"].to(logits.device)
            if tgt_boxes.numel() == 0:
                empty = torch.empty(0, dtype=torch.long)
                matches.append((empty, empty))
                continue
            cost_class = -prob[b][:, tgt_labels]
            cost_bbox = torch.cdist(boxes[b], tgt_boxes, p=1)
            cost_giou = -generalized_box_iou_pairwise(box_cxcywh_to_xyxy(boxes[b]), box_cxcywh_to_xyxy(tgt_boxes))
            cost = self.w_bbox * cost_bbox + self.w_class * cost_class + self.w_giou * cost_giou
            qi, ti = linear_sum_assignment(cost.cpu().numpy())
            matches.append((torch.as_tensor(qi, dtype=torch.long), torch.as_tensor(ti, dtype=torch.long)))
        return matches


class DetectionSetCriterion(nn.Module):
    """Set-prediction loss for a query-based detector.

    Matches queries to ground truth with :class:`HungarianMatcher`, then applies
    a weighted class cross-entropy over all queries (unmatched ones supervised to
    the no-object class) plus L1 and GIoU box losses over the matched pairs.

    Args:
        num_classes: Number of foreground categories. The no-object class is
            index ``num_classes`` (so ``logits`` must have ``num_classes + 1``
            columns).
        matcher: Assignment module; a default :class:`HungarianMatcher` is built
            from the loss weights when omitted.
        w_class: Weight on the classification loss.
        w_bbox: Weight on the L1 box loss.
        w_giou: Weight on the GIoU box loss.
        no_object_weight: Down-weight applied to the no-object class in the
            cross-entropy, to counter its dominance.
    """

    def __init__(
        self,
        num_classes: int,
        matcher: HungarianMatcher | None = None,
        w_class: float = 1.0,
        w_bbox: float = 5.0,
        w_giou: float = 2.0,
        no_object_weight: float = 0.1,
    ) -> None:
        super().__init__()
        self.num_classes = num_classes
        self.matcher = matcher or HungarianMatcher(w_class, w_bbox, w_giou)
        self.w_class, self.w_bbox, self.w_giou = w_class, w_bbox, w_giou
        class_weight = torch.ones(num_classes + 1)
        class_weight[num_classes] = no_object_weight
        self.register_buffer("class_weight", class_weight)

    def forward(self, outputs: dict[str, Tensor], targets: list[dict]) -> dict[str, Tensor]:
        """Compute the set-prediction loss.

        Args:
            outputs: ``{"logits": [B, Q, C + 1], "boxes": [B, Q, 4] cxcywh}``.
            targets: Length-``B`` list of ``{"boxes": [M, 4] cxcywh, "labels": [M]}``.

        Returns:
            Dict with the scalar ``"loss"`` and the detached ``"loss_class"``,
            ``"loss_bbox"``, and ``"loss_giou"`` components.
        """
        logits, boxes = outputs["logits"], outputs["boxes"]
        batch, num_queries, _ = logits.shape
        indices = self.matcher(logits, boxes, targets)
        target_classes = torch.full((batch, num_queries), self.num_classes, dtype=torch.long, device=logits.device)
        box_loss = boxes.new_zeros(())
        giou_loss = boxes.new_zeros(())
        matched = 0
        for b, (qi, ti) in enumerate(indices):
            if len(qi) == 0:
                continue
            tgt_boxes = targets[b]["boxes"].to(logits.device)
            tgt_labels = targets[b]["labels"].to(logits.device)
            target_classes[b, qi] = tgt_labels[ti]
            box_loss = box_loss + torch.nn.functional.l1_loss(boxes[b][qi], tgt_boxes[ti], reduction="sum")
            giou = generalized_box_iou_pairwise(box_cxcywh_to_xyxy(boxes[b][qi]), box_cxcywh_to_xyxy(tgt_boxes[ti]))
            giou_loss = giou_loss + (1 - giou.diag()).sum()
            matched += len(qi)
        matched = max(matched, 1)
        class_loss = torch.nn.functional.cross_entropy(
            logits.reshape(-1, logits.size(-1)), target_classes.reshape(-1), weight=self.class_weight
        )
        total = self.w_class * class_loss + self.w_bbox * box_loss / matched + self.w_giou * giou_loss / matched
        return {
            "loss": total,
            "loss_class": class_loss.detach(),
            "loss_bbox": (box_loss / matched).detach(),
            "loss_giou": (giou_loss / matched).detach(),
        }
