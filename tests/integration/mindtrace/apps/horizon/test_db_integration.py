"""Integration tests for HorizonDB with real MongoDB."""

import pytest

from mindtrace.apps.horizon.db import HorizonDB

from .conftest import MONGO_DB, MONGO_URL


@pytest.mark.asyncio
class TestHorizonDBConnection:
    """Integration tests for HorizonDB connection."""

    async def test_connect_to_mongodb(self):
        """Test connecting to real MongoDB instance."""
        db = HorizonDB(uri=MONGO_URL, db_name=MONGO_DB)

        try:
            await db.connect()
            assert db.is_connected
            assert db.client is not None
            assert db.db is not None
        finally:
            await db.disconnect()

    async def test_context_manager(self):
        """Test using HorizonDB as context manager."""
        async with HorizonDB(uri=MONGO_URL, db_name=MONGO_DB) as db:
            assert db.is_connected

        assert not db.is_connected

    async def test_reconnect_after_disconnect(self):
        """Test reconnecting after disconnect."""
        db = HorizonDB(uri=MONGO_URL, db_name=MONGO_DB)

        await db.connect()
        assert db.is_connected

        await db.disconnect()
        assert not db.is_connected

        await db.connect()
        assert db.is_connected

        await db.disconnect()


@pytest.mark.asyncio
class TestHorizonDBCRUD:
    """Integration tests for HorizonDB CRUD operations."""

    async def test_insert_and_find_one(self, horizon_db):
        """Test inserting and finding a document."""
        doc_id = await horizon_db.insert_one("test_crud", {"name": "Alice", "age": 30})
        assert doc_id is not None

        found = await horizon_db.find_one("test_crud", {"name": "Alice"})
        assert found is not None
        assert found["age"] == 30

        # Cleanup
        await horizon_db.delete_many("test_crud")

    async def test_find_many(self, horizon_db):
        """Test finding multiple documents."""
        await horizon_db.insert_one("test_find", {"type": "a", "val": 1})
        await horizon_db.insert_one("test_find", {"type": "b", "val": 2})
        await horizon_db.insert_one("test_find", {"type": "a", "val": 3})

        all_docs = await horizon_db.find_many("test_find")
        assert len(all_docs) == 3

        type_a = await horizon_db.find_many("test_find", query={"type": "a"})
        assert len(type_a) == 2

        # Cleanup
        await horizon_db.delete_many("test_find")

    async def test_find_many_with_sort_and_limit(self, horizon_db):
        """Test find_many with sorting and limit."""
        for i in range(5):
            await horizon_db.insert_one("test_sort", {"order": i})

        # Get top 3 in descending order
        docs = await horizon_db.find_many(
            "test_sort",
            sort=[("order", -1)],
            limit=3,
        )

        assert len(docs) == 3
        assert docs[0]["order"] == 4
        assert docs[1]["order"] == 3
        assert docs[2]["order"] == 2

        # Cleanup
        await horizon_db.delete_many("test_sort")

    async def test_delete_many(self, horizon_db):
        """Test deleting multiple documents."""
        await horizon_db.insert_one("test_delete", {"keep": False})
        await horizon_db.insert_one("test_delete", {"keep": False})
        await horizon_db.insert_one("test_delete", {"keep": True})

        deleted = await horizon_db.delete_many("test_delete", {"keep": False})
        assert deleted == 2

        remaining = await horizon_db.find_many("test_delete")
        assert len(remaining) == 1
        assert remaining[0]["keep"] is True

        # Cleanup
        await horizon_db.delete_many("test_delete")

    async def test_count(self, horizon_db):
        """Test counting documents."""
        for i in range(5):
            await horizon_db.insert_one("test_count", {"category": "x" if i < 3 else "y"})

        total = await horizon_db.count("test_count")
        assert total == 5

        x_count = await horizon_db.count("test_count", {"category": "x"})
        assert x_count == 3

        # Cleanup
        await horizon_db.delete_many("test_count")


@pytest.mark.asyncio
class TestHorizonDBAutoConnect:
    """Integration tests for auto-connect behavior."""

    async def test_insert_auto_connects(self):
        """Test that insert auto-connects if not connected."""
        db = HorizonDB(uri=MONGO_URL, db_name=MONGO_DB)
        assert not db.is_connected

        try:
            await db.insert_one("auto_test", {"x": 1})
            assert db.is_connected
        finally:
            await db.delete_many("auto_test")
            await db.disconnect()

    async def test_find_auto_connects(self):
        """Test that find auto-connects if not connected."""
        db = HorizonDB(uri=MONGO_URL, db_name=MONGO_DB)
        assert not db.is_connected

        try:
            await db.find_many("auto_test")
            assert db.is_connected
        finally:
            await db.disconnect()
