"""Concrete backbone adapters for timm, torchvision, and mindtrace registry.

Each adapter wraps a different model source behind the unified
:class:`~mindtrace.models.architectures.backbones.protocol.BackboneProtocol`
interface.

.. note::

    The DINO adapter is deliberately *not* included here.  DINO depends on
    domain-specific LoRA configuration and model wrappers that live in
    downstream packages (e.g. ``mip``).  Use
    :class:`~mindtrace.models.architectures.backbones.dino_hf.HuggingFaceDINOBackbone`
    for a generic HuggingFace DINO backbone.
"""

from __future__ import annotations

from typing import Any, Optional

import torch
import torch.nn as nn

from mindtrace.models.architectures.backbones.protocol import (
    BackboneFeatures,
    BackboneProtocol,
)

try:
    import timm as _timm  # noqa: F401

    _TIMM_AVAILABLE = True
except ImportError:
    _TIMM_AVAILABLE = False

try:
    import torchvision as _torchvision  # noqa: F401

    _TORCHVISION_AVAILABLE = True
except ImportError:
    _TORCHVISION_AVAILABLE = False


# ---------------------------------------------------------------------------
# timm adapter
# ---------------------------------------------------------------------------


class TimmBackboneAdapter(BackboneProtocol):
    """Wraps any model available through the ``timm`` library.

    The model is created with ``num_classes=0`` so the classification head is
    removed.  ``cls_token`` is the global pool / CLS output; patch tokens are
    exposed when the model provides them (ViT-style models).

    Args:
        model_name: timm model identifier, e.g. ``"vit_base_patch16_224"``.
        pretrained: Whether to download pre-trained weights.
        device: Target device string.
        **kwargs: Forwarded verbatim to ``timm.create_model``.
    """

    def __init__(
        self,
        model_name: str,
        pretrained: bool = True,
        device: str = "cpu",
        **kwargs: Any,
    ) -> None:
        if not _TIMM_AVAILABLE:
            raise ImportError("timm is required for TimmBackboneAdapter. Install it with: pip install timm")
        super().__init__()
        import timm

        self._model = timm.create_model(
            model_name,
            pretrained=pretrained,
            num_classes=0,
            **kwargs,
        )
        self._model_name = model_name
        self._embed_dim: int = self._model.num_features
        self._has_patch_tokens = hasattr(self._model, "patch_embed") and hasattr(self._model, "blocks")
        self._model.to(device)

    @property
    def embed_dim(self) -> int:
        return self._embed_dim

    def extract(self, pixel_values: torch.Tensor) -> BackboneFeatures:
        features = self._model.forward_features(pixel_values)
        if features.dim() == 3:
            cls_token = features[:, 0, :]
            patch_tokens: Optional[torch.Tensor] = features[:, 1:, :]
        else:
            cls_token = features
            patch_tokens = None
        return BackboneFeatures(
            cls_token=cls_token,
            patch_tokens=patch_tokens,
            embed_dim=self._embed_dim,
        )


# ---------------------------------------------------------------------------
# torchvision adapter
# ---------------------------------------------------------------------------


class TorchvisionBackboneAdapter(BackboneProtocol):
    """Wraps torchvision ResNet / ViT / EfficientNet models.

    The classification head is replaced with ``nn.Identity`` so the model
    returns pooled feature vectors.

    Args:
        model_name: Callable name in ``torchvision.models``, e.g.
                     ``"resnet50"`` or ``"vit_b_16"``.
        pretrained: Whether to use ``DEFAULT`` pre-trained weights.
        device: Target device string.
        **kwargs: Forwarded to the torchvision model factory.
    """

    def __init__(
        self,
        model_name: str,
        pretrained: bool = True,
        device: str = "cpu",
        **kwargs: Any,
    ) -> None:
        if not _TORCHVISION_AVAILABLE:
            raise ImportError(
                "torchvision is required for TorchvisionBackboneAdapter. Install it with: pip install torchvision"
            )
        super().__init__()
        import torchvision.models as tvm

        factory = getattr(tvm, model_name, None)
        if factory is None:
            raise ValueError(
                f"'{model_name}' is not a recognised torchvision model. Check torchvision.models for available names."
            )

        weights_arg: Any = "DEFAULT" if pretrained else None
        self._model = factory(weights=weights_arg, **kwargs)
        self._model_name = model_name
        self._embed_dim = self._remove_head()
        self._model.to(device)

    def _remove_head(self) -> int:
        """Strip the classification head and return the feature dimension."""
        # ResNet / RegNet
        if hasattr(self._model, "fc"):
            in_features: int = self._model.fc.in_features
            self._model.fc = nn.Identity()
            return in_features

        # torchvision ViT
        if hasattr(self._model, "heads"):
            head = self._model.heads
            if hasattr(head, "head"):
                in_features = head.head.in_features
            else:
                for m in head.modules():
                    if isinstance(m, nn.Linear):
                        in_features = m.in_features
                        break
                else:
                    in_features = 768
            self._model.heads = nn.Identity()
            return in_features

        # EfficientNet / MobileNet / ConvNeXt
        if hasattr(self._model, "classifier"):
            classifier = self._model.classifier
            if isinstance(classifier, nn.Linear):
                in_features = classifier.in_features
            else:
                for m in reversed(list(classifier.modules())):
                    if isinstance(m, nn.Linear):
                        in_features = m.in_features
                        break
                else:
                    in_features = 1280
            self._model.classifier = nn.Identity()
            return in_features

        # Generic fallback
        for _name, module in reversed(list(self._model.named_children())):
            if isinstance(module, nn.Linear):
                in_features = module.in_features
                setattr(self._model, _name, nn.Identity())
                return in_features

        raise RuntimeError(
            f"Could not automatically remove the classification head from "
            f"torchvision model '{self._model_name}'. "
            "Override TorchvisionBackboneAdapter._remove_head() for this model."
        )

    @property
    def embed_dim(self) -> int:
        return self._embed_dim

    def extract(self, pixel_values: torch.Tensor) -> BackboneFeatures:
        features = self._model(pixel_values)
        if features.dim() > 2:
            features = features.flatten(1)
        return BackboneFeatures(
            cls_token=features,
            patch_tokens=None,
            embed_dim=self._embed_dim,
        )


