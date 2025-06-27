from pydantic import BaseModel

from mindtrace.database import MindtraceODMBackend


class MongoMindtraceODMBackend(MindtraceODMBackend):
    def is_async(self) -> bool:
        return False

    def insert(self, obj: BaseModel):
        raise NotImplementedError("MongoMindtraceODMBackend does not support insert")

    def get(self, id: str) -> BaseModel:
        raise NotImplementedError("MongoMindtraceODMBackend does not support get")

    def delete(self, id: str):
        raise NotImplementedError("MongoMindtraceODMBackend does not support delete")

    def all(self) -> list[BaseModel]:
        raise NotImplementedError("MongoMindtraceODMBackend does not support all")
