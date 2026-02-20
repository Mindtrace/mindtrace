"""Tool manager for validation and execution.

This module implements the ToolManager that:
- Validates tool arguments
- Handles retries
- Orchestrates tool execution via toolset
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Generic

from ._run_context import AgentDepsT, RunContext
from .toolsets import AbstractToolset, ToolsetTool


@dataclass
class ToolManager(Generic[AgentDepsT]):
    """Manager for tool validation and execution.
    
    """
    
    toolset: AbstractToolset[AgentDepsT]
    """The toolset containing available tools."""
    
    ctx: RunContext[AgentDepsT] | None = field(default=None, repr=False)
    """The current run context."""
    
    tools: dict[str, ToolsetTool] | None = field(default=None, repr=False)
    """Available tools for the current run step."""
    
    async def for_run_step(self, ctx: RunContext[AgentDepsT]) -> ToolManager[AgentDepsT]:
        """Prepare the tool manager for a run step.
        
        This gets available tools from the toolset for this context.
        
        Args:
            ctx: The run context for this step
        
        Returns:
            Self (for chaining)
        """
        self.ctx = ctx
        self.tools = await self.toolset.get_tools(ctx)
        return self
    
    async def handle_call(
        self,
        tool_name: str,
        tool_args_json: str | dict[str, Any],
    ) -> Any:
        """Handle a tool call with retry support.

        Retries up to ``tool.max_retries`` times on failure. The
        ``ctx.retry`` counter is incremented on each successive attempt so
        tool functions can inspect it via their RunContext.

        Args:
            tool_name: The name of the tool to call.
            tool_args_json: Tool arguments (JSON string or dict).

        Returns:
            The tool execution result.

        Raises:
            ValueError: If the tool name is unknown or args are invalid.
            Exception: Re-raises the last exception after all retries are exhausted.
        """
        if self.tools is None or self.ctx is None:
            raise ValueError('ToolManager has not been prepared for a run step yet')

        tool = self.tools.get(tool_name)
        if tool is None:
            available = (
                ', '.join(f'{n!r}' for n in self.tools.keys())
                if self.tools
                else 'No tools'
            )
            raise ValueError(
                f'Unknown tool name: {tool_name!r}. Available tools: {available}'
            )

        max_retries = tool.max_retries if tool.max_retries is not None else 1

        last_exc: Exception | None = None
        for attempt in range(max_retries):
            self.ctx.retry = attempt
            try:
                return await self._call_tool(tool_name, tool_args_json)
            except Exception as exc:
                last_exc = exc
                # Re-raise immediately on the last attempt
                if attempt >= max_retries - 1:
                    raise
        # Unreachable, but satisfies type checkers
        raise last_exc  # type: ignore[misc]
    
    async def _call_tool(
        self,
        tool_name: str,
        tool_args_json: str | dict[str, Any],
    ) -> Any:
        """Execute a single tool call attempt (no retry logic here).

        Callers should go through handle_call() which wraps this with retries.

        Args:
            tool_name: The name of the tool.
            tool_args_json: The tool arguments (JSON string or dict).

        Returns:
            The tool execution result.
        """
        # Parse arguments
        if isinstance(tool_args_json, str):
            args_dict = json.loads(tool_args_json or '{}')
        else:
            args_dict = tool_args_json or {}

        tool = self.tools[tool_name]  # caller (handle_call) already verified existence
        return await self.toolset.call_tool(tool_name, args_dict, self.ctx, tool)


__all__ = [
    'ToolManager',
]
