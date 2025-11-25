"""Unit tests for the Datalake class with mocked dependencies."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake import Datalake
from mindtrace.datalake.dataset import Dataset
from mindtrace.datalake.datum import Datum


def create_mock_datum(
    data=None,
    registry_uri=None,
    registry_key=None,
    derived_from=None,
    metadata=None,
    datum_id=None,
    added_at=None,
    contract="default",
    project_id="test_project",
    line_id="test_line",
):
    """Create a mock Datum instance without requiring beanie initialization."""
    if datum_id is None:
        datum_id = "507f1f77bcf86cd799439011"
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
    mock_datum.project_id = project_id
    mock_datum.line_id = line_id
    return mock_datum


class TestDatalakeUnit:
    """Unit tests for the Datalake class."""

    @staticmethod
    def _create_mock_backend_class(mock_database, mock_dataset_database):
        """Helper to create a mock backend class that supports subscripting."""
        call_count = [0]

        def mock_backend_factory(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_database
            else:
                return mock_dataset_database

        class MockBackendMeta(type):
            def __getitem__(cls, item):
                return cls

        class MockBackendClass(metaclass=MockBackendMeta):
            def __new__(cls, *args, **kwargs):
                return mock_backend_factory(*args, **kwargs)

        return MockBackendClass

    @pytest.fixture
    def mock_database(self):
        """Mock database backend."""
        mock_db = AsyncMock()
        mock_db.initialize = AsyncMock()
        mock_db.insert = AsyncMock()
        mock_db.get = AsyncMock()
        mock_db.aggregate = AsyncMock()
        mock_db.find = AsyncMock()
        # get_raw_model must be sync and return an object with a derived_from attribute
        mock_db.get_raw_model = MagicMock(return_value=MagicMock(derived_from=MagicMock()))
        return mock_db

    @pytest.fixture
    def mock_dataset_database(self):
        """Mock dataset database backend."""
        mock_db = AsyncMock()
        mock_db.initialize = AsyncMock()
        mock_db.insert = AsyncMock()
        mock_db.get = AsyncMock()
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
    def datalake(self, mock_database, mock_registry, mock_dataset_database):
        """Create Datalake instance with mocked database and patched Datum model."""

        class _MockDatum:
            def __init__(
                self,
                data=None,
                registry_uri=None,
                registry_key=None,
                derived_from=None,
                metadata=None,
                added_at=None,
                contract="default",
                project_id="test_project",
                line_id="test_line",
            ):
                self.id = PydanticObjectId()
                self.data = data
                self.contract = contract
                self.registry_uri = registry_uri
                self.registry_key = registry_key
                self.derived_from = derived_from
                self.metadata = metadata or {}
                self.added_at = added_at if added_at is not None else datetime.now()
                self.project_id = project_id
                self.line_id = line_id

        # Create a callable that returns the appropriate mock based on call count
        call_count = [0]

        def mock_backend_factory(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_database
            else:
                return mock_dataset_database

        db_patcher = patch("mindtrace.datalake.datalake.MongoMindtraceODMBackend", side_effect=mock_backend_factory)
        registry_patcher = patch("mindtrace.datalake.datalake.Registry", return_value=mock_registry)
        datum_patcher = patch("mindtrace.datalake.datalake.Datum", _MockDatum)
        db_patcher.start()
        datum_patcher.start()
        registry_patcher.start()
        try:
            instance = Datalake("mongodb://test:27017", "test_db")
            # Ensure dataset_database is properly set to the mock
            instance.dataset_database = mock_dataset_database
            yield instance
        finally:
            datum_patcher.stop()
            db_patcher.stop()
            registry_patcher.stop()

    @pytest.mark.asyncio
    async def test_datalake_initialization(self, datalake, mock_database):
        """Test Datalake initialization."""
        assert datalake.mongo_db_uri == "mongodb://test:27017"
        assert datalake.mongo_db_name == "test_db"
        assert datalake.datum_database == mock_database
        assert datalake.registries == {}

    @pytest.mark.asyncio
    async def test_initialize(self, datalake, mock_database, mock_dataset_database):
        """Test datalake initialization."""
        await datalake.initialize()
        mock_database.initialize.assert_called_once()
        mock_dataset_database.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_datum_database_storage(self, datalake, mock_database):
        """Test adding datum with database storage."""
        test_data = {"test": "data"}
        test_metadata = {"source": "unit_test"}

        # Mock the inserted datum
        mock_datum = create_mock_datum(data=test_data, metadata=test_metadata)
        mock_database.insert.return_value = mock_datum

        result = await datalake.add_datum(test_data, test_metadata)

        # Verify database insert was called with correct datum
        mock_database.insert.assert_called_once()
        inserted_datum = mock_database.insert.call_args[0][0]
        assert inserted_datum.data == test_data
        assert inserted_datum.metadata == test_metadata
        assert inserted_datum.contract == "default"
        assert inserted_datum.registry_uri is None
        assert inserted_datum.registry_key is None
        assert inserted_datum.derived_from is None

        assert result == mock_datum

    @pytest.mark.asyncio
    async def test_add_datum_registry_storage(self, datalake, mock_database, mock_registry, tmp_path):
        """Test adding datum with registry storage."""
        test_data = {"large": "data"}
        test_metadata = {"source": "registry_test"}
        registry_uri = f"{(tmp_path / 'registry').as_posix()}"

        # Mock the inserted datum
        mock_datum = create_mock_datum(
            data=None, registry_uri=registry_uri, registry_key="test_key", metadata=test_metadata
        )
        mock_database.insert.return_value = mock_datum

        result = await datalake.add_datum(test_data, test_metadata, registry_uri=registry_uri)

        # Verify registry save was called
        mock_registry.save.assert_called_once()
        save_args, save_kwargs = mock_registry.save.call_args
        assert save_args[1] == test_data  # data
        assert save_kwargs.get("metadata") == test_metadata  # metadata

        # Verify database insert was called with correct datum
        mock_database.insert.assert_called_once()
        inserted_datum = mock_database.insert.call_args[0][0]
        assert inserted_datum.data is None
        assert inserted_datum.contract == "default"
        assert inserted_datum.registry_uri == registry_uri
        assert inserted_datum.registry_key is not None
        assert inserted_datum.metadata == test_metadata

        assert result == mock_datum

    @pytest.mark.asyncio
    async def test_add_datum_with_derivation(self, datalake, mock_database):
        """Test adding datum with derivation relationship."""
        test_data = {"derived": "data"}
        test_metadata = {"source": "derivation_test"}
        parent_id = PydanticObjectId()

        mock_datum = create_mock_datum(data=test_data, metadata=test_metadata, derived_from=parent_id)
        mock_database.insert.return_value = mock_datum

        result = await datalake.add_datum(test_data, test_metadata, derived_from=parent_id)

        # Verify database insert was called with correct datum
        inserted_datum = mock_database.insert.call_args[0][0]
        assert inserted_datum.derived_from == parent_id
        assert inserted_datum.contract == "default"

        assert result == mock_datum

    @pytest.mark.asyncio
    async def test_add_datum_with_contract(self, datalake, mock_database):
        """Test adding datum with explicit contract."""
        test_data = {"label": "cat", "confidence": 0.95}
        test_metadata = {"source": "classification_test"}
        contract = "classification"

        mock_datum = create_mock_datum(data=test_data, metadata=test_metadata, contract=contract)
        mock_database.insert.return_value = mock_datum

        result = await datalake.add_datum(test_data, test_metadata, contract=contract)

        # Verify database insert was called with correct datum
        mock_database.insert.assert_called_once()
        inserted_datum = mock_database.insert.call_args[0][0]
        assert inserted_datum.data == test_data
        assert inserted_datum.metadata == test_metadata
        assert inserted_datum.contract == contract
        assert inserted_datum.registry_uri is None
        assert inserted_datum.registry_key is None
        assert inserted_datum.derived_from is None

        assert result == mock_datum

    @pytest.mark.asyncio
    async def test_get_datum_database_storage(self, datalake, mock_database):
        """Test getting datum from database storage."""
        datum_id = PydanticObjectId()
        test_data = {"test": "data"}

        mock_datum = create_mock_datum(data=test_data, metadata={"source": "test"}, datum_id=datum_id)
        mock_database.get.return_value = mock_datum

        result = await datalake.get_datum(datum_id)

        mock_database.get.assert_called_once_with(datum_id)
        assert result == mock_datum
        assert result.data == test_data

    @pytest.mark.asyncio
    async def test_get_datum_registry_storage(self, datalake, mock_database, mock_registry, tmp_path):
        """Test getting datum from registry storage."""
        datum_id = PydanticObjectId()
        registry_uri = f"{(tmp_path / 'registry').as_posix()}"
        registry_key = "test_key"
        test_data = {"large": "data"}

        mock_datum = create_mock_datum(
            data=None,
            registry_uri=registry_uri,
            registry_key=registry_key,
            metadata={"source": "registry"},
            datum_id=datum_id,
        )
        mock_database.get.return_value = mock_datum
        mock_registry.load.return_value = test_data

        result = await datalake.get_datum(datum_id)

        mock_database.get.assert_called_once_with(datum_id)
        mock_registry.load.assert_called_once_with(registry_key)
        assert result.data == test_data
        assert result.registry_uri == registry_uri

    @pytest.mark.asyncio
    async def test_get_datum_nonexistent(self, datalake, mock_database):
        """Test getting nonexistent datum."""
        datum_id = PydanticObjectId()
        mock_database.get.side_effect = DocumentNotFoundError("Not found")

        with pytest.raises(DocumentNotFoundError):
            await datalake.get_datum(datum_id)

    @pytest.mark.asyncio
    async def test_get_data(self, datalake, mock_database):
        """Test getting multiple data."""
        datum_ids = [PydanticObjectId() for _ in range(3)]
        mock_data = [create_mock_datum(data={"test": i}, metadata={}, datum_id=datum_ids[i]) for i in range(3)]

        # Mock get_datum calls
        with patch.object(datalake, "get_datum", side_effect=mock_data):
            result = await datalake.get_data(datum_ids)

        assert len(result) == 3
        for i, datum in enumerate(result):
            assert datum.data == {"test": i}
            assert datum.id == datum_ids[i]

    @pytest.mark.asyncio
    async def test_get_directly_derived_data(self, datalake, mock_database):
        """Test getting directly derived data."""
        parent_id = PydanticObjectId()
        child_ids = [PydanticObjectId() for _ in range(2)]

        mock_children = [
            create_mock_datum(data={"child": i}, metadata={}, derived_from=parent_id, datum_id=child_ids[i])
            for i in range(2)
        ]
        mock_database.find.return_value = mock_children

        result = await datalake.get_directly_derived_data(parent_id)

        mock_database.find.assert_called_once()
        assert result == child_ids

    @pytest.mark.asyncio
    async def test_get_indirectly_derived_data(self, datalake):
        """Test getting indirectly derived data (breadth-first search)."""
        # Create a tree: A -> B -> C, A -> D
        root_id = PydanticObjectId()
        child1_id = PydanticObjectId()
        child2_id = PydanticObjectId()
        grandchild_id = PydanticObjectId()

        # Mock get_directly_derived_data calls
        with patch.object(datalake, "get_directly_derived_data") as mock_get_direct:
            mock_get_direct.side_effect = [
                [child1_id, child2_id],  # root -> [child1, child2]
                [grandchild_id],  # child1 -> [grandchild]
                [],  # child2 -> []
                [],  # grandchild -> []
            ]

            result = await datalake.get_indirectly_derived_data(root_id)

        # Should return all nodes in the tree
        expected_ids = [root_id, child1_id, child2_id, grandchild_id]
        assert set(result) == set(expected_ids)

        # Verify the breadth-first search pattern
        assert mock_get_direct.call_count == 4

    @pytest.mark.asyncio
    async def test_registry_caching(self, datalake, mock_database, mock_registry, tmp_path):
        """Test that registry instances are cached and reused."""
        registry_uri = f"{(tmp_path / 'registry').as_posix()}"

        # First call should create registry
        await datalake.add_datum({"test": "data1"}, {}, registry_uri=registry_uri)

        # Second call should reuse cached registry
        await datalake.add_datum({"test": "data2"}, {}, registry_uri=registry_uri)

        # Registry should be cached
        assert registry_uri in datalake.registries
        assert datalake.registries[registry_uri] == mock_registry

    @pytest.mark.asyncio
    async def test_get_datum_registry_caching(self, datalake, mock_database, mock_registry, tmp_path):
        """Test registry caching during datum retrieval."""
        datum_id = PydanticObjectId()
        registry_uri = f"{(tmp_path / 'registry').as_posix()}"

        mock_datum = create_mock_datum(
            data=None, registry_uri=registry_uri, registry_key="test_key", metadata={}, datum_id=datum_id
        )
        mock_database.get.return_value = mock_datum
        mock_registry.load.return_value = {"test": "data"}

        await datalake.get_datum(datum_id)

        # Registry should be cached
        assert registry_uri in datalake.registries
        assert datalake.registries[registry_uri] == mock_registry

    @pytest.mark.asyncio
    async def test_empty_metadata_default(self, datalake, mock_database):
        """Test that empty metadata defaults to empty dict."""
        test_data = {"test": "data"}

        mock_datum = create_mock_datum(data=test_data, metadata={})
        mock_database.insert.return_value = mock_datum

        await datalake.add_datum(test_data, {})

        inserted_datum = mock_database.insert.call_args[0][0]
        assert inserted_datum.metadata == {}
        assert inserted_datum.contract == "default"

    @pytest.mark.asyncio
    async def test_complex_metadata(self, datalake, mock_database):
        """Test handling of complex metadata structures."""
        test_data = {"test": "data"}
        complex_metadata = {"nested": {"deep": {"value": 123}}, "list": [1, 2, 3], "boolean": True, "null": None}

        mock_datum = create_mock_datum(data=test_data, metadata=complex_metadata)
        mock_database.insert.return_value = mock_datum

        await datalake.add_datum(test_data, complex_metadata)

        inserted_datum = mock_database.insert.call_args[0][0]
        assert inserted_datum.metadata == complex_metadata
        assert inserted_datum.contract == "default"

    @pytest.mark.asyncio
    async def test_added_at_field_populated_on_creation(self, datalake, mock_database):
        """Test that added_at field is populated when creating a datum."""
        test_data = {"test": "data"}
        test_metadata = {"source": "test"}

        mock_datum = create_mock_datum(data=test_data, metadata=test_metadata)
        mock_database.insert.return_value = mock_datum

        await datalake.add_datum(test_data, test_metadata)

        # Verify that the inserted datum has added_at populated
        inserted_datum = mock_database.insert.call_args[0][0]
        assert inserted_datum.added_at is not None
        assert isinstance(inserted_datum.added_at, datetime)

    @pytest.mark.asyncio
    async def test_added_at_field_retrieved_correctly(self, datalake, mock_database):
        """Test that added_at field is correctly retrieved when getting a datum."""
        datum_id = PydanticObjectId()
        test_data = {"test": "data"}
        test_metadata = {"source": "test"}
        added_at_time = datetime(2024, 1, 15, 10, 30, 45)

        mock_datum = create_mock_datum(
            data=test_data, metadata=test_metadata, datum_id=datum_id, added_at=added_at_time
        )
        mock_database.get.return_value = mock_datum

        result = await datalake.get_datum(datum_id)

        # Verify that the retrieved datum has the correct added_at value
        assert result.added_at == added_at_time

    @pytest.mark.asyncio
    async def test_added_at_field_with_registry_storage(self, datalake, mock_database, mock_registry, tmp_path):
        """Test that added_at field works correctly with registry storage."""
        test_data = {"large": "data"}
        test_metadata = {"source": "registry_test"}
        registry_uri = f"{(tmp_path / 'registry').as_posix()}"
        added_at_time = datetime(2024, 2, 20, 14, 25, 30)

        mock_datum = create_mock_datum(
            data=None,
            registry_uri=registry_uri,
            registry_key="test_key",
            metadata=test_metadata,
            added_at=added_at_time,
        )
        mock_database.insert.return_value = mock_datum

        await datalake.add_datum(test_data, test_metadata, registry_uri=registry_uri)

        # Verify that the inserted datum has added_at populated
        inserted_datum = mock_database.insert.call_args[0][0]
        assert inserted_datum.added_at is not None
        assert isinstance(inserted_datum.added_at, datetime)

    @pytest.mark.asyncio
    async def test_added_at_field_with_derivation(self, datalake, mock_database):
        """Test that added_at field works correctly with derived data."""
        test_data = {"test": "data"}
        test_metadata = {"source": "derivation_test"}
        parent_id = PydanticObjectId()
        added_at_time = datetime(2024, 3, 10, 9, 15, 20)

        mock_datum = create_mock_datum(
            data=test_data, metadata=test_metadata, derived_from=parent_id, added_at=added_at_time
        )
        mock_database.insert.return_value = mock_datum

        await datalake.add_datum(test_data, test_metadata, derived_from=parent_id)

        # Verify that the inserted datum has added_at populated
        inserted_datum = mock_database.insert.call_args[0][0]
        assert inserted_datum.added_at is not None
        assert isinstance(inserted_datum.added_at, datetime)

    @pytest.mark.asyncio
    async def test_added_at_field_chronological_ordering(self, datalake, mock_database):
        """Test that added_at field can be used for chronological ordering."""
        # Create multiple data with different added_at times
        earlier_time = datetime(2024, 1, 1, 10, 0, 0)
        later_time = datetime(2024, 1, 1, 11, 0, 0)

        # First datum
        mock_datum1 = create_mock_datum(data={"test": "data1"}, metadata={"source": "test1"}, added_at=earlier_time)
        mock_database.insert.return_value = mock_datum1

        await datalake.add_datum({"test": "data1"}, {"source": "test1"})

        # Second datum
        mock_datum2 = create_mock_datum(data={"test": "data2"}, metadata={"source": "test2"}, added_at=later_time)
        mock_database.insert.return_value = mock_datum2

        await datalake.add_datum({"test": "data2"}, {"source": "test2"})

        # Verify that both data have added_at populated
        first_inserted = mock_database.insert.call_args_list[0][0][0]
        second_inserted = mock_database.insert.call_args_list[1][0][0]

        assert first_inserted.added_at is not None
        assert second_inserted.added_at is not None
        assert isinstance(first_inserted.added_at, datetime)
        assert isinstance(second_inserted.added_at, datetime)

    @pytest.mark.asyncio
    async def test_added_at_field_with_get_data(self, datalake, mock_database):
        """Test that added_at field is preserved when getting multiple data."""
        datum_ids = [PydanticObjectId() for _ in range(3)]
        added_at_times = [
            datetime(2024, 1, 1, 10, 0, 0),
            datetime(2024, 1, 1, 11, 0, 0),
            datetime(2024, 1, 1, 12, 0, 0),
        ]

        mock_data = [
            create_mock_datum(data={"test": i}, metadata={}, datum_id=datum_ids[i], added_at=added_at_times[i])
            for i in range(3)
        ]

        # Mock get_datum calls
        with patch.object(datalake, "get_datum", side_effect=mock_data):
            result = await datalake.get_data(datum_ids)

        # Verify that all retrieved data have added_at populated
        assert len(result) == 3
        for i, datum in enumerate(result):
            assert datum.added_at == added_at_times[i]
            assert isinstance(datum.added_at, datetime)

    @pytest.mark.asyncio
    async def test_create_class_method_success(self, mock_registry):
        """Test successful creation of Datalake instance using create() class method."""
        mongo_db_uri = "mongodb://test:27017"
        mongo_db_name = "test_db"

        class _MockDatum:
            def __init__(
                self,
                data=None,
                registry_uri=None,
                registry_key=None,
                derived_from=None,
                metadata=None,
                added_at=None,
                contract="default",
                project_id="test_project",
                line_id="test_line",
            ):
                self.id = PydanticObjectId()
                self.data = data
                self.contract = contract
                self.registry_uri = registry_uri
                self.registry_key = registry_key
                self.derived_from = derived_from
                self.metadata = metadata or {}
                self.added_at = added_at if added_at is not None else datetime.now()
                self.project_id = project_id
                self.line_id = line_id

        # Create fresh mocks to avoid any fixture state issues
        mock_database = AsyncMock()
        mock_database.initialize = AsyncMock()
        mock_database.insert = AsyncMock()
        mock_database.get = AsyncMock()
        mock_database.aggregate = AsyncMock()
        mock_database.find = AsyncMock()
        mock_database.get_raw_model = MagicMock(return_value=MagicMock(derived_from=MagicMock()))

        mock_dataset_database = AsyncMock()
        mock_dataset_database.initialize = AsyncMock()
        mock_dataset_database.insert = AsyncMock()
        mock_dataset_database.get = AsyncMock()
        mock_dataset_database.find = AsyncMock()

        MockBackendClass = self._create_mock_backend_class(mock_database, mock_dataset_database)

        with (
            patch("mindtrace.datalake.datalake.MongoMindtraceODMBackend", new=MockBackendClass),
            patch("mindtrace.datalake.datalake.Registry", return_value=mock_registry),
            patch("mindtrace.datalake.datalake.Datum", _MockDatum),
        ):
            result = await Datalake.create(mongo_db_uri, mongo_db_name)

        # Verify the returned instance is a Datalake
        assert isinstance(result, Datalake)

        # Verify the instance is properly initialized
        assert result.mongo_db_uri == mongo_db_uri
        assert result.mongo_db_name == mongo_db_name
        # Verify initialize was called for both databases
        mock_database.initialize.assert_called_once()
        mock_dataset_database.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_class_method_with_different_parameters(self, mock_database, mock_registry):
        """Test create() class method with different MongoDB parameters."""
        mongo_db_uri = "mongodb://localhost:27018"
        mongo_db_name = "production_db"

        class _MockDatum:
            def __init__(
                self,
                data=None,
                registry_uri=None,
                registry_key=None,
                derived_from=None,
                metadata=None,
                added_at=None,
                contract="default",
                project_id="test_project",
                line_id="test_line",
            ):
                self.id = PydanticObjectId()
                self.data = data
                self.contract = contract
                self.registry_uri = registry_uri
                self.registry_key = registry_key
                self.derived_from = derived_from
                self.metadata = metadata or {}
                self.added_at = added_at if added_at is not None else datetime.now()
                self.project_id = project_id
                self.line_id = line_id

        mock_dataset_database = AsyncMock()
        mock_dataset_database.initialize = AsyncMock()
        mock_dataset_database.insert = AsyncMock()
        mock_dataset_database.get = AsyncMock()
        mock_dataset_database.find = AsyncMock()

        MockBackendClass = self._create_mock_backend_class(mock_database, mock_dataset_database)

        with (
            patch("mindtrace.datalake.datalake.MongoMindtraceODMBackend", new=MockBackendClass),
            patch("mindtrace.datalake.datalake.Registry", return_value=mock_registry),
            patch("mindtrace.datalake.datalake.Datum", _MockDatum),
        ):
            result = await Datalake.create(mongo_db_uri, mongo_db_name)

        # Verify the returned instance has correct parameters
        assert result.mongo_db_uri == mongo_db_uri
        assert result.mongo_db_name == mongo_db_name
        assert result.datum_database == mock_database
        assert result.dataset_database == mock_dataset_database
        assert result.registries == {}

        # Verify initialize was called for both databases
        mock_database.initialize.assert_called_once()
        mock_dataset_database.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_class_method_initialization_failure(self, mock_database, mock_registry):
        """Test create() class method when initialization fails."""
        mongo_db_uri = "mongodb://test:27017"
        mongo_db_name = "test_db"

        # Make initialize raise an exception
        mock_database.initialize.side_effect = Exception("Database connection failed")
        mock_dataset_database = AsyncMock()
        mock_dataset_database.initialize = AsyncMock()

        class _MockDatum:
            def __init__(
                self,
                data=None,
                registry_uri=None,
                registry_key=None,
                derived_from=None,
                metadata=None,
                added_at=None,
                contract="default",
                project_id="test_project",
                line_id="test_line",
            ):
                self.id = PydanticObjectId()
                self.data = data
                self.contract = contract
                self.registry_uri = registry_uri
                self.registry_key = registry_key
                self.derived_from = derived_from
                self.metadata = metadata or {}
                self.added_at = added_at if added_at is not None else datetime.now()
                self.project_id = project_id
                self.line_id = line_id

        # Create a callable that returns the appropriate mock based on call count
        call_count = [0]

        def mock_backend_factory(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_database
            else:
                return mock_dataset_database

        with (
            patch("mindtrace.datalake.datalake.MongoMindtraceODMBackend", side_effect=mock_backend_factory),
            patch("mindtrace.datalake.datalake.Registry", return_value=mock_registry),
            patch("mindtrace.datalake.datalake.Datum", _MockDatum),
        ):
            # Should raise the exception from initialize
            with pytest.raises(Exception, match="Database connection failed"):
                await Datalake.create(mongo_db_uri, mongo_db_name)

        # Verify initialize was called (fails on first call)
        mock_database.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_class_method_returns_initialized_instance(self, mock_database, mock_registry):
        """Test that create() class method returns a fully initialized instance."""
        mongo_db_uri = "mongodb://test:27017"
        mongo_db_name = "test_db"

        class _MockDatum:
            def __init__(
                self,
                data=None,
                registry_uri=None,
                registry_key=None,
                derived_from=None,
                metadata=None,
                added_at=None,
                contract="default",
                project_id="test_project",
                line_id="test_line",
            ):
                self.id = PydanticObjectId()
                self.data = data
                self.contract = contract
                self.registry_uri = registry_uri
                self.registry_key = registry_key
                self.derived_from = derived_from
                self.metadata = metadata or {}
                self.added_at = added_at if added_at is not None else datetime.now()
                self.project_id = project_id
                self.line_id = line_id

        mock_dataset_database = AsyncMock()
        mock_dataset_database.initialize = AsyncMock()
        mock_dataset_database.insert = AsyncMock()
        mock_dataset_database.get = AsyncMock()
        mock_dataset_database.find = AsyncMock()

        MockBackendClass = self._create_mock_backend_class(mock_database, mock_dataset_database)

        with (
            patch("mindtrace.datalake.datalake.MongoMindtraceODMBackend", new=MockBackendClass),
            patch("mindtrace.datalake.datalake.Registry", return_value=mock_registry),
            patch("mindtrace.datalake.datalake.Datum", _MockDatum),
        ):
            result = await Datalake.create(mongo_db_uri, mongo_db_name)

        # Verify the instance is ready to use (can call methods without additional initialization)
        assert hasattr(result, "datum_database")
        assert hasattr(result, "dataset_database")
        assert hasattr(result, "registries")
        assert hasattr(result, "mongo_db_uri")
        assert hasattr(result, "mongo_db_name")

        # Verify all attributes are properly set
        assert result.mongo_db_uri == mongo_db_uri
        assert result.mongo_db_name == mongo_db_name
        assert result.datum_database == mock_database
        assert result.dataset_database == mock_dataset_database
        assert result.registries == {}

        # Verify initialize was called for both databases
        mock_database.initialize.assert_called_once()
        mock_dataset_database.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_class_method_multiple_calls(self, mock_database, mock_registry):
        """Test multiple calls to create() class method create independent instances."""
        mongo_db_uri = "mongodb://test:27017"
        mongo_db_name = "test_db"

        class _MockDatum:
            def __init__(
                self,
                data=None,
                registry_uri=None,
                registry_key=None,
                derived_from=None,
                metadata=None,
                added_at=None,
                contract="default",
                project_id="test_project",
                line_id="test_line",
            ):
                self.id = PydanticObjectId()
                self.data = data
                self.contract = contract
                self.registry_uri = registry_uri
                self.registry_key = registry_key
                self.derived_from = derived_from
                self.metadata = metadata or {}
                self.added_at = added_at if added_at is not None else datetime.now()
                self.project_id = project_id
                self.line_id = line_id

        # Create separate mocks for each instance
        mock_dataset_database1 = AsyncMock()
        mock_dataset_database1.initialize = AsyncMock()
        mock_dataset_database1.insert = AsyncMock()
        mock_dataset_database1.get = AsyncMock()
        mock_dataset_database1.find = AsyncMock()
        mock_dataset_database2 = AsyncMock()
        mock_dataset_database2.initialize = AsyncMock()
        mock_dataset_database2.insert = AsyncMock()
        mock_dataset_database2.get = AsyncMock()
        mock_dataset_database2.find = AsyncMock()

        # Track call count to return appropriate mocks for multiple instances
        call_count = [0]

        def mock_backend_factory(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                # First instance: first call = datum_db, second call = dataset_db
                return mock_database if call_count[0] == 1 else mock_dataset_database1
            else:
                # Second instance: third call = datum_db, fourth call = dataset_db
                return mock_database if call_count[0] == 3 else mock_dataset_database2

        class MockBackendMeta(type):
            def __getitem__(cls, item):
                return cls

        class MockBackendClass(metaclass=MockBackendMeta):
            def __new__(cls, *args, **kwargs):
                return mock_backend_factory(*args, **kwargs)

        with (
            patch("mindtrace.datalake.datalake.MongoMindtraceODMBackend", new=MockBackendClass),
            patch("mindtrace.datalake.datalake.Registry", return_value=mock_registry),
            patch("mindtrace.datalake.datalake.Datum", _MockDatum),
        ):
            # Create two instances
            result1 = await Datalake.create(mongo_db_uri, mongo_db_name)
            result2 = await Datalake.create(mongo_db_uri, mongo_db_name)

        # Verify both instances are created successfully
        assert isinstance(result1, Datalake)
        assert isinstance(result2, Datalake)

        # Verify they are different instances
        assert result1 is not result2

        # Verify both have correct attributes
        assert result1.mongo_db_uri == mongo_db_uri
        assert result2.mongo_db_uri == mongo_db_uri
        assert result1.mongo_db_name == mongo_db_name
        assert result2.mongo_db_name == mongo_db_name

        # Verify initialize was called for both databases in each instance
        assert mock_database.initialize.call_count == 2
        mock_dataset_database1.initialize.assert_called_once()
        mock_dataset_database2.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_data_optimized_single_query(self, datalake, mock_database):
        """Test query_data_optimized with single query."""
        # Mock aggregation results
        mock_results = [{"image_id": "507f1f77bcf86cd799439011"}, {"image_id": "507f1f77bcf86cd799439012"}]
        mock_database.aggregate.return_value = mock_results

        query = {"metadata.project": "test_project", "column": "image_id"}
        result = await datalake.query_data(query)

        # Verify aggregation was called
        mock_database.aggregate.assert_called_once()

        # Verify result format
        assert len(result) == 2
        assert result[0]["image_id"] == "507f1f77bcf86cd799439011"
        assert result[1]["image_id"] == "507f1f77bcf86cd799439012"

    @pytest.mark.asyncio
    async def test_query_data_optimized_multi_query(self, datalake, mock_database):
        """Test query_data_optimized with multi-query."""
        # Mock aggregation results
        mock_results = [
            {"image_id": "507f1f77bcf86cd799439011", "label_id": "507f1f77bcf86cd799439021"},
            {"image_id": "507f1f77bcf86cd799439012", "label_id": "507f1f77bcf86cd799439022"},
        ]
        mock_database.aggregate.return_value = mock_results

        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "column": "label_id"},
        ]
        result = await datalake.query_data(query)

        # Verify aggregation was called
        mock_database.aggregate.assert_called_once()

        # Verify result format
        assert len(result) == 2
        assert result[0]["image_id"] == "507f1f77bcf86cd799439011"
        assert result[0]["label_id"] == "507f1f77bcf86cd799439021"

    @pytest.mark.asyncio
    async def test_query_data_optimized_transpose(self, datalake, mock_database):
        """Test query_data_optimized with transpose=True."""
        # Mock aggregation results
        mock_results = [{"image_id": "507f1f77bcf86cd799439011"}, {"image_id": "507f1f77bcf86cd799439012"}]
        mock_database.aggregate.return_value = mock_results

        query = {"metadata.project": "test_project", "column": "image_id"}
        result = await datalake.query_data(query, transpose=True)

        # Verify result format
        assert isinstance(result, dict)
        assert "image_id" in result
        assert len(result["image_id"]) == 2
        assert result["image_id"][0] == "507f1f77bcf86cd799439011"

    @pytest.mark.asyncio
    async def test_query_data_optimized_complex_chain(self, datalake, mock_database):
        """Complex multi-level queries are handled via the aggregation pipeline."""

        mock_database.aggregate.return_value = [
            {
                "image_id": "507f1f77bcf86cd799439011",
                "label_id": "507f1f77bcf86cd799439021",
                "bbox_id": "507f1f77bcf86cd799439031",
            }
        ]

        complex_query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "column": "label_id"},
            {"derived_from": "label_id", "data.type": "bbox", "column": "bbox_id"},
        ]

        result = await datalake.query_data(complex_query)

        mock_database.aggregate.assert_called_once()
        assert result == [
            {
                "image_id": "507f1f77bcf86cd799439011",
                "label_id": "507f1f77bcf86cd799439021",
                "bbox_id": "507f1f77bcf86cd799439031",
            }
        ]

    @pytest.mark.asyncio
    async def test_initialize_dataset_database(self, datalake, mock_database, mock_dataset_database):
        """Test that initialize also initializes dataset_database."""
        await datalake.initialize()
        mock_database.initialize.assert_called_once()
        mock_dataset_database.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_dataset(self, datalake, mock_dataset_database):
        """Test adding a dataset to the datalake."""
        # Create a mock dataset
        mock_dataset = MagicMock(spec=Dataset)
        mock_dataset.name = "test_dataset"
        mock_dataset.description = "Test dataset description"
        mock_dataset.datum_ids = [{"image": PydanticObjectId()}]
        mock_dataset.id = PydanticObjectId()

        inserted_dataset = MagicMock(spec=Dataset)
        inserted_dataset.name = "test_dataset"
        inserted_dataset.description = "Test dataset description"
        inserted_dataset.id = mock_dataset.id
        mock_dataset_database.insert.return_value = inserted_dataset

        result = await datalake.add_dataset(mock_dataset)

        mock_dataset_database.insert.assert_called_once()
        assert result == inserted_dataset

    @pytest.mark.asyncio
    async def test_get_dataset(self, datalake, mock_dataset_database):
        """Test getting a dataset from the datalake."""
        dataset_id = PydanticObjectId()
        mock_dataset = MagicMock(spec=Dataset)
        mock_dataset.name = "test_dataset"
        mock_dataset.description = "Test dataset description"
        mock_dataset.datum_ids = []
        mock_dataset.id = dataset_id
        mock_dataset_database.get.return_value = mock_dataset

        result = await datalake.get_dataset(dataset_id)

        mock_dataset_database.get.assert_called_once_with(dataset_id)
        assert result == mock_dataset
        assert result.id == dataset_id

    @pytest.mark.asyncio
    async def test_get_dataset_none_id(self, datalake):
        """Test getting a dataset with None ID raises error."""
        with pytest.raises(DocumentNotFoundError, match="Dataset ID is None"):
            await datalake.get_dataset(None)

    @pytest.mark.asyncio
    async def test_get_dataset_nonexistent(self, datalake, mock_dataset_database):
        """Test getting nonexistent dataset."""
        dataset_id = PydanticObjectId()
        mock_dataset_database.get.side_effect = DocumentNotFoundError("Not found")

        with pytest.raises(DocumentNotFoundError):
            await datalake.get_dataset(dataset_id)

    @pytest.mark.asyncio
    async def test_get_datasets(self, datalake, mock_dataset_database):
        """Test getting multiple datasets."""
        dataset_ids = [PydanticObjectId() for _ in range(3)]
        mock_datasets = []
        for i in range(3):
            mock_dataset = MagicMock(spec=Dataset)
            mock_dataset.name = f"dataset_{i}"
            mock_dataset.description = f"Description {i}"
            mock_dataset.datum_ids = []
            mock_dataset.id = dataset_ids[i]
            mock_datasets.append(mock_dataset)

        # Mock get_dataset calls
        with patch.object(datalake, "get_dataset", side_effect=mock_datasets):
            result = await datalake.get_datasets(dataset_ids)

        assert len(result) == 3
        for i, dataset in enumerate(result):
            assert dataset.name == f"dataset_{i}"
            assert dataset.id == dataset_ids[i]

    @pytest.mark.asyncio
    async def test_get_datasets_empty_list(self, datalake):
        """Test getting datasets with empty list."""
        result = await datalake.get_datasets([])
        assert result == []

    @pytest.mark.asyncio
    async def test_find_datasets_no_filter(self, datalake, mock_dataset_database):
        """Test finding datasets with no filter."""
        mock_dataset1 = MagicMock(spec=Dataset)
        mock_dataset1.name = "dataset1"
        mock_dataset1.description = "Description 1"
        mock_dataset1.datum_ids = []
        mock_dataset2 = MagicMock(spec=Dataset)
        mock_dataset2.name = "dataset2"
        mock_dataset2.description = "Description 2"
        mock_dataset2.datum_ids = []
        mock_datasets = [mock_dataset1, mock_dataset2]
        mock_dataset_database.find.return_value = mock_datasets

        result = await datalake.find_datasets()

        mock_dataset_database.find.assert_called_once_with({})
        assert len(result) == 2
        assert result[0].name == "dataset1"
        assert result[1].name == "dataset2"

    @pytest.mark.asyncio
    async def test_find_datasets_with_filter(self, datalake, mock_dataset_database):
        """Test finding datasets with a filter."""
        filter_dict = {"name": "test_dataset"}
        mock_dataset = MagicMock(spec=Dataset)
        mock_dataset.name = "test_dataset"
        mock_dataset.description = "Test"
        mock_dataset.datum_ids = []
        mock_dataset_database.find.return_value = [mock_dataset]

        result = await datalake.find_datasets(filter_dict)

        mock_dataset_database.find.assert_called_once_with(filter_dict)
        assert len(result) == 1
        assert result[0].name == "test_dataset"

    @pytest.mark.asyncio
    async def test_find_datasets_empty_result(self, datalake, mock_dataset_database):
        """Test finding datasets that returns empty result."""
        mock_dataset_database.find.return_value = []

        result = await datalake.find_datasets({"name": "nonexistent"})

        assert result == []
