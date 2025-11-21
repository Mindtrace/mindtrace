"""Unit tests for the query_data_legacy method in the Datalake class."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId

from mindtrace.datalake import Datalake
from mindtrace.datalake.types import Datum


def create_mock_datum(
    data=None, registry_uri=None, registry_key=None, derived_from=None, metadata=None, datum_id=None, added_at=None, contract="default"
):
    """Create a mock Datum instance without requiring beanie initialization."""
    if datum_id is None:
        datum_id = PydanticObjectId()
    if added_at is None:
        added_at = datetime.now()

    mock_datum = MagicMock(spec=Datum)
    mock_datum.data = data
    mock_datum.contract = contract
    mock_datum.registry_uri = registry_uri
    mock_datum.registry_key = registry_key
    mock_datum.derived_from = derived_from
    mock_datum.metadata = metadata or {}
    mock_datum.id = datum_id
    mock_datum.added_at = added_at
    return mock_datum


class TestQueryDataUnit:
    """Unit tests for the query_data_legacy method."""

    @pytest.fixture
    def mock_database(self):
        """Mock database backend."""
        mock_db = AsyncMock()
        mock_db.initialize = AsyncMock()
        mock_db.find = AsyncMock()
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
            def __init__(self, data=None, registry_uri=None, registry_key=None, derived_from=None, metadata=None, contract="default"):
                self.data = data
                self.contract = contract
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
    async def test_single_query_dict(self, datalake, mock_database):
        """Test single query with dict input."""
        # Mock data
        datum1 = create_mock_datum(
            data={"type": "image", "filename": "test1.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )
        datum2 = create_mock_datum(
            data={"type": "image", "filename": "test2.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )

        mock_database.find.return_value = [datum1, datum2]

        # Test single query
        query = {"metadata.project": "test_project", "column": "image_id"}
        result = await datalake.query_data_legacy(query)

        # Verify database call
        expected_query = {"metadata.project": "test_project"}
        mock_database.find.assert_called_once_with(expected_query)

        # Verify result format
        assert len(result) == 2
        assert all(isinstance(row, dict) for row in result)
        assert result[0]["image_id"] == datum1.id
        assert result[1]["image_id"] == datum2.id

    @pytest.mark.asyncio
    async def test_single_query_list(self, datalake, mock_database):
        """Test single query with list input (single element)."""
        datum = create_mock_datum(
            data={"type": "image"}, metadata={"project": "test_project"}, datum_id=PydanticObjectId()
        )

        mock_database.find.return_value = [datum]

        # Test single query as list
        query = [{"metadata.project": "test_project", "column": "image_id"}]
        result = await datalake.query_data_legacy(query)

        # Verify database call
        expected_query = {"metadata.project": "test_project"}
        mock_database.find.assert_called_once_with(expected_query)

        # Verify result format
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == datum.id

    @pytest.mark.asyncio
    async def test_multi_query_with_derivation(self, datalake, mock_database):
        """Test multi-query with derived data."""
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

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [derived_datum],  # Second query: find derived data
        ]

        # Test multi-query
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "column": "label_id"},
        ]
        result = await datalake.query_data_legacy(query)

        # Verify database calls
        assert mock_database.find.call_count == 2

        # First call should be the base query
        first_call = mock_database.find.call_args_list[0][0][0]
        assert first_call == {"metadata.project": "test_project"}

        # Second call should have derived_from replaced with actual ID
        second_call = mock_database.find.call_args_list[1][0][0]
        assert second_call == {"derived_from": base_datum.id, "data.type": "classification"}

        # Verify result format
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == base_datum.id
        assert result[0]["label_id"] == derived_datum.id

    @pytest.mark.asyncio
    async def test_multi_query_with_strategy_latest(self, datalake, mock_database):
        """Test multi-query with latest strategy."""
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

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [old_derived, new_derived],  # Second query: find derived data (multiple)
        ]

        # Test multi-query with latest strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "latest", "column": "label_id"},
        ]
        result = await datalake.query_data_legacy(query)

        # Verify database calls
        assert mock_database.find.call_count == 2

        # Verify result format - should select the latest (new_derived)
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == base_datum.id
        assert result[0]["label_id"] == new_derived.id  # Should be the latest one

    @pytest.mark.asyncio
    async def test_multi_query_missing_derived_data(self, datalake, mock_database):
        """Test multi-query where derived data is missing."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image"}, metadata={"project": "test_project"}, datum_id=PydanticObjectId()
        )

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [],  # Second query: no derived data found
        ]

        # Test multi-query
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "column": "label_id"},
        ]
        result = await datalake.query_data_legacy(query)

        # Verify database calls
        assert mock_database.find.call_count == 2

        # Verify result - should be empty because no derived data found
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_multi_query_complex_chain(self, datalake, mock_database):
        """Test complex multi-query with multiple derivation levels."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image"}, metadata={"project": "test_project"}, datum_id=PydanticObjectId()
        )

        # Mock level 1 derived data
        level1_datum = create_mock_datum(
            data={"type": "classification", "label": "cat"},
            metadata={"model": "resnet50"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
        )

        # Mock level 2 derived data
        level2_datum = create_mock_datum(
            data={"bbox": [[10.0, 20.0, 50.0, 60.0]]},  # x1, y1, x2, y2 format
            metadata={"model": "yolo"},
            contract="bbox",
            derived_from=level1_datum.id,
            datum_id=PydanticObjectId(),
        )

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # Query 1: find base data
            [level1_datum],  # Query 2: find level 1 derived data
            [level2_datum],  # Query 3: find level 2 derived data
        ]

        # Test complex multi-query
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "column": "label_id"},
            {"derived_from": "label_id", "data.type": "bbox", "column": "bbox_id"},
        ]
        result = await datalake.query_data_legacy(query)

        # Verify database calls
        assert mock_database.find.call_count == 3

        # Verify each query call
        first_call = mock_database.find.call_args_list[0][0][0]
        assert first_call == {"metadata.project": "test_project"}

        second_call = mock_database.find.call_args_list[1][0][0]
        assert second_call == {"derived_from": base_datum.id, "data.type": "classification"}

        third_call = mock_database.find.call_args_list[2][0][0]
        assert third_call == {"derived_from": level1_datum.id, "data.type": "bbox"}

        # Verify result format
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == base_datum.id
        assert result[0]["label_id"] == level1_datum.id
        assert result[0]["bbox_id"] == level2_datum.id

    @pytest.mark.asyncio
    async def test_query_with_empty_result(self, datalake, mock_database):
        """Test query that returns no results."""
        mock_database.find.return_value = []

        query = {"metadata.project": "nonexistent_project", "column": "image_id"}
        result = await datalake.query_data_legacy(query)

        # Verify database call
        expected_query = {"metadata.project": "nonexistent_project"}
        mock_database.find.assert_called_once_with(expected_query)

        # Verify result
        assert result == []

    @pytest.mark.asyncio
    async def test_query_with_invalid_strategy(self, datalake, mock_database):
        """Test query with invalid strategy raises error."""
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

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [derived_datum],  # Second query: find derived data
        ]

        # Test query with invalid strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "invalid", "column": "label_id"},
        ]

        with pytest.raises(ValueError, match="Invalid strategy: invalid"):
            await datalake.query_data_legacy(query)

    @pytest.mark.asyncio
    async def test_query_with_default_strategy(self, datalake, mock_database):
        """Test query with default strategy (latest)."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image"}, metadata={"project": "test_project"}, datum_id=PydanticObjectId()
        )

        # Mock multiple derived data
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

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [old_derived, new_derived],  # Second query: find derived data (multiple)
        ]

        # Test query without explicit strategy (should default to "latest")
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "column": "label_id"},
        ]
        result = await datalake.query_data_legacy(query)

        # Verify result - should select the latest (new_derived)
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == base_datum.id
        assert result[0]["label_id"] == new_derived.id  # Should be the latest one

    @pytest.mark.asyncio
    async def test_query_with_complex_data_filters(self, datalake, mock_database):
        """Test query with complex data field filters."""
        # Mock data with complex structures
        datum1 = create_mock_datum(
            data={
                "type": "image",
                "filename": "test1.jpg",
                "size": 1024,
                "tags": ["nature", "outdoor"],
                "location": {"city": "Paris", "country": "France"},
            },
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )

        _ = create_mock_datum(
            data={
                "type": "image",
                "filename": "test2.jpg",
                "size": 512,
                "tags": ["urban", "indoor"],
                "location": {"city": "London", "country": "UK"},
            },
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )

        mock_database.find.return_value = [datum1]

        # Test complex query
        query = {
            "data.type": "image",
            "data.size": {"$gt": 600},
            "data.tags": {"$in": ["nature"]},
            "data.location.city": "Paris",
            "column": "image_id",
        }
        result = await datalake.query_data_legacy(query)

        # Verify database call
        expected_query = {
            "data.type": "image",
            "data.size": {"$gt": 600},
            "data.tags": {"$in": ["nature"]},
            "data.location.city": "Paris",
        }
        mock_database.find.assert_called_once_with(expected_query)

        # Verify result
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == datum1.id

    @pytest.mark.asyncio
    async def test_query_with_complex_metadata_filters(self, datalake, mock_database):
        """Test query with complex metadata field filters."""
        # Mock data with complex metadata
        datum1 = create_mock_datum(
            data={"type": "image"},
            metadata={
                "project": "test_project",
                "tags": ["nature", "outdoor"],
                "location": {"city": "Paris", "country": "France"},
                "quality": 0.95,
                "models": ["resnet50", "vgg16"],
            },
            datum_id=PydanticObjectId(),
        )

        mock_database.find.return_value = [datum1]

        # Test complex metadata query
        query = {
            "metadata.project": "test_project",
            "metadata.tags": {"$in": ["nature"]},
            "metadata.location.city": "Paris",
            "metadata.quality": {"$gte": 0.9},
            "metadata.models": {"$in": ["resnet50"]},
            "column": "image_id",
        }
        result = await datalake.query_data_legacy(query)

        # Verify database call
        expected_query = {
            "metadata.project": "test_project",
            "metadata.tags": {"$in": ["nature"]},
            "metadata.location.city": "Paris",
            "metadata.quality": {"$gte": 0.9},
            "metadata.models": {"$in": ["resnet50"]},
        }
        mock_database.find.assert_called_once_with(expected_query)

        # Verify result
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == datum1.id

    @pytest.mark.asyncio
    async def test_query_with_multiple_base_results(self, datalake, mock_database):
        """Test query with multiple base results and derived data."""
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

        # Mock database calls
        mock_database.find.side_effect = [
            [base1, base2],  # First query: find base data
            [derived1],  # Second query for base1: find derived data
            [derived2],  # Second query for base2: find derived data
        ]

        # Test multi-query
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "column": "label_id"},
        ]
        result = await datalake.query_data_legacy(query)

        # Verify database calls
        assert mock_database.find.call_count == 3

        # Verify result format
        assert len(result) == 2
        assert all(isinstance(row, dict) for row in result)

        # Verify first result
        assert result[0]["image_id"] == base1.id
        assert result[0]["label_id"] == derived1.id

        # Verify second result
        assert result[1]["image_id"] == base2.id
        assert result[1]["label_id"] == derived2.id

    @pytest.mark.asyncio
    async def test_query_with_mixed_derivation_indices(self, datalake, mock_database):
        """Test query with mixed derivation indices (not just sequential)."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image"}, metadata={"project": "test_project"}, datum_id=PydanticObjectId()
        )

        # Mock level 1 derived data
        level1_datum = create_mock_datum(
            data={"type": "classification", "label": "cat"},
            metadata={"model": "resnet50"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
        )

        # Mock level 2 derived data (derived from level 1, not base)
        level2_datum = create_mock_datum(
            data={"bbox": [[10.0, 20.0, 50.0, 60.0]]},  # x1, y1, x2, y2 format
            metadata={"model": "yolo"},
            contract="bbox",
            derived_from=level1_datum.id,
            datum_id=PydanticObjectId(),
        )

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # Query 1: find base data
            [level1_datum],  # Query 2: find level 1 derived data
            [level2_datum],  # Query 3: find level 2 derived data (derived from level 1)
        ]

        # Test query with mixed derivation indices
        query = [
            {"metadata.project": "test_project", "column": "image_id"},  # Index 0: base
            {
                "derived_from": "image_id",
                "data.type": "classification",
                "column": "label_id",
            },  # Index 1: derived from 0
            {"derived_from": "label_id", "data.type": "bbox", "column": "bbox_id"},  # Index 2: derived from 1
        ]
        result = await datalake.query_data_legacy(query)

        # Verify database calls
        assert mock_database.find.call_count == 3

        # Verify each query call
        first_call = mock_database.find.call_args_list[0][0][0]
        assert first_call == {"metadata.project": "test_project"}

        second_call = mock_database.find.call_args_list[1][0][0]
        assert second_call == {"derived_from": base_datum.id, "data.type": "classification"}

        third_call = mock_database.find.call_args_list[2][0][0]
        assert third_call == {"derived_from": level1_datum.id, "data.type": "bbox"}

        # Verify result format
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == base_datum.id
        assert result[0]["label_id"] == level1_datum.id
        assert result[0]["bbox_id"] == level2_datum.id

    @pytest.mark.asyncio
    async def test_query_with_empty_query_list(self, datalake, mock_database):
        """Test query with empty query list raises assertion error."""
        query = []

        with pytest.raises(AssertionError):
            await datalake.query_data_legacy(query)

    @pytest.mark.asyncio
    async def test_query_without_column_raises_error(self, datalake, mock_database):
        """Test query without column raises ValueError."""
        query = {"metadata.project": "test_project"}

        with pytest.raises(ValueError, match="column must be provided"):
            await datalake.query_data_legacy(query)

    @pytest.mark.asyncio
    async def test_multi_query_with_strategy_missing_no_derived_data(self, datalake, mock_database):
        """Test multi-query with missing strategy when no derived data exists."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image", "filename": "test.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )

        # Mock database calls - no derived data found
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [],  # Second query: no derived data found
        ]

        # Test multi-query with missing strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "missing", "column": "label_id"},
        ]
        result = await datalake.query_data_legacy(query)

        # Should return 1 result because no derived data was found (missing strategy)
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == base_datum.id
        # label_id should not be present since no derived data was found

    @pytest.mark.asyncio
    async def test_multi_query_with_strategy_missing_derived_data_exists(self, datalake, mock_database):
        """Test multi-query with missing strategy when derived data exists."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image", "filename": "test.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )

        # Mock derived data
        derived_datum = create_mock_datum(
            data={"type": "classification", "label": "cat"},
            metadata={"model": "resnet50"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
        )

        # Mock database calls - derived data found
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [derived_datum],  # Second query: derived data found
        ]

        # Test multi-query with missing strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "missing", "column": "label_id"},
        ]
        result = await datalake.query_data_legacy(query)

        # Should return 0 results because derived data was found (missing strategy excludes it)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_multi_query_with_strategy_missing_multiple_base_results(self, datalake, mock_database):
        """Test multi-query with missing strategy with multiple base results."""
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

        # Mock database calls
        mock_database.find.side_effect = [
            [base1, base2],  # First query: find base data
            [derived1],  # Second query for base1: derived data found
            [],  # Second query for base2: no derived data found
        ]

        # Test multi-query with missing strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "missing", "column": "label_id"},
        ]
        result = await datalake.query_data_legacy(query)

        # Should return 1 result (only base2) because base1 has derived data
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == base2.id

    @pytest.mark.asyncio
    async def test_multi_query_with_strategy_missing_invalid_for_base_query(self, datalake, mock_database):
        """Test that missing strategy is not allowed for base query."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image", "filename": "test.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )

        mock_database.find.return_value = [base_datum]

        # Test that missing strategy in base query raises error
        query = [{"metadata.project": "test_project", "strategy": "missing", "column": "image_id"}]

        with pytest.raises(ValueError, match="Invalid strategy: missing"):
            await datalake.query_data_legacy(query)

    @pytest.mark.asyncio
    async def test_multi_query_without_column_raises_error(self, datalake, mock_database):
        """Test multi-query without column in subquery raises ValueError."""
        base_datum = create_mock_datum(datum_id=PydanticObjectId())
        mock_database.find.return_value = [base_datum]

        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification"},  # Missing column
        ]

        with pytest.raises(ValueError, match="column must be provided"):
            await datalake.query_data_legacy(query)

    @pytest.mark.asyncio
    async def test_multi_query_with_strategy_earliest(self, datalake, mock_database):
        """Test multi-query with earliest strategy selects the oldest by added_at."""
        base = create_mock_datum(datum_id=PydanticObjectId())
        older = create_mock_datum(
            derived_from=base.id, added_at=datetime.now() - timedelta(hours=2), datum_id=PydanticObjectId()
        )
        newer = create_mock_datum(
            derived_from=base.id, added_at=datetime.now() - timedelta(hours=1), datum_id=PydanticObjectId()
        )

        mock_database.find.side_effect = [
            [base],
            [newer, older],
        ]

        query = [
            {"metadata.project": "p", "column": "image_id"},
            {"derived_from": "image_id", "strategy": "earliest", "column": "label_id"},
        ]
        result = await datalake.query_data_legacy(query)

        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["label_id"] == older.id

    @pytest.mark.asyncio
    async def test_multi_query_with_strategy_random(self, datalake, mock_database):
        """Test multi-query with random strategy uses random.choice."""
        base = create_mock_datum(datum_id=PydanticObjectId())
        a = create_mock_datum(
            derived_from=base.id, added_at=datetime.now() - timedelta(hours=2), datum_id=PydanticObjectId()
        )
        b = create_mock_datum(
            derived_from=base.id, added_at=datetime.now() - timedelta(hours=1), datum_id=PydanticObjectId()
        )

        mock_database.find.side_effect = [
            [base],
            [a, b],
        ]

        with patch("mindtrace.datalake.datalake.random.choice", return_value=b):
            result = await datalake.query_data_legacy(
                [
                    {"metadata.project": "p", "column": "image_id"},
                    {"derived_from": "image_id", "strategy": "random", "column": "label_id"},
                ]
            )

        assert len(result) == 1
        assert result[0]["label_id"] == b.id

    @pytest.mark.asyncio
    async def test_datums_wanted_latest_single_query(self, datalake, mock_database):
        """Base selection uses latest strategy when datums_wanted is provided."""
        d1 = create_mock_datum(added_at=datetime.now() - timedelta(hours=3), datum_id=PydanticObjectId())
        d2 = create_mock_datum(added_at=datetime.now() - timedelta(hours=2), datum_id=PydanticObjectId())
        d3 = create_mock_datum(added_at=datetime.now() - timedelta(hours=1), datum_id=PydanticObjectId())

        mock_database.find.return_value = [d1, d2, d3]

        result = await datalake.query_data_legacy({"metadata.project": "p", "column": "image_id"}, datums_wanted=2)

        # Latest two should be selected: d3 and d2 (order not asserted)
        result_ids = {row["image_id"] for row in result}
        assert len(result) == 2
        assert result_ids == {d2.id, d3.id}

    @pytest.mark.asyncio
    async def test_datums_wanted_earliest_single_query(self, datalake, mock_database):
        """Base selection supports earliest strategy for datums_wanted."""
        d1 = create_mock_datum(added_at=datetime.now() - timedelta(hours=3), datum_id=PydanticObjectId())
        d2 = create_mock_datum(added_at=datetime.now() - timedelta(hours=2), datum_id=PydanticObjectId())
        d3 = create_mock_datum(added_at=datetime.now() - timedelta(hours=1), datum_id=PydanticObjectId())

        mock_database.find.return_value = [d1, d2, d3]

        result = await datalake.query_data_legacy(
            [{"metadata.project": "p", "strategy": "earliest", "column": "image_id"}], datums_wanted=2
        )

        result_ids = {row["image_id"] for row in result}
        assert len(result) == 2
        assert result_ids == {d1.id, d2.id}

    @pytest.mark.asyncio
    async def test_datums_wanted_random_single_query(self, datalake, mock_database):
        """Base selection supports random strategy for datums_wanted using random.sample."""
        d1 = create_mock_datum(added_at=datetime.now() - timedelta(hours=3), datum_id=PydanticObjectId())
        d2 = create_mock_datum(added_at=datetime.now() - timedelta(hours=2), datum_id=PydanticObjectId())
        d3 = create_mock_datum(added_at=datetime.now() - timedelta(hours=1), datum_id=PydanticObjectId())

        mock_database.find.return_value = [d1, d2, d3]

        with patch("mindtrace.datalake.datalake.random.sample", return_value=[d1, d3]):
            result = await datalake.query_data_legacy(
                [{"metadata.project": "p", "strategy": "random", "column": "image_id"}], datums_wanted=2
            )

        result_ids = {row["image_id"] for row in result}
        assert len(result) == 2
        # Should select from the available data (exact selection depends on random.sample mock)
        assert len(result_ids) == 2
        assert all(rid in {d1.id, d2.id, d3.id} for rid in result_ids)

    @pytest.mark.asyncio
    async def test_query_data_with_transpose_single_query(self, datalake, mock_database):
        """Test query_data with transpose=True for single query."""
        # Mock data
        datum1 = create_mock_datum(
            data={"type": "image", "filename": "test1.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )
        datum2 = create_mock_datum(
            data={"type": "image", "filename": "test2.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )

        mock_database.find.return_value = [datum1, datum2]

        # Test with transpose=True
        query = {"metadata.project": "test_project", "column": "image_id"}
        result = await datalake.query_data_legacy(query, transpose=True)

        # Should return dictionary of lists
        assert isinstance(result, dict)
        assert "image_id" in result
        assert len(result["image_id"]) == 2
        assert datum1.id in result["image_id"]
        assert datum2.id in result["image_id"]

    @pytest.mark.asyncio
    async def test_query_data_with_transpose_multi_query(self, datalake, mock_database):
        """Test query_data with transpose=True for multi-query."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image", "filename": "test.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )

        # Mock derived data
        derived_datum = create_mock_datum(
            data={"type": "classification", "label": "cat"},
            metadata={"model": "resnet50"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
        )

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [derived_datum],  # Second query: find derived data
        ]

        # Test with transpose=True
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "column": "label_id"},
        ]
        result = await datalake.query_data_legacy(query, transpose=True)

        # Should return dictionary of lists
        assert isinstance(result, dict)
        assert "image_id" in result
        assert "label_id" in result
        assert len(result["image_id"]) == 1
        assert len(result["label_id"]) == 1
        assert result["image_id"][0] == base_datum.id
        assert result["label_id"][0] == derived_datum.id

    @pytest.mark.asyncio
    async def test_query_data_with_transpose_empty_result(self, datalake, mock_database):
        """Test query_data with transpose=True for empty result."""
        mock_database.find.return_value = []

        query = {"metadata.project": "nonexistent_project", "column": "image_id"}
        result = await datalake.query_data_legacy(query, transpose=True)

        # Should return empty dictionary
        assert isinstance(result, dict)
        assert result == {}

    @pytest.mark.asyncio
    async def test_query_data_with_transpose_missing_strategy(self, datalake, mock_database):
        """Test query_data with transpose=True and missing strategy."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image", "filename": "test.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
        )

        # Mock database calls - no derived data found
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [],  # Second query: no derived data found
        ]

        # Test with transpose=True and missing strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "missing", "column": "label_id"},
        ]
        result = await datalake.query_data_legacy(query, transpose=True)

        # Should return dictionary with only image_id (no label_id since missing strategy)
        assert isinstance(result, dict)
        assert "image_id" in result
        assert "label_id" not in result
        assert len(result["image_id"]) == 1
        assert result["image_id"][0] == base_datum.id

    @pytest.mark.asyncio
    async def test_query_data_with_transpose_datums_wanted(self, datalake, mock_database):
        """Test query_data with transpose=True and datums_wanted parameter."""
        # Mock multiple data
        datums = []
        for i in range(5):
            datum = create_mock_datum(
                data={"type": "image", "filename": f"test{i}.jpg"},
                metadata={"project": "test_project"},
                datum_id=PydanticObjectId(),
            )
            datums.append(datum)

        mock_database.find.return_value = datums

        # Test with transpose=True and datums_wanted=3
        query = {"metadata.project": "test_project", "column": "image_id"}
        result = await datalake.query_data_legacy(query, datums_wanted=3, transpose=True)

        # Should return dictionary with 3 items
        assert isinstance(result, dict)
        assert "image_id" in result
        assert len(result["image_id"]) == 3

    @pytest.mark.asyncio
    async def test_multi_query_with_strategy_quickest(self, datalake, mock_database):
        """Test multi-query with quickest strategy selects the first entry without sorting."""
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

        # Mock database calls - return in order: old, new (database order)
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [old_derived, new_derived],  # Second query: find derived data (old first)
        ]

        # Test multi-query with quickest strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "quickest", "column": "label_id"},
        ]
        result = await datalake.query_data_legacy(query)

        # Verify database calls
        assert mock_database.find.call_count == 2

        # Verify result format - should select the first one (old_derived) without sorting
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == base_datum.id
        assert result[0]["label_id"] == old_derived.id  # Should be the first one (old_derived)

    @pytest.mark.asyncio
    async def test_datums_wanted_with_quickest_strategy(self, datalake, mock_database):
        """Test datums_wanted with quickest strategy doesn't sort entries."""
        # Mock multiple data with different timestamps
        old_time = datetime.now() - timedelta(hours=2)
        mid_time = datetime.now() - timedelta(hours=1)
        new_time = datetime.now()

        d1 = create_mock_datum(
            data={"type": "image", "filename": "test1.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
            added_at=old_time,
        )
        d2 = create_mock_datum(
            data={"type": "image", "filename": "test2.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
            added_at=mid_time,
        )
        d3 = create_mock_datum(
            data={"type": "image", "filename": "test3.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId(),
            added_at=new_time,
        )

        # Mock database to return in order: d1, d2, d3 (database order)
        mock_database.find.return_value = [d1, d2, d3]

        # Test with quickest strategy and datums_wanted=2
        query = [{"metadata.project": "test_project", "strategy": "quickest", "column": "image_id"}]
        result = await datalake.query_data_legacy(query, datums_wanted=2)

        # Should return first 2 entries as they come from database (no sorting)
        assert len(result) == 2
        assert all(isinstance(row, dict) for row in result)

        result_ids = [row["image_id"] for row in result]
        # Should be d1 and d2 (first two in database order)
        assert result_ids == [d1.id, d2.id]

    @pytest.mark.asyncio
    async def test_quickest_strategy_with_multiple_derived_data(self, datalake, mock_database):
        """Test quickest strategy with multiple derived data entries."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image"}, metadata={"project": "test_project"}, datum_id=PydanticObjectId()
        )

        # Mock multiple derived data
        derived1 = create_mock_datum(
            data={"type": "classification", "label": "label1"},
            metadata={"model": "model1"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
        )
        derived2 = create_mock_datum(
            data={"type": "classification", "label": "label2"},
            metadata={"model": "model2"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
        )
        derived3 = create_mock_datum(
            data={"type": "classification", "label": "label3"},
            metadata={"model": "model3"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
        )

        # Mock database calls - return in order: derived1, derived2, derived3
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [derived1, derived2, derived3],  # Second query: find derived data
        ]

        # Test with quickest strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "quickest", "column": "label_id"},
        ]
        result = await datalake.query_data_legacy(query)

        # Should select the first one (derived1) without sorting
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == base_datum.id
        assert result[0]["label_id"] == derived1.id  # Should be the first one

    @pytest.mark.asyncio
    async def test_quickest_strategy_with_single_derived_data(self, datalake, mock_database):
        """Test quickest strategy with single derived data entry."""
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

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [derived_datum],  # Second query: find derived data
        ]

        # Test with quickest strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "quickest", "column": "label_id"},
        ]
        result = await datalake.query_data_legacy(query)

        # Should work the same as other strategies when there's only one entry
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["image_id"] == base_datum.id
        assert result[0]["label_id"] == derived_datum.id

    @pytest.mark.asyncio
    async def test_quickest_strategy_with_empty_derived_data(self, datalake, mock_database):
        """Test quickest strategy when no derived data is found."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image"}, metadata={"project": "test_project"}, datum_id=PydanticObjectId()
        )

        # Mock database calls - no derived data found
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [],  # Second query: no derived data found
        ]

        # Test with quickest strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "quickest", "column": "label_id"},
        ]
        result = await datalake.query_data_legacy(query)

        # Should return empty result because no derived data found
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_quickest_strategy_with_transpose(self, datalake, mock_database):
        """Test quickest strategy with transpose=True."""
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

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [derived_datum],  # Second query: find derived data
        ]

        # Test with quickest strategy and transpose=True
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "quickest", "column": "label_id"},
        ]
        result = await datalake.query_data_legacy(query, transpose=True)

        # Should return dictionary of lists
        assert isinstance(result, dict)
        assert "image_id" in result
        assert "label_id" in result
        assert len(result["image_id"]) == 1
        assert len(result["label_id"]) == 1
        assert result["image_id"][0] == base_datum.id
        assert result["label_id"][0] == derived_datum.id
