"""ResNet backbone registrations via ``torchvision.models``.

Registers the following variants:

=============  ============
Registry name  num_features
=============  ============
``resnet18``   512
``resnet34``   512
``resnet50``   2048
``resnet101``  2048
``resnet152``  2048
=============  ============

The final fully-connected layer is replaced with ``nn.Identity()`` so that
the backbone outputs feature vectors rather than class logits.

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

    _RESNET_VARIANTS: list[tuple[str, object, object, int]] = [
        (
            "resnet18",
            _tv_models.resnet18,
            _tv_models.ResNet18_Weights.IMAGENET1K_V1,
            512,
        ),
        (
            "resnet34",
            _tv_models.resnet34,
            _tv_models.ResNet34_Weights.IMAGENET1K_V1,
            512,
        ),
        (
            "resnet50",
            _tv_models.resnet50,
            _tv_models.ResNet50_Weights.IMAGENET1K_V2,
            2048,
        ),
        (
            "resnet101",
            _tv_models.resnet101,
            _tv_models.ResNet101_Weights.IMAGENET1K_V2,
            2048,
        ),
        (
            "resnet152",
            _tv_models.resnet152,
            _tv_models.ResNet152_Weights.IMAGENET1K_V2,
            2048,
        ),
    ]

    def _make_resnet_factory(
        tv_builder: object,
        default_weights: WeightsEnum,
        num_features: int,
    ) -> object:
        """Return a factory closure for a specific ResNet variant.

        Args:
            tv_builder: The ``torchvision.models`` builder function
                (e.g. ``torchvision.models.resnet50``).
            default_weights: The pretrained weights enum value to use when
                ``pretrained=True``.
            num_features: Number of output features after the pooling layer
                (i.e. the dimension of the penultimate layer).

        Returns:
            A callable matching the backbone-factory contract
            ``(pretrained: bool = True) -> tuple[nn.Module, int]``.
        """

        def factory(pretrained: bool = True) -> tuple[nn.Module, int]:
            """Build a ResNet backbone with the FC layer removed.

            Args:
                pretrained: When ``True`` (default), loads ImageNet pretrained
                    weights.  When ``False``, uses random initialisation.

            Returns:
                A tuple of ``(model, num_features)`` where *model* outputs
                feature vectors of dimension *num_features*.
            """
            weights = default_weights if pretrained else None
            model: nn.Module = tv_builder(weights=weights)
            # Replace classification head with identity so the backbone
            # outputs raw feature vectors.
            model.fc = nn.Identity()
            return model, num_features

        return factory

    # Register all variants at import time.
    for _name, _builder, _weights, _nf in _RESNET_VARIANTS:
        register_backbone(_name)(_make_resnet_factory(_builder, _weights, _nf))
