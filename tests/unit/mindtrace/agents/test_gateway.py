"""Unit tests for MindtraceAgentGateway.

We test the gateway logic in isolation by patching out the ``Service`` base
class and ``FastAPI``/``WebSocket`` so this file has no heavy infrastructure
dependencies.
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Stub out mindtrace.services so the import doesn't fail ────────────────

_services_mod = types.ModuleType("mindtrace.services")
_services_core = types.ModuleType("mindtrace.services.core")
_services_core_service = types.ModuleType("mindtrace.services.core.service")


class _StubService:
    """Minimal Service stand-in for unit tests."""

    name = "MindtraceAgentGateway"

    def __init__(self, **kwargs):
        pass


_services_core_service.Service = _StubService
_services_core.service = _services_core_service
_services_mod.core = _services_core
sys.modules.setdefault("mindtrace.services", _services_mod)
sys.modules.setdefault("mindtrace.services.core", _services_core)
sys.modules.setdefault("mindtrace.services.core.service", _services_core_service)

# Also stub fastapi.WebSocket if fastapi is not installed
if "fastapi" not in sys.modules:
    _fastapi_mod = types.ModuleType("fastapi")

    class _WS:
        pass

    class _WSDisconnect(Exception):
        pass

    _fastapi_mod.WebSocket = _WS
    _fastapi_mod.WebSocketDisconnect = _WSDisconnect
    _fastapi_mod.HTTPException = Exception
    sys.modules["fastapi"] = _fastapi_mod

from mindtrace.agents.distributed.gateway import MindtraceAgentGateway
from mindtrace.agents.distributed.resilience import (
    BackpressureConfig,
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)
from mindtrace.agents.distributed.types import (
    AgentInfo,
    AgentInvokeRequest,
    AgentInvokeResponse,
)
from mindtrace.agents.distributed.registry import AgentDefinition


# ── Helpers ────────────────────────────────────────────────────────────────


class _MockQueue:
    def __init__(self):
        self._results: dict = {}
        self._submitted: list = []

    async def submit(self, task) -> str:
        self._submitted.append(task)
        return "task-001"

    async def get_result(self, task_id: str) -> str:
        return self._results.get(task_id, "result")

    async def status(self, task_id: str):
        from mindtrace.agents.execution._queue import TaskStatus
        return TaskStatus.DONE

    async def cancel(self, task_id: str) -> None:
        pass


class _MockRegistry:
    async def list_agents(self):
        return [
            AgentDefinition(
                name="test_bot",
                agent_class="myapp:TestBot",
                description="A test bot",
            )
        ]

    async def get_agent_definition(self, name: str):
        return AgentDefinition(name=name, agent_class="myapp:TestBot")


def _make_gateway(**kwargs) -> MindtraceAgentGateway:
    with patch("mindtrace.agents.distributed.gateway._SERVICES_AVAILABLE", False):
        with patch("mindtrace.agents.distributed.gateway._FASTAPI_AVAILABLE", False):
            gw = MindtraceAgentGateway(
                registry=_MockRegistry(),
                task_queue=_MockQueue(),
                **kwargs,
            )
    return gw


# ── Tests: gateway instantiation ──────────────────────────────────────────


def test_gateway_has_unique_id() -> None:
    gw = _make_gateway()
    assert isinstance(gw.gateway_id, str)
    assert len(gw.gateway_id) == 12


def test_gateway_custom_id() -> None:
    gw = _make_gateway(gateway_id="my-gw-01")
    assert gw.gateway_id == "my-gw-01"


def test_gateway_circuit_breakers_start_closed() -> None:
    gw = _make_gateway()
    assert gw._cb_queue.state == CircuitState.CLOSED
    assert gw._cb_redis.state == CircuitState.CLOSED


# ── Tests: backpressure ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_backpressure_blocks_invocation() -> None:
    gw = _make_gateway(backpressure=BackpressureConfig(max_active_sessions=0))
    # Inject a fake active session so the count exceeds the limit
    gw._active_sessions["existing"] = set()

    ws = MagicMock()
    ws.headers = {}
    ws.query_params = {}
    sent = []

    async def send(text):
        sent.append(json.loads(text))

    ws.send_text = send

    request = AgentInvokeRequest(agent_name="bot", input="hi")
    await gw._handle_invoke(ws, request, session_id="sess", user_id="user")

    assert any(m.get("code") == "backpressure" for m in sent)


# ── Tests: _authenticate_ws ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_authenticate_ws_no_secret_returns_anonymous() -> None:
    gw = _make_gateway(auth_secret=None)
    ws = MagicMock()
    ws.headers = {}
    ws.query_params = {}
    user_id = await gw._authenticate_ws(ws)
    assert user_id == "anonymous"


@pytest.mark.asyncio
async def test_authenticate_ws_valid_token() -> None:
    gw = _make_gateway(auth_secret="secret123")
    ws = MagicMock()
    ws.headers = {"authorization": "Bearer secret123"}
    ws.query_params = {}
    user_id = await gw._authenticate_ws(ws)
    assert user_id == "authenticated_user"


@pytest.mark.asyncio
async def test_authenticate_ws_invalid_token_raises() -> None:
    gw = _make_gateway(auth_secret="secret123")
    ws = MagicMock()
    ws.headers = {"authorization": "Bearer wrong"}
    ws.query_params = {}
    with pytest.raises(PermissionError):
        await gw._authenticate_ws(ws)


@pytest.mark.asyncio
async def test_authenticate_ws_token_in_query_param() -> None:
    gw = _make_gateway(auth_secret="secret123")
    ws = MagicMock()
    ws.headers = {}
    ws.query_params = {"token": "secret123"}
    user_id = await gw._authenticate_ws(ws)
    assert user_id == "authenticated_user"


# ── Tests: _build_context ─────────────────────────────────────────────────


def test_build_context_basic() -> None:
    gw = _make_gateway()
    request = AgentInvokeRequest(
        agent_name="bot",
        input="hello",
        session_id="sess-abc",
        metadata={"org_id": "org-1", "project_id": "proj-1"},
    )
    ctx = gw._build_context(request, "user-1", "sess-abc", "t" * 32, "s" * 16)
    assert ctx.user_id == "user-1"
    assert ctx.org_id == "org-1"
    assert ctx.project_id == "proj-1"
    assert ctx.session_id == "sess-abc"


def test_build_context_uses_request_session_if_set() -> None:
    gw = _make_gateway()
    request = AgentInvokeRequest(
        agent_name="bot", input="x", session_id="from-request"
    )
    ctx = gw._build_context(request, "u", "gateway-session", "t" * 32, "s" * 16)
    assert ctx.session_id == "from-request"


# ── Tests: circuit breaker integration in _handle_invoke ──────────────────


@pytest.mark.asyncio
async def test_circuit_open_blocks_invoke() -> None:
    gw = _make_gateway()
    # Force circuit open
    gw._cb_queue._state = CircuitState.OPEN
    import time
    gw._cb_queue._opened_at = time.monotonic()

    ws = MagicMock()
    ws.headers = {}
    ws.query_params = {}
    sent = []

    async def send(text):
        sent.append(json.loads(text))

    ws.send_text = send

    request = AgentInvokeRequest(agent_name="bot", input="hi")
    await gw._handle_invoke(ws, request, session_id="sess", user_id="user")

    assert any(m.get("code") == "circuit_open" for m in sent)


# ── Tests: _list_agents_route ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_agents_returns_info() -> None:
    gw = _make_gateway()
    agents = await gw._list_agents_route()
    assert len(agents) == 1
    assert agents[0]["name"] == "test_bot"


# ── Tests: _health ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    gw = _make_gateway()
    health = await gw._health()
    assert health["status"] == "ok"
    assert "gateway_id" in health
    assert health["circuit_queue"] == "closed"


# ── Tests: _task_status_route ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_task_status_route() -> None:
    gw = _make_gateway()
    status = await gw._task_status_route("test_bot", "task-xyz")
    assert status["task_id"] == "task-xyz"
    assert status["status"] == "DONE"
    assert status["agent_name"] == "test_bot"
