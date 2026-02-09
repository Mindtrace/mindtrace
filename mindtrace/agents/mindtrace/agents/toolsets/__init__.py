"""Toolset abstraction following Pydantic AI's pattern.

This module defines the abstract Toolset interface and related types.

Reference: `pydantic_ai_slim/pydantic_ai/toolsets/abstract.py`
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic

from ..tools import ToolAgentDepsT, ToolDefinition
from .._run_context import RunContext


@dataclass
class ToolsetTool:
    """Information about a tool in a toolset.
    
    This is similar to Pydantic AI's ToolsetTool.
    Reference: `pydantic_ai_slim/pydantic_ai/toolsets/abstract.py`
    """
    
    tool_def: ToolDefinition
    """The tool definition (sent to model)."""
    
    max_retries: int | None
    """Maximum number of retries for this tool."""


class AbstractToolset(ABC, Generic[ToolAgentDepsT]):
    """Abstract base class for toolsets.
    
    A toolset is responsible for:
    - Getting available tools for a run
    - Executing tool calls
    
    Reference: `pydantic_ai_slim/pydantic_ai/toolsets/abstract.py`
    """
    
    @abstractmethod
    async def get_tools(self, ctx: RunContext[ToolAgentDepsT]) -> dict[str, ToolsetTool]:
        """Get all available tools for this run step.
        
        Args:
            ctx: The run context
        
        Returns:
            Dictionary mapping tool names to ToolsetTool instances
        """
        raise NotImplementedError
    
    @abstractmethod
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
            ctx: The run context with dependencies
            tool: The ToolsetTool instance
        
        Returns:
            The tool execution result
        """
        raise NotImplementedError


__all__ = [
    'AbstractToolset',
    'ToolsetTool',
]
