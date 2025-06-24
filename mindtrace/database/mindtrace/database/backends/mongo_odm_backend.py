from pydantic import BaseModel
from typing import Type, TypeVar, List
from beanie import init_beanie, Document
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from mindtrace.database.backends.mindtrace_odm_backend import MindtraceODMBackend
from mindtrace.database.core.exceptions import DocumentNotFoundError, DuplicateInsertError

class MindtraceDocument(Document):
    class Settings:
        use_cache = False

ModelType = TypeVar("ModelType", bound=MindtraceDocument)

class MongoMindtraceODMBackend(MindtraceODMBackend):
    def __init__(self, model_cls: Type[ModelType], db_uri: str, db_name: str):
        self.model_cls = model_cls
        self.client = AsyncIOMotorClient(db_uri)
        self.db_name = db_name
        self._is_initialized = False

    async def initialize(self):
        if not self._is_initialized:
            await init_beanie(database=self.client[self.db_name], document_models=[self.model_cls])
            self._is_initialized = True

    def is_async(self) -> bool:
        return True

    async def insert(self, obj: BaseModel) -> ModelType:
        await self.initialize()
        doc = self.model_cls(**obj.model_dump())
        try:
            return await doc.insert()
        except DuplicateKeyError as e:
            raise DuplicateInsertError(f"Duplicate key error: {str(e)}")
        except Exception as e:
            raise DuplicateInsertError(str(e))

    async def get(self, id: str) -> ModelType:
        await self.initialize()
        doc = await self.model_cls.get(id)
        if not doc:
            raise DocumentNotFoundError(f"Object with id {id} not found")
        return doc

    async def delete(self, id: str):
        await self.initialize()
        doc = await self.model_cls.get(id)
        if doc:
            await doc.delete()
        else:
            raise DocumentNotFoundError(f"Object with id {id} not found")

    async def all(self) -> List[ModelType]:
        await self.initialize()
        return await self.model_cls.find_all().to_list()

    async def find(self, *args, **kwargs):
        await self.initialize()
        return await self.model_cls.find(*args, **kwargs).to_list()

    async def aggregate(self, pipeline: list):
        await self.initialize()
        return await self.model_cls.get_motor_collection().aggregate(pipeline).to_list(None)

    def get_raw_model(self) -> Type[ModelType]:
        return self.model_cls