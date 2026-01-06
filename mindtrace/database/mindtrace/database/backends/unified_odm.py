import asyncio
from enum import Enum
from typing import Dict, List, Optional, Type, TypeVar, Union

from pydantic import BaseModel, Field

from mindtrace.database.backends.mindtrace_odm import InitMode, MindtraceODM
from mindtrace.database.backends.mongo_odm import MindtraceDocument, MongoMindtraceODM
from mindtrace.database.backends.redis_odm import MindtraceRedisDocument, RedisMindtraceODM

# Module-level cache for generated MongoDB models to ensure class identity consistency
_mongo_model_cache: dict[type, type] = {}


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
        import sys

        current_module = sys.modules[__name__]
        if cls in current_module._mongo_model_cache:
            return current_module._mongo_model_cache[cls]

        from typing import Annotated

        from beanie import Indexed

        # Get field annotations from the original class, excluding inherited ones
        cls_annotations = getattr(cls, "__annotations__", {})
        meta = getattr(cls, "Meta", cls.Meta)

        # Get the original field values from the class using model_fields

        cls_fields = {}

        for field_name, field_info in cls.model_fields.items():
            cls_fields[field_name] = field_info

        annotations = {}
        field_defaults = {}

        for field_name, field_type in cls_annotations.items():
            if field_name == "id":
                continue  # Skip id field for MongoDB

            # Check if field has a default value from Pydantic Field
            field_default = ...
            if field_name in cls_fields:
                field_info = cls_fields[field_name]
                # check default and default_factory
                if hasattr(field_info, "default"):
                    default_val = field_info.default
                    if default_val is not ...:
                        # Check if it's not a PydanticUndefined type
                        default_type_str = str(type(default_val))
                        if "PydanticUndefined" not in default_type_str:
                            field_default = default_val

                # Check default_factory if default is not set
                if field_default is ... and hasattr(field_info, "default_factory"):
                    default_factory_val = field_info.default_factory
                    if default_factory_val is not None:
                        # Check if it's not a PydanticUndefined type
                        factory_type_str = str(type(default_factory_val))
                        if "PydanticUndefined" not in factory_type_str:
                            field_default = default_factory_val

                # If still no default, check if it's Optional - Optional fields default to None
                if field_default is ...:
                    from typing import Union, get_args, get_origin

                    origin = get_origin(field_type)
                    # Check if it's a Union type (including Optional which is Union[T, None])
                    if origin is not None:
                        origin_str = str(origin)
                        if "Union" in origin_str or origin is Union:
                            args = get_args(field_type)
                            if type(None) in args:
                                # It's Optional, default to None
                                field_default = None

            # Handle Link types - convert Link[UnifiedModel] to Link[MongoModel]
            from typing import Union, get_args, get_origin

            from beanie import Link

            processed_type = field_type
            # Check if it's a Link type (may be wrapped in Optional/Union)
            field_type_str = str(field_type)
            is_link = "Link" in field_type_str or "beanie" in field_type_str.lower()

            # Handle Optional[Link[...]] or Union[Link[...], None]
            origin = get_origin(field_type)
            if origin is Union or (origin is not None and "Union" in str(origin)):
                # It's Optional/Union - check the args for Link
                args = get_args(field_type)
                for arg in args:
                    if arg is not type(None):  # Skip None type
                        arg_origin = get_origin(arg)
                        arg_str = str(arg)
                        if (
                            arg_origin is Link
                            or "Link" in arg_str
                            or (hasattr(Link, "__origin__") and arg_origin == Link.__origin__)
                        ):
                            # Found Link in Union - extract it
                            link_args = get_args(arg)
                            if link_args:
                                target_unified_model = link_args[0]
                                if isinstance(target_unified_model, type) and issubclass(
                                    target_unified_model, UnifiedMindtraceDocument
                                ):
                                    target_mongo_model = target_unified_model._auto_generate_mongo_model()
                                    # Reconstruct Optional[Link[MongoModel]]
                                    processed_type = Union[Link[target_mongo_model], type(None)]
                                    is_link = True
                                    break
            elif not is_link:
                # Check if it's a direct Link type
                if origin is not None:
                    origin_str = str(origin)
                    is_link = (
                        origin is Link
                        or "Link" in origin_str
                        or (hasattr(Link, "__origin__") and origin == Link.__origin__)
                    )

            if is_link and processed_type == field_type:
                # Direct Link type (not wrapped in Optional)
                link_args = get_args(field_type)
                if link_args:
                    target_unified_model = link_args[0]
                    # Check if it's a UnifiedMindtraceDocument subclass
                    if isinstance(target_unified_model, type) and issubclass(
                        target_unified_model, UnifiedMindtraceDocument
                    ):
                        # Generate the MongoDB model for the target
                        target_mongo_model = target_unified_model._auto_generate_mongo_model()
                        # Convert Link[UnifiedModel] to Link[MongoModel]
                        processed_type = Link[target_mongo_model]

            # If field has a default, we need to ensure it's Optional and set the default
            if field_default is not ...:
                # Ensure the type is Optional if it has a default
                origin = get_origin(processed_type)
                if origin is not Union and type(None) not in get_args(processed_type):
                    # Make it Optional if it's not already
                    processed_type = Union[processed_type, type(None)]
                field_defaults[field_name] = field_default

            if hasattr(meta, "unique_fields") and field_name in meta.unique_fields:
                annotations[field_name] = Annotated[processed_type, Indexed(unique=True)]
            elif hasattr(meta, "indexed_fields") and field_name in meta.indexed_fields:
                annotations[field_name] = Annotated[processed_type, Indexed()]
            else:
                annotations[field_name] = processed_type

        # Create the class attributes dictionary
        class_dict = {
            "__annotations__": annotations,
            "__module__": cls.__module__,
        }

        # Add default values to class attributes
        for field_name, default_value in field_defaults.items():
            class_dict[field_name] = default_value

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

        import sys

        current_module = sys.modules[__name__]
        current_module._mongo_model_cache[cls] = DynamicMongoModel

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
        unified_models: Optional[Dict[str, Type[UnifiedMindtraceDocument]]] = None,
        mongo_model_cls: Optional[Type[MindtraceDocument]] = None,
        mongo_models: Optional[Dict[str, Type[MindtraceDocument]]] = None,
        redis_model_cls: Optional[Type[MindtraceRedisDocument]] = None,
        redis_models: Optional[Dict[str, Type[MindtraceRedisDocument]]] = None,
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
            unified_model_cls: Unified document model class (preferred, single model mode)
            unified_models: Dictionary of unified model names to model classes (multi-model mode).
                Example: {'user': User, 'address': Address}. When provided, access models via db.user, db.address, etc.
            mongo_model_cls: MongoDB document model class (fallback, single model mode)
            mongo_models: Dictionary of MongoDB model names to model classes (multi-model mode)
            redis_model_cls: Redis document model class (fallback, single model mode)
            redis_models: Dictionary of Redis model names to model classes (multi-model mode)
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
        self._unified_models = unified_models
        self._model_odms: Dict[str, "UnifiedMindtraceODM"] = {}

        # Support multi-model mode with unified models
        if unified_models is not None:
            if unified_model_cls is not None:
                raise ValueError("Cannot specify both unified_model_cls and unified_models. Use one or the other.")
            if not isinstance(unified_models, dict) or len(unified_models) == 0:
                raise ValueError("unified_models must be a non-empty dictionary")

            # Create UnifiedMindtraceODM instances for each model
            for name, model_cls in unified_models.items():
                odm = UnifiedMindtraceODM(
                    unified_model_cls=model_cls,
                    mongo_db_uri=mongo_db_uri,
                    mongo_db_name=mongo_db_name,
                    redis_url=redis_url,
                    preferred_backend=preferred_backend,
                    allow_index_dropping=allow_index_dropping,
                    auto_init=auto_init,
                    init_mode=init_mode,
                )
                self._model_odms[name] = odm

            # Set primary backends from first model (for backward compatibility)
            if self._model_odms:
                first_odm = list(self._model_odms.values())[0]
                self.mongo_backend = first_odm.mongo_backend
                self.redis_backend = first_odm.redis_backend
        elif unified_model_cls:
            # Single unified model mode
            if mongo_db_uri and mongo_db_name:
                mongo_model_cls = unified_model_cls._auto_generate_mongo_model()
                self.mongo_backend = MongoMindtraceODM(
                    model_cls=mongo_model_cls,
                    db_uri=mongo_db_uri,
                    db_name=mongo_db_name,
                    allow_index_dropping=allow_index_dropping,
                    auto_init=auto_init,
                    init_mode=init_mode,
                )

            if redis_url:
                redis_model_cls = unified_model_cls._auto_generate_redis_model()
                self.redis_backend = RedisMindtraceODM(
                    model_cls=redis_model_cls,
                    redis_url=redis_url,
                    auto_init=auto_init,
                    init_mode=init_mode,
                )
        elif mongo_models is not None or redis_models is not None:
            # Multi-model mode with backend-specific models
            if mongo_models is not None and mongo_db_uri and mongo_db_name:
                self.mongo_backend = MongoMindtraceODM(
                    models=mongo_models,
                    db_uri=mongo_db_uri,
                    db_name=mongo_db_name,
                    allow_index_dropping=allow_index_dropping,
                    auto_init=auto_init,
                    init_mode=init_mode,
                )

            if redis_models is not None and redis_url:
                self.redis_backend = RedisMindtraceODM(
                    models=redis_models,
                    redis_url=redis_url,
                    auto_init=auto_init,
                    init_mode=init_mode,
                )
        else:
            # Fallback to individual model classes (single model mode)
            if mongo_model_cls and mongo_db_uri and mongo_db_name:
                self.mongo_backend = MongoMindtraceODM(
                    model_cls=mongo_model_cls,
                    db_uri=mongo_db_uri,
                    db_name=mongo_db_name,
                    allow_index_dropping=allow_index_dropping,
                    auto_init=auto_init,
                    init_mode=init_mode,
                )

            if redis_model_cls and redis_url:
                self.redis_backend = RedisMindtraceODM(
                    model_cls=redis_model_cls,
                    redis_url=redis_url,
                    auto_init=auto_init,
                    init_mode=init_mode,
                )

        if not self.mongo_backend and not self.redis_backend:
            raise ValueError("At least one backend (MongoDB or Redis) must be configured")

    def __getattr__(self, name: str):
        """Support attribute-based access to model-specific ODMs in multi-model mode.

        Example:
            db = UnifiedMindtraceODM(unified_models={'user': User, 'address': Address}, ...)
            await db.user.get_async(user_id)
            await db.address.insert_async(address)
        """
        if self._unified_models is not None and name in self._model_odms:
            return self._model_odms[name]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

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
            **kwargs: Keyword arguments to pass to the method (including fetch_links).

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
            # Note: fetch_links is ignored for Redis as it doesn't support Beanie links
            kwargs_without_fetch_links = {k: v for k, v in kwargs.items() if k != "fetch_links"}
            method = getattr(backend, method_name)
            return method(*args, **kwargs_without_fetch_links)

    def _convert_unified_to_backend_data(self, obj: BaseModel | dict) -> BaseModel | dict:
        """Convert unified model data to backend-specific format."""

        if isinstance(obj, UnifiedMindtraceDocument):
            backend_type = self.get_current_backend_type()
            if backend_type == BackendType.MONGO:
                # Convert to MongoDB format - use model_dump to get clean data
                data = obj.model_dump(exclude_none=False)
                # Remove 'id' field for MongoDB as it uses '_id'
                if "id" in data:
                    del data["id"]
                # Convert any ObjectId values to strings for string fields
                data = self._convert_objectids_to_strings(data)
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
                # Convert any ObjectId values to strings
                data = self._convert_objectids_to_strings(data)
                # Create a simple data wrapper instead of actual model instance
                return DataWrapper(data)
        elif isinstance(obj, dict):
            # Handle dict input - convert ObjectIds to strings
            backend_type = self.get_current_backend_type()
            data = obj.copy()
            data = self._convert_objectids_to_strings(data)
            return data
        return obj

    def _convert_objectids_to_strings(self, data: dict) -> dict:
        """Recursively convert PydanticObjectId values to strings in a dict."""
        from beanie import PydanticObjectId

        if not isinstance(data, dict):
            return data

        converted = {}
        for key, value in data.items():
            if isinstance(value, PydanticObjectId):
                converted[key] = str(value)
            elif isinstance(value, dict):
                converted[key] = self._convert_objectids_to_strings(value)
            elif isinstance(value, list):
                converted[key] = [
                    str(item)
                    if isinstance(item, PydanticObjectId)
                    else self._convert_objectids_to_strings(item)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                converted[key] = value
        return converted

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

    def get(self, id: str, fetch_links: bool = False) -> ModelType:
        """
        Retrieve a document by its unique identifier.

        Args:
            id (str): The unique identifier of the document to retrieve.
            fetch_links (bool): If True, fetch linked documents (Beanie/MongoDB feature). Defaults to False.

        Returns:
            ModelType: The retrieved document.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.
            ValueError: If in multi-model mode (use db.model_name.get() instead).

        Example:
            .. code-block:: python

                try:
                    user = unified_backend.get("user_123")
                    print(f"Found user: {user.name}")

                    # With linked documents (MongoDB only)
                    user = unified_backend.get("user_123", fetch_links=True)
                    print(f"User address: {user.address.street}")
                except DocumentNotFoundError:
                    print("User not found")
        """
        if self._unified_models is not None:
            raise ValueError("Cannot use get() in multi-model mode. Use db.model_name.get() instead.")
        return self._handle_async_call("get", id, fetch_links=fetch_links)

    def update(self, obj: BaseModel) -> ModelType:
        """
        Update an existing document using the active backend.

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
                user = unified_backend.get("user_123")
                # Modify it
                user.age = 31
                user.name = "John Updated"
                # Save the changes
                updated_user = unified_backend.update(user)
        """
        if self._unified_models is not None:
            raise ValueError("Cannot use update() in multi-model mode. Use db.model_name.update() instead.")
        return self._handle_async_call("update", obj)

    def delete(self, id: str):
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
                    unified_backend.delete("user_123")
                    print("User deleted successfully")
                except DocumentNotFoundError:
                    print("User not found")
        """
        if self._unified_models is not None:
            raise ValueError("Cannot use delete() in multi-model mode. Use db.model_name.delete() instead.")
        return self._handle_async_call("delete", id)

    def all(self) -> List[ModelType]:
        """
        Retrieve all documents from the collection.

        Returns:
            List[ModelType]: A list of all documents in the collection.

        Raises:
            ValueError: If in multi-model mode (use db.model_name.all() instead).

        Example:
            .. code-block:: python

                all_users = unified_backend.all()
                print(f"Found {len(all_users)} users")
                for user in all_users:
                    print(f"- {user.name}")
        """
        if self._unified_models is not None:
            raise ValueError("Cannot use all() in multi-model mode. Use db.model_name.all() instead.")
        return self._handle_async_call("all")

    def find(self, *args, fetch_links: bool = False, **kwargs) -> List[ModelType]:
        """
        Find documents matching the specified criteria.

        Args:
            *args: Query conditions and filters.
            fetch_links (bool): If True, fetch linked documents (Beanie/MongoDB feature). Defaults to False.
            **kwargs: Additional query parameters.

        Returns:
            List[ModelType]: A list of documents matching the query criteria.

        Raises:
            ValueError: If in multi-model mode (use db.model_name.find() instead).

        Example:
            .. code-block:: python

                # Find users with specific criteria
                users = unified_backend.find(User.email == "john@example.com")

                # Find all users if no criteria specified
                all_users = unified_backend.find()

                # Find users with linked documents (MongoDB only)
                users = unified_backend.find({"name": "Alice"}, fetch_links=True)
        """
        if self._unified_models is not None:
            raise ValueError("Cannot use find() in multi-model mode. Use db.model_name.find() instead.")
        return self._handle_async_call("find", *args, fetch_links=fetch_links, **kwargs)

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
            ValueError: If in multi-model mode (use db.model_name.insert_async() instead).

        Example:
            .. code-block:: python

                user = User(name="John", email="john@example.com")
                inserted_user = await unified_backend.insert_async(user)
                print(f"Inserted user with ID: {inserted_user.id}")
        """
        if self._unified_models is not None:
            raise ValueError("Cannot use insert_async() in multi-model mode. Use db.model_name.insert_async() instead.")
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

    async def get_async(self, id: str, fetch_links: bool = False) -> ModelType:
        """
        Retrieve a document by its unique identifier (async version).

        Args:
            id (str): The unique identifier of the document to retrieve.
            fetch_links (bool): If True, fetch linked documents (Beanie/MongoDB feature). Defaults to False.

        Returns:
            ModelType: The retrieved document.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.
            ValueError: If in multi-model mode (use db.model_name.get_async() instead).

        Example:
            .. code-block:: python

                try:
                    user = await unified_backend.get_async("user_123")
                    print(f"Found user: {user.name}")

                    # With linked documents (MongoDB only)
                    user = await unified_backend.get_async("user_123", fetch_links=True)
                    print(f"User address: {user.address.street}")
                except DocumentNotFoundError:
                    print("User not found")
        """
        if self._unified_models is not None:
            raise ValueError("Cannot use get_async() in multi-model mode. Use db.model_name.get_async() instead.")
        backend = self._get_active_backend()
        if backend.is_async():
            # For async backends (MongoDB), call async method directly
            return await backend.get(id, fetch_links=fetch_links)
        else:
            # For sync backends (Redis), use async wrapper method
            if hasattr(backend, "get_async"):
                return await backend.get_async(id)
            else:
                # Fallback to sync method
                return backend.get(id)

    async def update_async(self, obj: BaseModel) -> ModelType:
        """
        Update an existing document using the active backend (async version).

        The document object should have been retrieved from the database,
        modified, and then passed to this method to save the changes.

        Args:
            obj (BaseModel): The document object with modified fields to save.

        Returns:
            ModelType: The updated document.

        Raises:
            DocumentNotFoundError: If the document doesn't exist in the database.
            ValueError: If in multi-model mode (use db.model_name.update_async() instead).

        Example:
            .. code-block:: python

                # Get the document
                user = await unified_backend.get_async("user_123")
                # Modify it
                user.age = 31
                user.name = "John Updated"
                # Save the changes
                updated_user = await unified_backend.update_async(user)
        """
        if self._unified_models is not None:
            raise ValueError("Cannot use update_async() in multi-model mode. Use db.model_name.update_async() instead.")
        backend = self._get_active_backend()
        if backend.is_async():
            # For async backends (MongoDB), call async method directly
            return await backend.update(obj)
        else:
            # For sync backends (Redis), use async wrapper method
            if hasattr(backend, "update_async"):
                return await backend.update_async(obj)
            else:
                # Fallback to sync method
                return backend.update(obj)

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

        Raises:
            ValueError: If in multi-model mode (use db.model_name.all_async() instead).

        Example:
            .. code-block:: python

                all_users = await unified_backend.all_async()
                print(f"Found {len(all_users)} users")
                for user in all_users:
                    print(f"- {user.name}")
        """
        if self._unified_models is not None:
            raise ValueError("Cannot use all_async() in multi-model mode. Use db.model_name.all_async() instead.")
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

    async def find_async(self, *args, fetch_links: bool = False, **kwargs) -> List[ModelType]:
        """
        Find documents matching the specified criteria (async version).

        Args:
            *args: Query conditions and filters.
            fetch_links (bool): If True, fetch linked documents (Beanie/MongoDB feature). Defaults to False.
            **kwargs: Additional query parameters.

        Returns:
            List[ModelType]: A list of documents matching the query criteria.

        Raises:
            ValueError: If in multi-model mode (use db.model_name.find_async() instead).

        Example:
            .. code-block:: python

                # Find users with specific criteria
                users = await unified_backend.find_async(User.email == "john@example.com")

                # Find all users if no criteria specified
                all_users = await unified_backend.find_async()

                # Find users with linked documents (MongoDB only)
                users = await unified_backend.find_async({"name": "Alice"}, fetch_links=True)
        """
        if self._unified_models is not None:
            raise ValueError("Cannot use find_async() in multi-model mode. Use db.model_name.find_async() instead.")
        backend = self._get_active_backend()
        if backend.is_async():
            # For async backends (MongoDB), call async method directly
            return await backend.find(*args, fetch_links=fetch_links, **kwargs)
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
