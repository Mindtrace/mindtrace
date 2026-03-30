"""Detection head module.

Provides a generic two-branch anchor-based detection head that can be coupled
with any backbone producing a flat feature vector.  For production detection
models (DETR, YOLO, etc.) the backbone-specific heads are typically defined
alongside the full model architecture; this module is intended as a reusable
building block for simpler single-scale detection tasks.
"""

from __future__ import annotations

import torch.nn as nn
from torch import Tensor


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
