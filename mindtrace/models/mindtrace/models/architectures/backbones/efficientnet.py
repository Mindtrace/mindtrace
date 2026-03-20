"""EfficientNet backbone registrations via ``torchvision.models``.

Registers the following variants:

===================  ============
Registry name        num_features
===================  ============
``efficientnet_b0``  1280
``efficientnet_b3``  1536
``efficientnet_b5``  2048
``efficientnet_v2_s`` 1280
``efficientnet_v2_m`` 1280
===================  ============

The classifier head (``model.classifier``) is replaced with ``nn.Identity()``
so the backbone outputs the pooled feature vector rather than class logits.

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
    # Variant table:
    # (registry_name, tv_builder, default_weights, num_features)
    # -----------------------------------------------------------------------

    _EFFICIENTNET_VARIANTS: list[tuple[str, object, object, int]] = [
        (
            "efficientnet_b0",
            _tv_models.efficientnet_b0,
            _tv_models.EfficientNet_B0_Weights.IMAGENET1K_V1,
            1280,
        ),
        (
            "efficientnet_b3",
            _tv_models.efficientnet_b3,
            _tv_models.EfficientNet_B3_Weights.IMAGENET1K_V1,
            1536,
        ),
        (
            "efficientnet_b5",
            _tv_models.efficientnet_b5,
            _tv_models.EfficientNet_B5_Weights.IMAGENET1K_V1,
            2048,
        ),
        (
            "efficientnet_v2_s",
            _tv_models.efficientnet_v2_s,
            _tv_models.EfficientNet_V2_S_Weights.IMAGENET1K_V1,
            1280,
        ),
        (
            "efficientnet_v2_m",
            _tv_models.efficientnet_v2_m,
            _tv_models.EfficientNet_V2_M_Weights.IMAGENET1K_V1,
            1280,
        ),
    ]

    def _make_efficientnet_factory(
        tv_builder: object,
        default_weights: WeightsEnum,
        num_features: int,
    ) -> object:
        """Return a factory closure for a specific EfficientNet variant.

        Args:
            tv_builder: The ``torchvision.models`` builder function
                (e.g. ``torchvision.models.efficientnet_b0``).
            default_weights: The pretrained weights enum value to use when
                ``pretrained=True``.
            num_features: Number of output features after adaptive pooling
                (channel count of the penultimate feature map).

        Returns:
            A callable matching the backbone-factory contract
            ``(pretrained: bool = True) -> tuple[nn.Module, int]``.
        """

        def factory(pretrained: bool = True) -> tuple[nn.Module, int]:
            """Build an EfficientNet backbone with the classifier removed.

            ``model.classifier`` is replaced with ``nn.Identity()`` so
            ``forward()`` returns the pooled feature vector of shape
            ``(B, num_features)``.

            Args:
                pretrained: When ``True`` (default), loads ImageNet pretrained
                    weights.  When ``False``, uses random initialisation.

            Returns:
                A tuple of ``(model, num_features)`` where *model* outputs
                feature vectors of dimension *num_features*.
            """
            weights = default_weights if pretrained else None
            model: nn.Module = tv_builder(weights=weights)
            # EfficientNet in torchvision uses a Sequential as ``classifier``.
            # Replacing it with Identity passes the pooled features through.
            model.classifier = nn.Identity()
            return model, num_features

        return factory

    # Register all variants at import time.
    for _name, _builder, _weights, _nf in _EFFICIENTNET_VARIANTS:
        register_backbone(_name)(_make_efficientnet_factory(_builder, _weights, _nf))
