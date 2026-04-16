"""Additional unit tests for `mindtrace.models.lifecycle.card`."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mindtrace.models.lifecycle.card import ModelCard, ModelStage


def _make_card(
    name: str = "model",
    version: str = "v1",
    stage: ModelStage = ModelStage.DEV,
    registry=None,
) -> ModelCard:
    return ModelCard(name=name, version=version, stage=stage, registry=registry)


class TestModelPersistence:
    def test_load_model_uses_registry_and_returns_value(self):
        registry = MagicMock()
        loaded_model = object()
        registry.load.return_value = loaded_model
        card = _make_card(registry=registry)

        result = card.load_model()

        registry.load.assert_called_once_with("model", version="v1")
        assert result is loaded_model

    def test_load_model_requires_registry(self):
        card = _make_card(registry=None)

        with pytest.raises(RuntimeError, match="requires a registry"):
            card.load_model()

    def test_model_exists_is_false_without_registry(self):
        card = _make_card(registry=None)

        assert card.model_exists is False

    def test_model_exists_falls_back_to_model_saved_when_registry_check_fails(self):
        registry = MagicMock()
        registry.has_object.side_effect = RuntimeError("backend unavailable")
        card = _make_card(registry=registry)
        card._model_saved = True

        assert card.model_exists is True


class TestLifecycleRollback:
    def test_promote_restores_stage_when_persist_fails(self):
        registry = MagicMock()
        card = _make_card(stage=ModelStage.DEV, registry=registry)
        card.persist = MagicMock(side_effect=RuntimeError("persist failed"))

        with pytest.raises(RuntimeError, match="persist failed"):
            card.promote(to_stage=ModelStage.STAGING)

        assert card.stage is ModelStage.DEV

    def test_demote_restores_stage_when_persist_fails(self):
        registry = MagicMock()
        card = _make_card(stage=ModelStage.PRODUCTION, registry=registry)
        card.persist = MagicMock(side_effect=RuntimeError("persist failed"))

        with pytest.raises(RuntimeError, match="persist failed"):
            card.demote(to_stage=ModelStage.STAGING)

        assert card.stage is ModelStage.PRODUCTION


class TestRegistryLoading:
    def test_from_registry_loads_card_and_attaches_registry(self):
        registry = MagicMock()
        registry.load.return_value = {
            "name": "detector",
            "version": "v2",
            "stage": "staging",
            "eval_results": [],
            "known_limitations": [],
            "extra": {},
        }

        card = ModelCard.from_registry(registry, "detector", "v2", stage=ModelStage.STAGING)

        registry.load.assert_called_once_with("detector:v2:card:staging")
        assert card.registry is registry
        assert card.name == "detector"
        assert card.version == "v2"
        assert card.stage is ModelStage.STAGING
        assert card._model_saved is True
