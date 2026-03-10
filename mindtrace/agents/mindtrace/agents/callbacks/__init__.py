from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


async def _invoke(cb: Callable[..., Any] | None, *args: Any) -> Any:
    if cb is None:
        return args[0] if args else None
    if inspect.iscoroutinefunction(cb):
        return await cb(*args)
    return cb(*args)


@dataclass
class AgentCallbacks:
    before_llm_call: Callable[..., Any] | None = field(default=None)
    after_llm_call: Callable[..., Any] | None = field(default=None)
    before_tool_call: Callable[..., Any] | None = field(default=None)
    after_tool_call: Callable[..., Any] | None = field(default=None)


__all__ = [
    "AgentCallbacks",
    "_invoke",
]
