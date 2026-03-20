"""Tests for ActiveLearningPipeline.

Verifies the fetch → infer → filter → push → optional retrain flow.
"""

from __future__ import annotations

from typing import Any

import pytest

from mindtrace.automation.pipeline import (
    ActiveLearningConfig,
    ActiveLearningPipeline,
    TrainingConfig,
    TrainingPipeline,
)

# -- Stubs -------------------------------------------------------------------


class _FakeDatalake:
    def __init__(self, records: list[dict]) -> None:
        self._records = records

    async def query_data(
        self,
        query: dict | list[dict],
        datums_wanted: int | None = None,
        transpose: bool = False,
    ) -> list[dict]:
        if isinstance(query, list):
            query = query[0] if query else {}
        results = [r for r in self._records if all(r.get(k) == v for k, v in query.items())]
        if datums_wanted:
            results = results[:datums_wanted]
        return results


class _LowConfidenceService:
    """Returns low confidence to trigger uncertainty filtering."""

    def predict(self, inp: Any) -> dict:
        return {"label": "uncertain", "confidence": 0.3}


class _HighConfidenceService:
    """Returns high confidence — nothing should be flagged uncertain."""

    def predict(self, inp: Any) -> dict:
        return {"label": "certain", "confidence": 0.99}


class _FakeLabelStudio:
    """Minimal LS stub that records pushed tasks."""

    def __init__(self):
        self.pushed: list[dict] = []

    class _Project:
        def __init__(self, parent):
            self._parent = parent

        def import_tasks(self, tasks):
            self._parent.pushed.extend(tasks)

    @property
    def client(self):
        return self

    def get_project(self, project_id):
        return self._Project(self)


class _FakeTrainer:
    def train(self, **kwargs):
        return {"loss": 0.1, "accuracy": 0.9}


class _FakeEvaluator:
    def evaluate(self, **kwargs):
        return {"accuracy": 0.9}


# -- Fixtures ----------------------------------------------------------------


@pytest.fixture()
def records():
    return [{"id": i, "type": "img"} for i in range(10)]


@pytest.fixture()
def datalake(records):
    return _FakeDatalake(records)


@pytest.fixture()
def label_studio():
    return _FakeLabelStudio()


# -- Tests -------------------------------------------------------------------


class TestActiveLearningPipeline:
    def test_low_confidence_triggers_push(self, datalake, label_studio):
        pipeline = ActiveLearningPipeline.build(
            name="test_al",
            datalake=datalake,
            service=_LowConfidenceService(),
            label_studio=label_studio,
            config=ActiveLearningConfig(
                query={"type": "img"},
                label_studio_project_id=1,
                uncertainty_threshold=0.5,
                max_samples_to_label=100,
            ),
        )
        result = pipeline.run()
        assert result.success

        filter_step = next(s for s in result.steps if s.step_name == "filter_uncertain")
        assert filter_step.metadata["uncertain"] == 10

        push_step = next(s for s in result.steps if s.step_name == "push_to_label_studio")
        assert push_step.metadata["pushed"] == 10
        assert len(label_studio.pushed) == 10

    def test_high_confidence_skips_push(self, datalake, label_studio):
        pipeline = ActiveLearningPipeline.build(
            name="test_al_skip",
            datalake=datalake,
            service=_HighConfidenceService(),
            label_studio=label_studio,
            config=ActiveLearningConfig(
                query={"type": "img"},
                label_studio_project_id=1,
                uncertainty_threshold=0.5,
            ),
        )
        result = pipeline.run()
        assert result.success

        filter_step = next(s for s in result.steps if s.step_name == "filter_uncertain")
        assert filter_step.metadata["uncertain"] == 0
        assert len(label_studio.pushed) == 0

    def test_max_samples_caps_push(self, datalake, label_studio):
        pipeline = ActiveLearningPipeline.build(
            name="test_al_cap",
            datalake=datalake,
            service=_LowConfidenceService(),
            label_studio=label_studio,
            config=ActiveLearningConfig(
                query={"type": "img"},
                label_studio_project_id=1,
                uncertainty_threshold=0.5,
                max_samples_to_label=3,
            ),
        )
        result = pipeline.run()
        filter_step = next(s for s in result.steps if s.step_name == "filter_uncertain")
        assert filter_step.metadata["uncertain"] == 3

    def test_no_label_studio_is_noop(self, datalake):
        pipeline = ActiveLearningPipeline.build(
            name="test_al_nols",
            datalake=datalake,
            service=_LowConfidenceService(),
            label_studio=None,
            config=ActiveLearningConfig(
                query={"type": "img"},
                uncertainty_threshold=0.5,
            ),
        )
        result = pipeline.run()
        assert result.success
        push_step = next(s for s in result.steps if s.step_name == "push_to_label_studio")
        assert push_step.metadata["pushed"] == 0

    def test_auto_retrain_triggers_sub_pipeline(self, datalake, label_studio):
        retrain = TrainingPipeline.build(
            name="retrain",
            trainer=_FakeTrainer(),
            evaluator=_FakeEvaluator(),
            config=TrainingConfig(
                model_name="test",
                version="v1",
                trainer_kwargs={"epochs": 1},
            ),
        )
        pipeline = ActiveLearningPipeline.build(
            name="test_al_retrain",
            datalake=datalake,
            service=_LowConfidenceService(),
            label_studio=label_studio,
            config=ActiveLearningConfig(
                query={"type": "img"},
                label_studio_project_id=1,
                uncertainty_threshold=0.5,
                auto_retrain=True,
                retrain_pipeline=retrain,
            ),
        )
        result = pipeline.run()
        assert result.success
        retrain_step = next(s for s in result.steps if s.step_name == "conditional_retrain")
        assert retrain_step.metadata["retrained"] is True

    def test_auto_retrain_skipped_when_nothing_pushed(self, datalake, label_studio):
        retrain = TrainingPipeline.build(
            name="retrain",
            trainer=_FakeTrainer(),
            config=TrainingConfig(model_name="test", version="v1"),
        )
        pipeline = ActiveLearningPipeline.build(
            name="test_al_no_retrain",
            datalake=datalake,
            service=_HighConfidenceService(),
            label_studio=label_studio,
            config=ActiveLearningConfig(
                query={"type": "img"},
                label_studio_project_id=1,
                uncertainty_threshold=0.5,
                auto_retrain=True,
                retrain_pipeline=retrain,
            ),
        )
        result = pipeline.run()
        assert result.success
        retrain_step = next(s for s in result.steps if s.step_name == "conditional_retrain")
        assert retrain_step.metadata["retrained"] is False

    def test_step_names(self, datalake, label_studio):
        pipeline = ActiveLearningPipeline.build(
            name="test_steps",
            datalake=datalake,
            service=_LowConfidenceService(),
            label_studio=label_studio,
            config=ActiveLearningConfig(
                query={"type": "img"},
                label_studio_project_id=1,
            ),
        )
        result = pipeline.run()
        names = [s.step_name for s in result.steps]
        assert names == [
            "fetch_records",
            "run_inference",
            "filter_uncertain",
            "push_to_label_studio",
        ]
