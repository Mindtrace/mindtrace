from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .._run_context import RunContext


def _parse_traceparent(header: str) -> tuple[str, str]:
    """Parse W3C traceparent header → (trace_id, span_id)."""
    parts = header.split("-")
    if len(parts) >= 3:
        return parts[1], parts[2]
    trace_id = uuid4().hex + uuid4().hex  # 32 hex chars
    span_id = uuid4().hex[:16]            # 16 hex chars
    return trace_id, span_id


def _parse_baggage(header: str) -> dict[str, str]:
    """Parse W3C baggage header → dict."""
    result: dict[str, str] = {}
    for item in header.split(","):
        item = item.strip()
        if "=" in item:
            k, _, v = item.partition("=")
            result[k.strip()] = v.strip()
    return result


class TaskProvenance(BaseModel):
    """Records the origin and submitter of a task for audit and routing."""

    submitter_id: str
    submitter_role: str
    origin_gateway_id: str
    origin_ip: str | None = None
    client_request_id: str | None = None


class AgentRunContext(BaseModel):
    """Serializable context for cross-process and cross-network propagation.

    Carries W3C TraceContext-compatible identifiers and serialized deps.
    """

    trace_id: str
    span_id: str
    session_id: str
    user_id: str
    org_id: str | None = None
    project_id: str | None = None
    run_id: str | None = None
    baggage: dict[str, str] = Field(default_factory=dict)
    deps_json: str = "{}"
    deps_type_path: str = "builtins.NoneType"
    step: int = 0
    retry: int = 0

    def to_run_context(self) -> RunContext:
        """Deserialize deps_json using deps_type_path and return a RunContext.

        Note: AllowlistViolationError check will be added in Phase 2 when
        MindtraceAllowlistRegistry is available.
        """
        deps: Any = None
        if self.deps_type_path not in ("builtins.NoneType", "pydantic.BaseModel"):
            module_path, _, class_name = self.deps_type_path.rpartition(".")
            if ":" in self.deps_type_path:
                module_path, class_name = self.deps_type_path.split(":", 1)
            module = importlib.import_module(module_path)
            deps_cls = getattr(module, class_name)
            deps_data = json.loads(self.deps_json)
            if hasattr(deps_cls, "model_validate"):
                deps = deps_cls.model_validate(deps_data)
            else:
                deps = deps_cls(**deps_data)

        return RunContext(
            deps=deps,
            run_id=self.run_id,
            step=self.step,
            retry=self.retry,
            session_id=self.session_id,
            user_id=self.user_id,
            trace_id=self.trace_id,
            span_id=self.span_id,
        )

    @classmethod
    def from_run_context(
        cls,
        ctx: RunContext,
        trace_id: str,
        span_id: str,
        session_id: str,
        user_id: str,
        baggage: dict[str, str] | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> "AgentRunContext":
        deps_json = "{}"
        deps_type_path = "builtins.NoneType"
        if ctx.deps is not None:
            deps_type = type(ctx.deps)
            deps_type_path = f"{deps_type.__module__}:{deps_type.__qualname__}"
            if hasattr(ctx.deps, "model_dump"):
                deps_json = json.dumps(ctx.deps.model_dump())
            else:
                try:
                    deps_json = json.dumps(vars(ctx.deps))
                except TypeError:
                    deps_json = "{}"

        return cls(
            trace_id=trace_id,
            span_id=span_id,
            session_id=session_id,
            user_id=user_id,
            run_id=ctx.run_id,
            step=ctx.step,
            retry=ctx.retry,
            baggage=baggage or {},
            deps_json=deps_json,
            deps_type_path=deps_type_path,
            org_id=org_id,
            project_id=project_id,
        )

    def to_headers(self) -> dict[str, str]:
        """Serialize as HTTP headers (W3C traceparent + X-Mindtrace-Baggage)."""
        headers: dict[str, str] = {
            "traceparent": f"00-{self.trace_id}-{self.span_id}-01",
        }
        carrier = dict(self.baggage)
        carrier["session_id"] = self.session_id
        carrier["user_id"] = self.user_id
        if self.org_id:
            carrier["org_id"] = self.org_id
        if self.project_id:
            carrier["project_id"] = self.project_id
        headers["baggage"] = ",".join(f"{k}={v}" for k, v in carrier.items())
        return headers

    @classmethod
    def from_headers(cls, headers: dict[str, str]) -> "AgentRunContext":
        """Reconstruct from HTTP headers (W3C traceparent + baggage)."""
        trace_id, span_id = _parse_traceparent(headers.get("traceparent", ""))
        baggage = _parse_baggage(headers.get("baggage", ""))
        session_id = baggage.pop("session_id", "")
        user_id = baggage.pop("user_id", "")
        org_id = baggage.pop("org_id", None)
        project_id = baggage.pop("project_id", None)
        return cls(
            trace_id=trace_id,
            span_id=span_id,
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
            project_id=project_id,
            baggage=baggage,
        )


class AgentTaskEnvelope(BaseModel):
    """Wire format for messages published to RabbitMQ or Redis queues.

    TTL semantics:
      task_ttl_seconds: worker must not start execution after this deadline.
      result_ttl_seconds: how long the result key lives in Redis after completion.
    """

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_name: str
    input: str
    session_id: str | None = None
    run_context: AgentRunContext
    provenance: TaskProvenance
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    task_ttl_seconds: int = 300
    result_ttl_seconds: int = 3600
    result_channel: str = ""
    result_key: str = ""
    retry_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not self.result_channel:
            object.__setattr__(self, "result_channel", f"task:{self.task_id}")
        if not self.result_key:
            object.__setattr__(self, "result_key", f"result:{self.task_id}")

    def is_expired(self) -> bool:
        age = (datetime.now(timezone.utc) - self.submitted_at).total_seconds()
        return age > self.task_ttl_seconds


__all__ = ["AgentRunContext", "AgentTaskEnvelope", "TaskProvenance"]
