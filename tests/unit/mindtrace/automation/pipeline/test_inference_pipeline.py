"""Tests for InferencePipeline with the fixed _StoreStep.

Verifies the full fetch → infer → store flow using a duck-typed
datalake that exposes the real Datalake.store_data() / query_data()
async interface.
"""

from __future__ import annotations

from typing import Any

import pytest

from mindtrace.automation.pipeline import (
    InferenceConfig,
    InferencePipeline,
)

# -- Duck-typed collaborators ------------------------------------------------


class _FakeDatalake:
    """Async datalake stub matching the real Datalake protocol."""

    def __init__(self, records: list[dict]) -> None:
        self._records = records
        self.stored: list[dict] = []

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

    async def store_data(
        self,
        data: Any,
        *,
        metadata: dict | None = None,
        schema: str | None = None,
        derived_from: Any = None,
        registry_uri: str | None = None,
    ) -> dict:
        record = {"data": data, "schema": schema}
        self.stored.append(record)
        return record


class _FakeService:
    """Synchronous predict service."""

    def predict(self, inp: Any) -> dict:
        return {"label": "ok", "confidence": 0.95}


# -- Fixtures ----------------------------------------------------------------


@pytest.fixture()
def records():
    return [{"id": i, "type": "image", "path": f"/data/{i:04d}.jpg"} for i in range(12)]


@pytest.fixture()
def datalake(records):
    return _FakeDatalake(records)


@pytest.fixture()
def service():
    return _FakeService()


# -- Tests -------------------------------------------------------------------


class TestInferencePipelineDryRun:
    def test_dry_run_does_not_store(self, datalake, service):
        pipeline = InferencePipeline.build(
            name="test_dry",
            datalake=datalake,
            service=service,
            config=InferenceConfig(
                query={"type": "image"},
                dry_run=True,
            ),
        )
        result = pipeline.run()
        assert result.success
        assert len(datalake.stored) == 0

    def test_dry_run_reports_would_store_count(self, datalake, service):
        pipeline = InferencePipeline.build(
            name="test_dry_count",
            datalake=datalake,
            service=service,
            config=InferenceConfig(
                query={"type": "image"},
                datums_wanted=5,
                dry_run=True,
            ),
        )
        result = pipeline.run()
        # dry_run step is omitted from pipeline — last step is run_inference
        infer_step = next(s for s in result.steps if s.step_name == "run_inference")
        assert infer_step.metadata["ok"] == 5


class TestInferencePipelineLiveStore:
    def test_store_writes_to_datalake(self, datalake, service):
        pipeline = InferencePipeline.build(
            name="test_live",
            datalake=datalake,
            service=service,
            config=InferenceConfig(
                query={"type": "image"},
                result_schema="predictions",
                dry_run=False,
            ),
        )
        result = pipeline.run()
        assert result.success

        store_step = next(s for s in result.steps if s.step_name == "store_results")
        assert store_step.metadata["stored"] == 12
        assert len(datalake.stored) == 12

    def test_store_records_schema(self, datalake, service):
        pipeline = InferencePipeline.build(
            name="test_schema",
            datalake=datalake,
            service=service,
            config=InferenceConfig(
                query={"type": "image"},
                datums_wanted=3,
                result_schema="my_schema",
                dry_run=False,
            ),
        )
        pipeline.run()
        assert all(r["schema"] == "my_schema" for r in datalake.stored)

    def test_store_with_transform(self, datalake, service):
        pipeline = InferencePipeline.build(
            name="test_transform",
            datalake=datalake,
            service=service,
            config=InferenceConfig(
                query={"type": "image"},
                datums_wanted=2,
                transform=lambda rec: {"path": rec["path"]},
                dry_run=False,
            ),
        )
        result = pipeline.run()
        assert result.success
        assert len(datalake.stored) == 2

    def test_batch_size_does_not_affect_count(self, datalake, service):
        pipeline = InferencePipeline.build(
            name="test_batch",
            datalake=datalake,
            service=service,
            config=InferenceConfig(
                query={"type": "image"},
                batch_size=3,
                dry_run=False,
            ),
        )
        result = pipeline.run()
        store_step = next(s for s in result.steps if s.step_name == "store_results")
        assert store_step.metadata["stored"] == 12


class TestInferencePipelineSteps:
    def test_three_steps_when_not_dry_run(self, datalake, service):
        pipeline = InferencePipeline.build(
            name="test_steps",
            datalake=datalake,
            service=service,
            config=InferenceConfig(
                query={"type": "image"},
                dry_run=False,
            ),
        )
        result = pipeline.run()
        assert [s.step_name for s in result.steps] == ["fetch_records", "run_inference", "store_results"]

    def test_two_steps_when_dry_run(self, datalake, service):
        pipeline = InferencePipeline.build(
            name="test_steps_dry",
            datalake=datalake,
            service=service,
            config=InferenceConfig(
                query={"type": "image"},
                dry_run=True,
            ),
        )
        result = pipeline.run()
        assert [s.step_name for s in result.steps] == ["fetch_records", "run_inference"]

    def test_fetch_metadata_has_record_count(self, datalake, service):
        pipeline = InferencePipeline.build(
            name="test_fetch_meta",
            datalake=datalake,
            service=service,
            config=InferenceConfig(
                query={"type": "image"},
                datums_wanted=7,
                dry_run=True,
            ),
        )
        result = pipeline.run()
        fetch = result.steps[0]
        assert fetch.metadata["record_count"] == 7
