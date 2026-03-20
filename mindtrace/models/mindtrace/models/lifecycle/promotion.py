"""Model lifecycle promotion and demotion utilities.

Provides :func:`promote` and :func:`demote` to move a :class:`ModelCard`
through its lifecycle stages, with optional evaluation threshold enforcement
and registry persistence.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from mindtrace.models.lifecycle.card import ModelCard
from mindtrace.models.lifecycle.stages import ModelStage

logger = logging.getLogger(__name__)


class PromotionError(Exception):
    """Raised when a model fails to meet promotion requirements.

    This exception is raised when:

    - The requested stage transition is not permitted by
      :data:`mindtrace.models.lifecycle.stages.VALID_TRANSITIONS`.
    - One or more required evaluation metrics are below their specified
      thresholds (and ``dry_run`` is ``False``).
    - A required metric has no recorded result on the card.
    """


@dataclass
class PromotionResult:
    """Result of a promotion or demotion attempt.

    Attributes:
        success: Whether the promotion/demotion completed successfully.
        from_stage: The stage the model was in before the operation.
        to_stage: The target stage requested.
        model_name: The ``name`` field of the affected :class:`ModelCard`.
        model_version: The ``version`` field of the affected
            :class:`ModelCard`.
        failed_requirements: Mapping of metric name to a
            ``(actual_value, required_value)`` tuple for every metric that
            did not meet its threshold.  Empty when all requirements passed.
        timestamp: UTC timestamp at which the operation was evaluated.
    """

    success: bool
    from_stage: ModelStage
    to_stage: ModelStage
    model_name: str
    model_version: str
    failed_requirements: dict[str, tuple[float, float]] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_transition(from_stage: ModelStage, to_stage: ModelStage) -> None:
    """Verify that a stage transition is permitted.

    Args:
        from_stage: The current lifecycle stage.
        to_stage: The desired target stage.

    Raises:
        PromotionError: If the transition is not allowed by
            :data:`mindtrace.models.lifecycle.stages.VALID_TRANSITIONS`.
    """
    if not from_stage.can_promote_to(to_stage):
        from mindtrace.models.lifecycle.stages import VALID_TRANSITIONS

        allowed = sorted(s.value for s in VALID_TRANSITIONS.get(from_stage, set()))
        raise PromotionError(
            f"Invalid stage transition: {from_stage.value!r} -> {to_stage.value!r}. "
            f"Allowed targets from {from_stage.value!r}: {allowed}."
        )


def _check_requirements(
    card: ModelCard,
    require: dict[str, float],
) -> dict[str, tuple[float, float]]:
    """Evaluate metric thresholds against card eval results.

    Args:
        card: The :class:`ModelCard` whose metrics are checked.
        require: Mapping of ``{metric_name: minimum_required_value}``.

    Returns:
        A dict of ``{metric: (actual, required)}`` for every metric that
        failed.  Missing metrics are treated as failing with an actual value
        of ``float("nan")``.
    """
    failures: dict[str, tuple[float, float]] = {}
    for metric, threshold in require.items():
        actual = card.get_metric(metric)
        if actual is None:
            failures[metric] = (float("nan"), threshold)
        elif actual < threshold:
            failures[metric] = (actual, threshold)
    return failures


def _persist_to_registry(
    registry: Any,
    key: str,
    card: ModelCard,
) -> None:
    """Attempt to save the card dict to the registry.

    If the registry does not support saving a plain dict (e.g. it requires a
    specific materializer), a warning is logged and execution continues — the
    in-memory card stage update is preserved regardless.

    Args:
        registry: A ``mindtrace.registry.Registry`` instance (or compatible
            object exposing a ``save`` method).
        key: Registry key under which the card will be stored.
        card: The :class:`ModelCard` to persist.
    """
    try:
        registry.save(key, card.to_dict())
    except Exception as exc:
        logger.warning(
            "Could not persist ModelCard to registry under key %r: %s. "
            "The in-memory card stage has been updated but was not saved.",
            key,
            exc,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def promote(
    card: ModelCard,
    registry: Any,
    *,
    to_stage: ModelStage,
    require: dict[str, float] | None = None,
    dry_run: bool = False,
) -> PromotionResult:
    """Promote a model to a new lifecycle stage.

    Validates that the transition is allowed, checks evaluation thresholds,
    updates the :class:`ModelCard` stage in place, and saves the card to the
    registry under the new stage key.

    Args:
        card: The :class:`ModelCard` to promote.
        registry: A ``mindtrace.registry.Registry`` instance.
        to_stage: Target stage.
        require: Mapping of ``{metric: minimum_required_value}``.  Promotion
            is blocked if any metric in ``card.eval_results`` is below its
            threshold.  If a required metric has no result recorded, promotion
            is also blocked.
        dry_run: If ``True``, validate requirements and transition validity
            without writing to the registry or mutating ``card.stage``.

    Returns:
        :class:`PromotionResult` describing the outcome.

    Raises:
        PromotionError: If the stage transition is invalid or one or more
            required metrics are not met (only raised when ``dry_run`` is
            ``False``).

    Example:
        >>> result = promote(
        ...     card=card,
        ...     registry=registry,
        ...     to_stage=ModelStage.PRODUCTION,
        ...     require={"val/iou": 0.82, "val/f1": 0.78},
        ... )
    """
    from_stage = card.stage

    # --- validate transition ---
    _validate_transition(from_stage, to_stage)

    # --- check evaluation thresholds ---
    failures: dict[str, tuple[float, float]] = {}
    if require:
        failures = _check_requirements(card, require)

    result = PromotionResult(
        success=len(failures) == 0,
        from_stage=from_stage,
        to_stage=to_stage,
        model_name=card.name,
        model_version=card.version,
        failed_requirements=failures,
    )

    if failures and not dry_run:
        details = "; ".join(
            f"{metric}: actual={'missing' if math.isnan(actual) else f'{actual:.4g}'}, required={required:.4g}"
            for metric, (actual, required) in failures.items()
        )
        raise PromotionError(
            f"Promotion of {card.name}:{card.version} to {to_stage.value!r} blocked by failed requirements: {details}"
        )

    if dry_run:
        logger.debug(
            "dry_run=True: promotion %s:%s %s -> %s not applied.",
            card.name,
            card.version,
            from_stage.value,
            to_stage.value,
        )
        return result

    # --- apply promotion ---
    card.stage = to_stage
    _persist_to_registry(registry, card.registry_key(to_stage), card)

    logger.info(
        "Promoted %s:%s from %s to %s.",
        card.name,
        card.version,
        from_stage.value,
        to_stage.value,
    )
    return result


def demote(
    card: ModelCard,
    registry: Any,
    *,
    to_stage: ModelStage,
    reason: str = "",
    dry_run: bool = False,
) -> PromotionResult:
    """Demote a model to an earlier or archival stage.

    Intended for rollback or retirement workflows.  Unlike :func:`promote`,
    demotion does *not* check evaluation thresholds — any valid stage
    transition is unconditionally permitted.

    Args:
        card: The :class:`ModelCard` to demote.
        registry: A ``mindtrace.registry.Registry`` instance.
        to_stage: Target stage.  Must be a valid transition from the card's
            current stage according to
            :data:`mindtrace.models.lifecycle.stages.VALID_TRANSITIONS`.
        reason: Optional human-readable reason for the demotion, recorded in
            the log and stored in ``card.extra["demotion_reason"]`` when not
            in dry-run mode.
        dry_run: If ``True``, validate the transition without writing to the
            registry or mutating ``card.stage``.

    Returns:
        :class:`PromotionResult` describing the outcome.

    Raises:
        PromotionError: If the stage transition is invalid.

    Example:
        >>> result = demote(
        ...     card=card,
        ...     registry=registry,
        ...     to_stage=ModelStage.STAGING,
        ...     reason="Regression detected in production — rolling back.",
        ... )
    """
    from_stage = card.stage

    # --- validate transition ---
    _validate_transition(from_stage, to_stage)

    result = PromotionResult(
        success=True,
        from_stage=from_stage,
        to_stage=to_stage,
        model_name=card.name,
        model_version=card.version,
        failed_requirements={},
    )

    if dry_run:
        logger.debug(
            "dry_run=True: demotion %s:%s %s -> %s not applied.",
            card.name,
            card.version,
            from_stage.value,
            to_stage.value,
        )
        return result

    # --- apply demotion ---
    if reason:
        card.extra["demotion_reason"] = reason

    card.stage = to_stage
    _persist_to_registry(registry, card.registry_key(to_stage), card)

    log_msg = "Demoted %s:%s from %s to %s."
    log_args: list[Any] = [card.name, card.version, from_stage.value, to_stage.value]
    if reason:
        log_msg += " Reason: %s"
        log_args.append(reason)
    logger.info(log_msg, *log_args)

    return result
