from abc import abstractmethod

from pydantic import BaseModel

from mindtrace.core.base import MindtraceABC


class MindtraceODMBackend(MindtraceABC):
    @abstractmethod
    def is_async(self) -> bool:
        pass

    @abstractmethod
    def insert(self, obj: BaseModel):
        pass

    @abstractmethod
    def get(self, id: str) -> BaseModel:
        pass

    @abstractmethod
    def delete(self, id: str):
        pass

    @abstractmethod
    def all(self) -> list[BaseModel]:
        pass