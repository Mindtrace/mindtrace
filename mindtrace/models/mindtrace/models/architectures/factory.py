"""High-level factory for assembling backbone + head models.

The primary entry point is :func:`build_model`, which wires together a
registered backbone and a named head type into a single :class:`ModelWrapper`
module ready for training or inference.

Example::

    from mindtrace.models.architectures import build_model

    model = build_model(
        backbone="resnet50",
        head="mlp",
        num_classes=10,
        pretrained=True,
        freeze_backbone=False,
        dropout=0.2,
        hidden_dim=1024,
    )
    # model is an nn.Module; call model(x) directly.
"""

from __future__ import annotations

from typing import Any

import torch.nn as nn
from torch import Tensor

from mindtrace.models.architectures.backbones import BackboneInfo, build_backbone
from mindtrace.models.architectures.heads.classification import (
    LinearHead,
    MLPHead,
    MultiLabelHead,
)
from mindtrace.models.architectures.heads.segmentation import (
    FPNSegHead,
    LinearSegHead,
)

# ---------------------------------------------------------------------------
# Supported head type keys
# ---------------------------------------------------------------------------

_HEAD_TYPES: frozenset[str] = frozenset(
    {"linear", "mlp", "multilabel", "linear_seg", "fpn_seg"}
)


# ---------------------------------------------------------------------------
# ModelWrapper
# ---------------------------------------------------------------------------


class ModelWrapper(nn.Module):
    """An assembled backbone + head model.

    :class:`ModelWrapper` is a standard ``nn.Module`` that stores the backbone
    and head as registered sub-modules so that PyTorch's parameter / state-dict
    machinery works transparently.

    Args:
        backbone_info: A :class:`BackboneInfo` returned by
            :func:`build_backbone`, containing the model instance and its
            output feature dimension.
        head: The head ``nn.Module`` whose input dimension must match
            ``backbone_info.num_features``.

    Attributes:
        backbone_info: The :class:`BackboneInfo` passed at construction time
            (kept for introspection).
        backbone: The backbone ``nn.Module`` (alias of
            ``backbone_info.model``), registered as a sub-module.
        head: The head ``nn.Module``, registered as a sub-module.

    Example:
        >>> info = build_backbone("resnet50", pretrained=False)
        >>> head = LinearHead(info.num_features, num_classes=10)
        >>> model = ModelWrapper(info, head)
        >>> out = model(torch.randn(2, 3, 224, 224))
        >>> out.shape
        torch.Size([2, 10])
    """

    def __init__(self, backbone_info: BackboneInfo, head: nn.Module) -> None:
        super().__init__()

        self.backbone_info: BackboneInfo = backbone_info
        # Register as named sub-modules so parameters are tracked by PyTorch.
        self.backbone: nn.Module = backbone_info.model
        self.head: nn.Module = head

    def forward(self, x: Tensor) -> Any:
        """Run a forward pass through backbone then head.

        Args:
            x: Input tensor.  For image models this is typically of shape
                ``(B, C, H, W)``.

        Returns:
            The output of the head module.  Shape and type depend on the
            specific head (logits for classification, ``(cls, reg)`` tuple for
            detection, spatial maps for segmentation).
        """
        features: Tensor = self.backbone(x)
        return self.head(features)


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def build_model(
    backbone: str,
    head: str,
    num_classes: int,
    *,
    pretrained: bool = True,
    freeze_backbone: bool = False,
    dropout: float = 0.0,
    **backbone_kwargs: object,
) -> ModelWrapper:
    """Assemble a backbone + head model from registered components.

    Args:
        backbone: Registered backbone name (e.g. ``"dino_v2_base"``,
            ``"resnet50"``).  Must be present in the backbone registry;
            call :func:`list_backbones` to see available options.
        head: Head type identifier.  One of:

            * ``"linear"`` -- :class:`LinearHead` (single linear layer).
            * ``"mlp"`` -- :class:`MLPHead` (MLP with batch norm + dropout).
              Pass ``hidden_dim`` as a keyword argument to override the default
              of 512.  Pass ``num_layers`` to control depth (default: 2).
            * ``"multilabel"`` -- :class:`MultiLabelHead` (raw logits for
              ``BCEWithLogitsLoss``).
            * ``"linear_seg"`` -- :class:`LinearSegHead` (1×1 conv).
            * ``"fpn_seg"`` -- :class:`FPNSegHead` (3×3 conv + 1×1 conv).
              Pass ``hidden_dim`` to override the default of 256.

        num_classes: Number of output classes (or labels for multi-label).
        pretrained: Load pretrained backbone weights.  Defaults to ``True``.
        freeze_backbone: If ``True``, set ``requires_grad=False`` on all
            backbone parameters so they are excluded from gradient computation.
            Defaults to ``False``.
        dropout: Dropout rate forwarded to the head.  Defaults to ``0.0``.
        **backbone_kwargs: Additional keyword arguments forwarded verbatim to
            the backbone factory (e.g. extra hub options).  Note that
            ``hidden_dim`` and ``num_layers`` in *backbone_kwargs* are
            intercepted for the MLP head and *not* forwarded to the backbone.

    Returns:
        A :class:`ModelWrapper` containing the assembled model, ready for
        training or inference.

    Raises:
        KeyError: If *backbone* is not registered.
        ValueError: If *head* is not a recognised head type.

    Example:
        >>> model = build_model("resnet50", "mlp", num_classes=10,
        ...                     pretrained=False, dropout=0.2, hidden_dim=1024)
        >>> model.backbone_info.num_features
        2048
    """
    if head not in _HEAD_TYPES:
        raise ValueError(
            f"Unknown head type '{head}'. "
            f"Supported types: {sorted(_HEAD_TYPES)}"
        )

    # Extract head-specific kwargs before forwarding to backbone factory.
    hidden_dim_cls: int = int(backbone_kwargs.pop("hidden_dim", 512))
    num_layers: int = int(backbone_kwargs.pop("num_layers", 2))
    hidden_dim_seg: int = hidden_dim_cls  # re-use same kwarg for seg heads

    # Build backbone.
    backbone_info: BackboneInfo = build_backbone(
        backbone, pretrained=pretrained, **backbone_kwargs
    )
    in_features: int = backbone_info.num_features

    # Optionally freeze backbone parameters.
    if freeze_backbone:
        for param in backbone_info.model.parameters():
            param.requires_grad_(False)

    # Build head.
    head_module: nn.Module
    if head == "linear":
        head_module = LinearHead(
            in_features=in_features,
            num_classes=num_classes,
            dropout=dropout,
        )
    elif head == "mlp":
        head_module = MLPHead(
            in_features=in_features,
            hidden_dim=hidden_dim_cls,
            num_classes=num_classes,
            dropout=dropout,
            num_layers=num_layers,
        )
    elif head == "multilabel":
        head_module = MultiLabelHead(
            in_features=in_features,
            num_classes=num_classes,
            dropout=dropout,
        )
    elif head == "linear_seg":
        head_module = LinearSegHead(
            in_channels=in_features,
            num_classes=num_classes,
        )
    else:  # "fpn_seg"
        head_module = FPNSegHead(
            in_channels=in_features,
            num_classes=num_classes,
            hidden_dim=hidden_dim_seg,
        )

    return ModelWrapper(backbone_info=backbone_info, head=head_module)
