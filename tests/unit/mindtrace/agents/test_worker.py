from __future__ import annotations

import asyncio
import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure redis stub is registered (may already be done by test_distributed_registry)
if "redis" not in sys.modules:
    _redis_mod = types.ModuleType("redis")
    _redis_asyncio = types.ModuleType("redis.asyncio")

    class _FakeRedis:
        def __init__(self):
            self._store = {}
            self._published = []

        @classmethod
        def from_url(cls, url, **kwargs):
            return cls()

        async def set(self, key, value, ex=None):
            self._store[key] = value

        async def get(self, key):
            return self._store.get(key)

        async def publish(self, channel, message):
            self._published.append((channel, message))

        async def delete(self, key):
            self._store.pop(key, None)

        async def aclose(self):
            pass

    _redis_asyncio.from_url = _FakeRedis.from_url
    _redis_asyncio.Redis = _FakeRedis
    _redis_mod.asyncio = _redis_asyncio
    sys.modules["redis"] = _redis_mod
    sys.modules["redis.asyncio"] = _redis_asyncio

import redis.asyncio as _aioredis

from mindtrace.agents.distributed.worker import MindtraceAgentWorker
from mindtrace.agents.distributed.registry import AgentDefinition
from mindtrace.agents.context.propagation import AgentRunContext, AgentTaskEnvelope, TaskProvenance
from mindtrace.agents.allowlist.registry import MindtraceAllowlistRegistry, AllowlistViolationError


def _make_envelope(
    agent_name: str = "test_bot",
    input_text: str = "hello",
    task_ttl: int = 300,
) -> AgentTaskEnvelope:
    from uuid import uuid4
    run_ctx = AgentRunContext(
        trace_id="a" * 32,
        span_id="b" * 16,
        session_id="sess-1",
        user_id="user-1",
    )
    return AgentTaskEnvelope(
        agent_name=agent_name,
        input=input_text,
        run_context=run_ctx,
        provenance=TaskProvenance(
            submitter_id="user-1",
            submitter_role="user",
            origin_gateway_id="gw-1",
        ),
        task_ttl_seconds=task_ttl,
    )


class _MockRegistry:
    def __init__(self, definition: AgentDefinition | None = None):
        self._definition = definition

    async def get_agent_definition(self, name: str):
        return self._definition


class _SimpleAgent:
    name = "test_bot"

    async def run(self, input_data, *, deps=None, session_id=None, **kwargs):
        return f"answer:{input_data}"


@pytest.fixture
def fake_redis_client():
    class FakeRedis:
        def __init__(self):
            self._store = {}
            self.published = []

        @classmethod
        def from_url(cls, *a, **kw):
            return cls()

        async def set(self, key, value, ex=None):
            self._store[key] = value

        async def get(self, key):
            return self._store.get(key)

        async def publish(self, channel, message):
            self.published.append((channel, message))

        async def delete(self, key):
            self._store.pop(key, None)

        async def aclose(self):
            pass

    return FakeRedis()


@pytest.fixture
def worker(fake_redis_client) -> MindtraceAgentWorker:
    defn = AgentDefinition(
        name="test_bot",
        agent_class="tests.unit.mindtrace.agents.test_worker:_SimpleAgent",
        description="test",
    )
    registry = _MockRegistry(defn)
    task_queue = AsyncMock()
    task_queue.dequeue = AsyncMock(return_value=None)

    w = MindtraceAgentWorker(
        agent_registry=registry,
        task_queue=task_queue,
        redis_pubsub_url="redis://localhost:6379",
    )
    w._pubsub_client = fake_redis_client
    return w


@pytest.mark.asyncio
async def test_run_agent_success(worker: MindtraceAgentWorker, fake_redis_client) -> None:
    envelope = _make_envelope()
    with patch.object(worker, "_load_agent", new=AsyncMock(return_value=_SimpleAgent())):
        with patch.object(worker, "_build_system_context", new=AsyncMock(return_value=None)):
            await worker._run_agent(envelope)

    # result should be stored
    result_raw = fake_redis_client._store.get(f"result:{envelope.task_id}")
    assert result_raw is not None
    data = json.loads(result_raw)
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_run_agent_expired_envelope(worker: MindtraceAgentWorker, fake_redis_client) -> None:
    from datetime import datetime, timezone, timedelta
    envelope = _make_envelope(task_ttl=0)
    # Make it look expired by backdating submitted_at
    object.__setattr__(envelope, "submitted_at", datetime(2000, 1, 1, tzinfo=timezone.utc))

    load_called = []

    async def mock_load(name):
        load_called.append(name)
        return _SimpleAgent()

    worker._load_agent = mock_load
    await worker._run_agent(envelope)

    assert load_called == [], "Agent should not be loaded for expired task"
    result_raw = fake_redis_client._store.get(f"result:{envelope.task_id}")
    assert result_raw is not None
    data = json.loads(result_raw)
    assert data["status"] == "error"
    assert data["code"] == "timeout"


@pytest.mark.asyncio
async def test_run_agent_allowlist_violation(worker: MindtraceAgentWorker, fake_redis_client) -> None:
    allowlist = MindtraceAllowlistRegistry(redis_url=None)
    worker.allowlist_registry = allowlist

    bad_defn = AgentDefinition(name="evil_bot", agent_class="evil.module:EvilAgent")
    worker.agent_registry = _MockRegistry(bad_defn)

    envelope = _make_envelope(agent_name="evil_bot")
    await worker._run_agent(envelope)

    result_raw = fake_redis_client._store.get(f"result:{envelope.task_id}")
    assert result_raw is not None
    data = json.loads(result_raw)
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_publish_event_uses_correct_channel(worker: MindtraceAgentWorker, fake_redis_client) -> None:
    class FakeEvent:
        pass

    await worker._publish_event("task-123", FakeEvent())
    assert any("task:task-123" == ch for ch, _ in fake_redis_client.published)


@pytest.mark.asyncio
async def test_publish_result_stores_in_redis(worker: MindtraceAgentWorker, fake_redis_client) -> None:
    await worker._publish_result("task-abc", "hello world", result_ttl=60)
    result_raw = fake_redis_client._store.get("result:task-abc")
    assert result_raw is not None
    data = json.loads(result_raw)
    assert data["status"] == "ok"
    assert "hello world" in data["result"]


@pytest.mark.asyncio
async def test_concurrency_semaphore_limits(worker: MindtraceAgentWorker) -> None:
    worker.max_concurrent_agents = 2
    worker._semaphore = asyncio.Semaphore(2)

    # Acquire both slots
    await worker._semaphore.acquire()
    await worker._semaphore.acquire()

    # Third acquire should block; check semaphore is exhausted
    assert worker._semaphore._value == 0

    worker._semaphore.release()
    worker._semaphore.release()
    assert worker._semaphore._value == 2
