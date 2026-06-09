from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from mindtrace.core import utcnow


@dataclass
class MemoryEntry:
    key: str
    value: str
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


class AbstractMemoryStore(ABC):
    @abstractmethod
    async def save(self, key: str, value: str, metadata: dict | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get(self, key: str) -> MemoryEntry | None:
        raise NotImplementedError

    @abstractmethod
    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_keys(self) -> list[str]:
        raise NotImplementedError


__all__ = ["AbstractMemoryStore", "MemoryEntry"]
