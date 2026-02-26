"""mindtrace.models.architectures — backbone + head assembly for ML models.

This sub-package exposes the full public API for building, registering, and
composing backbone/head architectures:

Backbone API::

    from mindtrace.models.architectures import (
        build_backbone,   # instantiate a registered backbone
        list_backbones,   # enumerate available backbone names
        register_backbone,  # decorator to add custom backbones
        BackboneInfo,     # dataclass returned by build_backbone
    )

Head classes::

    from mindtrace.models.architectures import (
        LinearHead, MLPHead, MultiLabelHead,   # classification
        LinearSegHead, FPNSegHead,              # segmentation
        DetectionHead,                          # detection
    )

High-level factory::

    from mindtrace.models.architectures import build_model, ModelWrapper

    model = build_model(
        backbone="resnet50",
        head="linear",
        num_classes=10,
        pretrained=True,
    )

Importing this package triggers registration of all built-in backbones
(ResNet, ViT, EfficientNet via torchvision; DINOv2 via torch.hub).
"""

from __future__ import annotations

# Backbones (also triggers all variant registrations via sub-package __init__)
from mindtrace.models.architectures.backbones import (
    BackboneInfo,
    build_backbone,
    list_backbones,
    register_backbone,
)

# Heads
from mindtrace.models.architectures.heads import (
    DetectionHead,
    FPNSegHead,
    LinearHead,
    LinearSegHead,
    MLPHead,
    MultiLabelHead,
)

# High-level factory
from mindtrace.models.architectures.factory import ModelWrapper, build_model, build_model_from_hf

__all__ = [
    # Backbone registry
    "BackboneInfo",
    "build_backbone",
    "list_backbones",
    "register_backbone",
    # Model factory
    "ModelWrapper",
    "build_model",
    "build_model_from_hf",
    # Classification heads
    "LinearHead",
    "MLPHead",
    "MultiLabelHead",
    # Segmentation heads
    "FPNSegHead",
    "LinearSegHead",
    # Detection heads
    "DetectionHead",
]
