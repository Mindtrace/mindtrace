"""Async MongoDB wrapper for Horizon service.

Provides a clean interface for MongoDB operations with proper resource management.
Uses motor (async pymongo driver) directly.
"""

from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase


class HorizonDB:
    """Async MongoDB wrapper with proper resource management.

    A thin wrapper around motor that handles connection lifecycle.
    No application-specific logic - just generic MongoDB operations.

    Example:
        ```python
        async with HorizonDB(uri="mongodb://localhost:27017", db_name="horizon") as db:
            await db.insert_one("users", {"name": "Alice"})
            user = await db.find_one("users", {"name": "Alice"})
        ```
    """

    def __init__(
        self,
        uri: str = "mongodb://localhost:27017",
        db_name: str = "horizon",
    ):
        """Initialize with connection parameters. No connection made until connect()."""
        self._uri = uri
        self._db_name = db_name
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None

    @property
    def client(self) -> Optional[AsyncIOMotorClient]:
        """The MongoDB client (None if not connected)."""
        return self._client

    @property
    def db(self) -> Optional[AsyncIOMotorDatabase]:
        """The database instance (None if not connected)."""
        return self._db

    @property
    def is_connected(self) -> bool:
        """Whether the database is connected."""
        return self._client is not None

    def collection(self, name: str) -> AsyncIOMotorCollection:
        """Get a collection by name."""
        if self._db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._db[name]

    async def connect(self) -> "HorizonDB":
        """Connect to MongoDB. Returns self for chaining."""
        if self._client is not None:
            return self
        self._client = AsyncIOMotorClient(self._uri)
        self._db = self._client[self._db_name]
        return self

    async def disconnect(self) -> None:
        """Disconnect and cleanup."""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None

    async def close(self) -> None:
        """Alias for disconnect()."""
        await self.disconnect()

    async def __aenter__(self) -> "HorizonDB":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()

    # -------------------------------------------------------------------------
    # Generic CRUD
    # -------------------------------------------------------------------------

    async def insert_one(self, collection: str, document: Dict[str, Any]) -> str:
        """Insert a document. Returns inserted ID as string."""
        if not self.is_connected:
            await self.connect()
        result = await self._db[collection].insert_one(document)
        return str(result.inserted_id)

    async def find_one(self, collection: str, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single document."""
        if not self.is_connected:
            await self.connect()
        return await self._db[collection].find_one(query)

    async def find_many(
        self,
        collection: str,
        query: Optional[Dict[str, Any]] = None,
        sort: Optional[List[tuple]] = None,
        limit: int = 0,
    ) -> List[Dict[str, Any]]:
        """Find multiple documents."""
        if not self.is_connected:
            await self.connect()
        cursor = self._db[collection].find(query or {})
        if sort:
            cursor = cursor.sort(sort)
        if limit > 0:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=None)

    async def delete_many(self, collection: str, query: Optional[Dict[str, Any]] = None) -> int:
        """Delete documents. Returns count deleted."""
        if not self.is_connected:
            await self.connect()
        result = await self._db[collection].delete_many(query or {})
        return result.deleted_count

    async def count(self, collection: str, query: Optional[Dict[str, Any]] = None) -> int:
        """Count documents matching query."""
        if not self.is_connected:
            await self.connect()
        return await self._db[collection].count_documents(query or {})
