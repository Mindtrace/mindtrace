"""OTA deployment safety: shadow evaluation, drift monitoring, and rollback.

Lifecycle stages map directly to deployment reality on the edge fleet:

- ``DEV``: the variant exists but is not trusted on-device.
- ``STAGING``: the variant is *shadow-running* on the device — it receives the
  same inputs as the production model, but its outputs are only recorded and
  compared, never served.
- ``PRODUCTION``: the variant serves live traffic. Promotion is *earned* by
  live agreement with the incumbent model, not granted by an offline metric.

The classes here are pure decision logic — no schedulers, timers, or HTTP.
Callers (device agents, serving loops) feed observations in and drive
:meth:`Deployment.step` at whatever cadence suits them:

- :class:`ShadowEvaluation` accumulates paired production/candidate outputs
  (and optionally latencies) and decides pass / fail / insufficient-data.
- :class:`ConfidenceMonitor` watches the served model's confidence stream for
  distribution drift against a reference window.
- :class:`Deployment` ties a :class:`ShadowEvaluation` to a
  :class:`~mindtrace.models.lifecycle.ModelCard` variant, promoting the
  variant to ``PRODUCTION`` on a passing shadow run and rolling it back to
  ``DEV`` on a failing one.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Literal, Sequence

import numpy as np

from mindtrace.core import Mindtrace
from mindtrace.models.lifecycle.stages import ModelStage

if TYPE_CHECKING:  # pragma: no cover
    from mindtrace.models.lifecycle.card import ModelCard

__all__ = [
    "ConfidenceMonitor",
    "Deployment",
    "ShadowDecision",
    "ShadowEvaluation",
]


# ---------------------------------------------------------------------------
# Output comparison
# ---------------------------------------------------------------------------


def _as_score_array(value: Any) -> np.ndarray | None:
    """Coerce an output to a numeric array suitable for argmax comparison.

    Args:
        value: A model output — numpy array, torch tensor, or a (nested)
            list/tuple of numbers.

    Returns:
        A numpy array with at least two elements, or ``None`` when the value
        is scalar-like or not numeric (callers fall back to ``==``).
    """
    array: np.ndarray
    if isinstance(value, np.ndarray):
        array = value
    elif isinstance(value, (list, tuple)):
        try:
            array = np.asarray(value, dtype=float)
        except (TypeError, ValueError):
            return None
    elif hasattr(value, "detach") and hasattr(value, "cpu"):  # torch tensor
        try:
            array = value.detach().cpu().numpy()
        except Exception:
            return None
    else:
        return None
    if array.ndim == 0 or array.size < 2:
        return None
    return array


def _outputs_agree(production: Any, candidate: Any) -> bool:
    """Compare two outputs: argmax for array-likes, equality otherwise."""
    production_scores = _as_score_array(production)
    candidate_scores = _as_score_array(candidate)
    if production_scores is not None and candidate_scores is not None:
        return int(np.argmax(production_scores)) == int(np.argmax(candidate_scores))
    return bool(production == candidate)


# ---------------------------------------------------------------------------
# Shadow evaluation
# ---------------------------------------------------------------------------


@dataclass
class ShadowDecision:
    """Outcome of a shadow evaluation.

    Attributes:
        status: ``"insufficient_data"`` while below the sample floor,
            otherwise ``"pass"`` or ``"fail"``.
        reasons: Human-readable explanations for a fail (or the data gap
            for ``"insufficient_data"``); empty on a pass.
        agreement: Fraction of recorded pairs whose outputs agreed.
        samples: Number of recorded pairs.
    """

    status: Literal["insufficient_data", "pass", "fail"]
    reasons: list[str] = field(default_factory=list)
    agreement: float = 0.0
    samples: int = 0


class ShadowEvaluation(Mindtrace):
    """Accumulates shadow-mode observations and decides promotion readiness.

    The candidate model runs alongside production on live inputs; each paired
    observation is recorded here. Once enough samples accumulate,
    :meth:`decide` checks agreement (and optionally latency) gates.

    Args:
        min_samples: Minimum paired observations before a verdict is issued.
        min_agreement: Minimum fraction of agreeing outputs required to pass.
        max_latency_ratio: Optional ceiling on mean candidate latency divided
            by mean production latency. ``None`` disables the latency gate.
    """

    def __init__(
        self,
        *,
        min_samples: int = 100,
        min_agreement: float = 0.98,
        max_latency_ratio: float | None = None,
    ) -> None:
        super().__init__()
        self.min_samples = min_samples
        self.min_agreement = min_agreement
        self.max_latency_ratio = max_latency_ratio
        self._samples = 0
        self._agreements = 0
        self._production_latencies: list[float] = []
        self._candidate_latencies: list[float] = []

    def record(
        self,
        production_output: Any,
        candidate_output: Any,
        *,
        production_latency_ms: float | None = None,
        candidate_latency_ms: float | None = None,
    ) -> bool:
        """Record one paired observation.

        Array-like outputs (numpy arrays, torch tensors, numeric sequences)
        are compared by argmax — i.e. same predicted class — while all other
        outputs are compared by equality.

        Args:
            production_output: Output of the serving (incumbent) model.
            candidate_output: Output of the shadow (candidate) model.
            production_latency_ms: Optional production inference latency.
            candidate_latency_ms: Optional candidate inference latency.

        Returns:
            True when the two outputs agreed.
        """
        agreed = _outputs_agree(production_output, candidate_output)
        self._samples += 1
        if agreed:
            self._agreements += 1
        if production_latency_ms is not None and candidate_latency_ms is not None:
            self._production_latencies.append(float(production_latency_ms))
            self._candidate_latencies.append(float(candidate_latency_ms))
        return agreed

    @property
    def samples(self) -> int:
        """Number of paired observations recorded so far."""
        return self._samples

    @property
    def agreement(self) -> float:
        """Fraction of agreeing pairs (0.0 when nothing is recorded)."""
        if self._samples == 0:
            return 0.0
        return self._agreements / self._samples

    @property
    def latency_ratio(self) -> float | None:
        """Mean candidate latency over mean production latency, or None.

        None when no latency pairs were recorded or the production mean
        is not positive.
        """
        if not self._production_latencies:
            return None
        production_mean = sum(self._production_latencies) / len(self._production_latencies)
        if production_mean <= 0:
            return None
        candidate_mean = sum(self._candidate_latencies) / len(self._candidate_latencies)
        return candidate_mean / production_mean

    def decide(self) -> ShadowDecision:
        """Evaluate the accumulated evidence.

        Returns:
            ``"insufficient_data"`` below the sample floor; otherwise
            ``"pass"`` when agreement (and, if configured, latency ratio)
            gates hold, ``"fail"`` with per-gate reasons when they do not.
        """
        if self._samples < self.min_samples:
            return ShadowDecision(
                status="insufficient_data",
                reasons=[f"only {self._samples}/{self.min_samples} shadow samples recorded"],
                agreement=self.agreement,
                samples=self._samples,
            )

        reasons: list[str] = []
        if self.agreement < self.min_agreement:
            reasons.append(f"agreement {self.agreement:.4f} below required {self.min_agreement:.4f}")
        if self.max_latency_ratio is not None:
            ratio = self.latency_ratio
            if ratio is not None and ratio > self.max_latency_ratio:
                reasons.append(f"latency ratio {ratio:.2f} above allowed {self.max_latency_ratio:.2f}")

        return ShadowDecision(
            status="fail" if reasons else "pass",
            reasons=reasons,
            agreement=self.agreement,
            samples=self._samples,
        )


# ---------------------------------------------------------------------------
# Confidence drift monitoring
# ---------------------------------------------------------------------------


class ConfidenceMonitor(Mindtrace):
    """Detects drift in a model's confidence distribution.

    Keeps a sliding window of recent confidences and compares it to a
    reference distribution captured when the model was known-healthy. The
    drift score is a simple, interpretable mean-plus-spread shift::

        drift = |mean(window) - mean(reference)| + |std(window) - std(reference)|

    Confidences live in ``[0, 1]``, so the score reads directly as absolute
    probability shift: a score of 0.15 means the combined mean/spread of the
    served confidences moved 15 points from the reference.

    Args:
        window: Number of most-recent confidences retained.
        reference: Optional reference confidence distribution. Without one,
            :meth:`drift` reports 0.0 until :meth:`set_reference_from_window`
            is called.
        threshold: Drift score above which :attr:`is_drifting` is True.
    """

    def __init__(
        self,
        *,
        window: int = 500,
        reference: Sequence[float] | None = None,
        threshold: float = 0.15,
    ) -> None:
        super().__init__()
        self.window = window
        self.threshold = threshold
        self._reference: list[float] | None = [float(v) for v in reference] if reference is not None else None
        self._values: deque[float] = deque(maxlen=window)

    def record(self, confidences: Sequence[float] | float) -> None:
        """Append one confidence or a batch of confidences to the window."""
        if isinstance(confidences, (int, float)):
            self._values.append(float(confidences))
        else:
            self._values.extend(float(v) for v in confidences)

    def drift(self) -> float:
        """Return the mean+std shift score vs the reference distribution.

        Returns:
            ``|Δmean| + |Δstd|`` between the current window and the
            reference; 0.0 when no reference is set or the window is empty.
        """
        if self._reference is None or not self._reference or not self._values:
            return 0.0
        window_values = np.asarray(self._values, dtype=float)
        reference_values = np.asarray(self._reference, dtype=float)
        mean_shift = abs(float(window_values.mean()) - float(reference_values.mean()))
        std_shift = abs(float(window_values.std()) - float(reference_values.std()))
        return mean_shift + std_shift

    @property
    def is_drifting(self) -> bool:
        """True when the drift score exceeds the configured threshold."""
        return self.drift() > self.threshold

    def set_reference_from_window(self) -> None:
        """Freeze the current window as the new reference distribution."""
        self._reference = list(self._values)


# ---------------------------------------------------------------------------
# Deployment driver
# ---------------------------------------------------------------------------


class Deployment(Mindtrace):
    """Drives a shadow-mode variant through promote-or-rollback decisions.

    Binds a :class:`ShadowEvaluation` to a specific variant on a
    :class:`~mindtrace.models.lifecycle.ModelCard`. Callers feed live
    observations into ``deployment.evaluation`` and periodically call
    :meth:`step`; this class only turns the accumulated evidence into a
    lifecycle transition.

    Args:
        card: Model card owning the variant.
        variant: Name of the variant shadow-running on the device (expected
            to be in ``STAGING``).
        evaluation: The shadow evaluation accumulating live observations.
        on_pass: Optional callback invoked with the :class:`ShadowDecision`
            after a successful promotion.
        on_fail: Optional callback invoked with the :class:`ShadowDecision`
            after a rollback.
    """

    def __init__(
        self,
        *,
        card: "ModelCard",
        variant: str,
        evaluation: ShadowEvaluation,
        on_pass: Callable[[ShadowDecision], Any] | None = None,
        on_fail: Callable[[ShadowDecision], Any] | None = None,
    ) -> None:
        super().__init__()
        self.card = card
        self.variant = variant
        self.evaluation = evaluation
        self.on_pass = on_pass
        self.on_fail = on_fail

    def step(self) -> ShadowDecision:
        """Evaluate the shadow run and apply the resulting transition.

        - ``"pass"``: promote the variant ``STAGING -> PRODUCTION`` via
          :meth:`ModelCard.promote_variant` and invoke ``on_pass``.
        - ``"fail"``: demote the variant to ``DEV`` via
          :meth:`ModelCard.demote_variant` with the failed checks as the
          reason, and invoke ``on_fail``.
        - ``"insufficient_data"``: no transition, no callbacks.

        Stage changes are skipped when the variant is already at the target
        stage, so repeated calls after a verdict are safe.

        Returns:
            The :class:`ShadowDecision` produced by the evaluation.
        """
        decision = self.evaluation.decide()

        if decision.status == "pass":
            current_stage = self.card.get_variant(self.variant).stage
            if current_stage is not ModelStage.PRODUCTION:
                self.card.promote_variant(self.variant, to_stage=ModelStage.PRODUCTION)
            if self.on_pass is not None:
                self.on_pass(decision)
        elif decision.status == "fail":
            current_stage = self.card.get_variant(self.variant).stage
            if current_stage is not ModelStage.DEV:
                self.card.demote_variant(
                    self.variant,
                    to_stage=ModelStage.DEV,
                    reason="; ".join(decision.reasons),
                )
            if self.on_fail is not None:
                self.on_fail(decision)

        return decision
