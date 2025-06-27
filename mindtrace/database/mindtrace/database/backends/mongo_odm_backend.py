from pydantic import BaseModel
from typing import Type, TypeVar, List, Optional, Dict
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

    async def get_by_id(self, id: str) -> Optional[ModelType]:
        """Get document by ID, returns None if not found"""
        await self.initialize()
        return await self.model_cls.get(id)

    async def update(self, id: str, update_data: Dict) -> Optional[ModelType]:
        """Update document by ID"""
        await self.initialize()
        doc = await self.model_cls.get(id)
        if not doc:
            return None
        
        for key, value in update_data.items():
            if hasattr(doc, key):
                setattr(doc, key, value)
        
        await doc.save()
        return doc

    async def delete(self, id: str) -> bool:
        """Delete document by ID, returns True if deleted, False if not found"""
        await self.initialize()
        doc = await self.model_cls.get(id)
        if doc:
            await doc.delete()
            return True
        return False

    async def count(self, query: Optional[Dict] = None) -> int:
        """Count documents matching query"""
        await self.initialize()
        if query:
            return await self.model_cls.find(query).count()
        else:
            return await self.model_cls.find_all().count()

    async def all(self) -> List[ModelType]:
        await self.initialize()
        return await self.model_cls.find_all().to_list()

    async def find(self, query: Optional[Dict] = None, skip: int = 0, limit: Optional[int] = None, sort: Optional[List] = None) -> List[ModelType]:
        """Find documents with pagination and sorting support"""
        await self.initialize()
        
        if query:
            find_query = self.model_cls.find(query)
        else:
            find_query = self.model_cls.find_all()
        
        if skip > 0:
            find_query = find_query.skip(skip)
        
        if limit:
            find_query = find_query.limit(limit)
        
        if sort:
            # Beanie expects sort tuples directly, not as a dictionary
            # Convert [("created_at", -1)] to the format Beanie expects
            for sort_item in sort:
                if isinstance(sort_item, tuple) and len(sort_item) == 2:
                    field, direction = sort_item
                    if direction == -1:
                        find_query = find_query.sort(f"-{field}")  # Descending
                    else:
                        find_query = find_query.sort(field)  # Ascending
        
        return await find_query.to_list()

    async def aggregate(self, pipeline: list):
        await self.initialize()
        return await self.model_cls.get_motor_collection().aggregate(pipeline).to_list(None)

    def get_raw_model(self) -> Type[ModelType]:
        return self.model_cls