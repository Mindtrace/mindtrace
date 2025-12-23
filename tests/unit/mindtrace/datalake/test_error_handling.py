"""Unit tests for error handling in the Datalake class."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake import Datalake
from mindtrace.datalake.types import Datum


def create_mock_datum(data=None, registry_uri=None, registry_key=None, derived_from=None, metadata=None, datum_id=None):
    """Create a mock Datum instance without requiring beanie initialization."""
    if datum_id is None:
        datum_id = "507f1f77bcf86cd799439011"

    mock_datum = MagicMock(spec=Datum)
    mock_datum.data = data
    mock_datum.registry_uri = registry_uri
    mock_datum.registry_key = registry_key
    mock_datum.derived_from = derived_from
    mock_datum.metadata = metadata or {}
    mock_datum.id = datum_id
    return mock_datum


class TestErrorHandling:
    """Unit tests for error handling in the Datalake class."""

    @pytest.fixture
    def mock_database(self):
        """Mock database backend."""
        mock_db = AsyncMock()
        mock_db.initialize = AsyncMock()
        mock_db.insert = AsyncMock()
        mock_db.get = AsyncMock()
        mock_db.find = AsyncMock()
        mock_db.get_raw_model = MagicMock(return_value=MagicMock(derived_from=MagicMock()))
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
                self.id = PydanticObjectId()
                self.data = data
                self.registry_uri = registry_uri
                self.registry_key = registry_key
                self.derived_from = derived_from
                self.metadata = metadata or {}

        db_patcher = patch("mindtrace.datalake.datalake.MongoMindtraceODM", return_value=mock_database)
        datum_patcher = patch("mindtrace.datalake.datalake.Datum", _MockDatum)
        registry_patcher = patch("mindtrace.datalake.datalake.Registry", return_value=mock_registry)
        db_patcher.start()
        datum_patcher.start()
        registry_patcher.start()
        try:
            instance = Datalake("mongodb://test:27017", "test_db")
            yield instance
        finally:
            datum_patcher.stop()
            db_patcher.stop()
            registry_patcher.stop()

    @pytest.mark.asyncio
    async def test_initialize_database_error(self, datalake, mock_database):
        """Test error handling during database initialization."""
        mock_database.initialize.side_effect = Exception("Database connection failed")

        with pytest.raises(Exception, match="Database connection failed"):
            await datalake.initialize()

    @pytest.mark.asyncio
    async def test_add_datum_database_insert_error(self, datalake, mock_database):
        """Test error handling during database insert."""
        test_data = {"test": "data"}
        test_metadata = {"source": "test"}

        mock_database.insert.side_effect = Exception("Insert failed")

        with pytest.raises(Exception, match="Insert failed"):
            await datalake.add_datum(test_data, test_metadata)

    @pytest.mark.asyncio
    async def test_add_datum_registry_save_error(self, datalake, mock_database, mock_registry, tmp_path):
        """Test error handling during registry save."""
        test_data = {"test": "data"}
        test_metadata = {"source": "test"}
        registry_uri = f"{(tmp_path / 'registry').as_posix()}"

        mock_registry.save.side_effect = Exception("Registry save failed")

        with pytest.raises(Exception, match="Registry save failed"):
            await datalake.add_datum(test_data, test_metadata, registry_uri=registry_uri)

    @pytest.mark.asyncio
    async def test_get_datum_database_error(self, datalake, mock_database):
        """Test error handling during database get."""
        datum_id = PydanticObjectId()
        mock_database.get.side_effect = Exception("Database query failed")

        with pytest.raises(Exception, match="Database query failed"):
            await datalake.get_datum(datum_id)

    @pytest.mark.asyncio
    async def test_get_datum_document_not_found(self, datalake, mock_database):
        """Test handling of DocumentNotFoundError."""
        datum_id = PydanticObjectId()
        mock_database.get.side_effect = DocumentNotFoundError("Document not found")

        with pytest.raises(DocumentNotFoundError, match="Document not found"):
            await datalake.get_datum(datum_id)

    @pytest.mark.asyncio
    async def test_get_datum_registry_load_error(self, datalake, mock_database, mock_registry, tmp_path):
        """Test error handling during registry load."""
        datum_id = PydanticObjectId()
        registry_uri = f"{(tmp_path / 'registry').as_posix()}"
        registry_key = "test_key"

        mock_datum = create_mock_datum(
            data=None, registry_uri=registry_uri, registry_key=registry_key, metadata={}, datum_id=datum_id
        )
        mock_database.get.return_value = mock_datum
        mock_registry.load.side_effect = Exception("Registry load failed")

        with pytest.raises(Exception, match="Registry load failed"):
            await datalake.get_datum(datum_id)

    @pytest.mark.asyncio
    async def test_get_data_with_mixed_errors(self, datalake):
        """Test get_data with some successful and some failed retrievals."""
        datum_ids = [PydanticObjectId() for _ in range(3)]

        # Mock get_datum to return success, error, success
        mock_datum1 = create_mock_datum(data={"test": 1}, metadata={}, datum_id=datum_ids[0])
        mock_datum3 = create_mock_datum(data={"test": 3}, metadata={}, datum_id=datum_ids[2])

        async def mock_get_datum(datum_id):
            if datum_id == datum_ids[0]:
                return mock_datum1
            elif datum_id == datum_ids[1]:
                raise DocumentNotFoundError("Not found")
            elif datum_id == datum_ids[2]:
                return mock_datum3
            else:
                raise Exception("Unexpected ID")

        with patch.object(datalake, "get_datum", side_effect=mock_get_datum):
            with pytest.raises(DocumentNotFoundError, match="Not found"):
                await datalake.get_data(datum_ids)

    @pytest.mark.asyncio
    async def test_get_directly_derived_data_database_error(self, datalake, mock_database):
        """Test error handling in get_directly_derived_data."""
        parent_id = PydanticObjectId()
        mock_database.find.side_effect = Exception("Database query failed")

        with pytest.raises(Exception, match="Database query failed"):
            await datalake.get_directly_derived_data(parent_id)

    @pytest.mark.asyncio
    async def test_get_indirectly_derived_data_error_propagation(self, datalake):
        """Test error propagation in get_indirectly_derived_data."""
        root_id = PydanticObjectId()

        with patch.object(datalake, "get_directly_derived_data") as mock_get_direct:
            mock_get_direct.side_effect = Exception("Derivation query failed")

            with pytest.raises(Exception, match="Derivation query failed"):
                await datalake.get_indirectly_derived_data(root_id)

    @pytest.mark.asyncio
    async def test_registry_creation_error(self, datalake, mock_database, tmp_path):
        """Test error handling during registry creation."""
        test_data = {"test": "data"}
        test_metadata = {"source": "test"}
        registry_uri = f"{(tmp_path / 'registry').as_posix()}"

        with patch("mindtrace.datalake.datalake.Registry") as mock_registry_class:
            mock_registry_class.side_effect = Exception("Registry creation failed")

            with pytest.raises(Exception, match="Registry creation failed"):
                await datalake.add_datum(test_data, test_metadata, registry_uri=registry_uri)

    @pytest.mark.asyncio
    async def test_registry_backend_error(self, datalake, mock_database, tmp_path):
        """Test error handling with registry backend errors."""
        test_data = {"test": "data"}
        test_metadata = {"source": "test"}
        registry_uri = f"{(tmp_path / 'registry').as_posix()}"

        with patch("mindtrace.datalake.datalake.LocalRegistryBackend") as mock_backend_class:
            mock_backend_class.side_effect = Exception("Backend creation failed")

            with pytest.raises(Exception, match="Backend creation failed"):
                await datalake.add_datum(test_data, test_metadata, registry_uri=registry_uri)

    @pytest.mark.asyncio
    async def test_none_datum_id(self, datalake, mock_database):
        """Test handling of None datum ID."""
        with pytest.raises(Exception):  # Should raise validation error
            await datalake.get_datum(None)

    @pytest.mark.asyncio
    async def test_empty_datum_ids_list(self, datalake):
        """Test get_data with empty list."""
        result = await datalake.get_data([])
        assert result == []

    @pytest.mark.asyncio
    async def test_none_datum_ids_list(self, datalake):
        """Test get_data with None list."""
        with pytest.raises(Exception):  # Should raise validation error
            await datalake.get_data(None)

    @pytest.mark.asyncio
    async def test_large_datum_ids_list(self, datalake):
        """Test get_data with very large list."""
        # Create a large list of IDs
        large_id_list = [PydanticObjectId() for _ in range(1000)]

        # Mock get_datum to return a datum for each ID
        mock_datum = create_mock_datum(data={"test": "data"}, metadata={})

        with patch.object(datalake, "get_datum", return_value=mock_datum):
            result = await datalake.get_data(large_id_list)

        assert len(result) == 1000
        assert all(datum == mock_datum for datum in result)

    @pytest.mark.asyncio
    async def test_concurrent_registry_access_error(self, datalake, mock_database, mock_registry, tmp_path):
        """Test error handling with concurrent registry access."""
        registry_uri = f"{(tmp_path / 'registry').as_posix()}"

        # First call succeeds
        mock_datum1 = create_mock_datum(data=None, registry_uri=registry_uri, registry_key="key1", metadata={})
        mock_database.insert.return_value = mock_datum1
        mock_registry.save.return_value = None

        await datalake.add_datum({"test": "data1"}, {}, registry_uri=registry_uri)

        # Second call fails during registry save
        mock_registry.save.side_effect = Exception("Concurrent access error")

        with pytest.raises(Exception, match="Concurrent access error"):
            await datalake.add_datum({"test": "data2"}, {}, registry_uri=registry_uri)

    @pytest.mark.asyncio
    async def test_memory_error_handling(self, datalake, mock_database):
        """Test handling of memory-related errors."""
        # Simulate memory error during large data insertion
        large_data = {"large": "x" * 1000000}  # 1MB string
        mock_database.insert.side_effect = MemoryError("Out of memory")

        with pytest.raises(MemoryError, match="Out of memory"):
            await datalake.add_datum(large_data, {"source": "memory_test"})

    @pytest.mark.asyncio
    async def test_timeout_error_handling(self, datalake, mock_database):
        """Test handling of timeout errors."""
        mock_database.get.side_effect = TimeoutError("Database timeout")

        with pytest.raises(TimeoutError, match="Database timeout"):
            await datalake.get_datum(PydanticObjectId())

    @pytest.mark.asyncio
    async def test_network_error_handling(self, datalake, mock_database):
        """Test handling of network-related errors."""
        mock_database.insert.side_effect = ConnectionError("Network connection failed")

        with pytest.raises(ConnectionError, match="Network connection failed"):
            await datalake.add_datum({"test": "data"}, {"source": "network_test"})

    @pytest.mark.asyncio
    async def test_permission_error_handling(self, datalake, mock_registry, tmp_path):
        """Test handling of permission errors."""
        registry_uri = f"{(tmp_path / 'readonly').as_posix()}"
        mock_registry.save.side_effect = PermissionError("Permission denied")

        with pytest.raises(PermissionError, match="Permission denied"):
            await datalake.add_datum({"test": "data"}, {"source": "permission_test"}, registry_uri=registry_uri)

    @pytest.mark.asyncio
    async def test_corrupted_data_handling(self, datalake, mock_database, mock_registry, tmp_path):
        """Test handling of corrupted data."""
        datum_id = PydanticObjectId()
        registry_uri = f"{(tmp_path / 'registry').as_posix()}"
        registry_key = "corrupted_key"

        mock_datum = create_mock_datum(
            data=None, registry_uri=registry_uri, registry_key=registry_key, metadata={}, datum_id=datum_id
        )
        mock_database.get.return_value = mock_datum
        mock_registry.load.return_value = None  # Corrupted data returns None

        result = await datalake.get_datum(datum_id)

        # Should handle None data gracefully
        assert result.data is None
        assert result.registry_uri == registry_uri

    @pytest.mark.asyncio
    async def test_partial_failure_recovery(self, datalake, mock_database):
        """Test recovery from partial failures."""
        # First operation fails
        mock_database.insert.side_effect = Exception("Temporary failure")

        with pytest.raises(Exception, match="Temporary failure"):
            await datalake.add_datum({"test": "data1"}, {"source": "test1"})

        # Second operation succeeds after recovery
        mock_datum = create_mock_datum(data={"test": "data2"}, metadata={"source": "test2"})
        mock_database.insert.return_value = mock_datum
        mock_database.insert.side_effect = None

        result = await datalake.add_datum({"test": "data2"}, {"source": "test2"})
        assert result == mock_datum
