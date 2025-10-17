"""Unit tests for the query_data method in the Datalake class."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId

from mindtrace.datalake import Datalake
from mindtrace.datalake.types import Datum


def create_mock_datum(data=None, registry_uri=None, registry_key=None, derived_from=None, metadata=None, datum_id=None, added_at=None):
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


class TestQueryDataUnit:
    """Unit tests for the query_data method."""

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
    async def test_single_query_dict(self, datalake, mock_database):
        """Test single query with dict input."""
        # Mock data
        datum1 = create_mock_datum(
            data={"type": "image", "filename": "test1.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId()
        )
        datum2 = create_mock_datum(
            data={"type": "image", "filename": "test2.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId()
        )

        mock_database.find.return_value = [datum1, datum2]

        # Test single query
        query = {"metadata.project": "test_project", "column": "image_id"}
        result = await datalake.query_data(query)

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
            data={"type": "image"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId()
        )

        mock_database.find.return_value = [datum]

        # Test single query as list
        query = [{"metadata.project": "test_project", "column": "image_id"}]
        result = await datalake.query_data(query)

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
            data={"type": "image"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId()
        )

        # Mock derived data
        derived_datum = create_mock_datum(
            data={"type": "classification", "label": "cat"},
            metadata={"model": "resnet50"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId()
        )

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [derived_datum]  # Second query: find derived data
        ]

        # Test multi-query
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "column": "label_id"}
        ]
        result = await datalake.query_data(query)

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
            data={"type": "image"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId()
        )

        # Mock multiple derived data with different timestamps
        old_time = datetime.now() - timedelta(hours=1)
        new_time = datetime.now()
        
        old_derived = create_mock_datum(
            data={"type": "classification", "label": "old"},
            metadata={"model": "old_model"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
            added_at=old_time
        )
        
        new_derived = create_mock_datum(
            data={"type": "classification", "label": "new"},
            metadata={"model": "new_model"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
            added_at=new_time
        )

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [old_derived, new_derived]  # Second query: find derived data (multiple)
        ]

        # Test multi-query with latest strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "latest", "column": "label_id"}
        ]
        result = await datalake.query_data(query)

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
            data={"type": "image"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId()
        )

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            []  # Second query: no derived data found
        ]

        # Test multi-query
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "column": "label_id"}
        ]
        result = await datalake.query_data(query)

        # Verify database calls
        assert mock_database.find.call_count == 2

        # Verify result - should be empty because no derived data found
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_multi_query_complex_chain(self, datalake, mock_database):
        """Test complex multi-query with multiple derivation levels."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId()
        )

        # Mock level 1 derived data
        level1_datum = create_mock_datum(
            data={"type": "classification", "label": "cat"},
            metadata={"model": "resnet50"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId()
        )

        # Mock level 2 derived data
        level2_datum = create_mock_datum(
            data={"type": "bbox", "x": 10, "y": 20},
            metadata={"model": "yolo"},
            derived_from=level1_datum.id,
            datum_id=PydanticObjectId()
        )

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # Query 1: find base data
            [level1_datum],  # Query 2: find level 1 derived data
            [level2_datum]  # Query 3: find level 2 derived data
        ]

        # Test complex multi-query
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "column": "label_id"},
            {"derived_from": "label_id", "data.type": "bbox", "column": "bbox_id"}
        ]
        result = await datalake.query_data(query)

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
        result = await datalake.query_data(query)

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
            data={"type": "image"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId()
        )

        # Mock derived data
        derived_datum = create_mock_datum(
            data={"type": "classification", "label": "cat"},
            metadata={"model": "resnet50"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId()
        )

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [derived_datum]  # Second query: find derived data
        ]

        # Test query with invalid strategy
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "invalid", "column": "label_id"}
        ]

        with pytest.raises(ValueError, match="Invalid strategy: invalid"):
            await datalake.query_data(query)

    @pytest.mark.asyncio
    async def test_query_with_default_strategy(self, datalake, mock_database):
        """Test query with default strategy (latest)."""
        # Mock base data
        base_datum = create_mock_datum(
            data={"type": "image"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId()
        )

        # Mock multiple derived data
        old_time = datetime.now() - timedelta(hours=1)
        new_time = datetime.now()
        
        old_derived = create_mock_datum(
            data={"type": "classification", "label": "old"},
            metadata={"model": "old_model"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
            added_at=old_time
        )
        
        new_derived = create_mock_datum(
            data={"type": "classification", "label": "new"},
            metadata={"model": "new_model"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId(),
            added_at=new_time
        )

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # First query: find base data
            [old_derived, new_derived]  # Second query: find derived data (multiple)
        ]

        # Test query without explicit strategy (should default to "latest")
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "column": "label_id"}
        ]
        result = await datalake.query_data(query)

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
                "location": {"city": "Paris", "country": "France"}
            },
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId()
        )
        
        datum2 = create_mock_datum(
            data={
                "type": "image",
                "filename": "test2.jpg",
                "size": 512,
                "tags": ["urban", "indoor"],
                "location": {"city": "London", "country": "UK"}
            },
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId()
        )

        mock_database.find.return_value = [datum1]

        # Test complex query
        query = {
            "data.type": "image",
            "data.size": {"$gt": 600},
            "data.tags": {"$in": ["nature"]},
            "data.location.city": "Paris",
            "column": "image_id"
        }
        result = await datalake.query_data(query)

        # Verify database call
        expected_query = {
            "data.type": "image",
            "data.size": {"$gt": 600},
            "data.tags": {"$in": ["nature"]},
            "data.location.city": "Paris"
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
                "models": ["resnet50", "vgg16"]
            },
            datum_id=PydanticObjectId()
        )

        mock_database.find.return_value = [datum1]

        # Test complex metadata query
        query = {
            "metadata.project": "test_project",
            "metadata.tags": {"$in": ["nature"]},
            "metadata.location.city": "Paris",
            "metadata.quality": {"$gte": 0.9},
            "metadata.models": {"$in": ["resnet50"]},
            "column": "image_id"
        }
        result = await datalake.query_data(query)

        # Verify database call
        expected_query = {
            "metadata.project": "test_project",
            "metadata.tags": {"$in": ["nature"]},
            "metadata.location.city": "Paris",
            "metadata.quality": {"$gte": 0.9},
            "metadata.models": {"$in": ["resnet50"]}
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
            datum_id=PydanticObjectId()
        )
        base2 = create_mock_datum(
            data={"type": "image", "filename": "test2.jpg"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId()
        )

        # Mock derived data for each base
        derived1 = create_mock_datum(
            data={"type": "classification", "label": "cat"},
            metadata={"model": "resnet50"},
            derived_from=base1.id,
            datum_id=PydanticObjectId()
        )
        derived2 = create_mock_datum(
            data={"type": "classification", "label": "dog"},
            metadata={"model": "resnet50"},
            derived_from=base2.id,
            datum_id=PydanticObjectId()
        )

        # Mock database calls
        mock_database.find.side_effect = [
            [base1, base2],  # First query: find base data
            [derived1],  # Second query for base1: find derived data
            [derived2]  # Second query for base2: find derived data
        ]

        # Test multi-query
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "column": "label_id"}
        ]
        result = await datalake.query_data(query)

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
            data={"type": "image"},
            metadata={"project": "test_project"},
            datum_id=PydanticObjectId()
        )

        # Mock level 1 derived data
        level1_datum = create_mock_datum(
            data={"type": "classification", "label": "cat"},
            metadata={"model": "resnet50"},
            derived_from=base_datum.id,
            datum_id=PydanticObjectId()
        )

        # Mock level 2 derived data (derived from level 1, not base)
        level2_datum = create_mock_datum(
            data={"type": "bbox", "x": 10, "y": 20},
            metadata={"model": "yolo"},
            derived_from=level1_datum.id,
            datum_id=PydanticObjectId()
        )

        # Mock database calls
        mock_database.find.side_effect = [
            [base_datum],  # Query 1: find base data
            [level1_datum],  # Query 2: find level 1 derived data
            [level2_datum]  # Query 3: find level 2 derived data (derived from level 1)
        ]

        # Test query with mixed derivation indices
        query = [
            {"metadata.project": "test_project", "column": "image_id"},  # Index 0: base
            {"derived_from": "image_id", "data.type": "classification", "column": "label_id"},  # Index 1: derived from 0
            {"derived_from": "label_id", "data.type": "bbox", "column": "bbox_id"}  # Index 2: derived from 1
        ]
        result = await datalake.query_data(query)

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
            await datalake.query_data(query)

    @pytest.mark.asyncio
    async def test_query_without_column_raises_error(self, datalake, mock_database):
        """Test query without column raises ValueError."""
        query = {"metadata.project": "test_project"}

        with pytest.raises(ValueError, match="column must be provided"):
            await datalake.query_data(query)

    @pytest.mark.asyncio
    async def test_multi_query_without_column_raises_error(self, datalake, mock_database):
        """Test multi-query without column in subquery raises ValueError."""
        base_datum = create_mock_datum(datum_id=PydanticObjectId())
        mock_database.find.return_value = [base_datum]

        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification"}  # Missing column
        ]

        with pytest.raises(ValueError, match="column must be provided"):
            await datalake.query_data(query)

    @pytest.mark.asyncio
    async def test_multi_query_with_strategy_earliest(self, datalake, mock_database):
        """Test multi-query with earliest strategy selects the oldest by added_at."""
        base = create_mock_datum(datum_id=PydanticObjectId())
        older = create_mock_datum(derived_from=base.id, added_at=datetime.now() - timedelta(hours=2), datum_id=PydanticObjectId())
        newer = create_mock_datum(derived_from=base.id, added_at=datetime.now() - timedelta(hours=1), datum_id=PydanticObjectId())

        mock_database.find.side_effect = [
            [base],
            [newer, older],
        ]

        query = [
            {"metadata.project": "p", "column": "image_id"},
            {"derived_from": "image_id", "strategy": "earliest", "column": "label_id"},
        ]
        result = await datalake.query_data(query)

        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["label_id"] == older.id

    @pytest.mark.asyncio
    async def test_multi_query_with_strategy_random(self, datalake, mock_database):
        """Test multi-query with random strategy uses random.choice."""
        base = create_mock_datum(datum_id=PydanticObjectId())
        a = create_mock_datum(derived_from=base.id, added_at=datetime.now() - timedelta(hours=2), datum_id=PydanticObjectId())
        b = create_mock_datum(derived_from=base.id, added_at=datetime.now() - timedelta(hours=1), datum_id=PydanticObjectId())

        mock_database.find.side_effect = [
            [base],
            [a, b],
        ]

        with patch("mindtrace.datalake.datalake.random.choice", return_value=b):
            result = await datalake.query_data([
                {"metadata.project": "p", "column": "image_id"},
                {"derived_from": "image_id", "strategy": "random", "column": "label_id"},
            ])

        assert len(result) == 1
        assert result[0]["label_id"] == b.id

    @pytest.mark.asyncio
    async def test_datums_wanted_latest_single_query(self, datalake, mock_database):
        """Base selection uses latest strategy when datums_wanted is provided."""
        d1 = create_mock_datum(added_at=datetime.now() - timedelta(hours=3), datum_id=PydanticObjectId())
        d2 = create_mock_datum(added_at=datetime.now() - timedelta(hours=2), datum_id=PydanticObjectId())
        d3 = create_mock_datum(added_at=datetime.now() - timedelta(hours=1), datum_id=PydanticObjectId())

        mock_database.find.return_value = [d1, d2, d3]

        result = await datalake.query_data({"metadata.project": "p", "column": "image_id"}, datums_wanted=2)

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

        result = await datalake.query_data([{"metadata.project": "p", "strategy": "earliest", "column": "image_id"}], datums_wanted=2)

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
            result = await datalake.query_data([{"metadata.project": "p", "strategy": "random", "column": "image_id"}], datums_wanted=2)

        result_ids = {row["image_id"] for row in result}
        assert len(result) == 2
        assert result_ids == {d1.id, d3.id}
