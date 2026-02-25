"""Backbone sub-package: registry + all variant registrations.

Importing this package guarantees that all backbone factory functions are
registered in :data:`_BACKBONE_REGISTRY`.  Consumers should call
:func:`build_backbone` rather than importing individual backbone modules
directly.

Optional dependencies (``torchvision``) are guarded per-module; failures at
import time are silently swallowed so that the package is importable in
environments where only a subset of heavy ML libraries is installed.

DINOv2 backbones additionally require network access for the first load (hub
download); missing network connectivity is caught at *call* time and raised as
:class:`RuntimeError`.
"""

from __future__ import annotations

from mindtrace.models.architectures.backbones.registry import (
    BackboneInfo,
    build_backbone,
    list_backbones,
    register_backbone,
)

# ---------------------------------------------------------------------------
# Trigger registrations — each module registers its backbones at import time.
# Failures are swallowed here so the package remains importable when optional
# dependencies are absent.
# ---------------------------------------------------------------------------

try:
    import mindtrace.models.architectures.backbones.dino  # noqa: F401
except Exception:
    pass

try:
    import mindtrace.models.architectures.backbones.resnet  # noqa: F401
except Exception:
    pass

try:
    import mindtrace.models.architectures.backbones.vit  # noqa: F401
except Exception:
    pass

try:
    import mindtrace.models.architectures.backbones.efficientnet  # noqa: F401
except Exception:
    pass

__all__ = [
    "BackboneInfo",
    "build_backbone",
    "list_backbones",
    "register_backbone",
]
