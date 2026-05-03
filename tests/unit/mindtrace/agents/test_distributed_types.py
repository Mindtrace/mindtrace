from __future__ import annotations

import pytest

from mindtrace.agents.distributed.types import (
    AgentAckMessage,
    AgentErrorMessage,
    AgentInvokeRequest,
    AgentInvokeResponse,
    AgentSessionMessage,
    AgentStreamEvent,
    MemoryEntry,
    MemoryEntryRequest,
    SessionInfo,
    TaskStatusResponse,
    TokenUsage,
    WorkerInfo,
)
from datetime import datetime, timezone


def test_agent_invoke_request_defaults() -> None:
    req = AgentInvokeRequest(agent_name="travel_assistant", input="Hello")
    assert req.agent_name == "travel_assistant"
    assert req.input == "Hello"
    assert req.stream is True
    assert req.session_id is None
    assert req.deps == {}


def test_agent_invoke_request_roundtrip() -> None:
    req = AgentInvokeRequest(
        agent_name="bot",
        input="hi",
        session_id="sess-1",
        stream=False,
        metadata={"source": "test"},
    )
    data = req.model_dump()
    req2 = AgentInvokeRequest.model_validate(data)
    assert req2.agent_name == req.agent_name
    assert req2.session_id == req.session_id
    assert req2.stream is False


def test_agent_session_message_type() -> None:
    msg = AgentSessionMessage(session_id="s1", gateway_id="gw1")
    assert msg.type == "connected"


def test_agent_ack_message_type() -> None:
    ack = AgentAckMessage(task_id="t1", trace_id="tr1")
    assert ack.type == "ack"


def test_agent_stream_event_type() -> None:
    ev = AgentStreamEvent(
        task_id="t1",
        trace_id="tr1",
        event_kind="part_delta",
        payload={"delta": "hello"},
    )
    assert ev.type == "stream_event"
    assert ev.event_kind == "part_delta"
    assert ev.payload["delta"] == "hello"


def test_agent_invoke_response_type() -> None:
    resp = AgentInvokeResponse(
        task_id="t1",
        trace_id="tr1",
        span_id="sp1",
        session_id="s1",
        output="done",
    )
    assert resp.type == "response"
    assert resp.usage is None


def test_agent_error_message_type() -> None:
    err = AgentErrorMessage(trace_id="tr1", code="timeout", message="too slow")
    assert err.type == "error"
    assert err.task_id is None


def test_token_usage() -> None:
    usage = TokenUsage(input_tokens=10, output_tokens=20, model_name="gpt-4o")
    assert usage.input_tokens == 10
    assert usage.model_name == "gpt-4o"


def test_worker_info() -> None:
    now = datetime.now(timezone.utc)
    w = WorkerInfo(
        worker_id="w1",
        node_id="n1",
        url="http://worker:8001",
        agent_names=["bot"],
        last_heartbeat=now,
    )
    assert w.status == "active"
    assert "bot" in w.agent_names


def test_memory_entry_request() -> None:
    req = MemoryEntryRequest(key="home_city", value="Amsterdam")
    assert req.metadata == {}


def test_session_info_defaults() -> None:
    si = SessionInfo(session_id="s1", message_count=5)
    assert si.user_id is None
    assert si.last_active is None
    assert si.ttl_seconds is None


def test_task_status_response() -> None:
    t = TaskStatusResponse(task_id="t1", status="DONE", agent_name="bot")
    assert t.task_id == "t1"
