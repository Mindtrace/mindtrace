from __future__ import annotations

import asyncio
from abc import abstractmethod
from contextlib import AbstractAsyncContextManager
from typing import Any, Generic

from typing_extensions import TypeVar as TypeVar_

from mindtrace.core import MindtraceABC

AgentDepsT = TypeVar_("AgentDepsT")
OutputDataT = TypeVar_("OutputDataT")
RunOutputDataT = TypeVar_("RunOutputDataT")


class AbstractMindtraceAgent(Generic[AgentDepsT, OutputDataT], MindtraceABC):
    @property
    @abstractmethod
    def name(self) -> str | None:
        raise NotImplementedError

    @name.setter
    @abstractmethod
    def name(self, value: str | None) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def deps_type(self) -> type:
        raise NotImplementedError

    @property
    @abstractmethod
    def output_type(self) -> type[OutputDataT]:
        raise NotImplementedError

    @abstractmethod
    async def run(
        self,
        input_data: Any,
        *,
        deps: AgentDepsT = None,
        **kwargs: Any,
    ) -> Any:
        raise NotImplementedError

    def run_sync(
        self,
        input_data: Any,
        *,
        deps: AgentDepsT = None,
        **kwargs: Any,
    ) -> Any:
        return asyncio.run(self.run(input_data, deps=deps, **kwargs))

    @abstractmethod
    def iter(
        self,
        input_data: Any,
        *,
        deps: AgentDepsT = None,
        **kwargs: Any,
    ) -> AbstractAsyncContextManager[Any]:
        raise NotImplementedError

    @abstractmethod
    async def __aenter__(self) -> AbstractMindtraceAgent[AgentDepsT, OutputDataT]:
        raise NotImplementedError

    @abstractmethod
    async def __aexit__(self, *args: Any) -> bool | None:
        raise NotImplementedError


__all__ = [
    "AbstractMindtraceAgent",
    "AgentDepsT",
    "OutputDataT",
    "RunOutputDataT",
]
