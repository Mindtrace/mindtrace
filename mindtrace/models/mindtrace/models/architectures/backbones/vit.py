"""Vision Transformer backbone registrations via ``torchvision.models``.

Registers the following variants:

=============  ============
Registry name  num_features
=============  ============
``vit_b_16``   768
``vit_b_32``   768
``vit_l_16``   1024
=============  ============

The classification head (``model.heads``) is replaced with ``nn.Identity()``
so the backbone outputs the raw CLS-token embedding rather than class logits.

This module is a no-op if ``torchvision`` is not installed.
"""

from __future__ import annotations

try:
    import torchvision.models as _tv_models
    from torchvision.models import WeightsEnum

    _TORCHVISION_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TORCHVISION_AVAILABLE = False

import torch.nn as nn

from mindtrace.models.architectures.backbones.registry import register_backbone

if _TORCHVISION_AVAILABLE:
    # -----------------------------------------------------------------------
    # Variant table: (registry_name, tv_builder, default_weights, num_features)
    # -----------------------------------------------------------------------

    _VIT_VARIANTS: list[tuple[str, object, object, int]] = [
        (
            "vit_b_16",
            _tv_models.vit_b_16,
            _tv_models.ViT_B_16_Weights.IMAGENET1K_V1,
            768,
        ),
        (
            "vit_b_32",
            _tv_models.vit_b_32,
            _tv_models.ViT_B_32_Weights.IMAGENET1K_V1,
            768,
        ),
        (
            "vit_l_16",
            _tv_models.vit_l_16,
            _tv_models.ViT_L_16_Weights.IMAGENET1K_V1,
            1024,
        ),
    ]

    def _make_vit_factory(
        tv_builder: object,
        default_weights: WeightsEnum,
        num_features: int,
    ) -> object:
        """Return a factory closure for a specific ViT variant.

        Args:
            tv_builder: The ``torchvision.models`` builder function
                (e.g. ``torchvision.models.vit_b_16``).
            default_weights: The pretrained weights enum value to use when
                ``pretrained=True``.
            num_features: Dimensionality of the CLS-token embedding output.

        Returns:
            A callable matching the backbone-factory contract
            ``(pretrained: bool = True) -> tuple[nn.Module, int]``.
        """

        def factory(pretrained: bool = True) -> tuple[nn.Module, int]:
            """Build a ViT backbone with the classification head removed.

            The ``model.heads`` attribute is replaced with ``nn.Identity()``
            so ``forward()`` returns the raw CLS-token feature vector of
            shape ``(B, num_features)``.

            Args:
                pretrained: When ``True`` (default), loads ImageNet pretrained
                    weights.  When ``False``, uses random initialisation.

            Returns:
                A tuple of ``(model, num_features)`` where *model* outputs
                embeddings of dimension *num_features*.
            """
            weights = default_weights if pretrained else None
            model: nn.Module = tv_builder(weights=weights)
            # torchvision ViT exposes the classification head as ``heads``.
            # Replacing it with Identity passes the raw encoder output through.
            model.heads = nn.Identity()
            return model, num_features

        return factory

    # Register all variants at import time.
    for _name, _builder, _weights, _nf in _VIT_VARIANTS:
        register_backbone(_name)(_make_vit_factory(_builder, _weights, _nf))
