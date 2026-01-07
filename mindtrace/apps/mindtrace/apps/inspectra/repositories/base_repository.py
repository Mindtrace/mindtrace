from abc import ABC, abstractmethod
from typing import Generic, List, TypeVar

T = TypeVar("T")

class BaseRepository(ABC, Generic[T]):
    @abstractmethod
    async def list(self) -> List[T]:
        ...

    @abstractmethod
    async def create(self, obj: T) -> T:
        ...
