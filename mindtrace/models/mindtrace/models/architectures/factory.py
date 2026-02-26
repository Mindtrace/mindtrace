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
import torch.nn.functional as F
from torch import Tensor

from mindtrace.models.architectures.backbones import BackboneInfo, build_backbone

# Optional generic HuggingFace backbone
try:
    from mindtrace.models.architectures.backbones.hf_generic import (  # noqa: PLC0415
        HuggingFaceBackbone as _HFGenericBackbone,
    )
    _HF_GENERIC_AVAILABLE = True
except Exception:
    _HFGenericBackbone = None   # type: ignore[assignment,misc]
    _HF_GENERIC_AVAILABLE = False
from mindtrace.models.architectures.heads.classification import (
    LinearHead,
    MLPHead,
    MultiLabelHead,
)
from mindtrace.models.architectures.heads.segmentation import (
    FPNSegHead,
    LinearSegHead,
)

# Optional HuggingFace DINO import — only needed for seg routing
try:
    from mindtrace.models.architectures.backbones.dino_hf import (  # noqa: PLC0415
        HuggingFaceDINOBackbone as _HFBackbone,
    )
    _HF_DINO_AVAILABLE = True
except Exception:
    _HFBackbone = None          # type: ignore[assignment,misc]
    _HF_DINO_AVAILABLE = False

# ---------------------------------------------------------------------------
# Supported head type keys
# ---------------------------------------------------------------------------

_HEAD_TYPES: frozenset[str] = frozenset(
    {"linear", "mlp", "multilabel", "linear_seg", "fpn_seg"}
)
_SEG_HEAD_TYPES: frozenset[str] = frozenset({"linear_seg", "fpn_seg"})


# ---------------------------------------------------------------------------
# ModelWrapper
# ---------------------------------------------------------------------------


class HFDINOSegWrapper(nn.Module):
    """Assembled HF-DINO backbone + segmentation head.

    Unlike :class:`ModelWrapper`, which uses the CLS token, this wrapper:

    1. Calls ``backbone.forward_spatial()`` → ``(B, D, H_p, W_p)`` patch map.
    2. Passes that map through the segmentation head.
    3. Bilinearly upsamples the output back to the input resolution.

    Instantiated automatically by :func:`build_model` when an HF DINO
    backbone is paired with a segmentation head (``"linear_seg"`` or
    ``"fpn_seg"``).  You do not need to use this class directly.

    Example::

        model = build_model("dino_v3_small", "fpn_seg", num_classes=19)
        # model is an HFDINOSegWrapper — call model(x) directly.
        logits = model(images)  # (B, 19, H, W)
    """

    def __init__(self, backbone_info: BackboneInfo, head: nn.Module) -> None:
        super().__init__()
        self.backbone_info: BackboneInfo = backbone_info
        self.backbone: nn.Module = backbone_info.model
        self.head: nn.Module = head

    def forward(self, x: Tensor) -> Tensor:
        """Spatial forward: extract patch map → head → upsample to input size."""
        H, W = x.shape[2], x.shape[3]
        spatial = self.backbone.forward_spatial(x)   # (B, D, H_p, W_p)
        logits  = self.head(spatial)                 # (B, C, H_p, W_p)
        return F.interpolate(logits, size=(H, W), mode="bilinear", align_corners=False)


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

    # HF DINO + segmentation head → spatial patch-token path with auto-upsample
    is_hf = _HF_DINO_AVAILABLE and isinstance(backbone_info.model, _HFBackbone)
    if is_hf and head in _SEG_HEAD_TYPES:
        return HFDINOSegWrapper(backbone_info=backbone_info, head=head_module)

    return ModelWrapper(backbone_info=backbone_info, head=head_module)


