from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Generic

from ._run_context import AgentDepsT, RunContext
from .toolsets import AbstractToolset, ToolsetTool


@dataclass
class ToolManager(Generic[AgentDepsT]):
    toolset: AbstractToolset[AgentDepsT]
    ctx: RunContext[AgentDepsT] | None = field(default=None, repr=False)
    tools: dict[str, ToolsetTool] | None = field(default=None, repr=False)

    async def for_run_step(self, ctx: RunContext[AgentDepsT]) -> ToolManager[AgentDepsT]:
        self.ctx = ctx
        self.tools = await self.toolset.get_tools(ctx)
        return self

    async def handle_call(
        self,
        tool_name: str,
        tool_args_json: str | dict[str, Any],
    ) -> Any:
        if self.tools is None or self.ctx is None:
            raise ValueError("ToolManager has not been prepared for a run step yet")

        tool = self.tools.get(tool_name)
        if tool is None:
            available = (
                ", ".join(f"{n!r}" for n in self.tools.keys()) if self.tools else "No tools"
            )
            raise ValueError(f"Unknown tool name: {tool_name!r}. Available tools: {available}")

        max_retries = tool.max_retries if tool.max_retries is not None else 1
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            self.ctx.retry = attempt
            try:
                return await self._call_tool(tool_name, tool_args_json)
            except Exception as exc:
                last_exc = exc
                if attempt >= max_retries - 1:
                    raise
        raise last_exc  # type: ignore[misc]

    async def _call_tool(
        self,
        tool_name: str,
        tool_args_json: str | dict[str, Any],
    ) -> Any:
        if isinstance(tool_args_json, str):
            args_dict = json.loads(tool_args_json or "{}")
        else:
            args_dict = tool_args_json or {}
        tool = self.tools[tool_name]
        return await self.toolset.call_tool(tool_name, args_dict, self.ctx, tool)


__all__ = ["ToolManager"]
