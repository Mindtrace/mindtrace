"""Detection head module.

Provides a generic two-branch anchor-based detection head that can be coupled
with any backbone producing a flat feature vector.  For production detection
models (DETR, YOLO, etc.) the backbone-specific heads are typically defined
alongside the full model architecture; this module is intended as a reusable
building block for simpler single-scale detection tasks.
"""

from __future__ import annotations

import torch
import torch.nn as nn
from torch import Tensor

from mindtrace.models.architectures.heads.attention import DecoderBlock

__all__ = ["DetectionHead", "QueryDetectionHead"]


class DetectionHead(nn.Module):
    """Anchor-based two-branch detection head.

    Produces parallel classification and bounding-box regression outputs from
    a flat feature vector.

    Architecture::

        x (B, in_channels)
        ├─► cls_branch  → Linear(in_channels, num_classes)       → cls_logits  (B, num_classes)
        └─► reg_branch  → Linear(in_channels, 4 * num_anchors)   → bbox_reg    (B, 4 * num_anchors)

    The ``bbox_reg`` output encodes ``(dx, dy, dw, dh)`` deltas relative to
    anchor boxes.  Decoding the deltas into absolute coordinates is the
    responsibility of the caller.

    Args:
        in_channels: Dimensionality of the input feature vector.
        num_classes: Number of foreground object categories (background class
            is *not* included — callers using cross-entropy should add it
            separately if required).
        num_anchors: Number of anchor boxes per spatial location.  Defaults
            to ``1``.  The regression output has shape
            ``(B, 4 * num_anchors)``.

    Example:
        >>> head = DetectionHead(in_channels=2048, num_classes=80, num_anchors=3)
        >>> feat = torch.randn(4, 2048)
        >>> cls_logits, bbox_reg = head(feat)
        >>> cls_logits.shape   # (4, 80)
        torch.Size([4, 80])
        >>> bbox_reg.shape     # (4, 12)  — 3 anchors × 4 coords
        torch.Size([4, 12])
    """

    def __init__(
        self,
        in_channels: int,
        num_classes: int,
        num_anchors: int = 1,
    ) -> None:
        super().__init__()

        self.cls_branch = nn.Linear(in_channels, num_classes)
        self.reg_branch = nn.Linear(in_channels, 4 * num_anchors)

    def forward(self, x: Tensor) -> tuple[Tensor, Tensor]:
        """Compute classification logits and bounding-box regression deltas.

        Args:
            x: Feature tensor of shape ``(B, in_channels)``.

        Returns:
            A tuple ``(cls_logits, bbox_reg)`` where:

            * ``cls_logits`` has shape ``(B, num_classes)`` — raw class scores.
            * ``bbox_reg`` has shape ``(B, 4 * num_anchors)`` — regression
              deltas ``(dx, dy, dw, dh)`` for each anchor.
        """
        cls_logits: Tensor = self.cls_branch(x)
        bbox_reg: Tensor = self.reg_branch(x)
        return cls_logits, bbox_reg


class QueryDetectionHead(nn.Module):
    """Query-based detection head over backbone patch tokens (DETR-style).

    Where :class:`DetectionHead` regresses from a pooled vector, this head keeps
    the backbone's patch tokens and attaches a fixed set of learned object
    queries. The queries self-attend to each other and cross-attend to the patch
    tokens through a stack of transformer decoder blocks (the same
    :class:`~mindtrace.models.architectures.heads.attention.DecoderBlock` used by
    the multi-task head), then each query predicts a class distribution — with an
    extra trailing "no-object" class — and one normalized box.

    Train it as set prediction with
    :class:`~mindtrace.models.training.losses.detection.HungarianMatcher` and
    :class:`~mindtrace.models.training.losses.detection.DetectionSetCriterion`.

    Args:
        dim: Backbone token dimension (the ``D`` of the ``[B, N, D]`` input).
        num_classes: Number of foreground categories. A trailing no-object class
            is added internally, so ``logits`` has ``num_classes + 1`` columns.
        num_queries: Number of object slots (upper bound on detections per image).
        layers: Number of stacked decoder blocks.
        num_heads: Attention heads per block.
        ffn_mult: Hidden expansion factor of each block's feed-forward sub-layer.

    The forward pass returns ``{"logits": [B, Q, num_classes + 1], "boxes":
    [B, Q, 4]}`` where boxes are ``(cx, cy, w, h)`` normalized to ``[0, 1]``.
    """

    def __init__(
        self,
        dim: int,
        num_classes: int,
        num_queries: int = 100,
        layers: int = 6,
        num_heads: int = 8,
        ffn_mult: int = 4,
    ) -> None:
        super().__init__()
        if num_classes < 1:
            raise ValueError("QueryDetectionHead requires num_classes >= 1.")
        if num_queries < 1:
            raise ValueError("QueryDetectionHead requires num_queries >= 1.")
        self.num_queries = num_queries
        self.num_classes = num_classes
        self.queries = nn.Parameter(torch.randn(1, num_queries, dim) * 0.02)
        self.token_norm = nn.LayerNorm(dim)
        self.blocks = nn.ModuleList([DecoderBlock(dim, num_heads, ffn_mult) for _ in range(layers)])
        self.norm = nn.LayerNorm(dim)
        self.class_head = nn.Linear(dim, num_classes + 1)
        self.box_head = nn.Sequential(nn.Linear(dim, dim), nn.ReLU(), nn.Linear(dim, dim), nn.ReLU(), nn.Linear(dim, 4))

    def forward(self, tokens: Tensor) -> dict[str, Tensor]:
        """Decode object queries against patch tokens.

        Args:
            tokens: Patch tokens of shape ``[B, N, D]`` from a token-level backbone.

        Returns:
            Dict with ``"logits"`` ``[B, Q, num_classes + 1]`` (raw class scores,
            last column is no-object) and ``"boxes"`` ``[B, Q, 4]`` as
            ``(cx, cy, w, h)`` in ``[0, 1]``.
        """
        context = self.token_norm(tokens)
        queries = self.queries.expand(tokens.size(0), -1, -1)
        for block in self.blocks:
            queries = block(queries, context)
        queries = self.norm(queries)
        return {"logits": self.class_head(queries), "boxes": self.box_head(queries).sigmoid()}
