from __future__ import annotations

from typing import Any

from .._run_context import RunContext
from ..tools import ToolAgentDepsT
from ._filter import ToolFilter
from ._toolset import AbstractToolset, ToolsetTool


class FilteredToolset(AbstractToolset[ToolAgentDepsT]):
    """
    Wraps any ``AbstractToolset`` and hides tools that do not pass a ``ToolFilter``.

    Not constructed directly — obtain via the shorthand methods on any toolset::

        toolset.include("tool_a", "tool_b")
        toolset.exclude("dangerous_tool")
        toolset.include_pattern("read_*")
        toolset.with_filter(ToolFilter.include_pattern("read_*") & ~ToolFilter.include("read_env"))
    """

    def __init__(self, inner: AbstractToolset[ToolAgentDepsT], filter: ToolFilter) -> None:
        self._inner = inner
        self._filter = filter

    async def get_tools(self, ctx: RunContext[ToolAgentDepsT]) -> dict[str, ToolsetTool]:
        all_tools = await self._inner.get_tools(ctx)
        return {
            name: tool
            for name, tool in all_tools.items()
            if self._filter.allows(name, tool.tool_def.description)
        }

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[ToolAgentDepsT],
        tool: ToolsetTool,
    ) -> Any:
        return await self._inner.call_tool(name, tool_args, ctx, tool)


__all__ = ["FilteredToolset"]
