from __future__ import annotations

import pytest

from mindtrace.agents.distributed.memory_api import MemoryContextBuilder
from mindtrace.agents.memory.in_memory import InMemoryStore


@pytest.fixture
def empty_builder() -> MemoryContextBuilder:
    return MemoryContextBuilder()


@pytest.fixture
def store_with_inject() -> InMemoryStore:
    store = InMemoryStore(namespace="user:u1")
    return store


@pytest.mark.asyncio
async def test_empty_builder_returns_none(empty_builder: MemoryContextBuilder) -> None:
    result = await empty_builder.build()
    assert result is None


@pytest.mark.asyncio
async def test_builder_no_inject_entries_returns_none() -> None:
    store = InMemoryStore(namespace="user:u1")
    await store.save("key1", "value1", metadata={"inject": False})
    await store.save("key2", "value2", metadata={})

    builder = MemoryContextBuilder(user_store=store)
    result = await builder.build()
    assert result is None


@pytest.mark.asyncio
async def test_builder_with_inject_entries_returns_string() -> None:
    store = InMemoryStore(namespace="user:u1")
    await store.save("home_city", "Amsterdam", metadata={"inject": True})
    await store.save("language", "Dutch", metadata={"inject": True})
    await store.save("not_injected", "hidden", metadata={"inject": False})

    builder = MemoryContextBuilder(user_store=store)
    result = await builder.build()
    assert result is not None
    assert "Amsterdam" in result
    assert "Dutch" in result
    assert "hidden" not in result


@pytest.mark.asyncio
async def test_builder_multiple_stores() -> None:
    user_store = InMemoryStore(namespace="user:u1")
    await user_store.save("pref", "dark_mode", metadata={"inject": True})

    project_store = InMemoryStore(namespace="project:p1")
    await project_store.save("camera_model", "Basler-A1", metadata={"inject": True})

    builder = MemoryContextBuilder(user_store=user_store, project_store=project_store)
    result = await builder.build()
    assert result is not None
    assert "dark_mode" in result
    assert "Basler-A1" in result


@pytest.mark.asyncio
async def test_builder_context_capped_at_max_tokens() -> None:
    store = InMemoryStore(namespace="user:u1")
    for i in range(100):
        await store.save(f"key{i}", "x" * 100, metadata={"inject": True})

    builder = MemoryContextBuilder(user_store=store, max_tokens=10)
    result = await builder.build()
    # With max_tokens=10, max_chars=40 — very small budget
    assert result is None or len(result) <= 200  # should be very short or None


@pytest.mark.asyncio
async def test_builder_sections_labeled() -> None:
    user_store = InMemoryStore(namespace="user:u1")
    await user_store.save("pref", "light", metadata={"inject": True})

    org_store = InMemoryStore(namespace="org:o1")
    await org_store.save("policy", "no PII", metadata={"inject": True})

    builder = MemoryContextBuilder(user_store=user_store, org_store=org_store)
    result = await builder.build()
    assert result is not None
    assert "User context" in result
    assert "Organisation context" in result
