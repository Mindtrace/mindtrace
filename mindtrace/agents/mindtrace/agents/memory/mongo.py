from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from ._store import AbstractMemoryStore, MemoryEntry

try:
    import motor.motor_asyncio as motor
except ImportError as e:
    raise ImportError(
        "MongoMemoryStore requires motor. "
        "Install it with: pip install 'mindtrace-agents[memory-mongo]'"
    ) from e


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for pluggable embedding backends."""

    async def embed(self, text: str) -> list[float]: ...


class MongoMemoryStore(AbstractMemoryStore):
    """Long-term memory with optional vector search backed by MongoDB.

    Falls back to $text search if no embedding_provider is configured.
    Namespaced: documents tagged with namespace field for isolation.

    For $text search, create a text index on the 'value' field:
        db.agent_memory.createIndex({"value": "text"})
    """

    def __init__(
        self,
        mongo_url: str,
        database: str,
        collection: str,
        namespace: str,
        embedding_provider: EmbeddingProvider | None = None,
        vector_index_name: str = "vector_index",
        **kwargs: Any,
    ) -> None:
        super().__init__(namespace=namespace, **kwargs)
        self._mongo_url = mongo_url
        self._database_name = database
        self._collection_name = collection
        self._embedding_provider = embedding_provider
        self._vector_index_name = vector_index_name
        self._client: motor.AsyncIOMotorClient | None = None

    def _get_collection(self) -> motor.AsyncIOMotorCollection:
        if self._client is None:
            self._client = motor.AsyncIOMotorClient(self._mongo_url)
        return self._client[self._database_name][self._collection_name]

    def _doc(self, key: str, value: str, metadata: dict) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "namespace": self.namespace,
            "key": key,
            "value": value,
            "metadata": metadata,
            "created_at": now,
            "updated_at": now,
        }

    async def save(self, key: str, value: str, metadata: dict | None = None) -> None:
        col = self._get_collection()
        now = datetime.now(timezone.utc)
        meta = metadata or {}
        await col.update_one(
            {"namespace": self.namespace, "key": key},
            {
                "$set": {"value": value, "metadata": meta, "updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    async def get(self, key: str) -> MemoryEntry | None:
        col = self._get_collection()
        doc = await col.find_one({"namespace": self.namespace, "key": key})
        if doc is None:
            return None
        return self._doc_to_entry(doc)

    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """$text search (vector search deferred to Phase 4)."""
        col = self._get_collection()
        cursor = col.find(
            {"namespace": self.namespace, "$text": {"$search": query}},
            {"score": {"$meta": "textScore"}},
        ).sort([("score", {"$meta": "textScore"})]).limit(top_k)
        results = []
        async for doc in cursor:
            results.append(self._doc_to_entry(doc))
        return results

    async def delete(self, key: str) -> None:
        col = self._get_collection()
        await col.delete_one({"namespace": self.namespace, "key": key})

    async def list_keys(self) -> list[str]:
        col = self._get_collection()
        cursor = col.find({"namespace": self.namespace}, {"key": 1, "_id": 0})
        keys = []
        async for doc in cursor:
            keys.append(doc["key"])
        return keys

    def _doc_to_entry(self, doc: dict) -> MemoryEntry:
        return MemoryEntry(
            key=doc["key"],
            value=doc["value"],
            metadata=doc.get("metadata", {}),
            created_at=doc.get("created_at", datetime.now(timezone.utc)),
            updated_at=doc.get("updated_at", datetime.now(timezone.utc)),
        )

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


__all__ = ["EmbeddingProvider", "MongoMemoryStore"]
