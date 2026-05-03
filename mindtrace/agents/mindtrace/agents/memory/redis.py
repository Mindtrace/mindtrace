from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ._store import AbstractMemoryStore, MemoryEntry

try:
    import redis.asyncio as aioredis
except ImportError as e:
    raise ImportError(
        "RedisMemoryStore requires redis. "
        "Install it with: pip install 'mindtrace-agents[memory-redis]'"
    ) from e


class RedisMemoryStore(AbstractMemoryStore):
    """Short-term TTL-scoped memory backed by Redis hashes.

    Keys are namespaced: {namespace}:{key}
    search() performs prefix scan (no vector search).
    """

    def __init__(
        self,
        redis_url: str,
        namespace: str,
        default_ttl: int = 3600,
        **kwargs: Any,
    ) -> None:
        super().__init__(namespace=namespace, **kwargs)
        self._redis_url = redis_url
        self._default_ttl = default_ttl
        self._client: aioredis.Redis | None = None

    def _full_key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def save(
        self,
        key: str,
        value: str,
        metadata: dict | None = None,
        ttl: int | None = None,
    ) -> None:
        client = await self._get_client()
        full_key = self._full_key(key)
        now = datetime.now(timezone.utc).isoformat()

        existing_raw = await client.hget(full_key, "created_at")
        created_at = existing_raw if existing_raw else now

        entry_data = {
            "key": key,
            "value": value,
            "metadata": json.dumps(metadata or {}),
            "created_at": created_at,
            "updated_at": now,
        }
        await client.hset(full_key, mapping=entry_data)
        await client.expire(full_key, ttl if ttl is not None else self._default_ttl)

    async def get(self, key: str) -> MemoryEntry | None:
        client = await self._get_client()
        full_key = self._full_key(key)
        data = await client.hgetall(full_key)
        if not data:
            return None
        return MemoryEntry(
            key=data["key"],
            value=data["value"],
            metadata=json.loads(data.get("metadata", "{}")),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )

    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """Prefix scan search — returns entries whose key or value contains the query."""
        client = await self._get_client()
        pattern = f"{self.namespace}:*"
        results: list[MemoryEntry] = []
        query_lower = query.lower()
        async for full_key in client.scan_iter(pattern):
            data = await client.hgetall(full_key)
            if not data:
                continue
            if query_lower in data.get("key", "").lower() or query_lower in data.get("value", "").lower():
                results.append(
                    MemoryEntry(
                        key=data["key"],
                        value=data["value"],
                        metadata=json.loads(data.get("metadata", "{}")),
                        created_at=datetime.fromisoformat(data["created_at"]),
                        updated_at=datetime.fromisoformat(data["updated_at"]),
                    )
                )
            if len(results) >= top_k:
                break
        return results

    async def delete(self, key: str) -> None:
        client = await self._get_client()
        await client.delete(self._full_key(key))

    async def list_keys(self) -> list[str]:
        client = await self._get_client()
        pattern = f"{self.namespace}:*"
        keys = []
        prefix_len = len(self.namespace) + 1
        async for full_key in client.scan_iter(pattern):
            keys.append(full_key[prefix_len:])
        return keys

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


__all__ = ["RedisMemoryStore"]
