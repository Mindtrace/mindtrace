"""Unit tests for HorizonDB database wrapper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.apps.horizon.db import HorizonDB


class TestHorizonDBInit:
    """Tests for HorizonDB initialization."""

    def test_init_stores_params(self):
        """Test that __init__ stores connection parameters without connecting."""
        db = HorizonDB(uri="mongodb://test:27017", db_name="test_db")

        assert db._uri == "mongodb://test:27017"
        assert db._db_name == "test_db"
        assert db._client is None
        assert db._db is None

    def test_init_default_params(self):
        """Test that __init__ has sensible defaults."""
        db = HorizonDB()

        assert db._uri == "mongodb://localhost:27017"
        assert db._db_name == "horizon"


class TestHorizonDBProperties:
    """Tests for HorizonDB properties."""

    def test_client_none_before_connect(self):
        """Test client is None before connect."""
        db = HorizonDB()
        assert db.client is None

    def test_db_none_before_connect(self):
        """Test db is None before connect."""
        db = HorizonDB()
        assert db.db is None

    def test_is_connected_false_before_connect(self):
        """Test is_connected is False before connect."""
        db = HorizonDB()
        assert db.is_connected is False


class TestHorizonDBConnect:
    """Tests for HorizonDB connect/disconnect."""

    @pytest.mark.asyncio
    async def test_connect_initializes_client(self):
        """Test connect creates motor client."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client):
            db = HorizonDB()
            result = await db.connect()

            assert result is db
            assert db._client is mock_client
            assert db._db is mock_db
            assert db.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_idempotent(self):
        """Test that connect is idempotent."""
        mock_client = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=MagicMock())

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client) as mock_ctor:
            db = HorizonDB()
            await db.connect()
            await db.connect()

            mock_ctor.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up(self):
        """Test disconnect cleans up resources."""
        mock_client = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=MagicMock())

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client):
            db = HorizonDB()
            await db.connect()
            await db.disconnect()

            mock_client.close.assert_called_once()
            assert db._client is None
            assert db._db is None
            assert db.is_connected is False

    @pytest.mark.asyncio
    async def test_close_is_alias(self):
        """Test close is alias for disconnect."""
        mock_client = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=MagicMock())

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client):
            db = HorizonDB()
            await db.connect()
            await db.close()

            mock_client.close.assert_called_once()


class TestHorizonDBContextManager:
    """Tests for HorizonDB context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_connects_and_disconnects(self):
        """Test async context manager connects on enter and disconnects on exit."""
        mock_client = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=MagicMock())

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client):
            async with HorizonDB() as db:
                assert db.is_connected
                assert db._client is mock_client

            mock_client.close.assert_called_once()


class TestHorizonDBOperations:
    """Tests for HorizonDB CRUD operations."""

    @pytest.mark.asyncio
    async def test_insert_one(self):
        """Test insert_one calls collection insert_one."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="abc123"))
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client):
            db = HorizonDB()
            await db.connect()
            result = await db.insert_one("test_collection", {"foo": "bar"})

            assert result == "abc123"
            mock_collection.insert_one.assert_called_once_with({"foo": "bar"})

    @pytest.mark.asyncio
    async def test_find_one(self):
        """Test find_one returns document."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value={"_id": "123", "name": "test"})
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client):
            db = HorizonDB()
            await db.connect()
            result = await db.find_one("test_collection", {"name": "test"})

            assert result["name"] == "test"
            mock_collection.find_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_many(self):
        """Test find_many returns documents."""
        mock_client = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=[{"a": 1}, {"a": 2}])

        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client):
            db = HorizonDB()
            await db.connect()
            result = await db.find_many("test_collection")

            assert len(result) == 2
            mock_collection.find.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_many_with_sort_and_limit(self):
        """Test find_many with sort and limit options."""
        mock_client = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=[{"a": 1}])

        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client):
            db = HorizonDB()
            await db.connect()
            result = await db.find_many("test", sort=[("ts", -1)], limit=10)

            assert len(result) == 1
            mock_cursor.sort.assert_called_once_with([("ts", -1)])
            mock_cursor.limit.assert_called_once_with(10)

    @pytest.mark.asyncio
    async def test_delete_many(self):
        """Test delete_many returns count."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=5))
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client):
            db = HorizonDB()
            await db.connect()
            result = await db.delete_many("test_collection", {"status": "old"})

            assert result == 5

    @pytest.mark.asyncio
    async def test_count(self):
        """Test count returns document count."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count_documents = AsyncMock(return_value=42)
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client):
            db = HorizonDB()
            await db.connect()
            result = await db.count("test_collection", {"active": True})

            assert result == 42


class TestHorizonDBCollection:
    """Tests for collection access."""

    def test_collection_raises_when_not_connected(self):
        """Test collection() raises RuntimeError when not connected."""
        db = HorizonDB()
        with pytest.raises(RuntimeError, match="Database not connected"):
            db.collection("test")

    @pytest.mark.asyncio
    async def test_collection_returns_collection_when_connected(self):
        """Test collection() returns collection when connected."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client):
            db = HorizonDB()
            await db.connect()
            result = db.collection("test")

            assert result is mock_collection


class TestHorizonDBAutoConnect:
    """Tests for auto-connect behavior."""

    @pytest.mark.asyncio
    async def test_insert_one_auto_connects(self):
        """Test insert_one auto-connects if not connected."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="123"))
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client):
            db = HorizonDB()
            assert not db.is_connected

            await db.insert_one("test", {"x": 1})

            assert db.is_connected

    @pytest.mark.asyncio
    async def test_find_one_auto_connects(self):
        """Test find_one auto-connects if not connected."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value={"_id": "1"})
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client):
            db = HorizonDB()
            assert not db.is_connected

            await db.find_one("test", {"x": 1})

            assert db.is_connected

    @pytest.mark.asyncio
    async def test_delete_many_auto_connects(self):
        """Test delete_many auto-connects if not connected."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client):
            db = HorizonDB()
            assert not db.is_connected

            await db.delete_many("test")

            assert db.is_connected

    @pytest.mark.asyncio
    async def test_count_auto_connects(self):
        """Test count auto-connects if not connected."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count_documents = AsyncMock(return_value=0)
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client):
            db = HorizonDB()
            assert not db.is_connected

            await db.count("test")

            assert db.is_connected

    @pytest.mark.asyncio
    async def test_find_many_auto_connects(self):
        """Test find_many auto-connects if not connected."""
        mock_client = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch("mindtrace.apps.horizon.db.AsyncIOMotorClient", return_value=mock_client):
            db = HorizonDB()
            assert not db.is_connected

            await db.find_many("test")

            assert db.is_connected
