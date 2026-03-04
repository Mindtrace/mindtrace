"""Wrapper/decorator pattern for mindtrace agents.

This module provides a wrapper class that can wrap any agent implementation,
enabling composition and cross-cutting concerns without modifying base classes.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from ..events import NativeEvent
from .abstract import AbstractMindtraceAgent, AgentDepsT, OutputDataT


class WrapperAgent(AbstractMindtraceAgent[AgentDepsT, OutputDataT]):
    """Agent wrapper that delegates to another agent.
    
    This class wraps another agent and forwards all calls to it. This enables:
    - Adding cross-cutting concerns (logging, caching, rate limiting)
    - Creating agent variants without modifying base classes
    - Implementing decorator patterns
    
    Example:
        ```python
        from mindtrace.agent import MindtraceAgent, WrapperAgent
        
        base_agent = MindtraceAgent[str, str](name="base")
        
        # Create a wrapper that adds logging
        class LoggingAgent(WrapperAgent[str, str]):
            async def run(self, input_data, *, deps=None, **kwargs):
                print(f"Running with input: {input_data}")
                result = await super().run(input_data, deps=deps, **kwargs)
                print(f"Result: {result}")
                return result
        
        logging_agent = LoggingAgent(base_agent)
        ```
    """
    
    def __init__(self, wrapped: AbstractMindtraceAgent[AgentDepsT, OutputDataT]):
        """Initialize the wrapper with an agent to wrap.
        
        Args:
            wrapped: The agent instance to wrap
        """
        self.wrapped = wrapped
    
    @property
    def name(self) -> str | None:
        """The name of the wrapped agent."""
        return self.wrapped.name
    
    @name.setter
    def name(self, value: str | None) -> None:
        """Set the name of the wrapped agent."""
        self.wrapped.name = value
    
    @property
    def deps_type(self) -> type:
        """The dependency type of the wrapped agent."""
        return self.wrapped.deps_type
    
    @property
    def output_type(self) -> type[OutputDataT]:
        """The output type of the wrapped agent."""
        return self.wrapped.output_type
    
    async def run(
        self,
        input_data: Any,
        *,
        deps: AgentDepsT = None,
        **kwargs: Any,
    ) -> Any:
        """Run the wrapped agent."""
        return await self.wrapped.run(input_data, deps=deps, **kwargs)

    async def run_stream_events(
        self,
        input_data: Any,
        *,
        deps: AgentDepsT = None,
        **kwargs: Any,
    ) -> AsyncIterator[NativeEvent]:
        """Stream events from the wrapped agent.

        Delegates to the wrapped agent's run_stream_events() method.

        Raises:
            NotImplementedError: If the wrapped agent does not support streaming.
        """
        if not hasattr(self.wrapped, 'run_stream_events'):
            raise NotImplementedError(
                f"Wrapped agent {type(self.wrapped).__name__!r} does not implement "
                "run_stream_events(). Override this method or wrap an agent that supports it."
            )
        async for event in self.wrapped.run_stream_events(  # type: ignore[attr-defined]
            input_data, deps=deps, **kwargs
        ):
            yield event

    @asynccontextmanager
    async def iter(
        self,
        input_data: Any,
        *,
        deps: AgentDepsT = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        """Iterate over the wrapped agent's execution."""
        async with self.wrapped.iter(input_data, deps=deps, **kwargs) as execution:
            yield execution
    
    async def __aenter__(self) -> AbstractMindtraceAgent[AgentDepsT, OutputDataT]:
        """Enter the wrapped agent's context."""
        return await self.wrapped.__aenter__()
    
    async def __aexit__(self, *args: Any) -> bool | None:
        """Exit the wrapped agent's context."""
        return await self.wrapped.__aexit__(*args)
