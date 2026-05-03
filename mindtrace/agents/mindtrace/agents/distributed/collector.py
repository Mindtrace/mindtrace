from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

try:
    from mindtrace.services.core.service import Service

    _SERVICES_AVAILABLE = True
except ImportError:
    _SERVICES_AVAILABLE = False

try:
    from fastapi.responses import JSONResponse

    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False


class SpanQuery(BaseModel):
    agent_name: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None
    status: Literal["ok", "error"] | None = None
    limit: int = 100


class AgentMetrics(BaseModel):
    agent_name: str
    total_runs: int
    error_rate: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    total_input_tokens: int
    total_output_tokens: int
    tool_call_counts: dict[str, int]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = (p / 100) * (len(sorted_vals) - 1)
    lower = int(idx)
    upper = min(lower + 1, len(sorted_vals) - 1)
    frac = idx - lower
    return sorted_vals[lower] * (1 - frac) + sorted_vals[upper] * frac


class AgentObservabilityCollector(Service if _SERVICES_AVAILABLE else object):  # type: ignore[misc]
    """Collects, stores, and exposes agent observability spans.

    When otlp_endpoint is set, spans are also forwarded to an OTLP-compatible
    collector (e.g. Jaeger) fire-and-forget.
    """

    def __init__(
        self,
        otlp_endpoint: str | None = None,
        mongo_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        if _SERVICES_AVAILABLE:
            super().__init__(**kwargs)
        self.otlp_endpoint = otlp_endpoint
        self.mongo_url = mongo_url
        self._spans: list[dict] = []

        if _FASTAPI_AVAILABLE and _SERVICES_AVAILABLE:
            self._register_routes()

    def _register_routes(self) -> None:
        from fastapi.responses import JSONResponse

        self.app.add_api_route(
            "/spans",
            self._ingest_span_endpoint,
            methods=["POST"],
            response_class=JSONResponse,
        )
        self.app.add_api_route(
            "/spans/query",
            self._query_spans_endpoint,
            methods=["POST"],
            response_class=JSONResponse,
        )
        self.app.add_api_route(
            "/metrics/{agent_name}",
            self._metrics_endpoint,
            methods=["GET"],
            response_class=JSONResponse,
        )
        self.app.add_api_route(
            "/health",
            self._health_endpoint,
            methods=["GET"],
            response_class=JSONResponse,
        )

    async def ingest_span(self, span_dict: dict) -> None:
        self._spans.append(span_dict)
        if self.otlp_endpoint:
            await self._export_otlp(span_dict)

    async def query_spans(self, query: SpanQuery) -> list[dict]:
        results = []
        for span in self._spans:
            if query.agent_name is not None and span.get("agent_name") != query.agent_name:
                continue
            if query.session_id is not None and span.get("session_id") != query.session_id:
                continue
            if query.trace_id is not None and span.get("trace_id") != query.trace_id:
                continue
            if query.status is not None and span.get("status") != query.status:
                continue
            if query.from_time is not None:
                started_at = span.get("started_at")
                if started_at is not None:
                    if isinstance(started_at, str):
                        started_dt = datetime.fromisoformat(started_at)
                        if started_dt.tzinfo is None:
                            started_dt = started_dt.replace(tzinfo=timezone.utc)
                    else:
                        started_dt = started_at
                    from_time = query.from_time
                    if from_time.tzinfo is None:
                        from_time = from_time.replace(tzinfo=timezone.utc)
                    if started_dt < from_time:
                        continue
            if query.to_time is not None:
                started_at = span.get("started_at")
                if started_at is not None:
                    if isinstance(started_at, str):
                        started_dt = datetime.fromisoformat(started_at)
                        if started_dt.tzinfo is None:
                            started_dt = started_dt.replace(tzinfo=timezone.utc)
                    else:
                        started_dt = started_at
                    to_time = query.to_time
                    if to_time.tzinfo is None:
                        to_time = to_time.replace(tzinfo=timezone.utc)
                    if started_dt > to_time:
                        continue
            results.append(span)
            if len(results) >= query.limit:
                break
        return results

    async def agent_metrics(self, agent_name: str) -> AgentMetrics:
        spans = [s for s in self._spans if s.get("agent_name") == agent_name]
        total = len(spans)
        if total == 0:
            return AgentMetrics(
                agent_name=agent_name,
                total_runs=0,
                error_rate=0.0,
                latency_p50_ms=0.0,
                latency_p95_ms=0.0,
                latency_p99_ms=0.0,
                total_input_tokens=0,
                total_output_tokens=0,
                tool_call_counts={},
            )

        errors = sum(1 for s in spans if s.get("status") == "error")
        durations = [s["duration_ms"] for s in spans if s.get("duration_ms") is not None]
        input_tokens = sum(s.get("input_tokens", 0) for s in spans)
        output_tokens = sum(s.get("output_tokens", 0) for s in spans)

        tool_call_counts: dict[str, int] = {}
        for span in spans:
            for tc in span.get("tool_calls", []):
                name = tc.get("tool_name", "")
                tool_call_counts[name] = tool_call_counts.get(name, 0) + 1

        return AgentMetrics(
            agent_name=agent_name,
            total_runs=total,
            error_rate=errors / total,
            latency_p50_ms=_percentile(durations, 50),
            latency_p95_ms=_percentile(durations, 95),
            latency_p99_ms=_percentile(durations, 99),
            total_input_tokens=input_tokens,
            total_output_tokens=output_tokens,
            tool_call_counts=tool_call_counts,
        )

    async def _export_otlp(self, span_dict: dict) -> None:
        try:
            import httpx

            payload = {
                "resourceSpans": [
                    {
                        "scopeSpans": [
                            {
                                "spans": [span_dict],
                            }
                        ]
                    }
                ]
            }
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(self.otlp_endpoint, json=payload)
        except Exception as exc:
            logger.warning("Failed to export span to OTLP endpoint %s: %s", self.otlp_endpoint, exc)

    async def _ingest_span_endpoint(self, body: dict) -> dict:
        await self.ingest_span(body)
        return {"ok": True}

    async def _query_spans_endpoint(self, query: SpanQuery) -> list[dict]:
        return await self.query_spans(query)

    async def _metrics_endpoint(self, agent_name: str) -> dict:
        metrics = await self.agent_metrics(agent_name)
        return metrics.model_dump()

    async def _health_endpoint(self) -> dict:
        return {"status": "ok"}


__all__ = ["AgentMetrics", "AgentObservabilityCollector", "SpanQuery"]
