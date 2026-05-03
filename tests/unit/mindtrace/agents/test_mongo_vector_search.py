from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Stub motor so MongoMemoryStore can be imported without MongoDB ────────

_motor_mod = types.ModuleType("motor")
_motor_asyncio = types.ModuleType("motor.motor_asyncio")


class _FakeMotorClient:
    def __init__(self, url: str) -> None:
        self._url = url
        self._db: dict = {}

    def __getitem__(self, name: str):
        if name not in self._db:
            self._db[name] = _FakeDatabase()
        return self._db[name]


class _FakeDatabase:
    def __init__(self) -> None:
        self._cols: dict = {}

    def __getitem__(self, name: str):
        if name not in self._cols:
            self._cols[name] = _FakeCollection()
        return self._cols[name]


class _FakeCollection:
    def __init__(self) -> None:
        self.update_one = AsyncMock()
        self.find_one = AsyncMock(return_value=None)
        self.delete_one = AsyncMock()

    def find(self, *args, **kwargs):
        return _FakeCursor([])

    def aggregate(self, pipeline):
        return _FakeCursor([])


class _FakeCursor:
    def __init__(self, docs):
        self._docs = iter(docs)

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._docs)
        except StopIteration:
            raise StopAsyncIteration


_motor_asyncio.AsyncIOMotorClient = _FakeMotorClient
_motor_mod.motor_asyncio = _motor_asyncio
sys.modules.setdefault("motor", _motor_mod)
sys.modules.setdefault("motor.motor_asyncio", _motor_asyncio)

from mindtrace.agents.memory.mongo import MongoMemoryStore


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_store(embedding_provider=None) -> tuple[MongoMemoryStore, _FakeCollection]:
    store = MongoMemoryStore(
        mongo_url="mongodb://localhost:27017",
        database="testdb",
        collection="testcol",
        namespace="test_ns",
        embedding_provider=embedding_provider,
        vector_index_name="vector_index",
    )
    col = _FakeCollection()
    store._get_collection = lambda: col  # type: ignore[method-assign]
    return store, col


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_stores_embedding_when_provider_set() -> None:
    mock_provider = MagicMock()
    mock_provider.embed = AsyncMock(return_value=[0.1, 0.2])

    store, col = _make_store(embedding_provider=mock_provider)
    await store.save("key1", "hello world")

    mock_provider.embed.assert_awaited_once_with("hello world")
    call_args = col.update_one.call_args
    set_doc = call_args[0][1]["$set"]
    assert "embedding" in set_doc
    assert set_doc["embedding"] == [0.1, 0.2]


@pytest.mark.asyncio
async def test_search_uses_vector_pipeline_when_provider_set() -> None:
    mock_provider = MagicMock()
    mock_provider.embed = AsyncMock(return_value=[0.3, 0.4])

    store, col = _make_store(embedding_provider=mock_provider)
    col.aggregate = MagicMock(return_value=_FakeCursor([]))

    results = await store.search("find something", top_k=3)

    mock_provider.embed.assert_awaited_once_with("find something")
    col.aggregate.assert_called_once()
    pipeline = col.aggregate.call_args[0][0]
    assert len(pipeline) == 1
    assert "$vectorSearch" in pipeline[0]
    vs = pipeline[0]["$vectorSearch"]
    assert vs["queryVector"] == [0.3, 0.4]
    assert vs["limit"] == 3
    assert vs["numCandidates"] == 30


@pytest.mark.asyncio
async def test_search_falls_back_to_text_when_no_provider() -> None:
    store, col = _make_store(embedding_provider=None)

    find_cursor = _FakeCursor([])
    col.find = MagicMock(return_value=find_cursor)
    col.aggregate = MagicMock(return_value=_FakeCursor([]))

    results = await store.search("some query", top_k=5)

    col.find.assert_called_once()
    col.aggregate.assert_not_called()
    assert results == []
