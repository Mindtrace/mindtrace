from pydantic import BaseModel

from mindtrace.database import MindtraceODMBackend


class LocalMindtraceODMBackend(MindtraceODMBackend):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def is_async(self) -> bool:
        return False

    def insert(self, obj: BaseModel):
        raise NotImplementedError("LocalMindtraceODMBackend does not support insert")

    def get(self, id: str) -> BaseModel:
        raise NotImplementedError("LocalMindtraceODMBackend does not support get")

    def delete(self, id: str):
        raise NotImplementedError("LocalMindtraceODMBackend does not support delete")

    def all(self) -> list[BaseModel]:
        raise NotImplementedError("LocalMindtraceODMBackend does not support all")
