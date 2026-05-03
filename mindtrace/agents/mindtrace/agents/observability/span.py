from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

logger = logging.getLogger(__name__)

_PREVIEW_LEN = 200


@dataclass
class ToolCallRecord:
    tool_name: str
    tool_call_id: str
    args_preview: str
    result_preview: str
    duration_ms: float
    success: bool


@dataclass
class AgentSpan:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    agent_name: str
    worker_id: str
    node_id: str
    session_id: str
    user_id: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: float | None = None
    status: Literal["ok", "error"] = "ok"
    error: str | None = None
    input_preview: str = ""
    output_preview: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    model_name: str = ""
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    memory_reads: int = 0
    memory_writes: int = 0
    history_loads: int = 0

    @classmethod
    def start(
        cls,
        agent_name: str,
        trace_id: str,
        span_id: str,
        session_id: str,
        user_id: str,
        parent_span_id: str | None = None,
        worker_id: str = "",
        node_id: str = "",
        input_text: str = "",
    ) -> "AgentSpan":
        return cls(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            agent_name=agent_name,
            worker_id=worker_id,
            node_id=node_id,
            session_id=session_id,
            user_id=user_id,
            started_at=datetime.now(timezone.utc),
            input_preview=input_text[:_PREVIEW_LEN],
        )

    def finish(
        self,
        status: str = "ok",
        output: Any = None,
        error: str | None = None,
    ) -> None:
        self.ended_at = datetime.now(timezone.utc)
        self.duration_ms = (self.ended_at - self.started_at).total_seconds() * 1000
        self.status = status  # type: ignore[assignment]
        self.error = error
        if output is not None:
            preview = str(output)
            self.output_preview = preview[:_PREVIEW_LEN]

    def record_event(self, event: Any) -> None:
        """Extract token counts and tool call data from NativeEvents (duck-typed)."""
        # Detect tool result events by presence of tool_name + tool_call_id attributes
        if hasattr(event, "tool_name") and hasattr(event, "tool_call_id"):
            result = getattr(event, "result", None)
            self.tool_calls.append(
                ToolCallRecord(
                    tool_name=getattr(event, "tool_name", ""),
                    tool_call_id=getattr(event, "tool_call_id", ""),
                    args_preview="",
                    result_preview=str(result)[:_PREVIEW_LEN] if result is not None else "",
                    duration_ms=0.0,
                    success=True,
                )
            )
        # Detect usage events by presence of usage attribute
        usage = getattr(event, "usage", None)
        if usage is not None:
            self.input_tokens += getattr(usage, "input_tokens", 0)
            self.output_tokens += getattr(usage, "output_tokens", 0)
            if not self.model_name:
                self.model_name = getattr(usage, "model_name", "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "agent_name": self.agent_name,
            "worker_id": self.worker_id,
            "node_id": self.node_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error": self.error,
            "input_preview": self.input_preview,
            "output_preview": self.output_preview,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "model_name": self.model_name,
            "tool_calls": [
                {
                    "tool_name": tc.tool_name,
                    "tool_call_id": tc.tool_call_id,
                    "args_preview": tc.args_preview,
                    "result_preview": tc.result_preview,
                    "duration_ms": tc.duration_ms,
                    "success": tc.success,
                }
                for tc in self.tool_calls
            ],
            "memory_reads": self.memory_reads,
            "memory_writes": self.memory_writes,
            "history_loads": self.history_loads,
        }

    def to_otlp(self) -> dict[str, Any]:
        """Serialize in a simplified OTLP-compatible JSON span format."""
        start_ns = int(self.started_at.timestamp() * 1e9)
        end_ns = int(self.ended_at.timestamp() * 1e9) if self.ended_at else start_ns
        return {
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "parentSpanId": self.parent_span_id or "",
            "name": f"agent.run/{self.agent_name}",
            "startTimeUnixNano": str(start_ns),
            "endTimeUnixNano": str(end_ns),
            "status": {"code": 1 if self.status == "ok" else 2},
            "attributes": [
                {"key": "agent.name", "value": {"stringValue": self.agent_name}},
                {"key": "session.id", "value": {"stringValue": self.session_id}},
                {"key": "user.id", "value": {"stringValue": self.user_id}},
                {"key": "worker.id", "value": {"stringValue": self.worker_id}},
            ],
        }


class AgentObservabilityMixin:
    """MRO mixin that wraps agent.run() and run_stream_events() with span recording.

    Place before the agent base in MRO:
        class ObservableAgent(AgentObservabilityMixin, MindtraceAgent): ...
    """

    _collector_url: str | None = None
    _worker_id: str = ""
    _node_id: str = ""

    async def run(self, input_data: Any, *, session_id: str | None = None, **kwargs: Any) -> Any:
        from uuid import uuid4
        span = AgentSpan.start(
            agent_name=getattr(self, "name", "") or "",
            trace_id=getattr(kwargs.get("deps", None), "trace_id", None) or uuid4().hex * 2,
            span_id=uuid4().hex[:16],
            session_id=session_id or "",
            user_id="",
            worker_id=self._worker_id,
            node_id=self._node_id,
            input_text=str(input_data),
        )
        try:
            result = await super().run(input_data, session_id=session_id, **kwargs)  # type: ignore[misc]
            span.finish(status="ok", output=result)
            return result
        except Exception as exc:
            span.finish(status="error", error=str(exc))
            raise
        finally:
            await self._emit_span(span)

    async def _emit_span(self, span: AgentSpan) -> None:
        if not self._collector_url:
            logger.debug("agent_span %s", json.dumps(span.to_dict()))
            return
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(f"{self._collector_url}/spans", json=span.to_dict())
        except Exception as exc:
            logger.warning("Failed to POST span to collector: %s", exc)


__all__ = ["AgentObservabilityMixin", "AgentSpan", "ToolCallRecord"]
