from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic

from typing_extensions import TypeVar

AgentDepsT = TypeVar("AgentDepsT", default=None)


@dataclass(kw_only=True)
class RunContext(Generic[AgentDepsT]):
    deps: AgentDepsT
    run_id: str | None = None
    metadata: dict[str, Any] | None = None
    step: int = 0
    retry: int = 0
    # Distributed execution fields — populated when running via MindtraceAgentWorker
    session_id: str | None = None
    user_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None


__all__ = ["AgentDepsT", "RunContext"]
