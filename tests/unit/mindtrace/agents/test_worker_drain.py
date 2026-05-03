"""Unit tests for MindtraceAgentWorker graceful drain / stop."""
from __future__ import annotations

import asyncio
import sys
import time
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure redis stub is available before importing worker
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

from mindtrace.agents.distributed.worker import MindtraceAgentWorker


def _make_worker(max_concurrent: int = 2) -> MindtraceAgentWorker:
    registry = MagicMock()
    task_queue = MagicMock()
    return MindtraceAgentWorker(
        agent_registry=registry,
        task_queue=task_queue,
        redis_pubsub_url=None,
        max_concurrent_agents=max_concurrent,
        worker_id="test-worker",
    )


@pytest.mark.asyncio
async def test_stop_returns_when_no_in_flight():
    """stop() should return quickly when no tasks are in flight."""
    worker = _make_worker(max_concurrent=2)
    # No tasks acquired the semaphore — _value == max_concurrent_agents
    start = asyncio.get_event_loop().time()
    await worker.stop(drain_timeout=5.0)
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed < 1.0, f"stop() took too long: {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_stop_drain_timeout_respected():
    """stop() should respect drain_timeout and return even if semaphore is held."""
    worker = _make_worker(max_concurrent=2)
    # Simulate an in-flight task by acquiring the semaphore without releasing it
    await worker._semaphore.acquire()

    start = asyncio.get_event_loop().time()
    await worker.stop(drain_timeout=0.1)
    elapsed = asyncio.get_event_loop().time() - start

    # Should have returned after ~drain_timeout, not hang
    assert elapsed >= 0.05, "stop() returned too quickly (drain timeout not respected)"
    assert elapsed < 2.0, f"stop() hung too long: {elapsed:.2f}s"
