"""Unit tests for mindtrace.agents.memory."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from mindtrace.agents._run_context import RunContext
from mindtrace.agents.memory import (
    InMemoryStore,
    JsonFileStore,
    MemoryEntry,
    MemoryToolset,
)


def _ctx() -> RunContext:
    return RunContext(deps=None)


# ---------------------------------------------------------------------------
# MemoryEntry
# ---------------------------------------------------------------------------


class TestMemoryEntry:
    """Tests for the MemoryEntry dataclass."""

    def test_fields_stored(self):
        """MemoryEntry stores key, value, and metadata."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        entry = MemoryEntry(key="k", value="v", metadata={"tag": "x"}, created_at=now, updated_at=now)
        assert entry.key == "k"
        assert entry.value == "v"
        assert entry.metadata == {"tag": "x"}

    def test_default_metadata_is_empty_dict(self):
        """metadata defaults to an empty dict."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        entry = MemoryEntry(key="k", value="v", created_at=now, updated_at=now)
        assert entry.metadata == {}


# ---------------------------------------------------------------------------
# InMemoryStore
# ---------------------------------------------------------------------------


class TestInMemoryStore:
    """Tests for InMemoryStore."""

    async def test_save_and_get(self):
        """save() stores a value; get() retrieves it."""
        store = InMemoryStore()
        await store.save("fact1", "The sky is blue")
        entry = await store.get("fact1")
        assert entry is not None
        assert entry.value == "The sky is blue"
        assert entry.key == "fact1"

    async def test_get_missing_key_returns_none(self):
        """get() returns None for a key that was never saved."""
        store = InMemoryStore()
        assert await store.get("missing") is None

    async def test_save_overwrites_value(self):
        """Saving to an existing key updates the value."""
        store = InMemoryStore()
        await store.save("k", "old")
        await store.save("k", "new")
        entry = await store.get("k")
        assert entry.value == "new"

    async def test_save_preserves_created_at_on_update(self):
        """created_at is not changed when an existing key is updated."""
        store = InMemoryStore()
        await store.save("k", "v1")
        original = await store.get("k")
        await store.save("k", "v2")
        updated = await store.get("k")
        assert updated.created_at == original.created_at

    async def test_updated_at_changes_on_update(self):
        """updated_at is refreshed when an existing key is saved again."""
        import asyncio

        store = InMemoryStore()
        await store.save("k", "v1")
        original = await store.get("k")
        await asyncio.sleep(0.01)
        await store.save("k", "v2")
        updated = await store.get("k")
        assert updated.updated_at >= original.updated_at

    async def test_delete_removes_entry(self):
        """delete() removes the key so subsequent get() returns None."""
        store = InMemoryStore()
        await store.save("k", "v")
        await store.delete("k")
        assert await store.get("k") is None

    async def test_delete_nonexistent_key_is_noop(self):
        """delete() on a missing key does not raise."""
        store = InMemoryStore()
        await store.delete("ghost")  # should not raise

    async def test_list_keys(self):
        """list_keys() returns all saved keys."""
        store = InMemoryStore()
        await store.save("a", "1")
        await store.save("b", "2")
        keys = await store.list_keys()
        assert set(keys) == {"a", "b"}

    async def test_list_keys_empty(self):
        """list_keys() returns empty list when no entries saved."""
        store = InMemoryStore()
        assert await store.list_keys() == []

    async def test_search_matches_value(self):
        """search() returns entries whose value contains the query."""
        store = InMemoryStore()
        await store.save("fact1", "Python is a programming language")
        await store.save("fact2", "The ocean is blue")
        results = await store.search("programming")
        assert len(results) == 1
        assert results[0].key == "fact1"

    async def test_search_matches_key(self):
        """search() also matches against the key string."""
        store = InMemoryStore()
        await store.save("python_fact", "Some value")
        results = await store.search("python")
        assert len(results) == 1

    async def test_search_is_case_insensitive(self):
        """search() matches regardless of case."""
        store = InMemoryStore()
        await store.save("k", "Hello World")
        results = await store.search("hello")
        assert len(results) == 1

    async def test_search_top_k_limits_results(self):
        """search() returns at most top_k results."""
        store = InMemoryStore()
        for i in range(10):
            await store.save(f"key_{i}", "common term")
        results = await store.search("common", top_k=3)
        assert len(results) <= 3

    async def test_search_no_matches_returns_empty(self):
        """search() returns empty list when no entries match."""
        store = InMemoryStore()
        await store.save("k", "unrelated")
        results = await store.search("xyzzy")
        assert results == []

    async def test_save_with_metadata(self):
        """save() stores metadata alongside the value."""
        store = InMemoryStore()
        await store.save("k", "v", metadata={"source": "web"})
        entry = await store.get("k")
        assert entry.metadata == {"source": "web"}


# ---------------------------------------------------------------------------
# JsonFileStore
# ---------------------------------------------------------------------------


class TestJsonFileStore:
    """Tests for JsonFileStore."""

    def _tmp_path(self) -> Path:
        return Path(tempfile.mktemp(suffix=".json"))

    async def test_save_and_get(self):
        """save() writes to disk; get() reads it back."""
        path = self._tmp_path()
        store = JsonFileStore(path)
        await store.save("k", "persisted value")
        entry = await store.get("k")
        assert entry is not None
        assert entry.value == "persisted value"

    async def test_persists_across_instances(self):
        """Data saved by one instance is readable by a fresh instance."""
        path = self._tmp_path()
        store1 = JsonFileStore(path)
        await store1.save("key", "hello")

        store2 = JsonFileStore(path)
        entry = await store2.get("key")
        assert entry is not None
        assert entry.value == "hello"

    async def test_file_is_valid_json(self):
        """The written file is valid JSON."""
        path = self._tmp_path()
        store = JsonFileStore(path)
        await store.save("k", "v")
        data = json.loads(path.read_text())
        assert "k" in data

    async def test_delete_removes_from_file(self):
        """delete() removes entry and flushes to disk."""
        path = self._tmp_path()
        store = JsonFileStore(path)
        await store.save("k", "v")
        await store.delete("k")
        store2 = JsonFileStore(path)
        assert await store2.get("k") is None

    async def test_get_missing_returns_none(self):
        """get() returns None for a key not in the file."""
        path = self._tmp_path()
        store = JsonFileStore(path)
        assert await store.get("missing") is None

    async def test_list_keys(self):
        """list_keys() returns all saved keys."""
        path = self._tmp_path()
        store = JsonFileStore(path)
        await store.save("a", "1")
        await store.save("b", "2")
        keys = await store.list_keys()
        assert set(keys) == {"a", "b"}

    async def test_search_substring(self):
        """search() performs substring match across entries."""
        path = self._tmp_path()
        store = JsonFileStore(path)
        await store.save("note1", "async programming tips")
        await store.save("note2", "sync vs async")
        await store.save("note3", "database indexing")
        results = await store.search("async")
        assert len(results) == 2

    async def test_nonexistent_file_starts_empty(self):
        """A store pointed at a non-existent file starts with no entries."""
        path = Path(tempfile.mktemp(suffix=".json"))
        store = JsonFileStore(path)
        assert await store.list_keys() == []


# ---------------------------------------------------------------------------
# MemoryToolset
# ---------------------------------------------------------------------------


class TestMemoryToolset:
    """Tests for MemoryToolset — memory operations exposed as agent tools."""

    async def _get_tool_names(self, toolset: MemoryToolset) -> set[str]:
        tools = await toolset.get_tools(_ctx())
        return set(tools.keys())

    async def test_exposes_five_tools(self):
        """MemoryToolset exposes exactly the five memory tools."""
        ts = MemoryToolset(InMemoryStore())
        names = await self._get_tool_names(ts)
        assert names == {"save_memory", "recall_memory", "search_memory", "forget_memory", "list_memories"}

    async def test_save_and_recall(self):
        """save_memory stores a value; recall_memory retrieves it."""
        store = InMemoryStore()
        ts = MemoryToolset(store)
        ctx = _ctx()
        tools = await ts.get_tools(ctx)

        await ts.call_tool("save_memory", {"key": "city", "value": "Paris"}, ctx, tools["save_memory"])
        result = await ts.call_tool("recall_memory", {"key": "city"}, ctx, tools["recall_memory"])
        assert result == "Paris"

    async def test_recall_missing_key(self):
        """recall_memory returns a not-found message for an unknown key."""
        ts = MemoryToolset(InMemoryStore())
        ctx = _ctx()
        tools = await ts.get_tools(ctx)
        result = await ts.call_tool("recall_memory", {"key": "ghost"}, ctx, tools["recall_memory"])
        assert "ghost" in result

    async def test_forget_removes_entry(self):
        """forget_memory deletes an entry so subsequent recall returns not-found."""
        store = InMemoryStore()
        ts = MemoryToolset(store)
        ctx = _ctx()
        tools = await ts.get_tools(ctx)

        await ts.call_tool("save_memory", {"key": "temp", "value": "data"}, ctx, tools["save_memory"])
        await ts.call_tool("forget_memory", {"key": "temp"}, ctx, tools["forget_memory"])
        result = await ts.call_tool("recall_memory", {"key": "temp"}, ctx, tools["recall_memory"])
        assert "temp" in result  # not-found message

    async def test_list_memories(self):
        """list_memories returns all saved keys (without namespace prefix)."""
        store = InMemoryStore()
        ts = MemoryToolset(store, namespace="ns")
        ctx = _ctx()
        tools = await ts.get_tools(ctx)

        await ts.call_tool("save_memory", {"key": "a", "value": "1"}, ctx, tools["save_memory"])
        await ts.call_tool("save_memory", {"key": "b", "value": "2"}, ctx, tools["save_memory"])
        result = await ts.call_tool("list_memories", {}, ctx, tools["list_memories"])
        assert "a" in result
        assert "b" in result

    async def test_list_memories_empty(self):
        """list_memories returns a message when no memories are stored."""
        ts = MemoryToolset(InMemoryStore())
        ctx = _ctx()
        tools = await ts.get_tools(ctx)
        result = await ts.call_tool("list_memories", {}, ctx, tools["list_memories"])
        assert result  # non-empty message

    async def test_search_memory(self):
        """search_memory returns matching entries."""
        store = InMemoryStore()
        ts = MemoryToolset(store)
        ctx = _ctx()
        tools = await ts.get_tools(ctx)

        await ts.call_tool("save_memory", {"key": "fact1", "value": "Python is fast"}, ctx, tools["save_memory"])
        await ts.call_tool("save_memory", {"key": "fact2", "value": "Go is compiled"}, ctx, tools["save_memory"])
        result = await ts.call_tool("search_memory", {"query": "Python"}, ctx, tools["search_memory"])
        assert "Python" in result
        assert "Go" not in result

    async def test_namespace_isolates_entries(self):
        """Two MemoryToolsets with different namespaces do not share entries."""
        store = InMemoryStore()
        ts_a = MemoryToolset(store, namespace="user_a")
        ts_b = MemoryToolset(store, namespace="user_b")

        ctx = _ctx()
        tools_a = await ts_a.get_tools(ctx)
        tools_b = await ts_b.get_tools(ctx)

        await ts_a.call_tool("save_memory", {"key": "secret", "value": "a_data"}, ctx, tools_a["save_memory"])

        result = await ts_b.call_tool("recall_memory", {"key": "secret"}, ctx, tools_b["recall_memory"])
        assert "a_data" not in result  # not visible in namespace b

    async def test_namespace_prefix_not_visible_in_list(self):
        """list_memories returns keys without the internal namespace prefix."""
        store = InMemoryStore()
        ts = MemoryToolset(store, namespace="myns")
        ctx = _ctx()
        tools = await ts.get_tools(ctx)

        await ts.call_tool("save_memory", {"key": "mykey", "value": "v"}, ctx, tools["save_memory"])
        result = await ts.call_tool("list_memories", {}, ctx, tools["list_memories"])
        assert "myns:" not in result
        assert "mykey" in result
