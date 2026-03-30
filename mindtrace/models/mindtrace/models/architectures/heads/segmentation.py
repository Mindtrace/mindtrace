"""Segmentation head modules.

Provides lightweight plug-and-play segmentation heads:

* :class:`LinearSegHead` -- 1×1 conv mapping feature channels to class logits.
* :class:`FPNSegHead` -- lightweight FPN-style head with 3×3 conv refinement.

Both heads return spatial logit maps of shape ``(B, num_classes, H, W)``.
Callers should apply ``F.interpolate`` to upsample to the original image
resolution before computing cross-entropy loss.
"""

from __future__ import annotations

import torch.nn as nn
from torch import Tensor


class LinearSegHead(nn.Module):
    """Minimal 1×1 convolution segmentation head.

    Maps the ``in_channels``-dimensional feature map produced by a backbone
    directly to per-pixel class logits via a single 1×1 convolution.  No
    spatial upsampling is performed; use ``torch.nn.functional.interpolate``
    downstream.

    Args:
        in_channels: Number of input feature channels (must match the
            channel dimension of the backbone output feature map).
        num_classes: Number of segmentation classes.

    Example:
        >>> head = LinearSegHead(in_channels=256, num_classes=21)
        >>> feat = torch.randn(2, 256, 32, 32)
        >>> logits = head(feat)  # shape (2, 21, 32, 32)
    """

    def __init__(self, in_channels: int, num_classes: int) -> None:
        super().__init__()
        self.conv = nn.Conv2d(in_channels, num_classes, kernel_size=1)

    def forward(self, x: Tensor) -> Tensor:
        """Produce per-pixel class logits.

        Args:
            x: Feature map of shape ``(B, in_channels, H, W)``.

        Returns:
            Logit map of shape ``(B, num_classes, H, W)``.
        """
        return self.conv(x)


class FPNSegHead(nn.Module):
    """Lightweight FPN-style segmentation head.

    Applies a 3×3 conv → BatchNorm → ReLU block to refine the feature map
    before projecting to class logits with a 1×1 conv.  The hidden dimension
    can be set independently of ``in_channels`` to control capacity.

    Args:
        in_channels: Number of input feature channels.
        num_classes: Number of segmentation classes.
        hidden_dim: Number of channels in the intermediate feature map.
            Defaults to ``256``.

    Example:
        >>> head = FPNSegHead(in_channels=512, num_classes=21, hidden_dim=256)
        >>> feat = torch.randn(2, 512, 32, 32)
        >>> logits = head(feat)  # shape (2, 21, 32, 32)
    """

    def __init__(
        self,
        in_channels: int,
        num_classes: int,
        hidden_dim: int = 256,
    ) -> None:
        super().__init__()

        self.refinement = nn.Sequential(
            nn.Conv2d(
                in_channels,
                hidden_dim,
                kernel_size=3,
                padding=1,
                bias=False,
            ),
            nn.BatchNorm2d(hidden_dim),
            nn.ReLU(inplace=True),
        )
        self.classifier = nn.Conv2d(hidden_dim, num_classes, kernel_size=1)

    def forward(self, x: Tensor) -> Tensor:
        """Produce per-pixel class logits.

        Args:
            x: Feature map of shape ``(B, in_channels, H, W)``.

        Returns:
            Logit map of shape ``(B, num_classes, H, W)``.
        """
        features = self.refinement(x)
        return self.classifier(features)
