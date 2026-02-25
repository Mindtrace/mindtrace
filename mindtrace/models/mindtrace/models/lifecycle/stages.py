"""Model lifecycle stage definitions.

Defines the :class:`ModelStage` enumeration and the allowed transition graph
that governs how a model moves through its lifecycle from initial development
to archival.
"""

from __future__ import annotations

from enum import Enum


class ModelStage(str, Enum):
    """Model lifecycle stage.

    Stages represent the promotion path a model follows from initial
    development through to production deployment.

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
        """Return True if promotion from this stage to target is a valid transition.

        Valid transitions:
            dev        -> staging, archived
            staging    -> production, dev, archived
            production -> archived
            archived   -> (none)

        Args:
            target: The destination :class:`ModelStage`.

        Returns:
            ``True`` when the transition is permitted, ``False`` otherwise.

        Example:
            >>> ModelStage.DEV.can_promote_to(ModelStage.STAGING)
            True
            >>> ModelStage.ARCHIVED.can_promote_to(ModelStage.DEV)
            False
        """
        return target in VALID_TRANSITIONS.get(self, set())

    @property
    def next_stage(self) -> ModelStage | None:
        """Return the natural next stage in the forward promotion path, or None if terminal.

        The natural progression is:
            DEV -> STAGING -> PRODUCTION -> ARCHIVED

        ``ARCHIVED`` is a terminal stage and returns ``None``.

        Returns:
            The next :class:`ModelStage` in the forward path, or ``None`` when
            there is no natural successor.

        Example:
            >>> ModelStage.DEV.next_stage
            <ModelStage.STAGING: 'staging'>
            >>> ModelStage.ARCHIVED.next_stage is None
            True
        """
        _next: dict[ModelStage, ModelStage] = {
            ModelStage.DEV: ModelStage.STAGING,
            ModelStage.STAGING: ModelStage.PRODUCTION,
            ModelStage.PRODUCTION: ModelStage.ARCHIVED,
        }
        return _next.get(self)


VALID_TRANSITIONS: dict[ModelStage, set[ModelStage]] = {
    ModelStage.DEV: {ModelStage.STAGING, ModelStage.ARCHIVED},
    ModelStage.STAGING: {ModelStage.PRODUCTION, ModelStage.DEV, ModelStage.ARCHIVED},
    ModelStage.PRODUCTION: {ModelStage.ARCHIVED},
    ModelStage.ARCHIVED: set(),
}
