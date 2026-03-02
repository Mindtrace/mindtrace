"""Backbone protocol: standardised output contract for all backbone adapters.

Defines :class:`BackboneFeatures` (the canonical output) and
:class:`BackboneProtocol` (the abstract base that every backbone adapter must
satisfy).  Consumers programme against these types rather than concrete adapter
classes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import torch
import torch.nn as nn


@dataclass
class BackboneFeatures:
    """Normalised output from any backbone adapter.

    Attributes:
        cls_token:     Global image representation, shape ``(B, D)``.
        patch_tokens:  Spatial tokens, shape ``(B, N, D)``, or ``None`` when
                       the backbone does not expose patch-level features.
        embed_dim:     Feature dimensionality ``D``.
    """

    cls_token: torch.Tensor
    patch_tokens: Optional[torch.Tensor]
    embed_dim: int


class BackboneProtocol(nn.Module, ABC):
    """Abstract base class for all backbone adapters.

    Subclasses must implement :attr:`embed_dim` and :meth:`extract`.
    :meth:`forward` delegates to :meth:`extract` so the adapter is usable as a
    standard ``nn.Module``.
    """

    @property
    @abstractmethod
    def embed_dim(self) -> int:
        """Output feature dimensionality."""

    @abstractmethod
    def extract(self, pixel_values: torch.Tensor) -> BackboneFeatures:
        """Extract features from a batch of pre-processed images.

        Args:
            pixel_values: Float tensor of shape ``(B, C, H, W)``.

        Returns:
            A :class:`BackboneFeatures` instance.
        """

    def forward(self, pixel_values: torch.Tensor) -> BackboneFeatures:
        """Alias for :meth:`extract`, enabling standard ``nn.Module`` usage."""
        return self.extract(pixel_values)
