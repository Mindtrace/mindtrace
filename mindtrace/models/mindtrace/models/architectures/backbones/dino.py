"""DINOv2 backbone registrations via ``torch.hub``.

Registers the following variants:

===================  =================  ============
Registry name        Hub model          num_features
===================  =================  ============
``dino_v2_small``    ``dinov2_vits14``  384
``dino_v2_base``     ``dinov2_vitb14``  768
``dino_v2_large``    ``dinov2_vitl14``  1024
``dino_v2_giant``    ``dinov2_vitg14``  1536
===================  =================  ============

All hub downloads are guarded so that import errors or network failures at
module-load time are raised as ``RuntimeError`` at *call* time rather than at
import time.
"""

from __future__ import annotations

import torch
import torch.nn as nn

from mindtrace.models.architectures.backbones.registry import register_backbone


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_HUB_REPO = "facebookresearch/dinov2"

# Map (registry_name) -> (hub_model_name, num_features)
_DINO_VARIANTS: dict[str, tuple[str, int]] = {
    "dino_v2_small": ("dinov2_vits14", 384),
    "dino_v2_base": ("dinov2_vitb14", 768),
    "dino_v2_large": ("dinov2_vitl14", 1024),
    "dino_v2_giant": ("dinov2_vitg14", 1536),
}


def _make_dino_factory(
    hub_name: str,
    num_features: int,
) -> object:
    """Return a factory closure for a specific DINOv2 hub model.

    Args:
        hub_name: Name of the model in the ``facebookresearch/dinov2`` hub
            repository (e.g. ``"dinov2_vitb14"``).
        num_features: Output embedding dimension of the model.

    Returns:
        A callable matching the backbone-factory contract
        ``(pretrained: bool = True) -> tuple[nn.Module, int]``.
    """

    def factory(pretrained: bool = True) -> tuple[nn.Module, int]:
        """Load a DINOv2 backbone from ``torch.hub``.

        Args:
            pretrained: When ``True`` (default), downloads pretrained weights
                from the ``facebookresearch/dinov2`` hub.  When ``False``,
                the model is initialised with random weights.

        Returns:
            A tuple of ``(model, num_features)``.

        Raises:
            RuntimeError: If the hub download fails or the model cannot be
                instantiated.
        """
        try:
            model: nn.Module = torch.hub.load(
                _HUB_REPO,
                hub_name,
                pretrained=pretrained,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load DINOv2 model '{hub_name}' from hub "
                f"'{_HUB_REPO}'. Ensure you have an internet connection and "
                f"that 'torch.hub' can reach GitHub. Original error: {exc}"
            ) from exc

        return model, num_features

    factory.__name__ = f"_build_{hub_name}"
    factory.__qualname__ = factory.__name__
    return factory


# ---------------------------------------------------------------------------
# Register all variants
# ---------------------------------------------------------------------------

for _registry_name, (_hub_name, _nf) in _DINO_VARIANTS.items():
    register_backbone(_registry_name)(_make_dino_factory(_hub_name, _nf))
