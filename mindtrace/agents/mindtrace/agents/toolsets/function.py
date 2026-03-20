from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .._run_context import RunContext
from ..tools import Tool, ToolAgentDepsT
from ._toolset import AbstractToolset, ToolsetTool


@dataclass
class FunctionToolsetTool(ToolsetTool):
    call_func: Callable[[dict[str, Any], RunContext[Any]], Any] = field(repr=False)
    is_async: bool = True


@dataclass
class FunctionToolset(AbstractToolset[ToolAgentDepsT]):
    tools: dict[str, Tool] = field(default_factory=dict)
    max_retries: int = 1

    def add_tool(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"Tool name conflicts with existing tool: {tool.name!r}")
        if tool.max_retries is None:
            tool.max_retries = self.max_retries
        self.tools[tool.name] = tool

    async def get_tools(self, ctx: RunContext[ToolAgentDepsT]) -> dict[str, ToolsetTool]:
        tools: dict[str, ToolsetTool] = {}
        for name, tool in self.tools.items():
            max_retries = tool.max_retries if tool.max_retries is not None else self.max_retries
            tools[name] = FunctionToolsetTool(
                tool_def=tool.tool_def(),
                max_retries=max_retries,
                call_func=tool.function_schema.call,
                is_async=tool.function_schema.is_async,
            )
        return tools

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[ToolAgentDepsT],
        tool: ToolsetTool,
    ) -> Any:
        assert isinstance(tool, FunctionToolsetTool)
        return await tool.call_func(tool_args, ctx)


__all__ = [
    "FunctionToolset",
    "FunctionToolsetTool",
]
