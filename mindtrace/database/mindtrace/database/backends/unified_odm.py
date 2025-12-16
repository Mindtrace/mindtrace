import asyncio
from enum import Enum
from typing import List, Optional, Type, TypeVar, Union

from pydantic import BaseModel, Field

from mindtrace.database.backends.mindtrace_odm import InitMode, MindtraceODM
from mindtrace.database.backends.mongo_odm import MindtraceDocument, MongoMindtraceODM
from mindtrace.database.backends.redis_odm import MindtraceRedisDocument, RedisMindtraceODM


class BackendType(Enum):
    MONGO = "mongo"
    REDIS = "redis"


class UnifiedMindtraceDocument(BaseModel):
    """
    Unified document model that works with both MongoDB and Redis backends.

    Simply define your fields and the backend will handle the rest automatically.
    No abstract methods to implement - just declare your fields and go!

    Example:
        class User(UnifiedMindtraceDocument):
            name: str
            age: int
            email: str = Field(index=True)

            class Meta:
                collection_name = "users"
                unique_fields = ["email"]
    """

    # Optional ID field that can be used by both backends
    id: Optional[str] = Field(default=None, description="Document ID")

    class Config:
        """Common configuration for unified documents."""

        # Allow arbitrary types for flexibility
        arbitrary_types_allowed = True
        # Use enum values for serialization
        use_enum_values = True
        # Validate assignment
        validate_assignment = True

    class Meta:
        """
        Simple metadata class for document configuration.
        Override this in your model class to customize behavior.
        """

        # Collection/key prefix name
        collection_name: str = "unified_documents"
        # Global key prefix for Redis
        global_key_prefix: str = "mindtrace"
        # Whether to use cache (MongoDB specific, ignored by Redis)
        use_cache: bool = False
        # Index hints for both backends
        indexed_fields: List[str] = []
        # Unique constraints (basic support)
        unique_fields: List[str] = []

    @classmethod
    def _auto_generate_mongo_model(cls) -> Type[MindtraceDocument]:
        """Automatically generate a MongoDB-compatible model from the unified model."""
        from typing import Annotated

        from beanie import Indexed

        # Get field annotations from the original class, excluding inherited ones
        cls_annotations = getattr(cls, "__annotations__", {})
        meta = getattr(cls, "Meta", cls.Meta)

        # Get the original field values from the class
        cls_fields = {}
        for field_name in cls_annotations:
            if hasattr(cls, field_name):
                cls_fields[field_name] = getattr(cls, field_name)

        # Use a simpler approach without exec to avoid annotation issues

        # Build field dictionary properly
        # fields = {}
        annotations = {}

        for field_name, field_type in cls_annotations.items():
            if field_name == "id":
                continue  # Skip id field for MongoDB

            # Handle field annotations properly
            if hasattr(meta, "unique_fields") and field_name in meta.unique_fields:
                annotations[field_name] = Annotated[field_type, Indexed(unique=True)]
            elif hasattr(meta, "indexed_fields") and field_name in meta.indexed_fields:
                annotations[field_name] = Annotated[field_type, Indexed()]
            else:
                annotations[field_name] = field_type

        # Create the class attributes dictionary
        class_dict = {
            "__annotations__": annotations,
            "__module__": cls.__module__,
        }

        # For Beanie, we need to set the Settings class after creation
        # to avoid Pydantic v2 annotation issues

        # Create the dynamic class using type()
        DynamicMongoModel = type(f"{cls.__name__}Mongo", (MindtraceDocument,), class_dict)

        # Now set the Settings class after creation to avoid Pydantic annotation issues
        settings_attrs = {
            "name": getattr(meta, "collection_name", "unified_documents"),
            "use_cache": getattr(meta, "use_cache", False),
        }
        SettingsClass = type("Settings", (), settings_attrs)
        setattr(DynamicMongoModel, "Settings", SettingsClass)

        return DynamicMongoModel

    @classmethod
    def _auto_generate_redis_model(cls) -> Type[MindtraceRedisDocument]:
        """Automatically generate a Redis-compatible model from the unified model."""
        from typing import Union, get_args, get_origin

        from redis_om import Field as RedisField

        # Get field annotations from the original class, excluding inherited ones
        cls_annotations = getattr(cls, "__annotations__", {})
        meta = getattr(cls, "Meta", cls.Meta)

        # Get the original field values/defaults from the class
        cls_fields = {}
        for field_name in cls_annotations:
            if hasattr(cls, field_name):
                cls_fields[field_name] = getattr(cls, field_name)

        # Use a simpler approach without exec to avoid annotation issues

        # Build field dictionary properly
        fields = {}
        annotations = {}

        for field_name, field_type in cls_annotations.items():
            if field_name == "id":
                continue  # Skip id field for Redis

            # Handle optional fields properly
            is_optional = False
            base_type = field_type

            # Check if the field is Optional (Union[X, None])
            if get_origin(field_type) is Union:
                args = get_args(field_type)
                if len(args) == 2 and type(None) in args:
                    is_optional = True
                    base_type = args[0] if args[1] is type(None) else args[1]

            # Check if field has a default value from Pydantic Field
            field_default = None
            if field_name in cls_fields:
                field_info = cls_fields[field_name]
                if hasattr(field_info, "default") and field_info.default is not ...:
                    field_default = field_info.default
                elif hasattr(field_info, "default_factory") and field_info.default_factory is not None:
                    field_default = field_info.default_factory()

            # For Redis, preserve the optional nature in annotations
            if is_optional:
                annotations[field_name] = Union[base_type, type(None)]
            else:
                annotations[field_name] = base_type

            # Create Redis field with proper defaults
            # Only index fields that are explicitly marked as indexed
            should_index = hasattr(meta, "indexed_fields") and field_name in meta.indexed_fields

            if should_index:
                if is_optional or field_default is not None:
                    fields[field_name] = RedisField(index=True, default=field_default)
                else:
                    fields[field_name] = RedisField(index=True)
            else:
                # For non-indexed fields, explicitly disable indexing
                if is_optional or field_default is not None:
                    fields[field_name] = RedisField(index=False, default=field_default)
                else:
                    fields[field_name] = RedisField(index=False)

        # Create the Meta class first - this must be done before class creation
        # so that Redis-OM can properly initialize its internal mechanisms
        parent_meta = MindtraceRedisDocument.Meta
        class_name = f"{cls.__name__}Redis"
        meta_attrs = {
            "global_key_prefix": getattr(meta, "global_key_prefix", "mindtrace"),
            "index_name": f"{getattr(meta, 'global_key_prefix', 'mindtrace')}:{class_name}:index",
            "model_key_prefix": class_name,  # Set the model key prefix to match the class name
        }
        MetaClass = type("Meta", (parent_meta,), meta_attrs)

        # Create the class attributes dictionary
        class_dict = {
            "__annotations__": annotations,
            "__module__": cls.__module__,
            "Meta": MetaClass,
        }

        # Add field instances to the class dict
        class_dict.update(fields)

        # Create the dynamic class using type()
        DynamicRedisModel = type(f"{cls.__name__}Redis", (MindtraceRedisDocument,), class_dict)

        return DynamicRedisModel

    @classmethod
    def get_meta(cls):
        """
        Get the metadata configuration for this document model.

        Returns:
            Meta: The metadata class containing configuration settings.

        Example:
            .. code-block:: python

                class User(UnifiedMindtraceDocument):
                    name: str

                    class Meta:
                        collection_name = "users"

                meta = User.get_meta()
                print(meta.collection_name)  # Output: "users"
        """
        return getattr(cls, "Meta", cls.Meta)

    def to_mongo_dict(self) -> dict:
        """
        Convert this document to a MongoDB-compatible dictionary.

        This method transforms the unified document format to one that's
        compatible with MongoDB's document structure, removing the 'id' field
        since MongoDB uses '_id' internally.

        Returns:
            dict: A dictionary representation suitable for MongoDB storage.

        Example:
            .. code-block:: python

                user = User(id="123", name="John", email="john@example.com")
                mongo_dict = user.to_mongo_dict()
                print(mongo_dict)  # Output: {"name": "John", "email": "john@example.com"}
        """
        data = self.model_dump(exclude_none=True)
        # Remove 'id' field for MongoDB as it uses '_id'
        if "id" in data:
            del data["id"]
        return data

    def to_redis_dict(self) -> dict:
        """
        Convert this document to a Redis-compatible dictionary.

        This method transforms the unified document format to one that's
        compatible with Redis storage, converting the 'id' field to 'pk'
        (primary key) as expected by redis-om.

        Returns:
            dict: A dictionary representation suitable for Redis storage.

        Example:
            .. code-block:: python

                user = User(id="123", name="John", email="john@example.com")
                redis_dict = user.to_redis_dict()
                print(redis_dict)  # Output: {"pk": "123", "name": "John", "email": "john@example.com"}
        """
        data = self.model_dump(exclude_none=True)
        # Redis uses 'pk' field instead of 'id'
        if "id" in data:
            if data["id"] is not None:
                data["pk"] = data["id"]
            del data["id"]
        return data


