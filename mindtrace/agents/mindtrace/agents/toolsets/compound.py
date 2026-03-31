from __future__ import annotations

from typing import Any

from .._run_context import RunContext
from ..tools import ToolAgentDepsT
from ._toolset import AbstractToolset, ToolsetTool


class CompoundToolset(AbstractToolset[ToolAgentDepsT]):
    """
    Merges tools from multiple toolsets into one.

    Later toolsets win on name collisions — use ``tool_prefix`` on ``MCPToolset``
    to avoid conflicts when combining toolsets from different services.

    Example::

        agent = MindtraceAgent(
            model=model,
            toolset=CompoundToolset(
                MCPToolset.from_http("http://localhost:8001/mcp-server/mcp/").include("generate_image"),
                MCPToolset.from_http("http://localhost:8002/mcp-server/mcp/").include("query_db"),
                FunctionToolset(),  # local tools
            ),
        )
    """

    def __init__(self, *toolsets: AbstractToolset) -> None:
        self._toolsets = list(toolsets)
        # Populated by get_tools(); maps tool name → owning toolset for fast routing.
        self._routing: dict[str, AbstractToolset] = {}

    async def get_tools(self, ctx: RunContext[ToolAgentDepsT]) -> dict[str, ToolsetTool]:
        merged: dict[str, ToolsetTool] = {}
        self._routing = {}
        for ts in self._toolsets:
            tools = await ts.get_tools(ctx)
            for name, tool in tools.items():
                merged[name] = tool
                self._routing[name] = ts
        return merged

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[ToolAgentDepsT],
        tool: ToolsetTool,
    ) -> Any:
        source = self._routing.get(name)
        if source is None:
            raise ValueError(f"Unknown tool {name!r}. Was get_tools() called first?")
        return await source.call_tool(name, tool_args, ctx, tool)


__all__ = ["CompoundToolset"]
