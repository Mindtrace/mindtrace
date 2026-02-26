"""Generic HuggingFace vision backbone for any AutoModel-compatible model.

:class:`HuggingFaceBackbone` wraps *any* HuggingFace vision model (ViT,
ResNet, EfficientNet, ConvNeXt, Swin, …) behind a standard ``nn.Module``
that returns a ``(B, D)`` feature vector from :meth:`forward`.

The embed dimension is resolved from the model config in order of priority:

1. ``config.hidden_size``
2. ``config.hidden_sizes[-1]``  (ConvNeXt-style staged configs)
3. ``config.num_channels``       (fallback; rarely the right choice)

The output feature is resolved from the model output in order of priority:

1. ``outputs.pooler_output``           (ResNet, ViT with pooler head)
2. ``outputs.last_hidden_state[:, 0]`` (CLS token for ViT-style models)
3. ``outputs.last_hidden_state.mean(1)`` (mean-pool fallback)

This module is used by :func:`~mindtrace.models.architectures.factory.build_model_from_hf`
and is registered in the backbone registry under the model's HuggingFace
identifier at call time.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import torch
import torch.nn as nn

logger = logging.getLogger(__name__)

try:
    from transformers import AutoModel  # noqa: F401
    _HF_AVAILABLE = True
except ImportError:
    _HF_AVAILABLE = False


def _require_hf() -> None:
    if not _HF_AVAILABLE:
        raise ImportError(
            "transformers is required for generic HuggingFace backbones.  "
            "Install it with: pip install transformers"
        )


class HuggingFaceBackbone(nn.Module):
    """Generic wrapper around any HuggingFace AutoModel for feature extraction.

    Suitable for classification and detection tasks (returns a ``(B, D)``
    pooled feature vector).  For segmentation, use
    :class:`~mindtrace.models.architectures.backbones.dino_hf.HuggingFaceDINOBackbone`
    which exposes :meth:`forward_spatial`.

    Args:
        model_name_or_path: HuggingFace model ID or local directory path.
        pretrained: Load pretrained weights.  When ``False`` the model config
            is loaded and weights are randomly initialised.
        cache_dir: Optional HuggingFace cache directory.
        device: Device to place the model on (default ``"cpu"``).

    Example::

        from mindtrace.models.architectures.backbones.hf_generic import HuggingFaceBackbone

        bb = HuggingFaceBackbone("microsoft/resnet-50")
        features = bb(torch.randn(2, 3, 224, 224))  # (2, 2048)
    """

    def __init__(
        self,
        model_name_or_path: str,
        pretrained: bool = True,
        cache_dir: Optional[str] = None,
        device: str = "cpu",
    ) -> None:
        _require_hf()
        super().__init__()

        from transformers import AutoConfig, AutoModel  # noqa: PLC0415

        self.model_name_or_path = model_name_or_path

        if pretrained:
            self._hf_model = AutoModel.from_pretrained(
                model_name_or_path, cache_dir=cache_dir
            )
        else:
            cfg = AutoConfig.from_pretrained(model_name_or_path, cache_dir=cache_dir)
            self._hf_model = AutoModel.from_config(cfg)

        self._hf_model.to(device)
        self._device = device

    # ------------------------------------------------------------------
    # Embed-dim resolution
    # ------------------------------------------------------------------

    @property
    def embed_dim(self) -> int:
        """Output feature dimension, resolved from the model config."""
        cfg = self._hf_model.config
        if hasattr(cfg, "hidden_size") and cfg.hidden_size:
            return int(cfg.hidden_size)
        if hasattr(cfg, "hidden_sizes") and cfg.hidden_sizes:
            return int(cfg.hidden_sizes[-1])
        if hasattr(cfg, "num_channels"):
            return int(cfg.num_channels)
        raise AttributeError(
            f"Cannot determine embed_dim for '{self.model_name_or_path}'.  "
            "Set it explicitly via the 'embed_dim' argument to build_model_from_hf()."
        )

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        """Extract a ``(B, D)`` feature vector.

        Tries, in order:

        1. ``outputs.pooler_output``              — explicit pool head.
        2. ``outputs.last_hidden_state[:, 0]``    — CLS token.
        3. ``outputs.last_hidden_state.mean(1)``  — mean-pool fallback.

        Args:
            pixel_values: ``(B, C, H, W)`` float tensor.

        Returns:
            ``(B, D)`` feature tensor on the same device as the model.
        """
        dev = next(self._hf_model.parameters()).device
        outputs = self._hf_model(pixel_values=pixel_values.to(dev))

        if getattr(outputs, "pooler_output", None) is not None:
            return outputs.pooler_output

        hidden = outputs.last_hidden_state
        if hidden.ndim == 3:
            # (B, seq_len, D) — take CLS token
            return hidden[:, 0, :]
        if hidden.ndim == 4:
            # (B, H, W, C) ConvNeXt-style — global average pool
            return hidden.mean(dim=(1, 2))

        # Fallback: mean over non-batch dims
        return hidden.flatten(start_dim=1).mean(dim=1, keepdim=True).squeeze(1)


__all__ = ["HuggingFaceBackbone"]
