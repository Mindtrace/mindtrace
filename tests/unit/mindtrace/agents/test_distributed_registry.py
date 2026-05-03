from __future__ import annotations

import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Stub redis before importing the registry module
_redis_mod = types.ModuleType("redis")
_redis_asyncio = types.ModuleType("redis.asyncio")


class _FakeRedis:
    def __init__(self):
        self._store = {}

    @classmethod
    def from_url(cls, url, **kwargs):
        return cls()

    async def set(self, key, value, ex=None):
        self._store[key] = value

    async def get(self, key):
        return self._store.get(key)

    async def delete(self, key):
        self._store.pop(key, None)

    async def scan_iter(self, pattern):
        prefix = pattern.rstrip("*")
        for k in list(self._store.keys()):
            if k.startswith(prefix):
                yield k

    async def hexists(self, key, field):
        return False

    async def aclose(self):
        pass


_redis_asyncio.from_url = _FakeRedis.from_url
_redis_asyncio.Redis = _FakeRedis
_redis_mod.asyncio = _redis_asyncio
sys.modules.setdefault("redis", _redis_mod)
sys.modules.setdefault("redis.asyncio", _redis_asyncio)

from mindtrace.agents.distributed.registry import AgentDefinition, MindtraceAgentRegistry


@pytest.fixture
def fake_redis() -> _FakeRedis:
    return _FakeRedis()


@pytest.fixture
def registry(fake_redis: _FakeRedis) -> MindtraceAgentRegistry:
    reg = MindtraceAgentRegistry(redis_url="redis://localhost:6379")
    reg._client = fake_redis
    return reg


def _make_definition(**kwargs) -> AgentDefinition:
    return AgentDefinition(
        name=kwargs.get("name", "travel_assistant"),
        description=kwargs.get("description", "A travel agent"),
        agent_class=kwargs.get("agent_class", "myapp.agents:TravelAssistant"),
        org_id=kwargs.get("org_id", None),
        project_id=kwargs.get("project_id", None),
    )


@pytest.mark.asyncio
async def test_register_and_get_agent(registry: MindtraceAgentRegistry) -> None:
    defn = _make_definition()
    await registry.register_agent(defn)
    retrieved = await registry.get_agent_definition("travel_assistant")
    assert retrieved is not None
    assert retrieved.name == "travel_assistant"
    assert retrieved.agent_class == "myapp.agents:TravelAssistant"


@pytest.mark.asyncio
async def test_get_agent_returns_none_for_missing(registry: MindtraceAgentRegistry) -> None:
    result = await registry.get_agent_definition("nonexistent_agent")
    assert result is None


@pytest.mark.asyncio
async def test_list_agents_returns_all(registry: MindtraceAgentRegistry) -> None:
    await registry.register_agent(_make_definition(name="agent_a"))
    await registry.register_agent(_make_definition(name="agent_b"))
    agents = await registry.list_agents()
    names = {a.name for a in agents}
    assert "agent_a" in names
    assert "agent_b" in names


@pytest.mark.asyncio
async def test_list_agents_filter_by_org(registry: MindtraceAgentRegistry) -> None:
    await registry.register_agent(_make_definition(name="org_agent", org_id="org-1"))
    await registry.register_agent(_make_definition(name="other_agent", org_id="org-2"))
    results = await registry.list_agents(org_id="org-1")
    names = [a.name for a in results]
    assert "org_agent" in names
    # other_agent has org_id="org-2" which doesn't match
    assert "other_agent" not in names


@pytest.mark.asyncio
async def test_list_agents_filter_by_project(registry: MindtraceAgentRegistry) -> None:
    await registry.register_agent(_make_definition(name="proj_agent", project_id="proj-1"))
    await registry.register_agent(_make_definition(name="global_agent", project_id=None))
    results = await registry.list_agents(project_id="proj-1")
    names = [a.name for a in results]
    assert "proj_agent" in names


@pytest.mark.asyncio
async def test_register_worker_and_find(registry: MindtraceAgentRegistry) -> None:
    await registry.register_worker(
        worker_id="w1",
        agent_names=["travel_assistant"],
        url="http://worker:8001",
        node_id="n1",
    )
    workers = await registry.find_workers("travel_assistant")
    assert len(workers) == 1
    assert workers[0].worker_id == "w1"
    assert "travel_assistant" in workers[0].agent_names


@pytest.mark.asyncio
async def test_find_workers_empty_for_unregistered(registry: MindtraceAgentRegistry) -> None:
    workers = await registry.find_workers("ghost_agent")
    assert workers == []


@pytest.mark.asyncio
async def test_heartbeat_does_not_raise(registry: MindtraceAgentRegistry) -> None:
    await registry.register_worker("w2", ["bot"], "http://w:9000", "n1")
    await registry.heartbeat("w2")


@pytest.mark.asyncio
async def test_deregister_worker(registry: MindtraceAgentRegistry) -> None:
    await registry.register_worker("w3", ["bot"], "http://w:9001", "n1")
    await registry.deregister_worker("w3")
    workers = await registry.find_workers("bot")
    assert not any(w.worker_id == "w3" for w in workers)


@pytest.mark.asyncio
async def test_register_agent_with_allowlist_violation() -> None:
    from mindtrace.agents.allowlist.registry import MindtraceAllowlistRegistry, AllowlistViolationError

    allowlist = MindtraceAllowlistRegistry(redis_url=None)
    fake_redis = _FakeRedis()
    reg = MindtraceAgentRegistry(
        redis_url="redis://localhost:6379",
        allowlist_registry=allowlist,
    )
    reg._client = fake_redis

    defn = _make_definition(agent_class="evil.module:EvilAgent")
    with pytest.raises(AllowlistViolationError):
        await reg.register_agent(defn)


@pytest.mark.asyncio
async def test_register_agent_with_allowlist_passes() -> None:
    from mindtrace.agents.allowlist.registry import AllowlistEntry, MindtraceAllowlistRegistry

    allowlist = MindtraceAllowlistRegistry(redis_url=None)
    await allowlist.register(AllowlistEntry(
        dotted_path="myapp.agents:TravelAssistant",
        entry_type="agent_class",
        registered_by="admin",
    ))

    fake_redis = _FakeRedis()
    reg = MindtraceAgentRegistry(
        redis_url="redis://localhost:6379",
        allowlist_registry=allowlist,
    )
    reg._client = fake_redis

    defn = _make_definition(agent_class="myapp.agents:TravelAssistant")
    await reg.register_agent(defn)  # should not raise
    retrieved = await reg.get_agent_definition("travel_assistant")
    assert retrieved is not None
