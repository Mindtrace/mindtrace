"""Integration tests for session history REST endpoints.

Uses RedisHistoryStrategy + make_history_router + HTTPX AsyncClient (no live server).
Requires Redis at REDIS_URL.
Tests are skipped when Redis or FastAPI are unavailable.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

REDIS_URL = "redis://localhost:6380"
pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def history_app():
    try:
        import redis.asyncio as aioredis
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient
    except ImportError as exc:
        pytest.skip(f"Required package not installed: {exc}")

    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        pytest.skip(f"Redis not available at {REDIS_URL}")
    await client.aclose()

    from mindtrace.agents.history.redis import RedisHistoryStrategy
    from mindtrace.agents.history.router import make_history_router

    history = RedisHistoryStrategy(redis_url=REDIS_URL, ttl=60, key_prefix="test:rest:history")
    app = FastAPI()
    app.include_router(make_history_router(history))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, history

    await history.close()


class TestSessionHistoryREST:
    async def test_get_empty_session_returns_empty_list(self, history_app):
        ac, _ = history_app
        resp = await ac.get("/sessions/nonexistent-session-xyz/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["messages"] == []
        assert data["count"] == 0

    async def test_get_session_history_returns_messages_in_order(self, history_app):
        from mindtrace.agents.messages import ModelMessage
        from mindtrace.agents.messages._parts import TextPart

        ac, history = history_app
        session_id = "rest-test-session-order"
        msgs = [
            ModelMessage(role="user", parts=[TextPart(content="hello")]),
            ModelMessage(role="assistant", parts=[TextPart(content="hi there")]),
            ModelMessage(role="user", parts=[TextPart(content="how are you?")]),
        ]
        await history.save(session_id, msgs)

        resp = await ac.get(f"/sessions/{session_id}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert data["count"] == 3
        roles = [m["role"] for m in data["messages"]]
        assert roles == ["user", "assistant", "user"]

    async def test_delete_session_history(self, history_app):
        from mindtrace.agents.messages import ModelMessage
        from mindtrace.agents.messages._parts import TextPart

        ac, history = history_app
        session_id = "rest-test-session-delete"
        await history.save(session_id, [ModelMessage(role="user", parts=[TextPart(content="msg")])])

        resp = await ac.delete(f"/sessions/{session_id}/history")
        assert resp.status_code == 204

        verify = await ac.get(f"/sessions/{session_id}/history")
        assert verify.json()["count"] == 0

    async def test_list_sessions_endpoint(self, history_app):
        from mindtrace.agents.messages import ModelMessage
        from mindtrace.agents.messages._parts import TextPart

        ac, history = history_app
        for i in range(3):
            sid = f"list-endpoint-sess-{i}"
            await history.save(sid, [ModelMessage(role="user", parts=[TextPart(content=f"m{i}")])])

        resp = await ac.get("/sessions?user_id=list-endpoint-sess")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        for i in range(3):
            assert f"list-endpoint-sess-{i}" in data["sessions"]

    async def test_session_history_returns_correct_content(self, history_app):
        from mindtrace.agents.messages import ModelMessage
        from mindtrace.agents.messages._parts import TextPart

        ac, history = history_app
        session_id = "rest-test-content-check"
        content = "The answer is 42"
        await history.save(session_id, [ModelMessage(role="assistant", parts=[TextPart(content=content)])])

        resp = await ac.get(f"/sessions/{session_id}/history")
        data = resp.json()
        assert data["count"] == 1
        msg = data["messages"][0]
        assert msg["role"] == "assistant"
