import asyncio
import threading
from typing import Any, Dict, List, Optional, Type, TypeVar

from beanie import Document, PydanticObjectId, init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from mindtrace.database.backends.mindtrace_odm import InitMode, MindtraceODM
from mindtrace.database.core.exceptions import DocumentNotFoundError, DuplicateInsertError


class MindtraceDocument(Document):
    """
    Base document class for MongoDB collections in Mindtrace.

    This class extends Beanie's Document class to provide a standardized
    base for all MongoDB document models in the Mindtrace ecosystem.

    Example:
        .. code-block:: python

            from mindtrace.database.backends.mongo_odm import MindtraceDocument

            class User(MindtraceDocument):
                name: str
                email: str

                class Settings:
                    name = "users"
                    use_cache = True
    """

    class Settings:
        """
        Configuration settings for the document.

        Attributes:
            use_cache (bool): Whether to enable caching for this document type.
        """

        use_cache = False


ModelType = TypeVar("ModelType", bound=MindtraceDocument)


class MongoMindtraceODM[T: MindtraceDocument](MindtraceODM):
    """
    MongoDB implementation of the Mindtrace ODM backend.

    This backend provides asynchronous database operations using MongoDB as the
    underlying storage engine. It uses Beanie ODM for document modeling and
    Motor for async MongoDB operations.

    Args:
        model_cls (Type[ModelType]): The document model class to use for operations.
        db_uri (str): MongoDB connection URI string.
        db_name (str): Name of the MongoDB database to use.

    Example:
        .. code-block:: python

            from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

            class User(MindtraceDocument):
                name: str
                email: str

            backend = MongoMindtraceODM(
                model_cls=User,
                db_uri="mongodb://localhost:27017",
                db_name="mindtrace_db"
            )

            # Initialize and use
            await backend.initialize()
            user = await backend.insert(User(name="John", email="john@example.com"))
    """

    def __init__(
        self,
        model_cls: Optional[Type[T]] = None,
        models: Optional[Dict[str, Type[MindtraceDocument]] | str] = None,
        db_uri: str = "",
        db_name: str = "",
        allow_index_dropping: bool = False,
        auto_init: bool = False,
        init_mode: InitMode | None = None,
        client: AsyncIOMotorClient | None = None,
    ):
        """
        Initialize the MongoDB ODM backend.

        Args:
            model_cls (Type[ModelType], optional): The document model class to use for operations (single model mode).
            models (Dict[str, Type[MindtraceDocument]] | str, optional): Dictionary of model names to model classes (multi-model mode).
                Example: {'user': User, 'address': Address}. When provided, access models via db.user, db.address, etc.
                For backward compatibility: if a string is provided, it's treated as db_uri.
            db_uri (str): MongoDB connection URI string.
            db_name (str): Name of the MongoDB database to use.
            allow_index_dropping (bool): If True, allows Beanie to drop and recreate
                conflicting indexes. Useful in test environments. Defaults to False.
            auto_init (bool): If True, attempts to initialize the backend during construction.
                In sync contexts, initialization only occurs if init_mode=InitMode.SYNC.
                In async contexts, initialization is always deferred regardless of init_mode.
                Defaults to False for backward compatibility. Operations will auto-init
                on first use regardless.
            init_mode (InitMode | None): Initialization mode. If None, defaults to InitMode.ASYNC
                for MongoDB. If InitMode.SYNC and auto_init=True, initialization happens
                synchronously in sync contexts. If InitMode.ASYNC, initialization is always
                deferred to first operation.
        """
        super().__init__()

        # Backward compatibility: if models is a string, it's actually db_uri from old API
        # Old API: MongoMindtraceODM(model_cls, db_uri, db_name)
        # New API: MongoMindtraceODM(model_cls=..., models=..., db_uri=..., db_name=...)
        if isinstance(models, str):
            # Old API: second positional arg is db_uri, third is db_name
            # Swap: models (string) -> db_uri, db_uri -> db_name
            actual_db_uri = models
            actual_db_name = db_uri if db_uri else ""
            db_uri = actual_db_uri
            db_name = actual_db_name
            models = None

        if not db_uri or not db_name:
            raise ValueError("db_uri and db_name are required")

        self.client = client or AsyncIOMotorClient(db_uri)
        self.db_name = db_name
        self._allow_index_dropping = allow_index_dropping
        self._is_initialized = False
        self._model_odms: Dict[str, "MongoMindtraceODM"] = {}
        self._parent_odm: Optional["MongoMindtraceODM"] = None  # Reference to parent in multi-model mode

        # Support both single model and multi-model modes
        if models is not None:
            # Multi-model mode
            if model_cls is not None:
                raise ValueError("Cannot specify both model_cls and models. Use one or the other.")
            if not isinstance(models, dict) or len(models) == 0:
                raise ValueError("models must be a non-empty dictionary")
            self._models = models
            self.model_cls = None  # No single model in multi-model mode
            # Create ODM instances for each model (they share the same client)
            for name, model in models.items():
                odm = MongoMindtraceODM(
                    model_cls=model,
                    db_uri=db_uri,
                    db_name=db_name,
                    allow_index_dropping=allow_index_dropping,
                    auto_init=False,  # We'll initialize all together
                    init_mode=init_mode,
                    client=self.client,
                )
                # Store parent reference for initialization delegation
                odm._parent_odm = self
                self._model_odms[name] = odm
        elif model_cls is not None:
            # Single model mode (backward compatible)
            self.model_cls: Type[T] = model_cls
            self._models = None
        else:
            raise ValueError("Must specify either model_cls or models")

        # Default to async for MongoDB if not specified
        if init_mode is None:
            init_mode = InitMode.ASYNC

        # Store init_mode for later reference
        self._init_mode = init_mode

        # Dedicated event-loop thread for sync wrappers.  Motor binds to
        # the first loop it touches; ``asyncio.run()`` creates & closes a
        # new loop every call which breaks motor.  A background thread
        # running ``loop.run_forever()`` lets any caller thread submit
        # coroutines lock-free via ``run_coroutine_threadsafe()``.
        self._sync_loop: Optional[asyncio.AbstractEventLoop] = None
        self._sync_thread: Optional[threading.Thread] = None
        self._sync_loop_lock = threading.Lock()  # guards loop/thread creation only

        # Auto-initialize in sync contexts (if requested)
        # Note: MongoDB/Beanie is always async, so in async contexts we always defer
        if auto_init:
            # First check if we're in an async context
            try:
                asyncio.get_running_loop()
                # We're in an async context - defer initialization regardless of init_mode
                self._needs_init = True
            except RuntimeError:
                # We're in a sync context
                if init_mode == InitMode.SYNC:
                    self._run_sync(self._do_initialize())
                    self._needs_init = False
                else:
                    # Async mode in sync context - defer to first operation
                    self._needs_init = True
        else:
            # Defer initialization - operations will auto-init on first use
            self._needs_init = True

    async def _do_initialize(self):
        """Internal method to perform the actual initialization."""
        if not self._is_initialized:
            if self._models is not None:
                # Multi-model mode: initialize all models together
                document_models = list(self._models.values())
            else:
                # Single model mode
                document_models = [self.model_cls]

            await init_beanie(
                database=self.client[self.db_name],
                document_models=document_models,
                allow_index_dropping=self._allow_index_dropping,
            )
            self._is_initialized = True
            # Mark all model ODMs as initialized
            for odm in self._model_odms.values():
                odm._is_initialized = True

    async def initialize(self, allow_index_dropping: bool | None = None):
        """
        Initialize the MongoDB connection and document models.

        This method sets up the Beanie ODM with the specified database and
        registers the document models. It should be called before performing
        any database operations. If auto_init was True in __init__, this is
        only needed when called from async contexts.

        Args:
            allow_index_dropping (bool | None): If provided, overrides the value
                set in __init__. If None, uses the value from __init__.

        Example:
            .. code-block:: python

                # Auto-initialized in sync context
                backend = MongoMindtraceODM(User, "mongodb://localhost:27017", "mydb")
                # Ready to use immediately

                # In async context, explicit init needed
                backend = MongoMindtraceODM(User, "mongodb://localhost:27017", "mydb")
                await backend.initialize()

        Note:
            This method is idempotent - calling it multiple times is safe and
            will only initialize once.
        """
        # If this is a child ODM in multi-model mode, delegate to parent
        if self._parent_odm is not None:
            await self._parent_odm.initialize(allow_index_dropping=allow_index_dropping)
            return

        # Idempotent - return early if already initialized
        if self._is_initialized:
            return

        if allow_index_dropping is not None:
            self._allow_index_dropping = allow_index_dropping
        await self._do_initialize()

    def __getattr__(self, name: str):
        """Support attribute-based access to model-specific ODMs in multi-model mode.

        Example:
            db = MongoMindtraceODM(models={'user': User, 'address': Address}, ...)
            await db.user.get(user_id)
            await db.address.insert(address)
        """
        models = self.__dict__.get("_models")
        model_odms = self.__dict__.get("_model_odms", {})
        if models is not None and name in model_odms:
            # Ensure parent is initialized when accessing child ODM
            # This allows document creation to work (Beanie requires init before creating instances)
            if not self._is_initialized:
                # In async context, we can't initialize here synchronously
                # But we'll initialize on first operation via the child ODM
                pass
            return model_odms[name]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def is_async(self) -> bool:
        """
        Determine if this backend operates asynchronously.

        Returns:
            bool: Always returns True as MongoDB operations are asynchronous.

        Example:
            .. code-block:: python

                backend = MongoMindtraceODM(User, "mongodb://localhost:27017", "mydb")
                if backend.is_async():
                    result = await backend.insert(user)
        """
        return True

    async def insert_one(self, obj: BaseModel | dict) -> T:
        """Insert one document. Returns the inserted document.

        Raises:
            DuplicateInsertError: If the document violates unique constraints.
        """
        if self._models is not None:
            raise ValueError("Cannot use insert_one() in multi-model mode. Use db.model_name.insert_one() instead.")

        # Auto-initialize if needed (backward compatible - works with or without explicit init)
        if not self._is_initialized:
            await self.initialize()

        # Handle DataWrapper from unified_odm (has model_dump() method that returns dict)
        if hasattr(obj, "model_dump") and not isinstance(obj, BaseModel) and obj.__class__.__name__ == "DataWrapper":
            data = obj.model_dump()
        elif isinstance(obj, dict):
            data = obj.copy()
        else:
            data = obj.model_dump()

        # Remove both 'id' and '_id' to ensure new document (Beanie will generate _id)
        if "id" in data:
            data.pop("id")
        if "_id" in data:
            data.pop("_id")

        doc = self.model_cls(**data)
        doc.id = None

        try:
            return await doc.insert()
        except DuplicateKeyError as e:
            raise DuplicateInsertError(f"Duplicate key error: {str(e)}")

    async def insert(self, obj: BaseModel | dict) -> T:
        """Legacy: insert a document. Prefer ``insert_one``."""
        return await self.insert_one(obj)

    async def get(self, id: str | PydanticObjectId, fetch_links: bool = False) -> T:
        """Legacy: retrieve a document by id. Prefer ``find_one``."""
        if self._models is not None:
            raise ValueError("Cannot use get() in multi-model mode. Use db.model_name.get() instead.")

        # Auto-initialize if needed (backward compatible)
        if not self._is_initialized:
            await self.initialize()

        doc = await self.model_cls.get(id, fetch_links=fetch_links)
        if not doc:
            raise DocumentNotFoundError(f"Object with id {id} not found")
        return doc

    async def update(self, obj: BaseModel) -> T:
        """Legacy: full-document save by id. Prefer ``update_one``."""
        if self._models is not None:
            raise ValueError("Cannot use update() in multi-model mode. Use db.model_name.update() instead.")

        # Auto-initialize if needed
        if not self._is_initialized:
            await self.initialize()

        # Check if obj is already a document instance
        if isinstance(obj, self.model_cls):
            # If it's already a document instance, just save it
            if not obj.id:
                raise DocumentNotFoundError("Document must have an id to be updated")
            await obj.save()
            return obj
        else:
            # If it's a BaseModel, we need to get the existing document first
            if not hasattr(obj, "id") or not obj.id:
                raise DocumentNotFoundError("Document must have an id to be updated")

            doc = await self.model_cls.get(obj.id)
            if not doc:
                raise DocumentNotFoundError(f"Object with id {obj.id} not found")

            # Update the document fields
            for key, value in obj.model_dump(exclude={"id"}).items():
                setattr(doc, key, value)

            await doc.save()
            return doc

    async def delete(self, id: str):
        """Legacy: delete a document by id. Prefer ``delete_one``."""
        if self._models is not None:
            raise ValueError("Cannot use delete() in multi-model mode. Use db.model_name.delete() instead.")

        # Auto-initialize if needed (backward compatible)
        if not self._is_initialized:
            await self.initialize()

        doc = await self.model_cls.get(id)
        if doc:
            await doc.delete()
        else:
            raise DocumentNotFoundError(f"Object with id {id} not found")

    async def all(self) -> List[T]:
        """Legacy: retrieve all documents. Prefer ``find()``."""
        if self._models is not None:
            raise ValueError("Cannot use all() in multi-model mode. Use db.model_name.all() instead.")

        # Auto-initialize if needed (backward compatible)
        if not self._is_initialized:
            await self.initialize()

        return await self.model_cls.find_all().to_list()

    def _translate_filter(self, filter_dict: dict | None) -> dict:
        """Translate portable filters to Mongo syntax.

        Portable convention: list/tuple values represent IN queries.
        Existing explicit operator dicts (e.g. {"$in": ...}) are preserved.
        """
        translated: dict[str, Any] = {}
        if not filter_dict:
            return translated
        for key, value in filter_dict.items():
            if str(key).startswith("$"):
                if key in {"$or", "$and", "$nor"} and isinstance(value, list):
                    translated[key] = [
                        self._translate_filter(clause) if isinstance(clause, dict) else clause for clause in value
                    ]
                else:
                    translated[key] = value
            elif isinstance(value, (list, tuple)):
                translated[key] = {"$in": list(value)}
            else:
                translated[key] = value
        return translated

    def _to_set_update(self, set_fields: dict) -> dict:
        """Accept either portable set_fields or Mongo update docs."""
        if any(str(k).startswith("$") for k in set_fields.keys()):
            return set_fields
        return {"$set": set_fields}

    async def find(
        self,
        where: dict | None = None,
        sort: list[tuple[str, int]] | None = None,
        limit: int | None = None,
        fetch_links: bool = False,
        **kwargs,
    ) -> List[T]:
        """Find documents matching a portable filter.

        Args:
            where: Portable filter dict (equality, list-as-IN, ``$or``).
            sort: ``[(field, 1|-1), ...]`` pairs.
            limit: Maximum number of results.
            fetch_links: If True, fetch linked documents (Beanie feature).

        Returns:
            list[T]: Matching documents.
        """
        if self._models is not None:
            raise ValueError("Cannot use find() in multi-model mode. Use db.model_name.find() instead.")

        # Auto-initialize if needed (backward compatible)
        if not self._is_initialized:
            await self.initialize()

        mongo_filter = self._translate_filter(where or {})
        query = self.model_cls.find(mongo_filter, fetch_links=fetch_links, **kwargs)
        if sort:
            query = query.sort(sort)
        if limit is not None:
            query = query.limit(max(0, limit))
        return await query.to_list()

    async def aggregate(self, pipeline: list) -> List[T]:
        """
        Execute a MongoDB aggregation pipeline.

        Args:
            pipeline (list): The aggregation pipeline stages.

        Returns:
            list: The aggregation results.

        Example:
            .. code-block:: python

                # Group users by age and count
                pipeline = [
                    {"$group": {"_id": "$age", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}}
                ]
                results = await backend.aggregate(pipeline)
        """
        # Auto-initialize if needed (backward compatible)
        if not self._is_initialized:
            await self.initialize()
        return await self.model_cls.get_motor_collection().aggregate(pipeline).to_list(None)

    async def find_one(self, where: dict, sort: list[tuple[str, int]] | None = None) -> T | None:
        """Find first document matching *where*. Returns None when empty."""
        if self._models is not None:
            raise ValueError("Cannot use find_one() in multi-model mode. Use db.model_name.find_one() instead.")
        docs = await self.find(where=where, sort=sort, limit=1)
        return docs[0] if docs else None

    async def update_one(
        self,
        where: dict,
        set_fields: dict,
        upsert: bool = False,
        return_document: str = "none",
    ) -> Any:
        """Update exactly one matching document (partial field update).

        Args:
            where: Portable filter dict.
            set_fields: Fields to update (``$set`` semantics).
            upsert: Insert a new document when no match exists.
            return_document: ``"none"`` | ``"before"`` | ``"after"``.
        """
        if self._models is not None:
            raise ValueError("Cannot use update_one() in multi-model mode. Use db.model_name.update_one() instead.")
        if return_document not in {"none", "before", "after"}:
            raise ValueError("return_document must be one of: 'none', 'before', 'after'")
        if not self._is_initialized:
            await self.initialize()

        collection = self.model_cls.get_motor_collection()
        mongo_filter = self._translate_filter(where)
        mongo_update = self._to_set_update(set_fields)

        if return_document == "none":
            return await collection.update_one(mongo_filter, mongo_update, upsert=upsert)

        return_doc = ReturnDocument.BEFORE if return_document == "before" else ReturnDocument.AFTER
        return await collection.find_one_and_update(
            mongo_filter,
            mongo_update,
            upsert=upsert,
            return_document=return_doc,
        )


    async def delete_one(self, where: dict) -> int:
        """Delete exactly one matching document. Returns 0 or 1."""
        if self._models is not None:
            raise ValueError("Cannot use delete_one() in multi-model mode. Use db.model_name.delete_one() instead.")
        if not self._is_initialized:
            await self.initialize()
        collection = self.model_cls.get_motor_collection()
        result = await collection.delete_one(self._translate_filter(where))
        return result.deleted_count if result else 0

    async def delete_many(self, where: dict) -> int:
        """Delete all matching documents. Returns deleted count."""
        if self._models is not None:
            raise ValueError("Cannot use delete_many() in multi-model mode. Use db.model_name.delete_many() instead.")
        if not self._is_initialized:
            await self.initialize()
        collection = self.model_cls.get_motor_collection()
        result = await collection.delete_many(self._translate_filter(where))
        return result.deleted_count if result else 0

    async def distinct(self, field: str, where: dict | None = None) -> list[Any]:
        """Return distinct values for *field* among documents matching *where*."""
        if self._models is not None:
            raise ValueError("Cannot use distinct() in multi-model mode. Use db.model_name.distinct() instead.")
        if not self._is_initialized:
            await self.initialize()
        collection = self.model_cls.get_motor_collection()
        values = await collection.distinct(field, self._translate_filter(where or {}))
        return sorted(values)

    def get_raw_model(self) -> Type[T]:
        """
        Get the raw document model class used by this backend.

        Returns:
            Type[ModelType]: The document model class.

        Raises:
            ValueError: If in multi-model mode (use db.model_name.get_raw_model() instead).

        Example:
            .. code-block:: python

                model_class = backend.get_raw_model()
                print(f"Using model: {model_class.__name__}")
        """
        if self._models is not None:
            raise ValueError(
                "Cannot use get_raw_model() in multi-model mode. Use db.model_name.get_raw_model() instead."
            )
        return self.model_cls

    # Synchronous wrapper methods for compatibility
    def initialize_sync(self, allow_index_dropping: bool = False):
        """
        Initialize the MongoDB connection synchronously (wrapper around async initialize).
        This method provides a synchronous interface to the async initialize method.
        It should be called before performing any database operations in a sync context.

        Args:
            allow_index_dropping: If True, allows Beanie to drop and recreate conflicting indexes.
                Useful in test environments. Defaults to False.

        Example:
            .. code-block:: python

                backend = MongoMindtraceODM(User, "mongodb://localhost:27017", "mydb")
                backend.initialize_sync()  # Can be called from sync code
        """
        if self._is_initialized:
            return
        self._run_sync(self.initialize(allow_index_dropping=allow_index_dropping))

    def insert_sync(self, obj: BaseModel) -> T:
        """Legacy sync wrapper. Prefer ``insert_one_sync``."""
        return self._run_sync(self.insert(obj))

    def get_sync(self, id: str | PydanticObjectId) -> T:
        """Legacy sync wrapper. Prefer ``find_one_sync``."""
        return self._run_sync(self.get(id))

    def delete_sync(self, id: str):
        """Legacy sync wrapper. Prefer ``delete_one_sync``."""
        return self._run_sync(self.delete(id))

    def update_sync(self, obj: BaseModel) -> T:
        """Legacy sync wrapper. Prefer ``update_one_sync``."""
        return self._run_sync(self.update(obj))

    def all_sync(self) -> List[T]:
        """Legacy sync wrapper. Prefer ``find_sync``."""
        return self._run_sync(self.all())

    def find_sync(
        self,
        where: dict | None = None,
        sort: list[tuple[str, int]] | None = None,
        limit: int | None = None,
        **kwargs,
    ) -> List[T]:
        """Find documents synchronously (wrapper around async find)."""
        return self._run_sync(self.find(where=where, sort=sort, limit=limit, **kwargs))

    def _get_sync_loop(self) -> asyncio.AbstractEventLoop:
        """Return a long-lived event loop running in a dedicated daemon thread.

        Motor's ``AsyncIOMotorClient`` binds to the first event loop it
        touches.  ``asyncio.run()`` creates **and closes** a new loop every
        call, so subsequent motor operations hit a closed loop.

        Instead we spin up a background thread running ``loop.run_forever()``.
        Any caller thread can then submit coroutines lock-free via
        ``asyncio.run_coroutine_threadsafe()``.
        """
        # Walk up to the root ODM so all children share the same loop.
        root = self
        while root._parent_odm is not None:
            root = root._parent_odm

        if root._sync_loop is not None and not root._sync_loop.is_closed():
            return root._sync_loop

        with root._sync_loop_lock:
            # Double-check after acquiring the lock.
            if root._sync_loop is not None and not root._sync_loop.is_closed():
                return root._sync_loop
            root._sync_loop = asyncio.new_event_loop()
            root._sync_thread = threading.Thread(
                target=root._sync_loop.run_forever,
                daemon=True,
                name="mongo-odm-loop",
            )
            root._sync_thread.start()
        return root._sync_loop

    def _run_sync(self, coro):
        """Run an async coroutine synchronously.  Lock-free and thread-safe.

        Submits the coroutine to the dedicated background event-loop thread
        via ``run_coroutine_threadsafe`` and blocks the calling thread until
        the result is ready.  Multiple threads can call this concurrently —
        the event loop multiplexes the work over motor's connection pool.
        """
        try:
            asyncio.get_running_loop()
            # We're inside an async context — close the coroutine to avoid
            # "coroutine was never awaited" warnings, then raise.
            coro.close()
            raise RuntimeError("Sync wrapper called from async context. Use the async method instead.")
        except RuntimeError as e:
            if "no running event loop" in str(e).lower():
                loop = self._get_sync_loop()
                future = asyncio.run_coroutine_threadsafe(coro, loop)
                return future.result()
            raise

    def aggregate_sync(self, pipeline: list) -> list:
        """Execute aggregation pipeline synchronously (wrapper around async aggregate)."""
        return self._run_sync(self.aggregate(pipeline))

    def insert_one_sync(self, doc: BaseModel | dict) -> T:
        """Insert one document synchronously (wrapper around async insert_one)."""
        return self._run_sync(self.insert_one(doc))

    def find_one_sync(self, where: dict, sort: list[tuple[str, int]] | None = None) -> T | None:
        """Find one document synchronously."""
        return self._run_sync(self.find_one(where, sort=sort))

    def update_one_sync(
        self,
        where: dict,
        set_fields: dict,
        upsert: bool = False,
        return_document: str = "none",
    ) -> Any:
        """Update one matching document synchronously."""
        return self._run_sync(
            self.update_one(where, set_fields, upsert=upsert, return_document=return_document)
        )



    def delete_one_sync(self, where: dict) -> int:
        """Delete one document synchronously."""
        return self._run_sync(self.delete_one(where))

    def delete_many_sync(self, where: dict) -> int:
        """Delete documents synchronously."""
        return self._run_sync(self.delete_many(where=where))

    def distinct_sync(self, field: str, where: dict | None = None) -> list[Any]:
        """Return distinct values for field matching filter synchronously."""
        return self._run_sync(self.distinct(field, where))
