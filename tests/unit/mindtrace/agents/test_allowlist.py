from __future__ import annotations

import pytest

from mindtrace.agents.allowlist.registry import (
    AllowlistEntry,
    AllowlistViolationError,
    MindtraceAllowlistRegistry,
)


@pytest.fixture
def registry() -> MindtraceAllowlistRegistry:
    return MindtraceAllowlistRegistry(redis_url=None)


@pytest.mark.asyncio
async def test_default_entries_permitted(registry: MindtraceAllowlistRegistry) -> None:
    assert await registry.is_permitted("builtins.NoneType", "deps_type")
    assert await registry.is_permitted("pydantic.BaseModel", "deps_type")


@pytest.mark.asyncio
async def test_unknown_path_not_permitted(registry: MindtraceAllowlistRegistry) -> None:
    assert not await registry.is_permitted("myapp.agents:MyAgent", "agent_class")
    assert not await registry.is_permitted("myapp.deps:MyDeps", "deps_type")


@pytest.mark.asyncio
async def test_enforce_agent_class_raises_for_unknown(registry: MindtraceAllowlistRegistry) -> None:
    with pytest.raises(AllowlistViolationError) as exc_info:
        await registry.enforce_agent_class("evil.code:EvilAgent")
    assert exc_info.value.path == "evil.code:EvilAgent"
    assert exc_info.value.entry_type == "agent_class"


@pytest.mark.asyncio
async def test_enforce_deps_type_raises_for_unknown(registry: MindtraceAllowlistRegistry) -> None:
    with pytest.raises(AllowlistViolationError):
        await registry.enforce_deps_type("myapp.deps:SomeDeps")


@pytest.mark.asyncio
async def test_register_and_permit(registry: MindtraceAllowlistRegistry) -> None:
    entry = AllowlistEntry(
        dotted_path="myapp.agents:GoodAgent",
        entry_type="agent_class",
        registered_by="admin-1",
    )
    await registry.register(entry)
    assert await registry.is_permitted("myapp.agents:GoodAgent", "agent_class")


@pytest.mark.asyncio
async def test_deregister_removes_entry(registry: MindtraceAllowlistRegistry) -> None:
    entry = AllowlistEntry(
        dotted_path="myapp.agents:TempAgent",
        entry_type="agent_class",
        registered_by="admin-1",
    )
    await registry.register(entry)
    assert await registry.is_permitted("myapp.agents:TempAgent", "agent_class")
    await registry.deregister("myapp.agents:TempAgent", "agent_class")
    assert not await registry.is_permitted("myapp.agents:TempAgent", "agent_class")


@pytest.mark.asyncio
async def test_list_entries_returns_all(registry: MindtraceAllowlistRegistry) -> None:
    entries = await registry.list_entries()
    paths = {e.dotted_path for e in entries}
    assert "builtins.NoneType" in paths
    assert "pydantic.BaseModel" in paths


@pytest.mark.asyncio
async def test_list_entries_filtered_by_type(registry: MindtraceAllowlistRegistry) -> None:
    await registry.register(AllowlistEntry(
        dotted_path="myapp.agents:FilterAgent",
        entry_type="agent_class",
        registered_by="admin",
    ))
    agent_entries = await registry.list_entries(entry_type="agent_class")
    assert all(e.entry_type == "agent_class" for e in agent_entries)

    deps_entries = await registry.list_entries(entry_type="deps_type")
    assert all(e.entry_type == "deps_type" for e in deps_entries)


@pytest.mark.asyncio
async def test_register_is_idempotent(registry: MindtraceAllowlistRegistry) -> None:
    entry = AllowlistEntry(
        dotted_path="myapp.agents:IdempotentAgent",
        entry_type="agent_class",
        registered_by="admin",
    )
    await registry.register(entry)
    await registry.register(entry)
    entries = await registry.list_entries(entry_type="agent_class")
    paths = [e.dotted_path for e in entries if e.dotted_path == "myapp.agents:IdempotentAgent"]
    assert len(paths) == 1


@pytest.mark.asyncio
async def test_enforce_passes_for_registered(registry: MindtraceAllowlistRegistry) -> None:
    await registry.register(AllowlistEntry(
        dotted_path="myapp.agents:SafeAgent",
        entry_type="agent_class",
        registered_by="admin",
    ))
    await registry.enforce_agent_class("myapp.agents:SafeAgent")  # should not raise


@pytest.mark.asyncio
async def test_enforce_deps_passes_for_defaults(registry: MindtraceAllowlistRegistry) -> None:
    await registry.enforce_deps_type("builtins.NoneType")  # should not raise
    await registry.enforce_deps_type("pydantic.BaseModel")  # should not raise
