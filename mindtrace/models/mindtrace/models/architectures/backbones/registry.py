"""Backbone registry: register, look up, and instantiate backbone factories.

All backbone modules in this sub-package self-register by calling
:func:`register_backbone` at import time.  Consumers should use
:func:`build_backbone` rather than instantiating models directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import torch.nn as nn


# ---------------------------------------------------------------------------
# Internal registry store
# ---------------------------------------------------------------------------

_BACKBONE_REGISTRY: dict[str, Callable[..., nn.Module]] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def register_backbone(name: str) -> Callable:
    """Decorator that registers a backbone factory function under *name*.

    The decorated callable must accept arbitrary keyword arguments and return
    an ``nn.Module`` whose output dimension matches the ``num_features`` value
    supplied when building a :class:`BackboneInfo`.

    Args:
        name: Unique registry key (e.g. ``"resnet50"``, ``"dino_v2_base"``).

    Returns:
        The original factory function, unmodified.

    Raises:
        ValueError: If *name* is already registered.

    Example:
        >>> @register_backbone("my_backbone")
        ... def _build_my_backbone(pretrained: bool = True) -> nn.Module:
        ...     ...
    """
    def decorator(fn: Callable[..., nn.Module]) -> Callable[..., nn.Module]:
        if name in _BACKBONE_REGISTRY:
            raise ValueError(
                f"Backbone '{name}' is already registered. "
                "Use a unique name or de-register the existing entry first."
            )
        _BACKBONE_REGISTRY[name] = fn
        return fn

    return decorator


def build_backbone(name: str, **kwargs: object) -> BackboneInfo:
    """Instantiate a registered backbone by name.

    Args:
        name: Registered backbone name (e.g. ``"dino_v2_base"``,
            ``"resnet50"``).
        **kwargs: Forwarded verbatim to the backbone factory
            (e.g. ``pretrained=True``, ``num_classes=0``).

    Returns:
        A :class:`BackboneInfo` containing the model instance and its output
        feature dimension.

    Raises:
        KeyError: If *name* is not present in the registry.

    Example:
        >>> info = build_backbone("resnet50", pretrained=False)
        >>> info.num_features
        2048
    """
    if name not in _BACKBONE_REGISTRY:
        available = list_backbones()
        raise KeyError(
            f"Backbone '{name}' is not registered. "
            f"Available backbones: {available}"
        )

    model, num_features = _BACKBONE_REGISTRY[name](**kwargs)
    return BackboneInfo(name=name, num_features=num_features, model=model)


def list_backbones() -> list[str]:
    """Return all registered backbone names, sorted alphabetically.

    Returns:
        Sorted list of registered backbone name strings.

    Example:
        >>> names = list_backbones()
        >>> "resnet50" in names
        True
    """
    return sorted(_BACKBONE_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------


@dataclass
class BackboneInfo:
    """Container returned by :func:`build_backbone`.

    Attributes:
        name: The registered name of the backbone.
        num_features: Dimensionality of the backbone's output feature vector
            (or channel count for 2-D feature maps).
        model: The instantiated ``nn.Module`` ready for use.
    """

    name: str
    num_features: int
    model: nn.Module
