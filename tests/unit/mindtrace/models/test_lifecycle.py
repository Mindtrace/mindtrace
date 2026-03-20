"""Unit tests for mindtrace.models.lifecycle.

Tests cover:
- ModelStage enum values and transition rules
- EvalResult default fields and serialisation
- ModelCard result tracking, serialisation, persistence, and registry key helpers
- promote() and demote() with valid/invalid transitions, threshold enforcement,
  dry-run mode, and registry persistence
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mindtrace.models.lifecycle import (
    EvalResult,
    ModelCard,
    ModelStage,
    PromotionError,
    demote,
    promote,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_card(
    name: str = "model",
    version: str = "v1",
    stage: ModelStage = ModelStage.DEV,
) -> ModelCard:
    return ModelCard(name=name, version=version, stage=stage)


# ---------------------------------------------------------------------------
# ModelStage
# ---------------------------------------------------------------------------


class TestModelStage:
    def test_values(self):
        assert ModelStage.DEV.value == "dev"
        assert ModelStage.STAGING.value == "staging"
        assert ModelStage.PRODUCTION.value == "production"
        assert ModelStage.ARCHIVED.value == "archived"

    def test_can_promote_to_valid(self):
        assert ModelStage.DEV.can_promote_to(ModelStage.STAGING) is True
        assert ModelStage.STAGING.can_promote_to(ModelStage.PRODUCTION) is True

    def test_can_promote_to_invalid(self):
        # dev -> production skips staging — not allowed
        assert ModelStage.DEV.can_promote_to(ModelStage.PRODUCTION) is False
        # production -> staging is a demotion but not in allowed transitions
        assert ModelStage.PRODUCTION.can_promote_to(ModelStage.STAGING) is False

    def test_next_stage(self):
        assert ModelStage.DEV.next_stage is ModelStage.STAGING
        assert ModelStage.STAGING.next_stage is ModelStage.PRODUCTION
        assert ModelStage.PRODUCTION.next_stage is ModelStage.ARCHIVED
        assert ModelStage.ARCHIVED.next_stage is None


# ---------------------------------------------------------------------------
# EvalResult
# ---------------------------------------------------------------------------


class TestEvalResult:
    def test_default_split_is_val(self):
        result = EvalResult(metric="acc", value=0.9)
        assert result.split == "val"

    def test_timestamp_set_on_creation(self):
        before = datetime.now(timezone.utc)
        result = EvalResult(metric="acc", value=0.9)
        after = datetime.now(timezone.utc)
        assert before <= result.timestamp <= after

    def test_to_dict_roundtrip(self):
        result = EvalResult(metric="val/iou", value=0.85, dataset="coco", split="test")
        d = result.to_dict()
        restored = EvalResult.from_dict(d)

        assert restored.metric == "val/iou"
        assert restored.value == pytest.approx(0.85)
        assert restored.dataset == "coco"
        assert restored.split == "test"


# ---------------------------------------------------------------------------
# ModelCard
# ---------------------------------------------------------------------------


class TestModelCard:
    def test_add_result_appends(self):
        card = _make_card()
        card.add_result("val/iou", 0.80)
        card.add_result("val/iou", 0.85)
        assert len(card.eval_results) == 2

    def test_get_metric_returns_latest(self):
        card = _make_card()
        card.add_result("val/iou", 0.80)
        card.add_result("val/iou", 0.85)
        assert card.get_metric("val/iou") == pytest.approx(0.85)

    def test_get_metric_missing_returns_none(self):
        card = _make_card()
        assert card.get_metric("nonexistent_metric") is None

    def test_summary_returns_latest_per_metric(self):
        card = _make_card()
        card.add_result("val/iou", 0.80)
        card.add_result("val/f1", 0.70)
        card.add_result("val/iou", 0.85)  # overwrites 0.80 in summary

        summary = card.summary()
        assert summary["val/iou"] == pytest.approx(0.85)
        assert summary["val/f1"] == pytest.approx(0.70)

    def test_to_dict_roundtrip(self):
        card = _make_card(name="sfz-detector", version="v2")
        card.add_result("val/iou", 0.87, dataset="coco-val")

        d = card.to_dict()
        restored = ModelCard.from_dict(d)

        assert restored.name == "sfz-detector"
        assert restored.version == "v2"
        assert restored.stage is ModelStage.DEV
        assert len(restored.eval_results) == 1
        assert restored.eval_results[0].value == pytest.approx(0.87)

    def test_save_and_load(self, tmp_path: Path):
        card = _make_card(name="save-test", version="v1")
        card.add_result("val/f1", 0.92)

        save_path = tmp_path / "card.json"
        card.save(save_path)

        assert save_path.exists()
        loaded = ModelCard.load(save_path)
        assert loaded.name == "save-test"
        assert loaded.get_metric("val/f1") == pytest.approx(0.92)

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        card = _make_card()
        nested_path = tmp_path / "sub" / "dir" / "card.json"
        card.save(nested_path)
        assert nested_path.exists()

    def test_save_writes_valid_json(self, tmp_path: Path):
        card = _make_card(name="json-check", version="v1")
        path = tmp_path / "card.json"
        card.save(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["name"] == "json-check"

    def test_registry_key_no_stage(self):
        card = _make_card(name="mymodel", version="v3")
        assert card.registry_key() == "mymodel:v3"

    def test_registry_key_with_stage(self):
        card = _make_card(name="mymodel", version="v3")
        assert card.registry_key(ModelStage.PRODUCTION) == "mymodel:v3:production"


# ---------------------------------------------------------------------------
# promote()
# ---------------------------------------------------------------------------


class TestPromote:
    def test_promote_valid_transition(self):
        card = _make_card(stage=ModelStage.DEV)
        registry = MagicMock()

        result = promote(card, registry, to_stage=ModelStage.STAGING)

        assert result.success is True
        assert card.stage is ModelStage.STAGING

    def test_promote_invalid_transition_raises(self):
        card = _make_card(stage=ModelStage.DEV)
        registry = MagicMock()

        with pytest.raises(PromotionError):
            promote(card, registry, to_stage=ModelStage.PRODUCTION)

    def test_promote_requirement_met(self):
        card = _make_card(stage=ModelStage.DEV)
        card.add_result("val/iou", 0.85)
        registry = MagicMock()

        result = promote(
            card,
            registry,
            to_stage=ModelStage.STAGING,
            require={"val/iou": 0.80},
        )

        assert result.success is True
        assert card.stage is ModelStage.STAGING

    def test_promote_requirement_not_met(self):
        card = _make_card(stage=ModelStage.DEV)
        card.add_result("val/iou", 0.75)
        registry = MagicMock()

        with pytest.raises(PromotionError):
            promote(
                card,
                registry,
                to_stage=ModelStage.STAGING,
                require={"val/iou": 0.80},
            )

    def test_promote_dry_run_does_not_update_stage(self):
        card = _make_card(stage=ModelStage.DEV)
        card.add_result("val/iou", 0.90)
        registry = MagicMock()

        result = promote(
            card,
            registry,
            to_stage=ModelStage.STAGING,
            require={"val/iou": 0.80},
            dry_run=True,
        )

        # Stage must remain unchanged in dry-run mode
        assert card.stage is ModelStage.DEV
        # Result still reports success (requirements were met)
        assert result.success is True

    def test_promote_saves_to_registry(self):
        card = _make_card(name="reg-model", version="v1", stage=ModelStage.DEV)
        registry = MagicMock()

        promote(card, registry, to_stage=ModelStage.STAGING)

        registry.save.assert_called_once()
        # The key must contain the new stage name
        call_args = registry.save.call_args
        key_arg = call_args[0][0]
        assert "staging" in key_arg

    def test_promote_missing_required_metric_raises(self):
        """A required metric that was never recorded blocks promotion."""
        card = _make_card(stage=ModelStage.DEV)
        # No eval results recorded — metric is absent
        registry = MagicMock()

        with pytest.raises(PromotionError):
            promote(
                card,
                registry,
                to_stage=ModelStage.STAGING,
                require={"val/iou": 0.80},
            )


# ---------------------------------------------------------------------------
# demote()
# ---------------------------------------------------------------------------


class TestDemote:
    def test_demote_production_to_archived(self):
        card = _make_card(stage=ModelStage.PRODUCTION)
        registry = MagicMock()

        result = demote(card, registry, to_stage=ModelStage.ARCHIVED)

        assert result.success is True
        assert card.stage is ModelStage.ARCHIVED

    def test_demote_invalid_raises(self):
        """Archived -> any transition is invalid."""
        card = _make_card(stage=ModelStage.ARCHIVED)
        registry = MagicMock()

        with pytest.raises(PromotionError):
            demote(card, registry, to_stage=ModelStage.PRODUCTION)

    def test_demote_dry_run_does_not_update_stage(self):
        card = _make_card(stage=ModelStage.PRODUCTION)
        registry = MagicMock()

        result = demote(card, registry, to_stage=ModelStage.ARCHIVED, dry_run=True)

        assert card.stage is ModelStage.PRODUCTION
        assert result.success is True
        registry.save.assert_not_called()

    def test_demote_saves_to_registry(self):
        card = _make_card(stage=ModelStage.STAGING)
        registry = MagicMock()

        demote(card, registry, to_stage=ModelStage.DEV)

        registry.save.assert_called_once()

    def test_demote_stores_reason_in_extra(self):
        card = _make_card(stage=ModelStage.PRODUCTION)
        registry = MagicMock()
        reason = "Regression detected in nightly eval"

        demote(card, registry, to_stage=ModelStage.ARCHIVED, reason=reason)

        assert card.extra.get("demotion_reason") == reason