def build_model_from_hf(
    model_name_or_path: str,
    head: str,
    num_classes: int,
    *,
    pretrained: bool = True,
    freeze_backbone: bool = False,
    embed_dim: int | None = None,
    dropout: float = 0.0,
    cache_dir: str | None = None,
    **head_kwargs: Any,
) -> ModelWrapper:
    """Assemble a model from *any* HuggingFace vision backbone + a task head.

    Unlike :func:`build_model`, which requires the backbone to be pre-registered
    under a short name, this factory accepts any HuggingFace model identifier
    directly.  It resolves the embedding dimension automatically from the model
    config, or accepts an explicit override via *embed_dim*.

    Args:
        model_name_or_path: HuggingFace model ID (e.g.
            ``"microsoft/resnet-50"``, ``"google/vit-base-patch16-224"``) or
            path to a local checkpoint directory.
        head: Head type — one of ``"linear"``, ``"mlp"``, ``"multilabel"``.
            Segmentation heads (``"linear_seg"``, ``"fpn_seg"``) are *not*
            supported here because arbitrary HF models do not expose a
            standardised spatial feature map.  Use
            :class:`~mindtrace.models.architectures.backbones.dino_hf.HuggingFaceDINOBackbone`
            with :func:`build_model` for segmentation.
        num_classes: Number of output classes.
        pretrained: Load pretrained HuggingFace weights.  Defaults to ``True``.
        freeze_backbone: Freeze backbone parameters.  Defaults to ``False``.
        embed_dim: Override the automatically detected embedding dimension.
            Useful when config introspection fails for an unusual architecture.
        dropout: Dropout rate forwarded to the head.
        cache_dir: Optional HuggingFace cache directory.
        **head_kwargs: Additional keyword arguments forwarded to the head
            constructor (e.g. ``hidden_dim``, ``num_layers`` for ``"mlp"``).

    Returns:
        A :class:`ModelWrapper` ready for training or inference.

    Raises:
        ImportError: If ``transformers`` is not installed.
        ValueError: If *head* is a segmentation head type.

    Example::

        from mindtrace.models.architectures import build_model_from_hf

        model = build_model_from_hf(
            "microsoft/resnet-50",
            head="linear",
            num_classes=10,
            pretrained=True,
        )
        output = model(torch.randn(2, 3, 224, 224))  # (2, 10)
    """
    if not _HF_GENERIC_AVAILABLE:
        raise ImportError(
            "transformers is required for build_model_from_hf().  "
            "Install it with: pip install transformers"
        )

    if head in _SEG_HEAD_TYPES:
        raise ValueError(
            f"Segmentation heads ({sorted(_SEG_HEAD_TYPES)}) are not supported "
            "by build_model_from_hf().  Use build_model() with a registered DINO "
            "backbone for segmentation."
        )

    if head not in _HEAD_TYPES:
        raise ValueError(
            f"Unknown head type '{head}'. Supported types: {sorted(_HEAD_TYPES)}"
        )

    backbone = _HFGenericBackbone(
        model_name_or_path=model_name_or_path,
        pretrained=pretrained,
        cache_dir=cache_dir,
    )

    in_features = embed_dim if embed_dim is not None else backbone.embed_dim
    backbone_info = BackboneInfo(model=backbone, num_features=in_features)

    if freeze_backbone:
        for param in backbone.parameters():
            param.requires_grad_(False)

    # Build head
    hidden_dim: int = int(head_kwargs.pop("hidden_dim", 512))
    num_layers: int = int(head_kwargs.pop("num_layers", 2))

    head_module: nn.Module
    if head == "linear":
        head_module = LinearHead(in_features=in_features, num_classes=num_classes, dropout=dropout)
    elif head == "mlp":
        head_module = MLPHead(
            in_features=in_features,
            hidden_dim=hidden_dim,
            num_classes=num_classes,
            dropout=dropout,
            num_layers=num_layers,
        )
    else:  # "multilabel"
        head_module = MultiLabelHead(in_features=in_features, num_classes=num_classes, dropout=dropout)

    return ModelWrapper(backbone_info=backbone_info, head=head_module)
