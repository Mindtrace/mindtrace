"""mindtrace.models.lifecycle — Model lifecycle management.

This package provides the building blocks for managing the full lifecycle of
a trained model: stage definitions, structured metadata cards, evaluation
result tracking, and promotion/demotion workflows with threshold enforcement.

Public API:

    ModelStage          Enum of lifecycle stages (dev, staging, production, archived).
    VALID_TRANSITIONS   Allowed stage-to-stage transition graph.
    EvalResult          Single evaluation metric result entry.
    ModelCard           Structured model metadata (provenance, metrics, description).
    PromotionError      Exception raised on invalid or failed promotion.
    PromotionResult     Dataclass describing the outcome of a promotion/demotion call.
    promote             Promote a ModelCard to a new stage with threshold checks.
    demote              Demote a ModelCard (rollback / archival), no threshold checks.

Example::

    from mindtrace.models.lifecycle import (
        ModelCard,
        ModelStage,
        promote,
    )

    card = ModelCard(name="sfz-segmenter", version="v3")
    card.add_result("val/iou", 0.87, dataset="coco-val")
    card.add_result("val/f1", 0.81, dataset="coco-val")

    result = promote(
        card=card,
        registry=registry,
        to_stage=ModelStage.PRODUCTION,
        require={"val/iou": 0.82, "val/f1": 0.78},
    )
"""

from __future__ import annotations

from mindtrace.models.lifecycle.card import EvalResult, ModelCard
from mindtrace.models.lifecycle.promotion import PromotionError, PromotionResult, demote, promote
from mindtrace.models.lifecycle.stages import VALID_TRANSITIONS, ModelStage

__all__ = [
    "ModelStage",
    "VALID_TRANSITIONS",
    "EvalResult",
    "ModelCard",
    "PromotionError",
    "PromotionResult",
    "promote",
    "demote",
]
