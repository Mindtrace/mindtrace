"""mindtrace.models.lifecycle -- Model lifecycle management.

Provides :class:`ModelCard` as the single entry point for managing the full
lifecycle of a trained model: saving weights to the registry, recording
evaluation metrics, and promoting through stages with metric-gated
thresholds.

Example::

    from mindtrace.models.lifecycle import ModelCard, ModelStage
    from mindtrace.registry import Registry

    registry = Registry("/tmp/my_registry")

    card = ModelCard(
        name="image-classifier",
        version="v1",
        task="classification",
        registry=registry,
    )
    card.save_model(model)
    card.add_result("val/accuracy", 0.94)
    card.promote(to_stage=ModelStage.STAGING, require={"val/accuracy": 0.85})
"""

from __future__ import annotations

from mindtrace.models.lifecycle.card import (
    EvalResult,
    ModelCard,
    PromotionError,
    PromotionResult,
)
from mindtrace.models.lifecycle.stages import VALID_DEMOTIONS, VALID_PROMOTIONS, ModelStage

__all__ = [
    "ModelStage",
    "VALID_PROMOTIONS",
    "VALID_DEMOTIONS",
    "EvalResult",
    "ModelCard",
    "PromotionError",
    "PromotionResult",
]
