from __future__ import annotations

from abc import abstractmethod
from collections import defaultdict
from typing import Any

from mindtrace.core import MindtraceABC

from ..messages import ModelMessage


class AbstractHistoryStrategy(MindtraceABC):
    @abstractmethod
    async def load(self, session_id: str) -> list[ModelMessage]:
        raise NotImplementedError

    @abstractmethod
    async def save(self, session_id: str, messages: list[ModelMessage]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def clear(self, session_id: str) -> None:
        raise NotImplementedError


class InMemoryHistory(AbstractHistoryStrategy):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._store: dict[str, list[ModelMessage]] = defaultdict(list)

    async def load(self, session_id: str) -> list[ModelMessage]:
        return list(self._store[session_id])

    async def save(self, session_id: str, messages: list[ModelMessage]) -> None:
        self._store[session_id] = list(messages)

    async def clear(self, session_id: str) -> None:
        self._store.pop(session_id, None)


__all__ = [
    "AbstractHistoryStrategy",
    "InMemoryHistory",
]
