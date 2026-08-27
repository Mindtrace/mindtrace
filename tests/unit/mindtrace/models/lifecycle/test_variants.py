"""Unit tests for per-target variants on `mindtrace.models.lifecycle.card.ModelCard`."""

from __future__ import annotations

import math

import pytest

from mindtrace.models.lifecycle import ModelCard, ModelStage, ModelVariant, PromotionError


class _StubReport:
    """BenchmarkReport-like stub with mixed numeric and non-numeric entries."""

    def to_dict(self) -> dict:
        return {
            "p95_ms": 12.5,
            "throughput": 80,
            "device": "cpu",
            "passed": True,  # bool must NOT be treated as numeric
            "shapes": [1, 3, 32, 32],
        }


def _make_card() -> ModelCard:
    return ModelCard(name="detector", version="v1")


class TestAddVariant:
    def test_add_variant_with_plain_metrics(self):
        card = _make_card()

        variant = card.add_variant(
            "cpu-int8",
            artifact="registry://detector/cpu-int8.onnx",
            recipe_json='{"quantize": "int8"}',
            metrics={"accuracy": 0.91, "size_mb": 4.2},
        )

        assert card.variants["cpu-int8"] is variant
        assert variant.name == "cpu-int8"
        assert variant.artifact == "registry://detector/cpu-int8.onnx"
        assert variant.recipe_json == '{"quantize": "int8"}'
        assert variant.stage is ModelStage.DEV
        assert variant.metrics == {"accuracy": 0.91, "size_mb": 4.2}
        assert variant.created_at  # timestamp populated

    def test_add_variant_merges_only_numeric_report_entries_with_bench_prefix(self):
        card = _make_card()

        variant = card.add_variant("cpu-int8", metrics={"accuracy": 0.9}, report=_StubReport())

        assert variant.metrics == {
            "accuracy": 0.9,
            "bench/p95_ms": 12.5,
            "bench/throughput": 80.0,
        }
        assert "bench/device" not in variant.metrics
        assert "bench/passed" not in variant.metrics


class TestGetVariant:
    def test_get_variant_keyerror_lists_available_names(self):
        card = _make_card()
        card.add_variant("cpu-int8")
        card.add_variant("gpu-fp16")

        with pytest.raises(KeyError, match=r"'nope'.*\['cpu-int8', 'gpu-fp16'\]"):
            card.get_variant("nope")


class TestPromoteVariant:
    def test_promote_passes_with_min_and_max_gates_satisfied(self):
        card = _make_card()
        card.add_variant("cpu-int8", metrics={"accuracy": 0.92, "bench/p95_ms": 10.0, "size_mb": 4.0})

        result = card.promote_variant(
            "cpu-int8",
            to_stage=ModelStage.STAGING,
            require={"accuracy": 0.9, "bench/p95_ms_max": 15.0, "size_mb_max": 5.0},
        )

        assert result.success is True
        assert result.failed_requirements == {}
        assert result.from_stage is ModelStage.DEV
        assert result.to_stage is ModelStage.STAGING
        assert card.get_variant("cpu-int8").stage is ModelStage.STAGING

    def test_promote_fails_listing_exactly_the_violated_gates(self):
        card = _make_card()
        card.add_variant(
            "cpu-int8",
            metrics={"accuracy": 0.80, "bench/p95_ms": 20.0, "size_mb": 4.0},
        )

        result = card.promote_variant(
            "cpu-int8",
            to_stage=ModelStage.STAGING,
            require={"accuracy": 0.9, "bench/p95_ms_max": 15.0, "size_mb_max": 5.0},
        )

        assert result.success is False
        assert set(result.failed_requirements) == {"accuracy", "bench/p95_ms_max"}
        assert result.failed_requirements["accuracy"] == (0.80, 0.9)
        assert result.failed_requirements["bench/p95_ms_max"] == (20.0, 15.0)
        # Missing metric fails with NaN actual.
        missing = card.promote_variant(
            "cpu-int8",
            to_stage=ModelStage.STAGING,
            require={"f1": 0.5},
        )
        assert math.isnan(missing.failed_requirements["f1"][0])
        # Failed gates never change the stage.
        assert card.get_variant("cpu-int8").stage is ModelStage.DEV

    def test_promote_dry_run_does_not_change_stage(self):
        card = _make_card()
        card.add_variant("cpu-int8", metrics={"accuracy": 0.95})

        result = card.promote_variant(
            "cpu-int8",
            to_stage=ModelStage.STAGING,
            require={"accuracy": 0.9},
            dry_run=True,
        )

        assert result.success is True
        assert card.get_variant("cpu-int8").stage is ModelStage.DEV

    def test_invalid_transition_raises_promotion_error(self):
        card = _make_card()
        card.add_variant("cpu-int8")

        with pytest.raises(PromotionError, match="Invalid promotion"):
            card.promote_variant("cpu-int8", to_stage=ModelStage.PRODUCTION)


class TestDemoteVariant:
    def test_demote_variant_records_reason_and_changes_stage(self):
        card = _make_card()
        card.add_variant("cpu-int8")
        card.promote_variant("cpu-int8", to_stage=ModelStage.STAGING)

        result = card.demote_variant("cpu-int8", to_stage=ModelStage.DEV, reason="latency regression")

        assert result.success is True
        assert card.get_variant("cpu-int8").stage is ModelStage.DEV
        assert card.extra["demotion_reason/cpu-int8"] == "latency regression"

    def test_demote_invalid_transition_raises(self):
        card = _make_card()
        card.add_variant("cpu-int8")

        with pytest.raises(PromotionError, match="Invalid demotion"):
            card.demote_variant("cpu-int8", to_stage=ModelStage.PRODUCTION)


class TestSerialization:
    def test_json_round_trip_with_variants(self, tmp_path):
        card = _make_card()
        card.add_result("val/accuracy", 0.93)
        variant = card.add_variant(
            "cpu-int8",
            artifact="a.onnx",
            recipe_json='{"quantize": "int8"}',
            metrics={"accuracy": 0.91},
            report=_StubReport(),
        )
        card.promote_variant("cpu-int8", to_stage=ModelStage.STAGING)
        path = tmp_path / "card.json"

        card.save_json(path)
        loaded = ModelCard.load_json(path)

        assert set(loaded.variants) == {"cpu-int8"}
        restored = loaded.get_variant("cpu-int8")
        assert isinstance(restored, ModelVariant)
        assert restored.artifact == "a.onnx"
        assert restored.recipe_json == '{"quantize": "int8"}'
        assert restored.stage is ModelStage.STAGING
        assert restored.metrics == variant.metrics
        assert restored.created_at == variant.created_at

    def test_legacy_dict_without_variants_loads(self):
        legacy = {"name": "detector", "version": "v1", "stage": "staging"}

        card = ModelCard.from_dict(legacy)

        assert card.variants == {}
        assert card.stage is ModelStage.STAGING
        # And re-serializing includes an empty variants map.
        assert card.to_dict()["variants"] == {}
