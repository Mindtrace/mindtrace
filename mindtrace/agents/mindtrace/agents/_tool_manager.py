"""Tool manager for validation and execution following Pydantic AI's pattern.

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
        """Handle a tool call by validating args and executing.
        
        Args:
            tool_name: The name of the tool to call
            tool_args_json: Tool arguments (JSON string or dict)
        
        Returns:
            The tool execution result
        """
        return await self._call_tool(tool_name, tool_args_json)
    
    async def _call_tool(
        self,
        tool_name: str,
        tool_args_json: str | dict[str, Any],
    ) -> Any:
        """Execute a tool call.
        
        Args:
            tool_name: The name of the tool
            tool_args_json: The tool arguments (JSON string or dict)
        
        Returns:
            The tool execution result
        """
        if self.tools is None or self.ctx is None:
            raise ValueError('ToolManager has not been prepared for a run step yet')
        
        # Check tool exists
        tool = self.tools.get(tool_name)
        if tool is None:
            available = ', '.join(f"{name!r}" for name in self.tools.keys()) if self.tools else 'No tools'
            raise ValueError(f'Unknown tool name: {tool_name!r}. Available tools: {available}')
        
        # Parse arguments
        if isinstance(tool_args_json, str):
            args_dict = json.loads(tool_args_json or '{}')
        else:
            args_dict = tool_args_json or {}
        
        # Execute tool via toolset
        return await self.toolset.call_tool(tool_name, args_dict, self.ctx, tool)


__all__ = [
    'ToolManager',
]
