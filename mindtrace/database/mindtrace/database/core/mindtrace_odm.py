from typing import Any

from pydantic import BaseModel

from mindtrace.core import ifnone, Mindtrace
from mindtrace.database import LocalMindtraceODMBackend, MindtraceODMBackend


class MindtraceODM(Mindtrace):
    def __init__(self, backend: MindtraceODMBackend | None = None):
        self.backend = ifnone(backend, default=LocalMindtraceODMBackend())

    def is_async(self) -> bool:
        return self.backend.is_async()

    def insert(self, obj: BaseModel):
        return self.backend.insert(obj)

    def get(self, id: str) -> BaseModel:
        return self.backend.get(id)

    def delete(self, id: str):
        return self.backend.delete(id)

    def all(self) -> list[BaseModel]:
        return self.backend.all()
