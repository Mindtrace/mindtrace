from __future__ import annotations

from typing import Any, Callable

from .._run_context import RunContext
from ..tools import ToolAgentDepsT, ToolDefinition
from ._toolset import AbstractToolset, ToolsetTool


class MCPToolset(AbstractToolset[ToolAgentDepsT]):
    """
    Exposes tools from any remote MCP server to a ``MindtraceAgent``.

    Supports HTTP (streamable-http), SSE, and stdio transports.
    Requires ``fastmcp`` — install with ``pip install mindtrace-agents[mcp]``.

    Do not construct directly; use the class methods::

        # Mindtrace service (HTTP)
        MCPToolset.from_http("http://localhost:8001/mcp-server/mcp/")

        # Any SSE-based MCP server
        MCPToolset.from_sse("http://localhost:9000/sse")

        # Local stdio server (e.g. npx MCP servers)
        MCPToolset.from_stdio(["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"])

    Control which tools are visible to the agent::

        MCPToolset.from_http(url).include("search", "summarise")
        MCPToolset.from_http(url).exclude("drop_table")
        MCPToolset.from_http(url).include_pattern("read_*", "list_*")

    Avoid name collisions when combining multiple services::

        MCPToolset.from_http(url, prefix="fs")   # exposes "fs__read_file", "fs__list_dir"
    """

    def __init__(
        self,
        transport_factory: Callable[[], Any],
        *,
        prefix: str | None = None,
    ) -> None:
        self._transport_factory = transport_factory
        self._prefix = prefix
        # Populated by get_tools(); maps exposed name → original MCP tool name.
        self._name_map: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_http(cls, url: str, *, prefix: str | None = None) -> MCPToolset:
        """Connect via HTTP (streamable-http) transport — the default for Mindtrace services."""
        return cls(lambda: url, prefix=prefix)

    @classmethod
    def from_sse(cls, url: str, *, prefix: str | None = None) -> MCPToolset:
        """Connect via SSE transport (legacy MCP HTTP)."""

        def _make():
            try:
                from fastmcp.client.transports import SSETransport
            except ImportError:
                raise ImportError(
                    "fastmcp is required for MCPToolset. Install with: pip install 'mindtrace-agents[mcp]'"
                )
            return SSETransport(url)

        return cls(_make, prefix=prefix)

    @classmethod
    def from_stdio(
        cls,
        command: list[str],
        *,
        env: dict[str, str] | None = None,
        prefix: str | None = None,
    ) -> MCPToolset:
        """Connect via stdio transport — for local subprocess MCP servers (e.g. npx)."""

        def _make():
            try:
                from fastmcp.client.transports import StdioTransport
            except ImportError:
                raise ImportError(
                    "fastmcp is required for MCPToolset. Install with: pip install 'mindtrace-agents[mcp]'"
                )
            return StdioTransport(command, env=env)

        return cls(_make, prefix=prefix)

    # ------------------------------------------------------------------
    # AbstractToolset interface
    # ------------------------------------------------------------------

    async def get_tools(self, ctx: RunContext[ToolAgentDepsT]) -> dict[str, ToolsetTool]:
        try:
            from fastmcp import Client
        except ImportError:
            raise ImportError("fastmcp is required for MCPToolset. Install with: pip install 'mindtrace-agents[mcp]'")

        async with Client(self._transport_factory()) as client:
            response = await client.list_tools()

        # list_tools() returns list[mcp.types.Tool] directly
        self._name_map = {}
        tools: dict[str, ToolsetTool] = {}
        for mcp_tool in response:
            exposed = f"{self._prefix}__{mcp_tool.name}" if self._prefix else mcp_tool.name
            self._name_map[exposed] = mcp_tool.name
            tools[exposed] = ToolsetTool(
                tool_def=ToolDefinition(
                    name=exposed,
                    description=mcp_tool.description,
                    parameters_json_schema=mcp_tool.inputSchema or {},
                ),
                max_retries=None,
            )
        return tools

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[ToolAgentDepsT],
        tool: ToolsetTool,
    ) -> Any:
        try:
            from fastmcp import Client
        except ImportError:
            raise ImportError("fastmcp is required for MCPToolset. Install with: pip install 'mindtrace-agents[mcp]'")

        mcp_name = self._name_map.get(name, name)
        async with Client(self._transport_factory()) as client:
            result = await client.call_tool(mcp_name, arguments=tool_args)

        # call_tool() returns CallToolResult; .content is list[ContentBlock]
        # structured responses (dataclass/dict) are in .data — prefer that when present
        if result.data is not None:
            return str(result.data)
        return "\n".join(part.text if hasattr(part, "text") else str(part) for part in result.content)


__all__ = ["MCPToolset"]