ModelType = TypeVar("ModelType", bound=Union[MindtraceDocument, MindtraceRedisDocument, UnifiedMindtraceDocument])


class DataWrapper:
    """
    Simple wrapper for data that can be serialized by backend systems.

    This class provides a lightweight wrapper around dictionary data that
    implements the model_dump interface expected by ODM backends, allowing
    raw data to be passed through the backend processing pipeline.

    Args:
        data (dict): The dictionary data to wrap.

    Example:
        .. code-block:: python

            data = {"name": "John", "email": "john@example.com"}
            wrapper = DataWrapper(data)
            serialized = wrapper.model_dump()
            print(serialized)  # Output: {"name": "John", "email": "john@example.com"}
    """

    def __init__(self, data: dict):
        """
        Initialize the data wrapper.

        Args:
            data (dict): The dictionary data to wrap.
        """
        self.data = data

    def model_dump(self, **kwargs) -> dict:
        """
        Return the wrapped data as a dictionary.

        Args:
            **kwargs: Additional keyword arguments (ignored for compatibility).

        Returns:
            dict: The wrapped dictionary data.

        Example:
            .. code-block:: python

                wrapper = DataWrapper({"key": "value"})
                data = wrapper.model_dump()
                print(data)  # Output: {"key": "value"}
        """
        return self.data


