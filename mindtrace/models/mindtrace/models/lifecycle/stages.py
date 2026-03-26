"""Model lifecycle stage definitions.

Defines the :class:`ModelStage` enumeration and the allowed transition graphs
for promotion (forward) and demotion (backward) that govern how a model moves
through its lifecycle.
"""

from __future__ import annotations

from enum import Enum


class ModelStage(str, Enum):
    """Model lifecycle stage.

    Attributes:
        DEV: Active development — experimental, not yet validated.
        STAGING: Validated against evaluation thresholds, ready for review.
        PRODUCTION: Live in production, serving real traffic.
        ARCHIVED: Retired model, preserved for reference.
    """

    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"

    def can_promote_to(self, target: ModelStage) -> bool:
        """Return True if forward promotion to *target* is valid.

        Valid promotions::

            DEV        -> STAGING
            STAGING    -> PRODUCTION
            DEV, STAGING, PRODUCTION -> ARCHIVED
        """
        return target in VALID_TRANSITIONS.get(self, set())

    def can_demote_to(self, target: ModelStage) -> bool:
        """Return True if backward demotion to *target* is valid.

        Valid demotions::

            STAGING    -> DEV
            PRODUCTION -> STAGING, DEV
            PRODUCTION -> ARCHIVED
        """
        return target in VALID_DEMOTIONS.get(self, set())

    @property
    def next_stage(self) -> ModelStage | None:
        """Return the natural next stage in the forward path, or None."""
        _next: dict[ModelStage, ModelStage] = {
            ModelStage.DEV: ModelStage.STAGING,
            ModelStage.STAGING: ModelStage.PRODUCTION,
            ModelStage.PRODUCTION: ModelStage.ARCHIVED,
        }
        return _next.get(self)


VALID_TRANSITIONS: dict[ModelStage, set[ModelStage]] = {
    ModelStage.DEV: {ModelStage.STAGING, ModelStage.ARCHIVED},
    ModelStage.STAGING: {ModelStage.PRODUCTION, ModelStage.ARCHIVED},
    ModelStage.PRODUCTION: {ModelStage.ARCHIVED},
    ModelStage.ARCHIVED: set(),
}

VALID_DEMOTIONS: dict[ModelStage, set[ModelStage]] = {
    ModelStage.DEV: set(),
    ModelStage.STAGING: {ModelStage.DEV},
    ModelStage.PRODUCTION: {ModelStage.STAGING, ModelStage.DEV, ModelStage.ARCHIVED},
    ModelStage.ARCHIVED: set(),
}
