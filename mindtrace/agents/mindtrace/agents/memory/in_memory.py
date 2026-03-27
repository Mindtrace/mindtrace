from __future__ import annotations

from datetime import datetime, timezone

from ._store import AbstractMemoryStore, MemoryEntry


class InMemoryStore(AbstractMemoryStore):
    """In-process memory store. Lost on process restart. Useful for dev and tests."""

    def __init__(self) -> None:
        self._data: dict[str, MemoryEntry] = {}

    async def save(self, key: str, value: str, metadata: dict | None = None) -> None:
        now = datetime.now(timezone.utc)
        existing = self._data.get(key)
        self._data[key] = MemoryEntry(
            key=key,
            value=value,
            metadata=metadata or {},
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )

    async def get(self, key: str) -> MemoryEntry | None:
        return self._data.get(key)

    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        query_lower = query.lower()
        matches = [
            entry
            for entry in self._data.values()
            if query_lower in entry.key.lower() or query_lower in entry.value.lower()
        ]
        return matches[:top_k]

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def list_keys(self) -> list[str]:
        return list(self._data.keys())


__all__ = ["InMemoryStore"]
