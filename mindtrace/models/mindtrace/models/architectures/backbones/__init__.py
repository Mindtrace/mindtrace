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
    import mindtrace.models.architectures.backbones.dino_hf  # noqa: F401
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

# Export HuggingFace DINO classes when transformers is available
try:
    from mindtrace.models.architectures.backbones.dino_hf import (  # noqa: F401
        HuggingFaceDINOBackbone,
        LoRAConfig,
    )
    _HF_DINO_AVAILABLE = True
except Exception:
    _HF_DINO_AVAILABLE = False

# Export generic HuggingFace backbone when transformers is available
try:
    from mindtrace.models.architectures.backbones.hf_generic import (  # noqa: F401
        HuggingFaceBackbone,
    )
    _HF_GENERIC_AVAILABLE = True
except Exception:
    _HF_GENERIC_AVAILABLE = False

__all__ = [
    "BackboneInfo",
    "build_backbone",
    "list_backbones",
    "register_backbone",
    # HuggingFace DINO (available when transformers is installed)
    "HuggingFaceDINOBackbone",
    "LoRAConfig",
    # Generic HuggingFace backbone (available when transformers is installed)
    "HuggingFaceBackbone",
]
