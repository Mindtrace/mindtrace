from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..memory._store import AbstractMemoryStore, MemoryEntry as StoreMemoryEntry
from .types import MemoryEntry, MemoryEntryRequest

if TYPE_CHECKING:
    from ..memory.mongo import MongoMemoryStore
    from ..memory.redis import RedisMemoryStore

logger = logging.getLogger(__name__)

_MAX_INJECT_CHARS = 8000  # ~2000 tokens at 4 chars/token


class MemoryContextBuilder:
    """Assembles injected system context from user, project, and org memory stores.

    Only entries with metadata.inject == True are included. The combined
    context is capped at max_tokens (approximate: 4 chars/token).
    """

    def __init__(
        self,
        user_store: MongoMemoryStore | None = None,
        project_store: MongoMemoryStore | None = None,
        org_store: MongoMemoryStore | None = None,
        max_tokens: int = 2000,
    ) -> None:
        self._user_store = user_store
        self._project_store = project_store
        self._org_store = org_store
        self._max_chars = max_tokens * 4

    async def build(self) -> str | None:
        sections: list[str] = []
        char_budget = self._max_chars

        for label, store in [
            ("User context", self._user_store),
            ("Project context", self._project_store),
            ("Organisation context", self._org_store),
        ]:
            if store is None or char_budget <= 0:
                continue
            try:
                keys = await store.list_keys()
                entries: list[str] = []
                for key in keys:
                    entry = await store.get(key)
                    if entry is None:
                        continue
                    if not entry.metadata.get("inject", False):
                        continue
                    line = f"- {key}: {entry.value}"
                    if char_budget - len(line) <= 0:
                        break
                    entries.append(line)
                    char_budget -= len(line)
                if entries:
                    sections.append(f"### {label}\n" + "\n".join(entries))
            except Exception as exc:
                logger.warning("MemoryContextBuilder error for %s: %s", label, exc)

        if not sections:
            return None
        return "\n\n".join(sections)


# ── Session memory (Redis) ────────────────────────────────────────────────────

async def list_session_memory(session_id: str, store: AbstractMemoryStore) -> list[StoreMemoryEntry]:
    keys = await store.list_keys()
    entries: list[StoreMemoryEntry] = []
    for key in keys:
        entry = await store.get(key)
        if entry is not None:
            entries.append(entry)
    return entries


async def get_session_memory_entry(key: str, store: AbstractMemoryStore) -> StoreMemoryEntry | None:
    return await store.get(key)


async def set_session_memory_entry(
    req: MemoryEntryRequest,
    store: AbstractMemoryStore,
) -> StoreMemoryEntry:
    await store.save(key=req.key, value=req.value, metadata=req.metadata)
    entry = await store.get(req.key)
    assert entry is not None
    return entry


async def delete_session_memory_entry(key: str, store: AbstractMemoryStore) -> None:
    await store.delete(key)


async def search_session_memory(
    query: str,
    store: AbstractMemoryStore,
    top_k: int = 5,
) -> list[StoreMemoryEntry]:
    return await store.search(query, top_k=top_k)


# ── User memory (MongoDB) ──────────────────────────────────────────────────────

async def list_user_memory(user_id: str, store: AbstractMemoryStore) -> list[StoreMemoryEntry]:
    return await list_session_memory(user_id, store)


async def get_user_memory_entry(user_id: str, key: str, store: AbstractMemoryStore) -> StoreMemoryEntry | None:
    return await store.get(key)


async def set_user_memory_entry(
    user_id: str,
    req: MemoryEntryRequest,
    store: AbstractMemoryStore,
) -> StoreMemoryEntry:
    await store.save(key=req.key, value=req.value, metadata=req.metadata)
    entry = await store.get(req.key)
    assert entry is not None
    return entry


async def delete_user_memory_entry(user_id: str, key: str, store: AbstractMemoryStore) -> None:
    await store.delete(key)


async def search_user_memory(
    user_id: str,
    query: str,
    store: AbstractMemoryStore,
    top_k: int = 5,
) -> list[StoreMemoryEntry]:
    return await store.search(query, top_k=top_k)


# ── Project / Org memory (MongoDB) — same operations, different namespace ─────

async def list_project_memory(project_id: str, store: AbstractMemoryStore) -> list[StoreMemoryEntry]:
    return await list_session_memory(project_id, store)


async def list_org_memory(org_id: str, store: AbstractMemoryStore) -> list[StoreMemoryEntry]:
    return await list_session_memory(org_id, store)


__all__ = [
    "MemoryContextBuilder",
    "delete_session_memory_entry",
    "delete_user_memory_entry",
    "get_session_memory_entry",
    "get_user_memory_entry",
    "list_org_memory",
    "list_project_memory",
    "list_session_memory",
    "list_user_memory",
    "search_session_memory",
    "search_user_memory",
    "set_session_memory_entry",
    "set_user_memory_entry",
]
