from pydantic import BaseModel
import redis_om

from mindtrace.database import MindtraceODMBackend


class RedisMindtraceODMBackend(MindtraceODMBackend):
    def is_async(self) -> bool:
        return False

    def insert(self, obj: BaseModel):
        raise NotImplementedError("RedisMindtraceODMBackend does not support insert")

    def get(self, id: str) -> BaseModel:
        raise NotImplementedError("RedisMindtraceODMBackend does not support get")

    def delete(self, id: str):
        raise NotImplementedError("RedisMindtraceODMBackend does not support delete")

    def all(self) -> list[BaseModel]:
        raise NotImplementedError("RedisMindtraceODMBackend does not support all")
