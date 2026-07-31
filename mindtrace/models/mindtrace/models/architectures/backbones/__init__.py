"""Backbone sub-package: registry + all variant registrations.

Importing this package guarantees that all backbone factory functions are
registered in :data:`_BACKBONE_REGISTRY`.  Consumers should call
:func:`build_backbone` rather than importing individual backbone modules
directly.

Optional dependencies (``torchvision``, ``transformers``) are guarded
per-module; a missing dependency (``ImportError``) is swallowed and logged at
debug level so the package stays importable in environments where only a subset
of heavy ML libraries is installed.  Genuine errors inside a backbone module are
*not* swallowed — they propagate so bugs surface instead of hiding.

DINOv2 backbones additionally require network access for the first load (hub
download); missing network connectivity is caught at *call* time and raised as
:class:`RuntimeError`.
"""

from __future__ import annotations

from mindtrace.core import get_logger
from mindtrace.models.architectures.backbones.protocol import (
    BackboneFeatures,
    BackboneProtocol,
)
from mindtrace.models.architectures.backbones.registry import (
    BackboneInfo,
    build_backbone,
    list_backbones,
    register_backbone,
)

_logger = get_logger(__name__)

# Adapters (depend on optional heavy ML libraries — guarded)
try:
    from mindtrace.models.architectures.backbones.adapters import (  # noqa: F401
        MindtraceBackboneAdapter,
        TimmBackboneAdapter,
        TorchvisionBackboneAdapter,
        build_backbone_adapter,
    )

    _ADAPTERS_AVAILABLE = True
except ImportError as exc:
    _logger.debug("Backbone adapters unavailable (optional dependency missing): %s", exc)
    _ADAPTERS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Trigger registrations — each module registers its backbones at import time.
# A missing optional dependency (torchvision, transformers, ...) is swallowed
# so the package remains importable; only ImportError is caught, so genuine
# bugs inside a backbone module still surface.
# ---------------------------------------------------------------------------

for _mod in (
    "dino",
    "dino_hf",
    "resnet",
    "vit",
    "efficientnet",
):
    try:
        __import__(f"mindtrace.models.architectures.backbones.{_mod}")
    except ImportError as exc:
        _logger.debug("Backbone module '%s' not registered (optional dependency missing): %s", _mod, exc)

# Export HuggingFace DINO classes when transformers is available
try:
    from mindtrace.models.architectures.backbones.dino_hf import (  # noqa: F401
        HuggingFaceDINOBackbone,
        LoRAConfig,
    )

    _HF_DINO_AVAILABLE = True
except ImportError as exc:
    _logger.debug("HuggingFace DINO backbones unavailable (transformers missing): %s", exc)
    _HF_DINO_AVAILABLE = False

# Export generic HuggingFace backbone when transformers is available
try:
    from mindtrace.models.architectures.backbones.hf_generic import (  # noqa: F401
        HuggingFaceBackbone,
    )

    _HF_GENERIC_AVAILABLE = True
except ImportError as exc:
    _logger.debug("Generic HuggingFace backbone unavailable (transformers missing): %s", exc)
    _HF_GENERIC_AVAILABLE = False

__all__ = [
    # Protocol
    "BackboneFeatures",
    "BackboneProtocol",
    # Registry
    "BackboneInfo",
    "build_backbone",
    "list_backbones",
    "register_backbone",
    # Adapters
    "TimmBackboneAdapter",
    "TorchvisionBackboneAdapter",
    "MindtraceBackboneAdapter",
    "build_backbone_adapter",
    # HuggingFace DINO (available when transformers is installed)
    "HuggingFaceDINOBackbone",
    "LoRAConfig",
    # Generic HuggingFace backbone (available when transformers is installed)
    "HuggingFaceBackbone",
]