class UnifiedMindtraceODM(MindtraceODM):
    """
    A unified backend that works with both MongoDB and Redis backends.

    This class provides a consistent interface over both backends, supporting only
    the intersection of features available in both:
    - insert, get, delete, all, find operations
    - Common exception handling
    - Automatic backend detection and initialization

    Note: Advanced features like MongoDB's aggregation are not supported
    to maintain compatibility with both backends.
    """

    def __init__(
        self,
        unified_model_cls: Optional[Type[UnifiedMindtraceDocument]] = None,
        mongo_model_cls: Optional[Type[MindtraceDocument]] = None,
        redis_model_cls: Optional[Type[MindtraceRedisDocument]] = None,
        mongo_db_uri: Optional[str] = None,
        mongo_db_name: Optional[str] = None,
        redis_url: Optional[str] = None,
        preferred_backend: BackendType = BackendType.MONGO,
        allow_index_dropping: bool = False,
        auto_init: bool = False,
        init_mode: InitMode | None = None,
    ):
        """
        Initialize the unified backend with both MongoDB and Redis configurations.

        Args:
            unified_model_cls: Unified document model class (preferred)
            mongo_model_cls: MongoDB document model class (fallback)
            redis_model_cls: Redis document model class (fallback)
            mongo_db_uri: MongoDB connection URI
            mongo_db_name: MongoDB database name
            redis_url: Redis connection URL
            preferred_backend: Which backend to prefer when both are available
            allow_index_dropping: If True, allows MongoDB to drop and recreate
                conflicting indexes. Useful in test environments. Defaults to False.
            auto_init: If True, automatically initializes backends in sync contexts.
                In async contexts, initialization is deferred. Defaults to False for backward
                compatibility. Operations will auto-initialize on first use regardless.
            init_mode: Initialization mode for both backends. If None, MongoDB defaults to
                InitMode.ASYNC and Redis defaults to InitMode.SYNC. If provided, both backends
                will use the same initialization mode.
        """
        super().__init__()
        self.mongo_backend = None
        self.redis_backend = None
        self.preferred_backend = preferred_backend
        self._active_backend = None
        self.unified_model_cls = unified_model_cls

        # If unified model is provided, generate backend-specific models automatically
        if unified_model_cls:
            if mongo_db_uri and mongo_db_name:
                mongo_model_cls = unified_model_cls._auto_generate_mongo_model()
                self.mongo_backend = MongoMindtraceODM(
                    mongo_model_cls,
                    mongo_db_uri,
                    mongo_db_name,
                    allow_index_dropping=allow_index_dropping,
                    auto_init=auto_init,
                    init_mode=init_mode,
                )

            if redis_url:
                redis_model_cls = unified_model_cls._auto_generate_redis_model()
                self.redis_backend = RedisMindtraceODM(
                    redis_model_cls,
                    redis_url,
                    auto_init=auto_init,
                    init_mode=init_mode,
                )
        else:
            # Fallback to individual model classes
            if mongo_model_cls and mongo_db_uri and mongo_db_name:
                self.mongo_backend = MongoMindtraceODM(
                    mongo_model_cls,
                    mongo_db_uri,
                    mongo_db_name,
                    allow_index_dropping=allow_index_dropping,
                    auto_init=auto_init,
                    init_mode=init_mode,
                )

            if redis_model_cls and redis_url:
                self.redis_backend = RedisMindtraceODM(
                    redis_model_cls,
                    redis_url,
                    auto_init=auto_init,
                    init_mode=init_mode,
                )

        if not self.mongo_backend and not self.redis_backend:
            raise ValueError("At least one backend (MongoDB or Redis) must be configured")

    def _get_active_backend(self):
        """
        Get the currently active backend based on preference and availability.

        This internal method determines which backend to use based on the
        configured preference and which backends are available. It caches
        the result to avoid repeated lookups.

        Returns:
            MindtraceODM: The active backend instance.

        Raises:
            RuntimeError: If no backend is available.

        Example:
            .. code-block:: python

                # Internal method - not typically called directly
                backend = unified_backend._get_active_backend()
                print(f"Using backend: {type(backend).__name__}")
        """
        if self._active_backend:
            return self._active_backend

        if self.preferred_backend == BackendType.MONGO and self.mongo_backend:
            self._active_backend = self.mongo_backend
        elif self.preferred_backend == BackendType.REDIS and self.redis_backend:
            self._active_backend = self.redis_backend
        elif self.mongo_backend:
            self._active_backend = self.mongo_backend
        elif self.redis_backend:
            self._active_backend = self.redis_backend
        else:
            raise RuntimeError("No backend available")

        return self._active_backend

    def switch_backend(self, backend_type: BackendType):
        """
        Switch to a specific backend.

        Args:
            backend_type: The backend type to switch to

        Raises:
            ValueError: If the requested backend is not configured
        """
        if backend_type == BackendType.MONGO:
            if not self.mongo_backend:
                raise ValueError("MongoDB backend is not configured")
            self._active_backend = self.mongo_backend
        elif backend_type == BackendType.REDIS:
            if not self.redis_backend:
                raise ValueError("Redis backend is not configured")
            self._active_backend = self.redis_backend
        else:
            raise ValueError(f"Unknown backend type: {backend_type}")

    def get_current_backend_type(self) -> BackendType:
        """
        Get the currently active backend type.

        Returns:
            BackendType: The type of the currently active backend.

        Raises:
            RuntimeError: If the active backend is not recognized.

        Example:
            .. code-block:: python

                backend_type = unified_backend.get_current_backend_type()
                if backend_type == BackendType.MONGO:
                    print("Using MongoDB backend")
                elif backend_type == BackendType.REDIS:
                    print("Using Redis backend")
        """
        active = self._get_active_backend()
        if active == self.mongo_backend:
            return BackendType.MONGO
        elif active == self.redis_backend:
            return BackendType.REDIS
        else:
            raise RuntimeError("Unknown active backend")

    def is_async(self) -> bool:
        """
        Check if the currently active backend operates asynchronously.

        Returns:
            bool: True if the active backend is asynchronous, False otherwise.

        Example:
            .. code-block:: python

                if unified_backend.is_async():
                    result = await unified_backend.insert_async(document)
                else:
                    result = unified_backend.insert(document)
        """
        return self._get_active_backend().is_async()

    async def initialize_async(self, allow_index_dropping: bool | None = None):
        """
        Initialize all configured backends asynchronously.

        This method initializes both MongoDB (native async) and Redis (via async wrapper)
        backends. It should be called in an async context. If auto_init was True in __init__,
        this is only needed when called from async contexts.

        Args:
            allow_index_dropping (bool | None): If provided, overrides the value
                set in __init__ for MongoDB. If None, uses the value from __init__.

        Example:
            .. code-block:: python

                # Auto-initialized in sync context
                backend = UnifiedMindtraceODM(...)
                # Ready to use immediately

                # In async context, explicit init needed
                backend = UnifiedMindtraceODM(...)
                await backend.initialize_async()
        """
        # Initialize MongoDB backend (native async)
        if self.mongo_backend:
            if allow_index_dropping is not None:
                await self.mongo_backend.initialize(allow_index_dropping=allow_index_dropping)
            else:
                await self.mongo_backend.initialize()

        # Initialize Redis backend (via async wrapper)
        # Only initialize if not already initialized and not in ASYNC mode
        if self.redis_backend:
            # Check if Redis is in ASYNC mode - if so, defer to first operation
            redis_init_mode = getattr(self.redis_backend, "_init_mode", None)
            # Default to SYNC mode if not set (backward compatible)
            is_async_mode = redis_init_mode == InitMode.ASYNC
            # Check if already initialized (handle missing attribute gracefully)
            if hasattr(self.redis_backend, "_is_initialized"):
                attr_value = self.redis_backend._is_initialized
                # Only treat as initialized if it's explicitly a boolean True
                is_initialized = isinstance(attr_value, bool) and attr_value is True
            else:
                is_initialized = False

            if is_async_mode and not is_initialized:
                # Skip initialization - will auto-init on first operation
                pass
            elif not is_initialized:
                # Initialize Redis (either SYNC mode or default)
                if hasattr(self.redis_backend, "initialize_async"):
                    await self.redis_backend.initialize_async()
                else:
                    # Fallback to sync method if async wrapper doesn't exist
                    self.redis_backend.initialize()

    def initialize_sync(self, allow_index_dropping: bool | None = None):
        """
        Initialize all configured backends synchronously.

        This method initializes both Redis (native sync) and MongoDB (via sync wrapper)
        backends. It should be called in a synchronous context.

        Args:
            allow_index_dropping (bool | None): If provided, overrides the value
                set in __init__ for MongoDB. If None, uses the value from __init__.

        Example:
            .. code-block:: python

                # In a synchronous context
                unified_backend.initialize_sync()
        """
        # Initialize Redis backend (native sync)
        if self.redis_backend:
            self.redis_backend.initialize()

        # Initialize MongoDB backend (via sync wrapper)
        if self.mongo_backend:
            if hasattr(self.mongo_backend, "initialize_sync"):
                self.mongo_backend.initialize_sync(allow_index_dropping=allow_index_dropping)
            else:
                # Fallback to async method in event loop if sync wrapper doesn't exist
                if allow_index_dropping is not None:
                    asyncio.run(self.mongo_backend.initialize(allow_index_dropping=allow_index_dropping))
                else:
                    asyncio.run(self.mongo_backend.initialize())

    def initialize(self, allow_index_dropping: bool | None = None):
        """
        Initialize all configured backends.

        This method initializes both synchronous (Redis) and asynchronous (MongoDB)
        backends. It automatically detects the execution context and handles
        async backends appropriately. If called from an async context, it will
        print a warning and skip async initialization.

        This method is a convenience wrapper that calls initialize_sync() for sync
        initialization. For explicit control, use initialize_sync() or initialize_async().

        Args:
            allow_index_dropping (bool | None): If provided, overrides the value
                set in __init__ for MongoDB. If None, uses the value from __init__.

        Example:
            .. code-block:: python

                # In a synchronous context
                unified_backend.initialize()

                # In an async context - use this instead:
                # await unified_backend.initialize_async()
        """
        # Use initialize_sync which now handles both backends
        self.initialize_sync(allow_index_dropping=allow_index_dropping)

    def _handle_async_call(self, method_name: str, *args, **kwargs):
        """
        Handle calls to async methods by running them in the event loop.

        This internal method abstracts the complexity of calling async methods
        from synchronous code. It creates a new event loop for async operations
        when needed, providing a clean interface for unified backend operations.

        Args:
            method_name (str): The name of the method to call on the backend.
            *args: Positional arguments to pass to the method.
            **kwargs: Keyword arguments to pass to the method.

        Returns:
            Any: The result of the backend method call.

        Example:
            .. code-block:: python

                # Internal method - not typically called directly
                result = unified_backend._handle_async_call('insert', document)
        """
        backend = self._get_active_backend()

        if backend.is_async():
            # For async backends (MongoDB), use sync wrapper methods
            sync_method_name = f"{method_name}_sync"
            if hasattr(backend, sync_method_name):
                method = getattr(backend, sync_method_name)
                return method(*args, **kwargs)
            else:
                # Fallback to running async method in event loop
                method = getattr(backend, method_name)
                return asyncio.run(method(*args, **kwargs))
        else:
            # For sync backends (Redis), call method directly
            method = getattr(backend, method_name)
            return method(*args, **kwargs)

    def _convert_unified_to_backend_data(self, obj: BaseModel) -> BaseModel:
        """Convert unified model data to backend-specific format."""
        if isinstance(obj, UnifiedMindtraceDocument):
            backend_type = self.get_current_backend_type()
            if backend_type == BackendType.MONGO:
                # Convert to MongoDB format - use model_dump to get clean data
                data = obj.model_dump(exclude_none=True)
                # Remove 'id' field for MongoDB as it uses '_id'
                if "id" in data:
                    del data["id"]
                # Create a simple data wrapper instead of actual model instance
                # to avoid Beanie initialization issues
                return DataWrapper(data)
            elif backend_type == BackendType.REDIS:
                # Convert to Redis format - include None values for optional fields
                data = obj.model_dump(exclude_none=False)
                # Redis uses 'pk' field instead of 'id'
                if "id" in data:
                    if data["id"] is not None:
                        data["pk"] = data["id"]
                    del data["id"]
                # Create a simple data wrapper instead of actual model instance
                return DataWrapper(data)
        return obj

    # Synchronous interface methods
    def insert(self, obj: BaseModel) -> ModelType:
        """
        Insert a document using the active backend.

        Args:
            obj (BaseModel): The document object to insert into the database.

        Returns:
            ModelType: The inserted document with generated fields populated.

        Raises:
            DuplicateInsertError: If the document violates unique constraints.

        Example:
            .. code-block:: python

                user = User(name="John", email="john@example.com")
                inserted_user = unified_backend.insert(user)
                print(f"Inserted user with ID: {inserted_user.id}")
        """
        converted_obj = self._convert_unified_to_backend_data(obj)
        return self._handle_async_call("insert", converted_obj)

    def get(self, id: str) -> ModelType:
        """
        Retrieve a document by its unique identifier.

        Args:
            id (str): The unique identifier of the document to retrieve.

        Returns:
            ModelType: The retrieved document.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.

        Example:
            .. code-block:: python

                try:
                    user = unified_backend.get("user_123")
                    print(f"Found user: {user.name}")
                except DocumentNotFoundError:
                    print("User not found")
        """
        return self._handle_async_call("get", id)

    def delete(self, id: str):
        """
        Delete a document by its unique identifier.

        Args:
            id (str): The unique identifier of the document to delete.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.

        Example:
            .. code-block:: python

                try:
                    unified_backend.delete("user_123")
                    print("User deleted successfully")
                except DocumentNotFoundError:
                    print("User not found")
        """
        return self._handle_async_call("delete", id)

    def all(self) -> List[ModelType]:
        """
        Retrieve all documents from the collection.

        Returns:
            List[ModelType]: A list of all documents in the collection.

        Example:
            .. code-block:: python

                all_users = unified_backend.all()
                print(f"Found {len(all_users)} users")
                for user in all_users:
                    print(f"- {user.name}")
        """
        return self._handle_async_call("all")

    def find(self, *args, **kwargs) -> List[ModelType]:
        """
        Find documents matching the specified criteria.

        Args:
            *args: Query conditions and filters.
            **kwargs: Additional query parameters.

        Returns:
            List[ModelType]: A list of documents matching the query criteria.

        Example:
            .. code-block:: python

                # Find users with specific criteria
                users = unified_backend.find(User.email == "john@example.com")

                # Find all users if no criteria specified
                all_users = unified_backend.find()
        """
        return self._handle_async_call("find", *args, **kwargs)

    # Asynchronous interface methods
    async def insert_async(self, obj: BaseModel) -> ModelType:
        """
        Insert a document using the active backend (async version).

        Args:
            obj (BaseModel): The document object to insert into the database.

        Returns:
            ModelType: The inserted document with generated fields populated.

        Raises:
            DuplicateInsertError: If the document violates unique constraints.

        Example:
            .. code-block:: python

                user = User(name="John", email="john@example.com")
                inserted_user = await unified_backend.insert_async(user)
                print(f"Inserted user with ID: {inserted_user.id}")
        """
        converted_obj = self._convert_unified_to_backend_data(obj)
        backend = self._get_active_backend()
        if backend.is_async():
            # For async backends (MongoDB), call async method directly
            return await backend.insert(converted_obj)
        else:
            # For sync backends (Redis), use async wrapper method
            if hasattr(backend, "insert_async"):
                return await backend.insert_async(converted_obj)
            else:
                # Fallback to sync method
                return backend.insert(converted_obj)

    async def get_async(self, id: str) -> ModelType:
        """
        Retrieve a document by its unique identifier (async version).

        Args:
            id (str): The unique identifier of the document to retrieve.

        Returns:
            ModelType: The retrieved document.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.

        Example:
            .. code-block:: python

                try:
                    user = await unified_backend.get_async("user_123")
                    print(f"Found user: {user.name}")
                except DocumentNotFoundError:
                    print("User not found")
        """
        backend = self._get_active_backend()
        if backend.is_async():
            # For async backends (MongoDB), call async method directly
            return await backend.get(id)
        else:
            # For sync backends (Redis), use async wrapper method
            if hasattr(backend, "get_async"):
                return await backend.get_async(id)
            else:
                # Fallback to sync method
                return backend.get(id)

    async def delete_async(self, id: str):
        """
        Delete a document by its unique identifier (async version).

        Args:
            id (str): The unique identifier of the document to delete.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.

        Example:
            .. code-block:: python

                try:
                    await unified_backend.delete_async("user_123")
                    print("User deleted successfully")
                except DocumentNotFoundError:
                    print("User not found")
        """
        backend = self._get_active_backend()
        if backend.is_async():
            # For async backends (MongoDB), call async method directly
            return await backend.delete(id)
        else:
            # For sync backends (Redis), use async wrapper method
            if hasattr(backend, "delete_async"):
                return await backend.delete_async(id)
            else:
                # Fallback to sync method
                return backend.delete(id)

    async def all_async(self) -> List[ModelType]:
        """
        Retrieve all documents from the collection (async version).

        Returns:
            List[ModelType]: A list of all documents in the collection.

        Example:
            .. code-block:: python

                all_users = await unified_backend.all_async()
                print(f"Found {len(all_users)} users")
                for user in all_users:
                    print(f"- {user.name}")
        """
        backend = self._get_active_backend()
        if backend.is_async():
            # For async backends (MongoDB), call async method directly
            return await backend.all()
        else:
            # For sync backends (Redis), use async wrapper method
            if hasattr(backend, "all_async"):
                return await backend.all_async()
            else:
                # Fallback to sync method
                return backend.all()

    async def find_async(self, *args, **kwargs) -> List[ModelType]:
        """
        Find documents matching the specified criteria (async version).

        Args:
            *args: Query conditions and filters.
            **kwargs: Additional query parameters.

        Returns:
            List[ModelType]: A list of documents matching the query criteria.

        Example:
            .. code-block:: python

                # Find users with specific criteria
                users = await unified_backend.find_async(User.email == "john@example.com")

                # Find all users if no criteria specified
                all_users = await unified_backend.find_async()
        """
        backend = self._get_active_backend()
        if backend.is_async():
            # For async backends (MongoDB), call async method directly
            return await backend.find(*args, **kwargs)
        else:
            # For sync backends (Redis), use async wrapper method
            if hasattr(backend, "find_async"):
                return await backend.find_async(*args, **kwargs)
            else:
                # Fallback to sync method
                return backend.find(*args, **kwargs)

    def get_raw_model(self) -> Type[ModelType]:
        """
        Get the raw model class from the active backend.

        Returns:
            Type[ModelType]: The backend-specific model class.

        Example:
            .. code-block:: python

                model_class = unified_backend.get_raw_model()
                print(f"Backend model: {model_class.__name__}")
        """
        return self._get_active_backend().get_raw_model()

    def get_unified_model(self) -> Type[UnifiedMindtraceDocument]:
        """
        Get the unified model class if available.

        Returns:
            Type[UnifiedMindtraceDocument]: The unified document model class.

        Raises:
            ValueError: If no unified model class is configured.

        Example:
            .. code-block:: python

                try:
                    unified_model = unified_backend.get_unified_model()
                    print(f"Unified model: {unified_model.__name__}")
                except ValueError:
                    print("No unified model configured")
        """
        if not self.unified_model_cls:
            raise ValueError("No unified model class configured")
        return self.unified_model_cls

    def has_mongo_backend(self) -> bool:
        """
        Check if MongoDB backend is configured.

        Returns:
            bool: True if MongoDB backend is available, False otherwise.

        Example:
            .. code-block:: python

                if unified_backend.has_mongo_backend():
                    print("MongoDB backend is available")
                    mongo_backend = unified_backend.get_mongo_backend()
        """
        return self.mongo_backend is not None

    def has_redis_backend(self) -> bool:
        """
        Check if Redis backend is configured.

        Returns:
            bool: True if Redis backend is available, False otherwise.

        Example:
            .. code-block:: python

                if unified_backend.has_redis_backend():
                    print("Redis backend is available")
                    redis_backend = unified_backend.get_redis_backend()
        """
        return self.redis_backend is not None

    def get_mongo_backend(self) -> MongoMindtraceODM:
        """
        Get the MongoDB backend instance.

        Returns:
            MongoMindtraceODM: The MongoDB backend instance.

        Raises:
            ValueError: If MongoDB backend is not configured.

        Example:
            .. code-block:: python

                try:
                    mongo_backend = unified_backend.get_mongo_backend()
                    # Use MongoDB-specific features
                    results = await mongo_backend.aggregate(pipeline)
                except ValueError:
                    print("MongoDB backend not configured")
        """
        if not self.mongo_backend:
            raise ValueError("MongoDB backend is not configured")
        return self.mongo_backend

    def get_redis_backend(self) -> RedisMindtraceODM:
        """
        Get the Redis backend instance.

        Returns:
            RedisMindtraceODM: The Redis backend instance.

        Raises:
            ValueError: If Redis backend is not configured.

        Example:
            .. code-block:: python

                try:
                    redis_backend = unified_backend.get_redis_backend()
                    # Use Redis-specific features
                    all_docs = redis_backend.all()
                except ValueError:
                    print("Redis backend not configured")
        """
        if not self.redis_backend:
            raise ValueError("Redis backend is not configured")
        return self.redis_backend
