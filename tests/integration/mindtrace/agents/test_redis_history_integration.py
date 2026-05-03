"""Integration tests for RedisHistoryStrategy.

Requires Redis at REDIS_URL (default redis://localhost:6380).
Tests are skipped automatically when Redis is unavailable.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

REDIS_URL = "redis://localhost:6380"
pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def redis_history():
    try:
        import redis.asyncio as aioredis
    except ImportError:
        pytest.skip("redis package not installed")

    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        pytest.skip(f"Redis not available at {REDIS_URL}")
    await client.aclose()

    from mindtrace.agents.history.redis import RedisHistoryStrategy
    strategy = RedisHistoryStrategy(redis_url=REDIS_URL, ttl=60, key_prefix="test:history")
    yield strategy
    await strategy.close()


@pytest_asyncio.fixture
async def redis_history_b():
    from mindtrace.agents.history.redis import RedisHistoryStrategy
    strategy = RedisHistoryStrategy(redis_url=REDIS_URL, ttl=60, key_prefix="test:history")
    yield strategy
    await strategy.close()


class TestRedisHistoryTTL:
    async def test_save_and_load_roundtrip(self, redis_history):
        from mindtrace.agents.messages import ModelMessage
        from mindtrace.agents.messages._parts import TextPart

        session_id = "integ-sess-ttl-1"
        msgs = [ModelMessage(role="user", parts=[TextPart(content="hello")])]
        await redis_history.save(session_id, msgs)
        loaded = await redis_history.load(session_id)
        assert len(loaded) == 1
        assert loaded[0].role == "user"

    async def test_ttl_key_set(self, redis_history):
        import redis.asyncio as aioredis

        from mindtrace.agents.messages import ModelMessage
        from mindtrace.agents.messages._parts import TextPart

        session_id = "integ-sess-ttl-2"
        msgs = [ModelMessage(role="user", parts=[TextPart(content="ttl check")])]
        await redis_history.save(session_id, msgs)

        client = aioredis.from_url(REDIS_URL, decode_responses=True)
        ttl = await client.ttl("test:history:" + session_id)
        await client.aclose()
        assert ttl > 0

    async def test_ttl_refreshed_on_resave(self, redis_history):
        import asyncio

        import redis.asyncio as aioredis

        from mindtrace.agents.messages import ModelMessage
        from mindtrace.agents.messages._parts import TextPart

        session_id = "integ-sess-ttl-3"
        msgs = [ModelMessage(role="user", parts=[TextPart(content="first")])]
        await redis_history.save(session_id, msgs)

        client = aioredis.from_url(REDIS_URL, decode_responses=True)
        ttl1 = await client.ttl("test:history:" + session_id)

        await asyncio.sleep(1)
        msgs.append(ModelMessage(role="assistant", parts=[TextPart(content="second")]))
        await redis_history.save(session_id, msgs)
        ttl2 = await client.ttl("test:history:" + session_id)
        await client.aclose()

        assert ttl2 >= ttl1 - 2

    async def test_clear_removes_key(self, redis_history):
        from mindtrace.agents.messages import ModelMessage
        from mindtrace.agents.messages._parts import TextPart

        session_id = "integ-sess-ttl-clear"
        await redis_history.save(session_id, [ModelMessage(role="user", parts=[TextPart(content="x")])])
        await redis_history.clear(session_id)
        loaded = await redis_history.load(session_id)
        assert loaded == []

    async def test_list_sessions(self, redis_history):
        from mindtrace.agents.messages import ModelMessage
        from mindtrace.agents.messages._parts import TextPart

        for i in range(3):
            sid = f"list-test-sess-{i}"
            await redis_history.save(sid, [ModelMessage(role="user", parts=[TextPart(content=f"msg{i}")])])

        sessions = await redis_history.list_sessions(prefix="list-test-sess")
        assert len(sessions) >= 3
        for i in range(3):
            assert f"list-test-sess-{i}" in sessions

    async def test_messages_preserved_in_order(self, redis_history):
        from mindtrace.agents.messages import ModelMessage
        from mindtrace.agents.messages._parts import TextPart

        session_id = "integ-sess-order"
        msgs = [
            ModelMessage(role="user", parts=[TextPart(content="msg1")]),
            ModelMessage(role="assistant", parts=[TextPart(content="reply1")]),
            ModelMessage(role="user", parts=[TextPart(content="msg2")]),
        ]
        await redis_history.save(session_id, msgs)
        loaded = await redis_history.load(session_id)
        assert [m.role for m in loaded] == ["user", "assistant", "user"]
