"""Unit tests for StreamsRelay using a stubbed redis.asyncio."""
from __future__ import annotations

import sys
import types
import json as _json
import pytest


# ---------------------------------------------------------------------------
# Stub redis.asyncio with xadd / xread / expire support
# ---------------------------------------------------------------------------

class _FakeRedisStreams:
    """Minimal in-memory stub for Redis Streams (xadd, xread, expire)."""

    def __init__(self):
        self._streams: dict[str, list[tuple[str, dict]]] = {}
        self._counter: dict[str, int] = {}

    @classmethod
    def from_url(cls, url, **kwargs):
        return cls()

    async def xadd(self, key: str, fields: dict) -> str:
        if key not in self._streams:
            self._streams[key] = []
            self._counter[key] = 0
        self._counter[key] += 1
        entry_id = f"1000000000000-{self._counter[key]}"
        self._streams[key].append((entry_id, dict(fields)))
        return entry_id

    async def xread(self, streams: dict, count: int = 100, block: int = 0) -> list:
        results = []
        for key, last_id in streams.items():
            entries = self._streams.get(key, [])
            filtered = []
            for eid, data in entries:
                if last_id == "0" or _id_gt(eid, last_id):
                    filtered.append((eid, dict(data)))
            if filtered:
                results.append((key, filtered))
        return results

    async def expire(self, key: str, ttl: int) -> None:
        pass  # no-op in stub

    async def aclose(self) -> None:
        pass


def _id_gt(a: str, b: str) -> bool:
    """Compare Redis stream entry IDs like '1000000000000-2' > '1000000000000-1'."""
    try:
        a_ms, a_seq = a.split("-")
        b_ms, b_seq = b.split("-")
        return (int(a_ms), int(a_seq)) > (int(b_ms), int(b_seq))
    except Exception:
        return a > b


def _install_stub():
    if "redis" not in sys.modules:
        _redis_mod = types.ModuleType("redis")
        _redis_asyncio = types.ModuleType("redis.asyncio")
        _redis_asyncio.from_url = _FakeRedisStreams.from_url
        _redis_asyncio.Redis = _FakeRedisStreams
        _redis_mod.asyncio = _redis_asyncio
        sys.modules["redis"] = _redis_mod
        sys.modules["redis.asyncio"] = _redis_asyncio
    else:
        # Patch the existing stub to add xadd/xread if not present
        existing = sys.modules["redis.asyncio"]
        existing.from_url = _FakeRedisStreams.from_url
        existing.Redis = _FakeRedisStreams


_install_stub()

# Patch the from_url inside StreamsRelay's module after import
from mindtrace.agents.distributed.streams import StreamsRelay
import mindtrace.agents.distributed.streams as _streams_module


@pytest.fixture(autouse=True)
def patch_redis(monkeypatch):
    """Ensure StreamsRelay uses our stub."""
    fake_mod = types.ModuleType("redis.asyncio")
    fake_mod.from_url = _FakeRedisStreams.from_url
    fake_mod.Redis = _FakeRedisStreams

    import redis
    monkeypatch.setattr(redis, "asyncio", fake_mod)
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_mod)


@pytest.fixture
def relay():
    r = StreamsRelay(redis_url="redis://localhost:6379")
    r._client = _FakeRedisStreams()
    return r


@pytest.mark.asyncio
async def test_publish_returns_entry_id(relay):
    entry_id = await relay.publish("task_1", {"event": "start"})
    assert entry_id and isinstance(entry_id, str)
    assert len(entry_id) > 0


@pytest.mark.asyncio
async def test_read_from_returns_published_events(relay):
    await relay.publish("task_2", {"event": "a"})
    await relay.publish("task_2", {"event": "b"})
    results = await relay.read_from("task_2", last_event_id="0", block_ms=0)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_read_from_last_id_skips_earlier(relay):
    id_a = await relay.publish("task_3", {"event": "A"})
    await relay.publish("task_3", {"event": "B"})
    results = await relay.read_from("task_3", last_event_id=id_a, block_ms=0)
    assert len(results) == 1
    _, data = results[0]
    assert data.get("event") == "B"


@pytest.mark.asyncio
async def test_empty_stream_returns_empty_list(relay):
    results = await relay.read_from("task_nonexistent", last_event_id="0", block_ms=0)
    assert results == []


@pytest.mark.asyncio
async def test_set_ttl_does_not_raise(relay):
    await relay.publish("task_ttl", {"event": "x"})
    await relay.set_ttl("task_ttl", ttl_seconds=300)  # should not raise
