"""Abstract base class for mindtrace agents.

This module provides the abstract interface that all agent implementations must follow.
Inspired by Pydantic AI's AbstractAgent pattern.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from typing import Any, Generic, TypeVar

# For minimal starter, define AgentDepsT here
# In full implementation, import from tools.py: from ..tools import AgentDepsT
from typing_extensions import TypeVar as TypeVar_

# Type variables for generic agent types
AgentDepsT = TypeVar_('AgentDepsT')
"""Type variable for agent dependencies - the type injected into tools and context."""

OutputDataT = TypeVar('OutputDataT')
"""Type variable for the default output data type returned by agent runs."""

RunOutputDataT = TypeVar('RunOutputDataT')
"""Type variable for the result data of a run where output_type was customized on the run call."""


class AbstractMindtraceAgent(Generic[AgentDepsT, OutputDataT], ABC):
    """Abstract superclass for all mindtrace agent implementations.
    
    This class defines the interface that all agents must implement, providing
    a consistent API while allowing different implementations.
    
    Agents are generic in:
    - `AgentDepsT`: The type of dependencies used by the agent
    - `OutputDataT`: The type of data output by agent runs
    
    Example:
        ```python
        from mindtrace.agent import AbstractMindtraceAgent
        
        class MyAgent(AbstractMindtraceAgent[MyDeps, str]):
            # Implement required abstract methods
            ...
        ```
    """

    @property
    @abstractmethod
    def name(self) -> str | None:
        """The name of the agent, used for logging and identification.
        
        If `None`, the name may be inferred from the call frame when first run.
        """
        raise NotImplementedError

    @name.setter
    @abstractmethod
    def name(self, value: str | None) -> None:
        """Set the name of the agent."""
        raise NotImplementedError

    @property
    @abstractmethod
    def deps_type(self) -> type:
        """The type of dependencies used by the agent."""
        raise NotImplementedError

    @property
    @abstractmethod
    def output_type(self) -> type[OutputDataT]:
        """The type of data output by agent runs.
        
        Used to validate and structure the data returned by the agent.
        """
        raise NotImplementedError

    @abstractmethod
    async def run(
        self,
        input_data: Any,
        *,
        deps: AgentDepsT = None,
        **kwargs: Any,
    ) -> Any:
        """Run the agent with input data in async mode.
        
        This is the primary method for executing agent runs. It should:
        1. Process the input data
        2. Execute the agent's logic
        3. Return structured output matching `output_type`
        
        Args:
            input_data: The input to process (type depends on agent implementation)
            deps: Optional dependencies to inject into the agent's context
            **kwargs: Additional implementation-specific arguments
            
        Returns:
            The result of the agent run, validated against `output_type`
        """
        raise NotImplementedError

    def run_sync(
        self,
        input_data: Any,
        *,
        deps: AgentDepsT = None,
        **kwargs: Any,
    ) -> Any:
        """Synchronously run the agent with input data.
        
        This is a convenience method that wraps `run()` with `asyncio.run()`.
        You cannot use this method inside async code or if there's an active event loop.
        
        Args:
            input_data: The input to process
            deps: Optional dependencies to inject
            **kwargs: Additional implementation-specific arguments
            
        Returns:
            The result of the agent run
        """
        import asyncio
        
        return asyncio.run(self.run(input_data, deps=deps, **kwargs))

    @abstractmethod
    def iter(
        self,
        input_data: Any,
        *,
        deps: AgentDepsT = None,
        **kwargs: Any,
    ) -> AbstractAsyncContextManager[Any]:
        """A context manager to iterate over agent execution steps.
        
        This provides low-level access to the agent's execution, allowing you to
        observe intermediate states and results.
        
        Example:
            ```python
            async with agent.iter(input_data) as execution:
                async for step in execution:
                    print(f"Step: {step}")
            ```
        
        Args:
            input_data: The input to process
            deps: Optional dependencies to inject
            **kwargs: Additional implementation-specific arguments
            
        Returns:
            An async context manager yielding an iterable of execution steps
        """
        raise NotImplementedError

    @abstractmethod
    async def __aenter__(self) -> AbstractMindtraceAgent[AgentDepsT, OutputDataT]:
        """Enter the agent context for resource management.
        
        Use this to initialize resources needed by the agent (e.g., connections,
        file handles, etc.). Resources will be cleaned up in `__aexit__`.
        """
        raise NotImplementedError

    @abstractmethod
    async def __aexit__(self, *args: Any) -> bool | None:
        """Exit the agent context and clean up resources."""
        raise NotImplementedError