# ---------------------------------------------------------------------------
# Mindtrace registry adapter
# ---------------------------------------------------------------------------


class MindtraceBackboneAdapter(BackboneProtocol):
    """Wraps a backbone registered in the mindtrace backbone registry.

    Args:
        arch_name: Name registered in the mindtrace backbone registry,
                    e.g. ``"resnet50"`` or ``"dino_v2_base"``.
        device: Target device string.
        **kwargs: Forwarded verbatim to ``build_backbone``.
    """

    def __init__(
        self,
        arch_name: str,
        device: str = "cpu",
        **kwargs: Any,
    ) -> None:
        super().__init__()
        from mindtrace.models.architectures.backbones.registry import build_backbone

        info = build_backbone(arch_name, **kwargs)
        self._model: nn.Module = info.model
        self._arch_name = arch_name
        self._embed_dim: int = info.num_features
        self._model.to(device)

    @property
    def embed_dim(self) -> int:
        return self._embed_dim

    def extract(self, pixel_values: torch.Tensor) -> BackboneFeatures:
        output = self._model(pixel_values)

        if isinstance(output, torch.Tensor):
            if output.dim() == 3:
                cls_token = output[:, 0, :]
                patch_tokens: Optional[torch.Tensor] = output[:, 1:, :]
            else:
                cls_token = output
                patch_tokens = None
        else:
            primary = output[0] if isinstance(output, (tuple, list)) else output
            if primary.dim() == 3:
                cls_token = primary[:, 0, :]
                patch_tokens = primary[:, 1:, :]
            else:
                cls_token = primary
                patch_tokens = None

        return BackboneFeatures(
            cls_token=cls_token,
            patch_tokens=patch_tokens,
            embed_dim=self._embed_dim,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_ADAPTER_REGISTRY: dict[str, type[BackboneProtocol]] = {
    "timm": TimmBackboneAdapter,
    "torchvision": TorchvisionBackboneAdapter,
    "mindtrace": MindtraceBackboneAdapter,
}


def build_backbone_adapter(
    backbone_type: str,
    model_name: str,
    *,
    device: str = "cpu",
    **kwargs: Any,
) -> BackboneProtocol:
    """Instantiate a :class:`BackboneProtocol` adapter.

    Args:
        backbone_type: One of ``"timm"``, ``"torchvision"``, ``"mindtrace"``.
        model_name: Backbone-type-specific model identifier.
        device: Target device string.
        **kwargs: Additional keyword arguments forwarded to the adapter.

    Returns:
        An initialised :class:`BackboneProtocol` instance on *device*.

    Raises:
        ValueError: If *backbone_type* is not registered.
    """
    if backbone_type not in _ADAPTER_REGISTRY:
        available = sorted(_ADAPTER_REGISTRY.keys())
        raise ValueError(f"Unknown backbone_type '{backbone_type}'. Available types: {available}")

    adapter_cls = _ADAPTER_REGISTRY[backbone_type]

    if backbone_type == "mindtrace":
        return adapter_cls(arch_name=model_name, device=device, **kwargs)  # type: ignore[call-arg]
    return adapter_cls(model_name=model_name, device=device, **kwargs)  # type: ignore[call-arg]
