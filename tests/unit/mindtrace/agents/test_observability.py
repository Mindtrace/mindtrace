from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from mindtrace.agents.observability.span import AgentObservabilityMixin, AgentSpan, ToolCallRecord


def _make_span(**kwargs) -> AgentSpan:
    return AgentSpan.start(
        agent_name=kwargs.get("agent_name", "test_agent"),
        trace_id=kwargs.get("trace_id", "a" * 32),
        span_id=kwargs.get("span_id", "b" * 16),
        session_id=kwargs.get("session_id", "sess-1"),
        user_id=kwargs.get("user_id", "user-1"),
        input_text=kwargs.get("input_text", "hello"),
    )


def test_span_start_sets_started_at() -> None:
    span = _make_span()
    assert span.started_at is not None
    assert span.ended_at is None
    assert span.status == "ok"
    assert span.input_preview == "hello"


def test_span_finish_ok() -> None:
    span = _make_span()
    span.finish(status="ok", output="the answer")
    assert span.ended_at is not None
    assert span.duration_ms is not None and span.duration_ms >= 0
    assert span.status == "ok"
    assert span.output_preview is not None
    assert "the answer" in span.output_preview


def test_span_finish_error() -> None:
    span = _make_span()
    span.finish(status="error", error="something broke")
    assert span.status == "error"
    assert span.error == "something broke"


def test_span_input_preview_truncated() -> None:
    long_input = "x" * 300
    span = _make_span(input_text=long_input)
    assert len(span.input_preview) == 200


def test_span_to_dict_keys() -> None:
    span = _make_span()
    span.finish(status="ok", output="done")
    d = span.to_dict()
    required = {
        "trace_id", "span_id", "agent_name", "session_id", "user_id",
        "started_at", "ended_at", "duration_ms", "status", "error",
        "input_preview", "output_preview", "input_tokens", "output_tokens",
        "model_name", "tool_calls", "memory_reads", "memory_writes", "history_loads",
    }
    assert required.issubset(d.keys())


def test_span_to_dict_serializable() -> None:
    import json
    span = _make_span()
    span.finish(status="ok")
    json.dumps(span.to_dict())  # should not raise


def test_span_tool_call_recorded() -> None:
    span = _make_span()

    class FakeToolResultEvent:
        tool_name = "get_weather"
        tool_call_id = "tc-1"
        result = "sunny"

    span.record_event(FakeToolResultEvent())
    assert len(span.tool_calls) == 1
    assert span.tool_calls[0].tool_name == "get_weather"


def test_span_to_otlp() -> None:
    span = _make_span()
    span.finish(status="ok")
    otlp = span.to_otlp()
    assert otlp["traceId"] == "a" * 32
    assert "name" in otlp
    assert "startTimeUnixNano" in otlp


class _FakeAgent:
    name = "fake_agent"

    async def run(self, input_data, *, session_id=None, **kwargs):
        return f"result:{input_data}"


class ObservableAgent(AgentObservabilityMixin, _FakeAgent):
    pass


@pytest.mark.asyncio
async def test_mixin_emits_span_on_success() -> None:
    agent = ObservableAgent()
    emitted = []

    async def fake_emit(span):
        emitted.append(span)

    agent._emit_span = fake_emit
    result = await agent.run("test input")
    assert result == "result:test input"
    assert len(emitted) == 1
    assert emitted[0].status == "ok"


@pytest.mark.asyncio
async def test_mixin_emits_error_span_on_exception() -> None:
    class BrokenAgent:
        name = "broken"

        async def run(self, input_data, *, session_id=None, **kwargs):
            raise ValueError("broken!")

    class ObservableBroken(AgentObservabilityMixin, BrokenAgent):
        pass

    agent = ObservableBroken()
    emitted = []

    async def fake_emit(span):
        emitted.append(span)

    agent._emit_span = fake_emit

    with pytest.raises(ValueError, match="broken!"):
        await agent.run("input")

    assert len(emitted) == 1
    assert emitted[0].status == "error"
    assert "broken!" in emitted[0].error
