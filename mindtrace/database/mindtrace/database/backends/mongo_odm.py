import asyncio
from typing import Dict, List, Optional, Type, TypeVar

from beanie import Document, PydanticObjectId, init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
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

        self.client = AsyncIOMotorClient(db_uri)
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
                )
                # Share the same client instance
                odm.client = self.client
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
                    asyncio.run(self._do_initialize())
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
        if self._models is not None and name in self._model_odms:
            # Ensure parent is initialized when accessing child ODM
            # This allows document creation to work (Beanie requires init before creating instances)
            if not self._is_initialized:
                # In async context, we can't initialize here synchronously
                # But we'll initialize on first operation via the child ODM
                pass
            return self._model_odms[name]
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

    async def insert(self, obj: BaseModel | dict) -> T:
        """
        Insert a new document into the MongoDB collection.

        Args:
            obj (BaseModel): The document object to insert into the database.
                Can be a BaseModel instance or a Beanie Document. If it's a Document
                created before initialization, it will be recreated from dict data.

        Returns:
            ModelType: The inserted document with generated fields populated.

        Raises:
            DuplicateInsertError: If the document violates unique constraints.
            ValueError: If in multi-model mode (use db.model_name.insert() instead).

        Example:
            .. code-block:: python

                user = User(name="John", email="john@example.com")
                try:
                    inserted_user = await backend.insert(user)
                    print(f"Inserted user with ID: {inserted_user.id}")
                except DuplicateInsertError as e:
                    print(f"Duplicate entry: {e}")
        """
        if self._models is not None:
            raise ValueError("Cannot use insert() in multi-model mode. Use db.model_name.insert() instead.")

        # Auto-initialize if needed (backward compatible - works with or without explicit init)
        if not self._is_initialized:
            await self.initialize()

        # Handle DataWrapper from unified_odm (has model_dump() method that returns dict)
        if hasattr(obj, "model_dump") and not isinstance(obj, BaseModel) and obj.__class__.__name__ == "DataWrapper":
            data = obj.model_dump()
        elif isinstance(obj, dict):
            data = obj.copy()
            # Beanie handles Document objects in dicts directly for Link fields
            # No conversion needed - just pass the dict as-is
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
        except Exception as e:
            raise DuplicateInsertError(str(e))

    async def get(self, id: str | PydanticObjectId, fetch_links: bool = False) -> T:
        """
        Retrieve a document by its unique identifier.

        Args:
            id (str): The unique identifier of the document to retrieve.
            fetch_links (bool): If True, fetch linked documents (Beanie feature). Defaults to False.

        Returns:
            ModelType: The retrieved document.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.
            ValueError: If in multi-model mode (use db.model_name.get() instead).

        Example:
            .. code-block:: python

                try:
                    user = await backend.get("507f1f77bcf86cd799439011")
                    print(f"Found user: {user.name}")

                    # With linked documents
                    user = await backend.get("507f1f77bcf86cd799439011", fetch_links=True)
                    print(f"User address: {user.address.street}")
                except DocumentNotFoundError:
                    print("User not found")
        """
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
        """
        Update an existing document in the MongoDB collection.

        The document object should have been retrieved from the database,
        modified, and then passed to this method to save the changes.

        Args:
            obj (BaseModel): The document object with modified fields to save.

        Returns:
            ModelType: The updated document.

        Raises:
            DocumentNotFoundError: If the document doesn't exist in the database.
            ValueError: If in multi-model mode (use db.model_name.update() instead).

        Example:
            .. code-block:: python

                # Get the document
                user = await backend.get("507f1f77bcf86cd799439011")
                # Modify it
                user.age = 31
                user.name = "John Updated"
                # Save the changes
                updated_user = await backend.update(user)
        """
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
        """
        Delete a document by its unique identifier.

        Args:
            id (str): The unique identifier of the document to delete.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.
            ValueError: If in multi-model mode (use db.model_name.delete() instead).

        Example:
            .. code-block:: python

                try:
                    await backend.delete("507f1f77bcf86cd799439011")
                    print("User deleted successfully")
                except DocumentNotFoundError:
                    print("User not found")
        """
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
        """
        Retrieve all documents from the collection.

        Returns:
            List[ModelType]: A list of all documents in the collection.

        Raises:
            ValueError: If in multi-model mode (use db.model_name.all() instead).

        Example:
            .. code-block:: python

                all_users = await backend.all()
                print(f"Found {len(all_users)} users")
                for user in all_users:
                    print(f"- {user.name}")
        """
        if self._models is not None:
            raise ValueError("Cannot use all() in multi-model mode. Use db.model_name.all() instead.")

        # Auto-initialize if needed (backward compatible)
        if not self._is_initialized:
            await self.initialize()

        return await self.model_cls.find_all().to_list()

    async def find(self, *args, fetch_links: bool = False, **kwargs) -> List[T]:
        """
        Find documents matching the specified criteria.

        Args:
            *args: Query conditions and filters.
            fetch_links (bool): If True, fetch linked documents (Beanie feature). Defaults to False.
            **kwargs: Additional query parameters.

        Returns:
            List[ModelType]: A list of documents matching the query criteria.

        Raises:
            ValueError: If in multi-model mode (use db.model_name.find() instead).

        Example:
            .. code-block:: python

                # Find users with specific email
                users = await backend.find(User.email == "john@example.com")

                # Find users with name containing "John"
                users = await backend.find({"name": {"$regex": "John"}})

                # Find users with linked documents
                users = await backend.find(User.name == "Alice", fetch_links=True)
        """
        if self._models is not None:
            raise ValueError("Cannot use find() in multi-model mode. Use db.model_name.find() instead.")

        # Auto-initialize if needed (backward compatible)
        if not self._is_initialized:
            await self.initialize()

        # Remove fetch_links from kwargs if present (it's a parameter, not a query field)
        kwargs_without_fetch_links = {k: v for k, v in kwargs.items() if k != "fetch_links"}

        # In Beanie, fetch_links is passed as a parameter to find(), not called as a method
        query = self.model_cls.find(*args, fetch_links=fetch_links, **kwargs_without_fetch_links)
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
        # Idempotent - return early if already initialized
        if self._is_initialized:
            return

        try:
            # Check if we're already in an async context
            _ = asyncio.get_running_loop()
            # We're in an async context, so we can't use asyncio.run()
            # The caller should use await initialize() directly
            raise RuntimeError("initialize_sync() called from async context. Use await initialize() instead.")
        except RuntimeError as e:
            # Check if this is the "no running event loop" error from get_running_loop()
            if "no running event loop" in str(e).lower():
                # No running loop, safe to use asyncio.run()
                # Call initialize() to maintain consistency and allow mocking
                asyncio.run(self.initialize(allow_index_dropping=allow_index_dropping))
            else:
                # Re-raise if it's a different RuntimeError (like our custom one)
                raise

    def insert_sync(self, obj: BaseModel) -> T:
        """
        Insert a new document synchronously (wrapper around async insert).

        Args:
            obj (BaseModel): The document object to insert into the database.

        Returns:
            ModelType: The inserted document with generated fields populated.

        Raises:
            DuplicateInsertError: If the document violates unique constraints.

        Example:
            .. code-block:: python

                user = User(name="John", email="john@example.com")
                try:
                    inserted_user = backend.insert_sync(user)
                    print(f"Inserted user with ID: {inserted_user.id}")
                except DuplicateInsertError as e:
                    print(f"Duplicate entry: {e}")
        """
        try:
            _ = asyncio.get_running_loop()
            # We're in an async context, raise error
            raise RuntimeError("insert_sync() called from async context. Use await insert() instead.")
        except RuntimeError as e:
            # Check if this is the "no running event loop" error from get_running_loop()
            if "no running event loop" in str(e).lower():
                # No running loop, safe to use asyncio.run()
                return asyncio.run(self.insert(obj))
            else:
                # Re-raise if it's a different RuntimeError (like our custom one)
                raise

    def get_sync(self, id: str | PydanticObjectId) -> T:
        """
        Retrieve a document synchronously (wrapper around async get).

        Args:
            id (str): The unique identifier of the document to retrieve.

        Returns:
            ModelType: The retrieved document.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.

        Example:
            .. code-block:: python

                try:
                    user = backend.get_sync("507f1f77bcf86cd799439011")
                    print(f"Found user: {user.name}")
                except DocumentNotFoundError:
                    print("User not found")
        """
        try:
            _ = asyncio.get_running_loop()
            # We're in an async context, raise error
            raise RuntimeError("get_sync() called from async context. Use await get() instead.")
        except RuntimeError as e:
            # Check if this is the "no running event loop" error from get_running_loop()
            if "no running event loop" in str(e).lower():
                # No running loop, safe to use asyncio.run()
                return asyncio.run(self.get(id))
            else:
                # Re-raise if it's a different RuntimeError (like our custom one)
                raise

    def delete_sync(self, id: str):
        """
        Delete a document synchronously (wrapper around async delete).

        Args:
            id (str): The unique identifier of the document to delete.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.

        Example:
            .. code-block:: python

                try:
                    backend.delete_sync("507f1f77bcf86cd799439011")
                    print("User deleted successfully")
                except DocumentNotFoundError:
                    print("User not found")
        """
        try:
            _ = asyncio.get_running_loop()
            # We're in an async context, raise error
            raise RuntimeError("delete_sync() called from async context. Use await delete() instead.")
        except RuntimeError as e:
            # Check if this is the "no running event loop" error from get_running_loop()
            if "no running event loop" in str(e).lower():
                # No running loop, safe to use asyncio.run()
                return asyncio.run(self.delete(id))
            else:
                # Re-raise if it's a different RuntimeError (like our custom one)
                raise

    def update_sync(self, obj: BaseModel) -> T:
        """
        Update an existing document synchronously (wrapper around async update).

        Args:
            obj (BaseModel): The document object with modified fields to save.

        Returns:
            ModelType: The updated document.

        Raises:
            DocumentNotFoundError: If the document doesn't exist in the database.

        Example:
            .. code-block:: python

                # Get the document
                user = backend.get_sync("507f1f77bcf86cd799439011")
                # Modify it
                user.age = 31
                user.name = "John Updated"
                # Save the changes
                updated_user = backend.update_sync(user)
        """
        try:
            _ = asyncio.get_running_loop()
            # We're in an async context, raise error
            raise RuntimeError("update_sync() called from async context. Use await update() instead.")
        except RuntimeError as e:
            # Check if this is the "no running event loop" error from get_running_loop()
            if "no running event loop" in str(e).lower():
                # No running loop, safe to use asyncio.run()
                return asyncio.run(self.update(obj))
            else:
                # Re-raise if it's a different RuntimeError (like our custom one)
                raise

    def all_sync(self) -> List[T]:
        """
        Retrieve all documents synchronously (wrapper around async all).

        Returns:
            List[ModelType]: A list of all documents in the collection.

        Example:
            .. code-block:: python

                all_users = backend.all_sync()
                print(f"Found {len(all_users)} users")
                for user in all_users:
                    print(f"- {user.name}")
        """
        try:
            _ = asyncio.get_running_loop()
            # We're in an async context, raise error
            raise RuntimeError("all_sync() called from async context. Use await all() instead.")
        except RuntimeError as e:
            # Check if this is the "no running event loop" error from get_running_loop()
            if "no running event loop" in str(e).lower():
                # No running loop, safe to use asyncio.run()
                return asyncio.run(self.all())
            else:
                # Re-raise if it's a different RuntimeError (like our custom one)
                raise

    def find_sync(self, *args, **kwargs) -> List[T]:
        """
        Find documents synchronously (wrapper around async find).

        Args:
            *args: Query conditions and filters.
            **kwargs: Additional query parameters.

        Returns:
            List[ModelType]: A list of documents matching the query criteria.

        Example:
            .. code-block:: python

                # Find users with specific email
                users = backend.find_sync(User.email == "john@example.com")

                # Find users with name containing "John"
                users = backend.find_sync({"name": {"$regex": "John"}})
        """
        try:
            _ = asyncio.get_running_loop()
            # We're in an async context, raise error
            raise RuntimeError("find_sync() called from async context. Use await find() instead.")
        except RuntimeError as e:
            # Check if this is the "no running event loop" error from get_running_loop()
            if "no running event loop" in str(e).lower():
                # No running loop, safe to use asyncio.run()
                return asyncio.run(self.find(*args, **kwargs))
            else:
                # Re-raise if it's a different RuntimeError (like our custom one)
                raise
