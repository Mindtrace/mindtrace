"""Run context for mindtrace agents.

This module provides the context object that's passed to tools and functions
during agent execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic

from typing_extensions import TypeVar

# Type variable for agent dependencies
AgentDepsT = TypeVar('AgentDepsT', default=None)
"""Type variable for agent dependencies - the type injected into tools and context."""


@dataclass(kw_only=True)
class RunContext(Generic[AgentDepsT]):
    """Context information available during agent execution.
    
    This object is passed to tool functions and provides access to:
    - Dependencies injected into the agent
    - Current execution state
    - Metadata about the run
    
    Example:
        ```python
        from mindtrace import RunContext
        
        def my_tool(ctx: RunContext[str], x: int) -> str:
            # Access dependencies
            user_id = ctx.deps  # str
            
            # Access metadata
            run_id = ctx.run_id
            
            return f"User {user_id} processed {x}"
        ```
    """
    
    deps: AgentDepsT
    """Dependencies injected into the agent for this run."""
    
    run_id: str | None = None
    """Unique identifier for this agent run."""
    
    metadata: dict[str, Any] | None = None
    """Optional metadata associated with this run."""
    
    step: int = 0
    """Current step number in the execution."""
    
    retry: int = 0
    """Number of retries for the current operation."""
