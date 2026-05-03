from __future__ import annotations

import sys
import types
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

# ── Stub out mindtrace.services so the import doesn't fail ────────────────

_services_mod = types.ModuleType("mindtrace.services")
_services_core = types.ModuleType("mindtrace.services.core")
_services_core_service = types.ModuleType("mindtrace.services.core.service")


class _StubService:
    name = "AgentObservabilityCollector"

    def __init__(self, **kwargs):
        pass


_services_core_service.Service = _StubService
_services_core.service = _services_core_service
_services_mod.core = _services_core
sys.modules.setdefault("mindtrace.services", _services_mod)
sys.modules.setdefault("mindtrace.services.core", _services_core)
sys.modules.setdefault("mindtrace.services.core.service", _services_core_service)

from mindtrace.agents.distributed.collector import (
    AgentMetrics,
    AgentObservabilityCollector,
    SpanQuery,
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_collector(**kwargs) -> AgentObservabilityCollector:
    with patch("mindtrace.agents.distributed.collector._SERVICES_AVAILABLE", False):
        with patch("mindtrace.agents.distributed.collector._FASTAPI_AVAILABLE", False):
            return AgentObservabilityCollector(**kwargs)


def _span(
    agent_name: str = "agent_a",
    status: str = "ok",
    duration_ms: float = 100.0,
    input_tokens: int = 10,
    output_tokens: int = 20,
    session_id: str = "sess-1",
    trace_id: str = "trace-1",
    started_at: str | None = None,
    tool_calls: list | None = None,
) -> dict:
    if started_at is None:
        started_at = datetime.now(timezone.utc).isoformat()
    return {
        "agent_name": agent_name,
        "status": status,
        "duration_ms": duration_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "session_id": session_id,
        "trace_id": trace_id,
        "started_at": started_at,
        "tool_calls": tool_calls or [],
    }


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_collector_ingest_and_query() -> None:
    col = _make_collector()
    await col.ingest_span(_span(agent_name="bot"))
    await col.ingest_span(_span(agent_name="bot"))
    results = await col.query_spans(SpanQuery())
    assert len(results) == 2


@pytest.mark.asyncio
async def test_collector_query_filters_by_agent_name() -> None:
    col = _make_collector()
    await col.ingest_span(_span(agent_name="agent_a"))
    await col.ingest_span(_span(agent_name="agent_b"))
    results = await col.query_spans(SpanQuery(agent_name="agent_a"))
    assert len(results) == 1
    assert results[0]["agent_name"] == "agent_a"


@pytest.mark.asyncio
async def test_collector_query_filters_by_status() -> None:
    col = _make_collector()
    await col.ingest_span(_span(status="ok"))
    await col.ingest_span(_span(status="error"))
    results = await col.query_spans(SpanQuery(status="error"))
    assert len(results) == 1
    assert results[0]["status"] == "error"


@pytest.mark.asyncio
async def test_collector_query_respects_limit() -> None:
    col = _make_collector()
    for _ in range(5):
        await col.ingest_span(_span())
    results = await col.query_spans(SpanQuery(limit=2))
    assert len(results) == 2


@pytest.mark.asyncio
async def test_collector_metrics_basic() -> None:
    col = _make_collector()
    await col.ingest_span(_span(agent_name="agent_x", status="ok", duration_ms=100.0, input_tokens=5, output_tokens=10))
    await col.ingest_span(_span(agent_name="agent_x", status="ok", duration_ms=200.0, input_tokens=5, output_tokens=10))
    await col.ingest_span(_span(agent_name="agent_x", status="ok", duration_ms=300.0, input_tokens=5, output_tokens=10))
    await col.ingest_span(_span(agent_name="agent_x", status="error", duration_ms=50.0, input_tokens=5, output_tokens=0))

    metrics = await col.agent_metrics("agent_x")
    assert metrics.total_runs == 4
    assert metrics.error_rate == pytest.approx(0.25)
    assert metrics.total_input_tokens == 20
    assert metrics.latency_p50_ms > 0
    assert metrics.latency_p95_ms >= metrics.latency_p50_ms
    assert metrics.latency_p99_ms >= metrics.latency_p95_ms


@pytest.mark.asyncio
async def test_collector_metrics_empty() -> None:
    col = _make_collector()
    metrics = await col.agent_metrics("nonexistent_agent")
    assert metrics.total_runs == 0
    assert metrics.error_rate == 0.0
    assert metrics.latency_p50_ms == 0.0
    assert metrics.latency_p95_ms == 0.0
    assert metrics.latency_p99_ms == 0.0
    assert metrics.total_input_tokens == 0
    assert metrics.total_output_tokens == 0


@pytest.mark.asyncio
async def test_collector_query_from_time() -> None:
    col = _make_collector()
    old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    new_time = datetime.now(timezone.utc).isoformat()
    await col.ingest_span(_span(started_at=old_time, agent_name="bot"))
    await col.ingest_span(_span(started_at=new_time, agent_name="bot"))

    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    results = await col.query_spans(SpanQuery(from_time=cutoff))
    assert len(results) == 1
    assert results[0]["started_at"] == new_time


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    col = _make_collector()
    result = await col._health_endpoint()
    assert result == {"status": "ok"}
