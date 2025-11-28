"""Unit tests for the optimized query_data implementation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.datalake import Datalake


@pytest.fixture
def mock_database() -> MagicMock:
    """Provide a mocked database backend with aggregate support."""

    db = MagicMock()
    db.initialize = AsyncMock()
    db.aggregate = AsyncMock()
    db.find = AsyncMock()
    return db


@pytest.fixture
def mock_registry() -> MagicMock:
    """Provide a mocked registry backend."""

    registry = MagicMock()
    registry.save = MagicMock()
    registry.load = MagicMock()
    return registry


@pytest.fixture
def datalake(mock_database: MagicMock, mock_registry: MagicMock) -> Datalake:
    """Instantiate Datalake with mocked dependencies."""

    class _MockDatum:  # pragma: no cover - simple stand-in for beanie model
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    with (
        patch("mindtrace.datalake.datalake.MongoMindtraceODMBackend", return_value=mock_database),
        patch("mindtrace.datalake.datalake.Registry", return_value=mock_registry),
        patch("mindtrace.datalake.datalake.Datum", _MockDatum),
    ):
        return Datalake("mongodb://test", "test_db")


@pytest.mark.asyncio
async def test_query_data_single_base_pipeline(datalake: Datalake, mock_database: MagicMock) -> None:
    """Ensure a single base query builds the expected aggregation pipeline."""

    mock_database.aggregate.return_value = [{"image_id": "base-id"}]

    query = {"metadata.project": "test_project", "column": "image_id"}
    result = await datalake.query_data(query)

    pipeline = mock_database.aggregate.call_args[0][0]

    assert pipeline[0] == {"$match": {"metadata.project": "test_project"}}
    assert pipeline[1] == {"$sort": {"added_at": -1}}
    assert pipeline[2] == {"$addFields": {"image_id": "$_id"}}
    assert pipeline[-1] == {"$project": {"image_id": 1}}

    assert result == [{"image_id": "base-id"}]


@pytest.mark.asyncio
async def test_query_data_multi_level_pipeline(datalake: Datalake, mock_database: MagicMock) -> None:
    """Verify multi-level derivations use intermediate join fields."""

    mock_database.aggregate.return_value = [{"base_id": "b", "label_id": "l", "bbox_id": "bb"}]

    query = [
        {"metadata.project": "test_project", "column": "base_id"},
        {"derived_from": "base_id", "data.type": "classification", "column": "label_id"},
        {"derived_from": "label_id", "data.type": "bbox", "column": "bbox_id"},
    ]

    result = await datalake.query_data(query)
    pipeline = mock_database.aggregate.call_args[0][0]

    lookups = [stage["$lookup"] for stage in pipeline if "$lookup" in stage]
    assert lookups[0]["localField"] == "base_id"
    assert lookups[1]["localField"] == "label_id__join"
    assert lookups[1]["as"] == "bbox_id"

    join_add_fields = [
        stage["$addFields"] for stage in pipeline if "$addFields" in stage and "label_id__join" in stage["$addFields"]
    ]
    assert join_add_fields

    project_stage = pipeline[-1]
    assert project_stage == {"$project": {"base_id": 1, "label_id": 1, "bbox_id": 1}}

    assert result == [{"base_id": "b", "label_id": "l", "bbox_id": "bb"}]


@pytest.mark.asyncio
async def test_query_data_random_strategy_uses_rand(datalake: Datalake, mock_database: MagicMock) -> None:
    """Random strategy should rely on $rand instead of returning first item."""

    mock_database.aggregate.return_value = [{"image_id": "i", "label_id": "l"}]

    query = [
        {"metadata.project": "p", "column": "image_id"},
        {"derived_from": "image_id", "column": "label_id", "strategy": "random"},
    ]

    await datalake.query_data(query)

    pipeline = mock_database.aggregate.call_args[0][0]

    def contains_rand(value):
        if isinstance(value, dict):
            return "$rand" in value or any(contains_rand(v) for v in value.values())
        if isinstance(value, list):
            return any(contains_rand(v) for v in value)
        return False

    random_stage = next(stage for stage in pipeline if "$addFields" in stage and contains_rand(stage))

    assert contains_rand(random_stage)


def test_build_match_conditions_nested_fields(datalake: Datalake) -> None:
    """_build_match_conditions should create nested $getField expressions."""

    conditions = datalake._build_match_conditions(
        {
            "data.type": "classification",
            "metadata.score": {"$gte": 0.5},
        }
    )

    expected = {
        "$and": [
            {
                "$and": [
                    {
                        "$ne": [
                            {
                                "$getField": {
                                    "field": "type",
                                    "input": {
                                        "$getField": {
                                            "field": "data",
                                            "input": "$$this",
                                        }
                                    },
                                }
                            },
                            None,
                        ]
                    },
                    {
                        "$eq": [
                            {
                                "$getField": {
                                    "field": "type",
                                    "input": {
                                        "$getField": {
                                            "field": "data",
                                            "input": "$$this",
                                        }
                                    },
                                }
                            },
                            "classification",
                        ]
                    },
                ]
            },
            {
                "$gte": [
                    {
                        "$getField": {
                            "field": "score",
                            "input": {
                                "$getField": {
                                    "field": "metadata",
                                    "input": "$$this",
                                }
                            },
                        }
                    },
                    0.5,
                ]
            },
        ]
    }

    assert conditions == expected


def test_build_match_conditions_empty(datalake: Datalake) -> None:
    """Empty query dictionaries should return None."""

    assert datalake._build_match_conditions({}) is None
