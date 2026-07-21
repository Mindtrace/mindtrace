"""Unit tests for mindtrace.models.serving.deployment.

Covers:
- ShadowEvaluation: argmax vs equality comparison, agreement accounting,
  latency ratio gate, insufficient-data verdicts
- ConfidenceMonitor: mean+std drift score, window trimming, re-referencing
- Deployment.step: promotion to PRODUCTION on pass, rollback to DEV on fail,
  no-op on insufficient data, callback invocation
"""

from __future__ import annotations

import numpy as np
import pytest

from mindtrace.models.lifecycle import ModelCard, ModelStage
from mindtrace.models.serving import (
    ConfidenceMonitor,
    Deployment,
    ShadowDecision,
    ShadowEvaluation,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def staged_card() -> ModelCard:
    """Card with one variant shadow-running in STAGING."""
    card = ModelCard(name="detector", version="v1", task="classification")
    card.add_variant("edge-int8", artifact="/models/edge-int8.onnx")
    card.get_variant("edge-int8").stage = ModelStage.STAGING
    return card


# ===================================================================
# 1. ShadowEvaluation — comparison semantics
# ===================================================================


def test_argmax_agreement_for_array_likes():
    evaluation = ShadowEvaluation(min_samples=1)
    # Different scores, same argmax -> agree.
    assert evaluation.record(np.array([0.1, 0.9]), [0.2, 0.8]) is True
    # Different argmax -> disagree.
    assert evaluation.record([0.9, 0.1], np.array([0.3, 0.7])) is False
    assert evaluation.samples == 2
    assert evaluation.agreement == pytest.approx(0.5)


def test_equality_comparison_for_scalars_and_labels():
    evaluation = ShadowEvaluation(min_samples=1)
    assert evaluation.record("cat", "cat") is True
    assert evaluation.record("cat", "dog") is False
    assert evaluation.record(3, 3.0) is True  # numeric equality
    assert evaluation.agreement == pytest.approx(2 / 3)


def test_torch_tensor_outputs_compared_via_argmax():
    torch = pytest.importorskip("torch")
    evaluation = ShadowEvaluation(min_samples=1)
    assert evaluation.record(torch.tensor([0.1, 0.7, 0.2]), np.array([0.0, 0.6, 0.4])) is True
    assert evaluation.record(torch.tensor([0.7, 0.1, 0.2]), np.array([0.0, 0.6, 0.4])) is False


def test_agreement_zero_before_any_samples():
    evaluation = ShadowEvaluation()
    assert evaluation.samples == 0
    assert evaluation.agreement == 0.0
    assert evaluation.latency_ratio is None


# ===================================================================
# 2. ShadowEvaluation — decisions
# ===================================================================


def test_decide_insufficient_data():
    evaluation = ShadowEvaluation(min_samples=100)
    for _ in range(99):
        evaluation.record([0.1, 0.9], [0.1, 0.9])
    decision = evaluation.decide()
    assert decision.status == "insufficient_data"
    assert decision.samples == 99
    assert any("99/100" in reason for reason in decision.reasons)


def test_decide_pass_at_full_agreement():
    evaluation = ShadowEvaluation(min_samples=100, min_agreement=0.98)
    for _ in range(100):
        evaluation.record([0.1, 0.9], [0.2, 0.8])
    decision = evaluation.decide()
    assert decision.status == "pass"
    assert decision.reasons == []
    assert decision.agreement == pytest.approx(1.0)
    assert decision.samples == 100


def test_decide_fail_below_agreement_threshold():
    evaluation = ShadowEvaluation(min_samples=100, min_agreement=0.98)
    for i in range(100):
        candidate = [0.2, 0.8] if i < 90 else [0.8, 0.2]
        evaluation.record([0.1, 0.9], candidate)
    decision = evaluation.decide()
    assert decision.status == "fail"
    assert decision.agreement == pytest.approx(0.9)
    assert any("agreement" in reason for reason in decision.reasons)


def test_latency_ratio_gate():
    evaluation = ShadowEvaluation(min_samples=10, min_agreement=0.5, max_latency_ratio=1.5)
    for _ in range(10):
        evaluation.record(
            [0.1, 0.9],
            [0.1, 0.9],
            production_latency_ms=10.0,
            candidate_latency_ms=30.0,
        )
    assert evaluation.latency_ratio == pytest.approx(3.0)
    decision = evaluation.decide()
    assert decision.status == "fail"
    assert any("latency ratio" in reason for reason in decision.reasons)


def test_latency_gate_disabled_by_default():
    evaluation = ShadowEvaluation(min_samples=10)
    for _ in range(10):
        evaluation.record(
            [0.1, 0.9],
            [0.1, 0.9],
            production_latency_ms=10.0,
            candidate_latency_ms=100.0,
        )
    assert evaluation.decide().status == "pass"


def test_latency_gate_passes_when_within_budget():
    evaluation = ShadowEvaluation(min_samples=5, max_latency_ratio=1.5)
    for _ in range(5):
        evaluation.record(
            [0.1, 0.9],
            [0.1, 0.9],
            production_latency_ms=10.0,
            candidate_latency_ms=12.0,
        )
    assert evaluation.latency_ratio == pytest.approx(1.2)
    assert evaluation.decide().status == "pass"


# ===================================================================
# 3. ConfidenceMonitor
# ===================================================================


def test_no_drift_for_identical_distribution():
    reference = [0.9, 0.92, 0.88, 0.91, 0.9] * 20
    monitor = ConfidenceMonitor(window=100, reference=reference, threshold=0.15)
    monitor.record(reference)
    assert monitor.drift() == pytest.approx(0.0, abs=1e-12)
    assert monitor.is_drifting is False


def test_shifted_distribution_flags_drift():
    reference = [0.9, 0.92, 0.88, 0.91, 0.9] * 20
    monitor = ConfidenceMonitor(window=100, reference=reference, threshold=0.15)
    monitor.record([value - 0.3 for value in reference])  # mean shifted down 0.3
    assert monitor.drift() == pytest.approx(0.3, abs=1e-6)
    assert monitor.is_drifting is True


def test_drift_zero_without_reference_or_samples():
    monitor = ConfidenceMonitor()
    assert monitor.drift() == 0.0
    monitor.record(0.5)
    assert monitor.drift() == 0.0  # still no reference
    assert monitor.is_drifting is False


def test_window_keeps_only_recent_values():
    monitor = ConfidenceMonitor(window=10, reference=[0.9] * 10, threshold=0.15)
    monitor.record([0.2] * 10)  # old, drifting values
    monitor.record([0.9] * 10)  # recent healthy values push them out
    assert monitor.drift() == pytest.approx(0.0, abs=1e-12)
    assert monitor.is_drifting is False


def test_set_reference_from_window():
    monitor = ConfidenceMonitor(window=50, reference=[0.9] * 50, threshold=0.15)
    monitor.record([0.6] * 50)
    assert monitor.is_drifting is True
    monitor.set_reference_from_window()  # accept the new normal
    assert monitor.drift() == pytest.approx(0.0, abs=1e-12)
    assert monitor.is_drifting is False


def test_record_accepts_single_float():
    monitor = ConfidenceMonitor(window=5, reference=[0.5, 0.5, 0.5])
    monitor.record(0.5)
    assert monitor.drift() == pytest.approx(0.0, abs=1e-12)


# ===================================================================
# 4. Deployment.step
# ===================================================================


def test_step_pass_promotes_to_production_and_fires_on_pass(staged_card: ModelCard):
    evaluation = ShadowEvaluation(min_samples=100, min_agreement=0.98)
    for _ in range(100):
        evaluation.record(np.array([0.1, 0.9]), np.array([0.15, 0.85]))
    passed: list[ShadowDecision] = []
    failed: list[ShadowDecision] = []
    deployment = Deployment(
        card=staged_card,
        variant="edge-int8",
        evaluation=evaluation,
        on_pass=passed.append,
        on_fail=failed.append,
    )

    decision = deployment.step()

    assert decision.status == "pass"
    assert staged_card.get_variant("edge-int8").stage is ModelStage.PRODUCTION
    assert passed == [decision]
    assert failed == []


def test_step_fail_demotes_to_dev_with_reasons_and_fires_on_fail(staged_card: ModelCard):
    evaluation = ShadowEvaluation(min_samples=100, min_agreement=0.98)
    for i in range(100):
        candidate = [0.2, 0.8] if i < 80 else [0.8, 0.2]
        evaluation.record([0.1, 0.9], candidate)
    passed: list[ShadowDecision] = []
    failed: list[ShadowDecision] = []
    deployment = Deployment(
        card=staged_card,
        variant="edge-int8",
        evaluation=evaluation,
        on_pass=passed.append,
        on_fail=failed.append,
    )

    decision = deployment.step()

    assert decision.status == "fail"
    assert staged_card.get_variant("edge-int8").stage is ModelStage.DEV
    assert failed == [decision]
    assert passed == []
    # The demotion reason lists the failed checks.
    reason = staged_card.extra["demotion_reason/edge-int8"]
    assert "agreement" in reason


def test_step_insufficient_data_neither_promotes_nor_demotes(staged_card: ModelCard):
    evaluation = ShadowEvaluation(min_samples=100)
    for _ in range(10):
        evaluation.record([0.1, 0.9], [0.1, 0.9])
    calls: list[str] = []
    deployment = Deployment(
        card=staged_card,
        variant="edge-int8",
        evaluation=evaluation,
        on_pass=lambda d: calls.append("pass"),
        on_fail=lambda d: calls.append("fail"),
    )

    decision = deployment.step()

    assert decision.status == "insufficient_data"
    assert staged_card.get_variant("edge-int8").stage is ModelStage.STAGING
    assert calls == []


def test_step_is_idempotent_after_promotion(staged_card: ModelCard):
    evaluation = ShadowEvaluation(min_samples=1)
    evaluation.record([0.1, 0.9], [0.1, 0.9])
    deployment = Deployment(card=staged_card, variant="edge-int8", evaluation=evaluation)

    first = deployment.step()
    second = deployment.step()  # already in PRODUCTION; must not raise

    assert first.status == second.status == "pass"
    assert staged_card.get_variant("edge-int8").stage is ModelStage.PRODUCTION


def test_step_without_callbacks(staged_card: ModelCard):
    evaluation = ShadowEvaluation(min_samples=1, min_agreement=0.98)
    evaluation.record("cat", "dog")
    deployment = Deployment(card=staged_card, variant="edge-int8", evaluation=evaluation)

    decision = deployment.step()

    assert decision.status == "fail"
    assert staged_card.get_variant("edge-int8").stage is ModelStage.DEV
