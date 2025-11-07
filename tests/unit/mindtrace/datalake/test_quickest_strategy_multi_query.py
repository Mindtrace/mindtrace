"""Unit tests for the quickest strategy in multi-query scenarios."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId

from mindtrace.datalake import Datalake
from mindtrace.datalake.types import Datum


def create_mock_datum(
    data=None, registry_uri=None, registry_key=None, derived_from=None, metadata=None, datum_id=None, added_at=None
):
    """Create a mock Datum instance without requiring beanie initialization."""
    if datum_id is None:
        datum_id = PydanticObjectId()
    if added_at is None:
        added_at = datetime.now()

    mock_datum = MagicMock(spec=Datum)
    mock_datum.data = data
    mock_datum.registry_uri = registry_uri
    mock_datum.registry_key = registry_key
    mock_datum.derived_from = derived_from
    mock_datum.metadata = metadata or {}
    mock_datum.id = datum_id
    mock_datum.added_at = added_at
    return mock_datum


class TestQuickestStrategyMultiQuery:
    """Unit tests for the quickest strategy in multi-query scenarios."""

    @pytest.fixture
    def mock_database(self):
        """Mock database backend."""
        mock_db = AsyncMock()
        mock_db.initialize = AsyncMock()
        mock_db.find = AsyncMock()
        mock_db.aggregate = AsyncMock()
        return mock_db

    @pytest.fixture
    def mock_registry(self):
        """Mock registry backend."""
        mock_registry = MagicMock()
        mock_registry.save = MagicMock()
        mock_registry.load = MagicMock()
        return mock_registry

    @pytest.fixture
    def datalake(self, mock_database, mock_registry):
        """Create Datalake instance with mocked database and patched Datum model."""

        class _MockDatum:
            def __init__(self, data=None, registry_uri=None, registry_key=None, derived_from=None, metadata=None):
                self.data = data
                self.registry_uri = registry_uri
                self.registry_key = registry_key
                self.derived_from = derived_from
                self.metadata = metadata or {}

        db_patcher = patch("mindtrace.datalake.datalake.MongoMindtraceODMBackend", return_value=mock_database)
        registry_patcher = patch("mindtrace.datalake.datalake.Registry", return_value=mock_registry)
        datum_patcher = patch("mindtrace.datalake.datalake.Datum", _MockDatum)
        db_patcher.start()
        datum_patcher.start()
        registry_patcher.start()

        datalake_instance = Datalake("mongodb://test", "test_db")
        yield datalake_instance

        db_patcher.stop()
        datum_patcher.stop()
        registry_patcher.stop()

    @pytest.mark.asyncio
    async def test_quickest_strategy_multi_query_complex_chain(self, datalake, mock_database):
        """Test quickest strategy with complex multi-query derivation chain."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image"}, metadata={"project": "test_project"}, datum_id=PydanticObjectId()
        )

        # Mock level 1 derived data (multiple options)
        level1_datum1 = create_mock_datum(
            data={"type": "classification", "label": "label1"},
            metadata={"model": "model1"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
        )
        level1_datum2 = create_mock_datum(
            data={"type": "classification", "label": "label2"},
            metadata={"model": "model2"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
        )

        # Mock level 2 derived data (multiple options for each level 1)
        level2_datum1 = create_mock_datum(
            data={"type": "bbox", "x": 10, "y": 20},
            metadata={"model": "yolo"},
            derived_from=level1_datum1.id,
            datum_id=PydanticObjectId(),
        )
        level2_datum2 = create_mock_datum(
            data={"type": "bbox", "x": 30, "y": 40},
            metadata={"model": "yolo"},
            derived_from=level1_datum2.id,
            datum_id=PydanticObjectId(),
        )

        mock_database.aggregate.return_value = [
            {
                "image_id": base_datum.id,
                "label_id": level1_datum1.id,
                "bbox_id": level2_datum1.id,
            }
        ]

        # Test complex multi-query with quickest strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "quickest", "column": "label_id"},
            {"derived_from": "label_id", "data.type": "bbox", "strategy": "quickest", "column": "bbox_id"},
        ]
        result = await datalake.query_data(query)

        # Should return 1 result with complete chain
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == base_datum.id
        assert result[0]["label_id"] == level1_datum1.id  # Should be the first level 1 datum
        assert result[0]["bbox_id"] == level2_datum1.id  # Should be the first level 2 datum

    @pytest.mark.asyncio
    async def test_quickest_strategy_multi_query_with_multiple_base_entries(self, datalake, mock_database):
        """Test quickest strategy with multiple base entries in multi-query."""
        # Mock multiple base data
        base1 = create_mock_datum(
            data={"type": "image", "filename": "test1.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )
        base2 = create_mock_datum(
            data={"type": "image", "filename": "test2.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )

        # Mock derived data for each base
        derived1 = create_mock_datum(
            data={"type": "classification", "label": "cat"},
            metadata={"model": "resnet50"},
            derived_from=base1.id,
            datum_id=PydanticObjectId(),
        )
        derived2 = create_mock_datum(
            data={"type": "classification", "label": "dog"},
            metadata={"model": "resnet50"},
            derived_from=base2.id,
            datum_id=PydanticObjectId(),
        )

        mock_database.aggregate.return_value = [
            {"image_id": base1.id, "label_id": derived1.id},
            {"image_id": base2.id, "label_id": derived2.id},
        ]

        # Test multi-query with quickest strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "quickest", "column": "label_id"},
        ]
        result = await datalake.query_data(query)

        # Should return 2 results
        assert len(result) == 2
        assert all(isinstance(row, dict) for row in result)

        # Verify first result
        assert result[0]["image_id"] == base1.id
        assert result[0]["label_id"] == derived1.id

        # Verify second result
        assert result[1]["image_id"] == base2.id
        assert result[1]["label_id"] == derived2.id

    @pytest.mark.asyncio
    async def test_quickest_strategy_multi_query_with_missing_derived_data(self, datalake, mock_database):
        """Test quickest strategy with missing derived data in multi-query."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image"}, metadata={"project": "test_project"}, datum_id=PydanticObjectId()
        )

        # Mock database calls - no derived data found
        mock_database.aggregate.return_value = []

        # Test multi-query with quickest strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "quickest", "column": "label_id"},
        ]
        result = await datalake.query_data(query)

        # Should return empty result because no derived data found
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_quickest_strategy_multi_query_with_mixed_strategies(self, datalake, mock_database):
        """Test quickest strategy mixed with other strategies in multi-query."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image"}, metadata={"project": "test_project"}, datum_id=PydanticObjectId()
        )

        # Mock multiple derived data with different timestamps
        old_time = datetime.now() - timedelta(hours=1)
        new_time = datetime.now()

        old_derived = create_mock_datum(
            data={"type": "classification", "label": "old"},
            metadata={"model": "old_model"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
            added_at=old_time,
        )

        new_derived = create_mock_datum(
            data={"type": "classification", "label": "new"},
            metadata={"model": "new_model"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
            added_at=new_time,
        )

        # Mock level 2 derived data
        level2_datum = create_mock_datum(
            data={"type": "bbox", "x": 10, "y": 20},
            metadata={"model": "yolo"},
            derived_from=new_derived.id,  # Derived from the "new" classification
            datum_id=PydanticObjectId(),
        )

        mock_database.aggregate.return_value = [
            {
                "image_id": base_datum.id,
                "label_id": old_derived.id,
                "bbox_id": level2_datum.id,
            }
        ]

        # Test multi-query with mixed strategies
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "quickest", "column": "label_id"},
            {"derived_from": "label_id", "data.type": "bbox", "strategy": "latest", "column": "bbox_id"},
        ]
        result = await datalake.query_data(query)

        # Should return 1 result
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == base_datum.id
        assert result[0]["label_id"] == old_derived.id  # Should be the first one (quickest strategy)
        # Note: bbox_id might not be set if the bbox is derived from new_derived but we selected old_derived
        # This depends on the implementation details

    @pytest.mark.asyncio
    async def test_quickest_strategy_multi_query_with_transpose(self, datalake, mock_database):
        """Test quickest strategy with transpose=True in multi-query."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image"}, metadata={"project": "test_project"}, datum_id=PydanticObjectId()
        )

        # Mock derived data
        derived_datum = create_mock_datum(
            data={"type": "classification", "label": "cat"},
            metadata={"model": "resnet50"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
        )

        mock_database.aggregate.return_value = [
            {"image_id": base_datum.id, "label_id": derived_datum.id}
        ]

        # Test with quickest strategy and transpose=True
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "quickest", "column": "label_id"},
        ]
        result = await datalake.query_data(query, transpose=True)

        # Should return dictionary of lists
        assert isinstance(result, dict)
        assert "image_id" in result
        assert "label_id" in result
        assert len(result["image_id"]) == 1
        assert len(result["label_id"]) == 1
        assert result["image_id"][0] == base_datum.id
        assert result["label_id"][0] == derived_datum.id

    @pytest.mark.asyncio
    async def test_quickest_strategy_multi_query_with_datums_wanted(self, datalake, mock_database):
        """Test quickest strategy with datums_wanted in multi-query."""
        # Mock multiple base data
        base1 = create_mock_datum(
            data={"type": "image", "filename": "test1.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )
        base2 = create_mock_datum(
            data={"type": "image", "filename": "test2.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )
        base3 = create_mock_datum(
            data={"type": "image", "filename": "test3.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )

        # Mock derived data for each base
        derived1 = create_mock_datum(
            data={"type": "classification", "label": "cat"},
            metadata={"model": "resnet50"},
            derived_from=base1.id,
            datum_id=PydanticObjectId(),
        )
        derived2 = create_mock_datum(
            data={"type": "classification", "label": "dog"},
            metadata={"model": "resnet50"},
            derived_from=base2.id,
            datum_id=PydanticObjectId(),
        )
        derived3 = create_mock_datum(
            data={"type": "classification", "label": "bird"},
            metadata={"model": "resnet50"},
            derived_from=base3.id,
            datum_id=PydanticObjectId(),
        )

        mock_database.aggregate.return_value = [
            {"image_id": base1.id, "label_id": derived1.id},
            {"image_id": base2.id, "label_id": derived2.id},
        ]

        # Test multi-query with quickest strategy and datums_wanted=2
        query = [
            {"metadata.project": "test_project", "strategy": "quickest", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "quickest", "column": "label_id"},
        ]
        result = await datalake.query_data(query, datums_wanted=2)

        # Should return 2 results (first 2 base entries with their derived data)
        assert len(result) == 2
        assert all(isinstance(row, dict) for row in result)

        # Verify first result
        assert result[0]["image_id"] == base1.id
        assert result[0]["label_id"] == derived1.id

        # Verify second result
        assert result[1]["image_id"] == base2.id
        assert result[1]["label_id"] == derived2.id

    @pytest.mark.asyncio
    async def test_quickest_strategy_multi_query_with_partial_derived_data(self, datalake, mock_database):
        """Test quickest strategy with partial derived data in multi-query."""
        # Mock multiple base data
        base1 = create_mock_datum(
            data={"type": "image", "filename": "test1.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )
        base2 = create_mock_datum(
            data={"type": "image", "filename": "test2.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )

        # Mock derived data only for base1
        derived1 = create_mock_datum(
            data={"type": "classification", "label": "cat"},
            metadata={"model": "resnet50"},
            derived_from=base1.id,
            datum_id=PydanticObjectId(),
        )

        mock_database.aggregate.return_value = [
            {"image_id": base1.id, "label_id": derived1.id}
        ]

        # Test multi-query with quickest strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "quickest", "column": "label_id"},
        ]
        result = await datalake.query_data(query)

        # Should return only 1 result (base1 with its derived data)
        # base2 should be excluded because it has no derived data
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == base1.id
        assert result[0]["label_id"] == derived1.id

    @pytest.mark.asyncio
    async def test_quickest_strategy_multi_query_with_empty_base_data(self, datalake, mock_database):
        """Test quickest strategy with empty base data in multi-query."""
        # Mock database calls - no base data found
        mock_database.aggregate.return_value = []

        # Test multi-query with quickest strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "quickest", "column": "label_id"},
        ]
        result = await datalake.query_data(query)

        # Should return empty result because no base data found
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_quickest_strategy_multi_query_with_single_entry(self, datalake, mock_database):
        """Test quickest strategy with single entry in multi-query."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image"}, metadata={"project": "test_project"}, datum_id=PydanticObjectId()
        )

        # Mock single derived data
        derived_datum = create_mock_datum(
            data={"type": "classification", "label": "cat"},
            metadata={"model": "resnet50"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
        )

        mock_database.aggregate.return_value = [
            {"image_id": base_datum.id, "label_id": derived_datum.id}
        ]

        # Test multi-query with quickest strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "quickest", "column": "label_id"},
        ]
        result = await datalake.query_data(query)

        # Should return 1 result
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == base_datum.id
        assert result[0]["label_id"] == derived_datum.id
