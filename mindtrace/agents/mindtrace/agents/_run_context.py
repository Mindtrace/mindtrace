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


__all__ = ["AgentDepsT", "RunContext"]
