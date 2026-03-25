from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ._store import AbstractMemoryStore, MemoryEntry

_DATE_FMT = "%Y-%m-%dT%H:%M:%S.%f%z"


def _entry_to_dict(entry: MemoryEntry) -> dict:
    return {
        "key": entry.key,
        "value": entry.value,
        "metadata": entry.metadata,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
    }


def _dict_to_entry(d: dict) -> MemoryEntry:
    return MemoryEntry(
        key=d["key"],
        value=d["value"],
        metadata=d.get("metadata", {}),
        created_at=datetime.fromisoformat(d["created_at"]),
        updated_at=datetime.fromisoformat(d["updated_at"]),
    )


class JsonFileStore(AbstractMemoryStore):
    """Persists memories to a JSON file. Suitable for single-process apps."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._data: dict[str, MemoryEntry] = {}
        if self._path.exists():
            self._load()

    def _load(self) -> None:
        raw = json.loads(self._path.read_text())
        self._data = {k: _dict_to_entry(v) for k, v in raw.items()}

    def _flush(self) -> None:
        self._path.write_text(json.dumps({k: _entry_to_dict(v) for k, v in self._data.items()}, indent=2))

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
        self._flush()

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
        self._flush()

    async def list_keys(self) -> list[str]:
        return list(self._data.keys())


__all__ = ["JsonFileStore"]
