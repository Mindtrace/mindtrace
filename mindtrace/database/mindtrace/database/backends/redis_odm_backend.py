from pydantic import BaseModel
from typing import Type, TypeVar, List
from redis_om import JsonModel, Migrator, get_redis_connection
from redis_om.model.model import NotFoundError
from redis.exceptions import ResponseError

from mindtrace.database.backends.mindtrace_odm_backend import MindtraceODMBackend
from mindtrace.database.core.exceptions import DocumentNotFoundError, DuplicateInsertError

class MindtraceRedisDocument(JsonModel):
    class Meta:
        global_key_prefix = "mindtrace"

ModelType = TypeVar("ModelType", bound=MindtraceRedisDocument)

class RedisMindtraceODMBackend(MindtraceODMBackend):
    def __init__(self, model_cls: Type[ModelType], redis_url: str):
        self.model_cls = model_cls
        self.redis = get_redis_connection(url=redis_url)
        self._is_initialized = False

    def initialize(self):
        if not self._is_initialized:
            Migrator().run()
            self._is_initialized = True

    def is_async(self) -> bool:
        return False

    def insert(self, obj: BaseModel) -> ModelType:
        self.initialize()
        # Check for duplicates by email if it exists
        if hasattr(obj, 'email'):
            existing = self.model_cls.find(self.model_cls.email == obj.email).all()
            if existing:
                raise DuplicateInsertError(f"Document with email {obj.email} already exists")
            
        doc = self.model_cls(**obj.model_dump())
        doc.save()
        return doc

    def get(self, id: str) -> ModelType:
        self.initialize()
        try:
            doc = self.model_cls.get(id)
            if not doc:
                raise DocumentNotFoundError(f"Object with id {id} not found")
            return doc
        except NotFoundError:
            raise DocumentNotFoundError(f"Object with id {id} not found")

    def delete(self, id: str):
        self.initialize()
        try:
            doc = self.model_cls.get(id)
            if doc:
                # Get all keys associated with this document
                pattern = f"{self.model_cls.Meta.global_key_prefix}:*{doc.pk}*"
                keys = self.redis.keys(pattern)
                
                # Delete all associated keys
                if keys:
                    self.redis.delete(*keys)
                
                # Delete the document itself
                self.model_cls.delete(doc.pk)
        except NotFoundError:
            raise DocumentNotFoundError(f"Object with id {id} not found")

    def all(self) -> List[ModelType]:
        self.initialize()
        return self.model_cls.find().all()

    def find(self, *args, **kwargs) -> List[ModelType]:
        self.initialize()
        return self.model_cls.find(*args).all()

    def get_raw_model(self) -> Type[ModelType]:
        return self.model_cls