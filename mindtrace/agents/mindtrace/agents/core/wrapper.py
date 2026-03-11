from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from ..events import NativeEvent
from .abstract import AbstractMindtraceAgent, AgentDepsT, OutputDataT


class WrapperAgent(AbstractMindtraceAgent[AgentDepsT, OutputDataT]):
    def __init__(
        self,
        wrapped: AbstractMindtraceAgent[AgentDepsT, OutputDataT],
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.wrapped = wrapped

    @property
    def name(self) -> str | None:
        return self.wrapped.name

    @name.setter
    def name(self, value: str | None) -> None:
        self.wrapped.name = value

    @property
    def deps_type(self) -> type:
        return self.wrapped.deps_type

    @property
    def output_type(self) -> type[OutputDataT]:
        return self.wrapped.output_type

    async def run(
        self,
        input_data: Any,
        *,
        deps: AgentDepsT = None,
        **kwargs: Any,
    ) -> Any:
        return await self.wrapped.run(input_data, deps=deps, **kwargs)

    async def run_stream_events(
        self,
        input_data: Any,
        *,
        deps: AgentDepsT = None,
        **kwargs: Any,
    ) -> AsyncIterator[NativeEvent]:
        if not hasattr(self.wrapped, "run_stream_events"):
            raise NotImplementedError(
                f"Wrapped agent {type(self.wrapped).__name__!r} does not implement run_stream_events()."
            )
        async for event in self.wrapped.run_stream_events(input_data, deps=deps, **kwargs):  # type: ignore[attr-defined]
            yield event

    @asynccontextmanager
    async def iter(
        self,
        input_data: Any,
        *,
        deps: AgentDepsT = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        async with self.wrapped.iter(input_data, deps=deps, **kwargs) as execution:
            yield execution

    async def __aenter__(self) -> AbstractMindtraceAgent[AgentDepsT, OutputDataT]:
        return await self.wrapped.__aenter__()

    async def __aexit__(self, *args: Any) -> bool | None:
        return await self.wrapped.__aexit__(*args)


__all__ = ["WrapperAgent"]
