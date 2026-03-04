"""Function toolset implementation.

This module implements a toolset that wraps Python functions.

"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import AbstractToolset, ToolsetTool
from ..tools import Tool, ToolAgentDepsT
from .._run_context import RunContext


@dataclass
class FunctionToolsetTool(ToolsetTool):
    """A tool in a FunctionToolset.
    
    """
    
    call_func: Callable[[dict[str, Any], RunContext[Any]], Any] = field(repr=False)
    """The prepared function that handles RunContext injection."""
    
    is_async: bool = True
    """Whether the call_func is async."""


@dataclass
class FunctionToolset(AbstractToolset[ToolAgentDepsT]):
    """Toolset that wraps Python functions.
    
    """
    
    tools: dict[str, Tool[ToolAgentDepsT]] = field(default_factory=dict)
    """Registered tools, keyed by name."""
    
    max_retries: int = 1
    """Default maximum number of retries for tools."""
    
    def add_tool(self, tool: Tool[ToolAgentDepsT]) -> None:
        """Add a tool to the toolset.
        
        Args:
            tool: The tool to add
        """
        if tool.name in self.tools:
            raise ValueError(f'Tool name conflicts with existing tool: {tool.name!r}')
        
        if tool.max_retries is None:
            tool.max_retries = self.max_retries
        
        self.tools[tool.name] = tool
    
    async def get_tools(self, ctx: RunContext[ToolAgentDepsT]) -> dict[str, ToolsetTool]:
        """Get all available tools for this run step.
        
        Args:
            ctx: The run context
        
        Returns:
            Dictionary of tool name to FunctionToolsetTool
        """
        tools: dict[str, ToolsetTool] = {}
        
        for name, tool in self.tools.items():
            max_retries = tool.max_retries if tool.max_retries is not None else self.max_retries
            
            # Get tool definition
            tool_def = tool.tool_def()
            
            # Create FunctionToolsetTool with prepared call_func
            # The call_func is tool.function_schema.call which handles RunContext injection
            tools[name] = FunctionToolsetTool(
                tool_def=tool_def,
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
        """Execute a tool.
        
        Args:
            name: The tool name
            tool_args: Validated arguments for the tool
            ctx: The run context
            tool: The ToolsetTool instance
        
        Returns:
            The tool execution result
        """
        assert isinstance(tool, FunctionToolsetTool)
        
        # Call the prepared function
        # The call_func is FunctionSchema.call() which handles RunContext injection
        return await tool.call_func(tool_args, ctx)


__all__ = [
    'FunctionToolset',
    'FunctionToolsetTool',
]
