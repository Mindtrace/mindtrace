import asyncio
from typing import Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel
from redis_om import JsonModel, Migrator, get_redis_connection
from redis_om.model.model import NotFoundError

from mindtrace.database.backends.mindtrace_odm import InitMode, MindtraceODM
from mindtrace.database.core.exceptions import DocumentNotFoundError, DuplicateInsertError


class MindtraceRedisDocument(JsonModel):
    """
    Base document class for Redis collections in Mindtrace.

    This class extends redis-om's JsonModel to provide a standardized
    base for all Redis document models in the Mindtrace ecosystem.

    The `id` property automatically returns the `pk` value for consistency
    with MongoDB, eliminating the need to set it manually on each document.

    Example:
        .. code-block:: python

            from mindtrace.database.backends.redis_odm import MindtraceRedisDocument
            from redis_om import Field

            class User(MindtraceRedisDocument):
                name: str
                email: str = Field(index=True)

                class Meta:
                    global_key_prefix = "myapp"
    """

    class Meta:
        """
        Configuration metadata for the Redis document.

        Attributes:
            global_key_prefix (str): The global prefix for all keys of this document type.
        """

        global_key_prefix = "mindtrace"

    @property
    def id(self) -> str | None:
        """
        Return the primary key as 'id' for consistency with MongoDB.

        This property automatically returns the `pk` value, allowing
        code to use `doc.id` instead of `doc.pk` for unified access
        across MongoDB and Redis backends.
        """
        return getattr(self, "pk", None)

    @id.setter
    def id(self, value: str | None) -> None:
        """
        Set the primary key when 'id' is set.

        This allows Redis-OM deserialization to work properly while
        maintaining the unified 'id' interface. Setting 'id' sets 'pk'.
        """
        object.__setattr__(self, "pk", value)


ModelType = TypeVar("ModelType", bound=MindtraceRedisDocument)


class RedisMindtraceODM(MindtraceODM):
    """
    Redis implementation of the Mindtrace ODM backend.

    This backend provides synchronous database operations using Redis as the
    underlying storage engine. It uses redis-om for document modeling and
    JSON serialization.

    Args:
        model_cls (Type[ModelType]): The document model class to use for operations.
        redis_url (str): Redis connection URL string.

    Example:
        .. code-block:: python

            from mindtrace.database.backends.redis_odm import RedisMindtraceODM
            from redis_om import Field

            class User(MindtraceRedisDocument):
                name: str
                email: str = Field(index=True)

            backend = RedisMindtraceODM(
                model_cls=User,
                redis_url="redis://localhost:6379"
            )

            # Use the backend
            user = backend.insert(User(name="John", email="john@example.com"))
    """

    def __init__(
        self,
        model_cls: Optional[Type[ModelType]] = None,
        models: Optional[Dict[str, Type[MindtraceRedisDocument]] | str] = None,
        redis_url: str = "",
        auto_init: bool = False,
        init_mode: InitMode | None = None,
    ):
        """
        Initialize the Redis ODM backend.

        Args:
            model_cls (Type[ModelType], optional): The document model class to use for operations (single model mode).
            models (Dict[str, Type[MindtraceRedisDocument]] | str, optional): Dictionary of model names to model classes (multi-model mode).
                Example: {'user': User, 'address': Address}. When provided, access models via db.user, db.address, etc.
                For backward compatibility: if a string is provided, it's treated as redis_url.
            redis_url (str): Redis connection URL string.
            auto_init (bool): If True, automatically initializes the backend.
                Defaults to False for backward compatibility. Operations will auto-initialize
                on first use regardless.
            init_mode (InitMode | None): Initialization mode. If None, defaults to InitMode.SYNC
                for Redis. If InitMode.SYNC, initialization will be synchronous. If InitMode.ASYNC,
                initialization will be deferred to first operation.
        """
        super().__init__()

        # Backward compatibility: if models is a string, it's actually redis_url from old API
        # Old API: RedisMindtraceODM(model_cls, redis_url)
        # New API: RedisMindtraceODM(model_cls=..., models=..., redis_url=...)
        if isinstance(models, str):
            # Old API: second positional arg is redis_url
            redis_url = models
            models = None

        if not redis_url:
            raise ValueError("redis_url is required")

        self.redis_url = redis_url
        self.redis = get_redis_connection(url=redis_url)
        self._is_initialized = False
        self._model_odms: Dict[str, "RedisMindtraceODM"] = {}
        self._parent_odm: Optional["RedisMindtraceODM"] = None  # Reference to parent in multi-model mode

        # Support both single model and multi-model modes
        if models is not None:
            # Multi-model mode
            if model_cls is not None:
                raise ValueError("Cannot specify both model_cls and models. Use one or the other.")
            if not isinstance(models, dict) or len(models) == 0:
                raise ValueError("models must be a non-empty dictionary")
            self._models = models
            self.model_cls = None  # No single model in multi-model mode
            # Create ODM instances for each model (they share the same redis connection)
            for name, model in models.items():
                odm = RedisMindtraceODM(
                    model_cls=model,
                    redis_url=redis_url,
                    auto_init=False,
                    init_mode=init_mode,
                )
                # Share the same redis connection
                odm.redis = self.redis
                odm.model_cls.Meta.database = self.redis
                # Store parent reference for initialization delegation
                odm._parent_odm = self
                self._model_odms[name] = odm
        elif model_cls is not None:
            # Single model mode (backward compatible)
            self.model_cls = model_cls
            self.model_cls.Meta.database = self.redis
            self._models = None
        else:
            raise ValueError("Must specify either model_cls or models")

        # Default to sync for Redis if not specified
        if init_mode is None:
            init_mode = InitMode.SYNC

        # Store init_mode for later reference
        self._init_mode = init_mode

        # Auto-initialize if requested (otherwise operations will auto-init on first use)
        if auto_init:
            if init_mode == InitMode.SYNC:
                # Sync initialization
                self._do_initialize()
            else:
                # Async mode - defer initialization (operations will auto-init)
                pass

    def _create_index_for_model(self, model: Type[ModelType]):
        """Manually create an index for a specific model using its connection."""
        try:
            model_redis = model.Meta.database
            prefix = getattr(model.Meta, "global_key_prefix", "mindtrace")
            model_name = model.__name__
            model_module = getattr(model, "__module__", "")

            # Construct index name: {prefix}:{module}.{class_name}:index
            if hasattr(model.Meta, "index_name") and model.Meta.index_name:
                index_name = model.Meta.index_name
            else:
                if model_module == "__main__":
                    full_model_name = f"__main__.{model_name}"
                elif model_module:
                    full_model_name = f"{model_module}.{model_name}"
                else:
                    full_model_name = model_name
                index_name = f"{prefix}:{full_model_name}:index"
                if not hasattr(model.Meta, "index_name") or not model.Meta.index_name:
                    model.Meta.index_name = index_name

            # Build key patterns to match redis-om's key format
            model_key_prefix = getattr(model.Meta, "model_key_prefix", None)
            key_patterns = []
            if model_key_prefix:
                key_patterns.append(f"{prefix}:{model_key_prefix}:*")
            else:
                if model_module == "__main__":
                    key_patterns.append(f"{prefix}:__main__.{model_name}:*")
                    key_patterns.append(f"{prefix}:{model_name}:*")
                else:
                    key_patterns.append(f"{prefix}:{model_name}:*")
                    if model_module:
                        key_patterns.append(f"{prefix}:{model_module}.{model_name}:*")

            key_pattern = key_patterns[0] if key_patterns else f"{prefix}:{model_name}:*"
            indexed_fields = []
            for attr_name in dir(model):
                if attr_name.startswith("_") or attr_name in ("id", "pk", "Meta"):
                    continue
                try:
                    attr_value = getattr(model, attr_name)
                    if hasattr(attr_value, "index") and attr_value.index:
                        indexed_fields.append(attr_name)
                except Exception:
                    pass

            if not indexed_fields:
                return  # No indexed fields

            # Check if index exists; drop and recreate if it has 0 docs but keys exist
            index_exists = False
            try:
                model_redis.execute_command("FT.INFO", index_name)
                index_exists = True
                try:
                    index_info = model_redis.execute_command("FT.INFO", index_name)
                    if isinstance(index_info, list) and "num_docs" in index_info:
                        num_docs_idx = index_info.index("num_docs")
                        num_docs = index_info[num_docs_idx + 1] if num_docs_idx + 1 < len(index_info) else 0
                        matching_keys = []
                        for pattern in key_patterns:
                            matching_keys.extend(model_redis.keys(pattern))
                        matching_keys = list(set(matching_keys))
                        if num_docs == 0 and len(matching_keys) > 0:
                            self.logger.debug(
                                f"Dropping index {index_name} to recreate (has 0 docs but {len(matching_keys)} keys exist)"
                            )
                            try:
                                model_redis.execute_command("FT.DROPINDEX", index_name)
                                index_exists = False
                            except Exception:
                                pass
                except Exception:
                    pass
            except Exception:
                pass

            if index_exists:
                return  # Index exists and is valid

            # Build schema with field types (TEXT or NUMERIC)
            schema_parts = []
            for field_name in indexed_fields:
                field_type = "TEXT"
                try:
                    if hasattr(model, "__annotations__"):
                        field_annotation = model.__annotations__.get(field_name, None)
                        if field_annotation:
                            # Check if it's a numeric type
                            if "int" in str(field_annotation) or "float" in str(field_annotation):
                                field_type = "NUMERIC"
                            else:
                                field_type = "TEXT"
                except Exception:
                    pass
                schema_parts.extend([field_name, field_type])

            if schema_parts:
                try:
                    if hasattr(model, "create_index"):
                        if not hasattr(model.Meta, "database") or model.Meta.database is None:
                            model.Meta.database = model_redis
                        if not hasattr(model.Meta, "index_name") or not model.Meta.index_name:
                            model.Meta.index_name = index_name
                        model.create_index()
                        self.logger.debug(f"Created index for {model.__name__} using redis-om's create_index()")
                        try:
                            actual_index_name = getattr(model.Meta, "index_name", index_name)
                            index_info = model_redis.execute_command("FT.INFO", actual_index_name)
                            if isinstance(index_info, list) and "num_docs" in index_info:
                                num_docs_idx = index_info.index("num_docs")
                                num_docs = index_info[num_docs_idx + 1] if num_docs_idx + 1 < len(index_info) else 0
                                self.logger.debug(f"Index {actual_index_name} verified, has {num_docs} documents")
                        except Exception as info_error:
                            self.logger.debug(f"Could not verify index: {info_error}")
                        return
                except Exception as builtin_error:
                    error_str = str(builtin_error).lower()
                    if "index already exists" in error_str or "already exists" in error_str:
                        self.logger.debug("Index already exists (via redis-om), that's OK")
                        return
                    self.logger.debug(f"redis-om create_index() failed: {builtin_error}, trying manual creation")

                try:
                    # JsonModel uses JSON format with JSON path syntax: $.field_name
                    json_schema_parts = []
                    for i in range(0, len(schema_parts), 2):
                        field_name = schema_parts[i]
                        field_type = schema_parts[i + 1]
                        json_schema_parts.extend([f"$.{field_name}", "AS", field_name, field_type])

                    # Try creating index with each key pattern
                    index_created = False
                    for pattern in key_patterns:
                        try:
                            cmd = [
                                "FT.CREATE",
                                index_name,
                                "ON",
                                "JSON",
                                "PREFIX",
                                "1",
                                pattern,
                                "SCHEMA",
                            ] + json_schema_parts
                            model_redis.execute_command(*cmd)
                            self.logger.debug(f"Created index {index_name} with pattern {pattern} (JSON format)")
                            index_created = True
                            break
                        except Exception as pattern_error:
                            error_str = str(pattern_error).lower()
                            if "index already exists" in error_str:
                                index_created = True
                                break
                            continue

                    if not index_created:
                        cmd = [
                            "FT.CREATE",
                            index_name,
                            "ON",
                            "JSON",
                            "PREFIX",
                            "1",
                            key_pattern,
                            "SCHEMA",
                        ] + json_schema_parts
                        model_redis.execute_command(*cmd)
                        self.logger.debug(
                            f"Created index {index_name} with primary pattern {key_pattern} (JSON format)"
                        )
                except Exception as create_error:
                    error_str = str(create_error).lower()
                    if "index already exists" in error_str:
                        pass
                    else:
                        # Fallback to HASH format
                        try:
                            cmd = [
                                "FT.CREATE",
                                index_name,
                                "ON",
                                "HASH",
                                "PREFIX",
                                "1",
                                key_pattern,
                                "SCHEMA",
                            ] + schema_parts
                            model_redis.execute_command(*cmd)
                            self.logger.debug(f"Created index {index_name} with pattern {key_pattern} (HASH format)")
                        except Exception:
                            # Try alternative pattern with JSON
                            alt_pattern = f"{prefix}:*"
                            try:
                                json_schema_parts = []
                                for i in range(0, len(schema_parts), 2):
                                    field_name = schema_parts[i]
                                    field_type = schema_parts[i + 1]
                                    json_schema_parts.extend([f"$.{field_name}", "AS", field_name, field_type])
                                cmd = [
                                    "FT.CREATE",
                                    index_name,
                                    "ON",
                                    "JSON",
                                    "PREFIX",
                                    "1",
                                    alt_pattern,
                                    "SCHEMA",
                                ] + json_schema_parts
                                model_redis.execute_command(*cmd)
                                self.logger.debug(
                                    f"Created index {index_name} with alternative pattern {alt_pattern} (JSON format)"
                                )
                            except Exception as alt_error:
                                self.logger.debug(f"Could not create index {index_name}: {alt_error}")
        except Exception as e:
            self.logger.debug(f"Could not create index for {model.__name__}: {e}")

    def _ensure_index_has_documents(self, model: Type[ModelType]):
        """Ensure the index has documents indexed. If not, recreate it."""
        try:
            model_redis = model.Meta.database
            prefix = getattr(model.Meta, "global_key_prefix", "mindtrace")
            model_name = model.__name__
            model_module = getattr(model, "__module__", "")

            # Construct index name
            if model_module == "__main__":
                full_model_name = f"__main__.{model_name}"
            elif model_module:
                full_model_name = f"{model_module}.{model_name}"
            else:
                full_model_name = model_name
            index_name = f"{prefix}:{full_model_name}:index"

            # Build key patterns
            model_key_prefix = getattr(model.Meta, "model_key_prefix", None)
            key_patterns = []
            if model_key_prefix:
                key_patterns.append(f"{prefix}:{model_key_prefix}:*")
            else:
                if model_module == "__main__":
                    key_patterns.append(f"{prefix}:__main__.{model_name}:*")
                    key_patterns.append(f"{prefix}:{model_name}:*")
                else:
                    key_patterns.append(f"{prefix}:{model_name}:*")
                    if model_module:
                        key_patterns.append(f"{prefix}:{model_module}.{model_name}:*")

            # Check if index exists and has documents
            try:
                index_info = model_redis.execute_command("FT.INFO", index_name)
                if isinstance(index_info, list) and "num_docs" in index_info:
                    num_docs_idx = index_info.index("num_docs")
                    num_docs = index_info[num_docs_idx + 1] if num_docs_idx + 1 < len(index_info) else 0

                    # Check if there are keys but index has 0 docs
                    matching_keys = []
                    for pattern in key_patterns:
                        matching_keys.extend(model_redis.keys(pattern))
                    matching_keys = list(set(matching_keys))

                    if num_docs == 0 and len(matching_keys) > 0:
                        self.logger.debug(
                            f"Recreating index {index_name} (has 0 docs but {len(matching_keys)} keys exist)"
                        )
                        try:
                            model_redis.execute_command("FT.DROPINDEX", index_name)
                            self._create_index_for_model(model)

                            # Wait for indexing to complete
                            import time

                            time.sleep(0.2)

                            # Verify documents are indexed
                            try:
                                index_info_after = model_redis.execute_command("FT.INFO", index_name)
                                if isinstance(index_info_after, list) and "num_docs" in index_info_after:
                                    num_docs_idx_after = index_info_after.index("num_docs")
                                    num_docs_after = (
                                        index_info_after[num_docs_idx_after + 1]
                                        if num_docs_idx_after + 1 < len(index_info_after)
                                        else 0
                                    )
                                    self.logger.debug(f"After recreation, index has {num_docs_after} documents")

                                    if num_docs_after == 0 and matching_keys:
                                        sample_key = matching_keys[0]
                                        try:
                                            json_data = model_redis.json().get(sample_key)
                                            self.logger.debug(
                                                f"Sample key {sample_key} has JSON data: {bool(json_data)}"
                                            )
                                            try:
                                                search_result = model_redis.execute_command(
                                                    "FT.SEARCH", index_name, "*", "LIMIT", "0", "10"
                                                )
                                                self.logger.debug(
                                                    f"Direct FT.SEARCH returned {len(search_result) if isinstance(search_result, list) else 'error'}"
                                                )
                                            except Exception as se:
                                                self.logger.debug(f"FT.SEARCH error: {se}")
                                        except Exception as je:
                                            self.logger.debug(f"Could not get JSON for key: {je}")
                            except Exception:
                                pass
                        except Exception as e:
                            self.logger.debug(f"Could not recreate index: {e}")
            except Exception:
                pass  # Index doesn't exist or can't check
        except Exception:
            pass  # Don't fail if check fails

    def _do_initialize(self):
        """Internal method to perform the actual initialization."""
        if not self._is_initialized:
            try:
                # Set REDIS_OM_URL before Migrator runs (must be done first)
                import os

                if self.redis_url:
                    os.environ["REDIS_OM_URL"] = self.redis_url
                    try:
                        from redis_om import connections

                        connections.URL = self.redis_url
                    except Exception:
                        pass

                # Test connection
                try:
                    self.redis.ping()
                except Exception as conn_error:
                    raise ConnectionError(f"Redis connection failed: {conn_error}") from conn_error

                # Set Meta.database for all models before Migrator runs
                models_to_migrate = []
                if self._models is not None:
                    for model in self._models.values():
                        model.Meta.database = self.redis
                        models_to_migrate.append(model)
                    for odm in self._model_odms.values():
                        if odm.model_cls:
                            odm.model_cls.Meta.database = self.redis
                            if odm.model_cls not in models_to_migrate:
                                models_to_migrate.append(odm.model_cls)
                else:
                    if self.model_cls:
                        self.model_cls.Meta.database = self.redis
                        models_to_migrate.append(self.model_cls)

                # Ensure all models use our connection
                for model in models_to_migrate:
                    model.Meta.database = self.redis

                    if hasattr(model.Meta.database, "connection_pool"):
                        port = model.Meta.database.connection_pool.connection_kwargs.get("port", "unknown")
                        expected_port = 6381 if "6381" in self.redis_url else "unknown"
                        if port != expected_port and expected_port != "unknown":
                            self.logger.warning(
                                f"Model {model.__name__} Meta.database using port {port}, expected {expected_port}"
                            )

                # Use Migrator to create indexes (required for redis-om's find() to work)
                migrator_success = False
                migrator_error_msg = None
                original_redis_url = os.environ.get("REDIS_OM_URL", None)

                if self.redis_url:
                    os.environ["REDIS_OM_URL"] = self.redis_url
                    try:
                        from redis_om import connections

                        connections.URL = self.redis_url
                    except Exception:
                        pass

                try:
                    # Ensure all models in registry use our connection
                    for model in models_to_migrate:
                        if hasattr(model, "Meta"):
                            model.Meta.database = self.redis

                    # Update all models in redis-om's registry to use our connection
                    try:
                        from redis_om.model.model import model_registry

                        for name, cls in model_registry.items():
                            if hasattr(cls, "Meta") and hasattr(cls.Meta, "database"):
                                current_port = None
                                if hasattr(cls.Meta.database, "connection_pool"):
                                    current_port = cls.Meta.database.connection_pool.connection_kwargs.get("port", None)
                                if current_port == 6379 or cls.Meta.database is None:
                                    cls.Meta.database = self.redis
                    except Exception:
                        pass

                    # Run Migrator to create indexes
                    migrator = Migrator()
                    migrator.run()
                    migrator_success = True
                except Exception as migrator_error:
                    # Migrator failed - log the error and fall back
                    migrator_error_msg = str(migrator_error)
                    error_str = migrator_error_msg.lower()
                    current_redis_url = os.environ.get("REDIS_OM_URL", "not set")
                    if "connection" not in error_str and "111" not in error_str and "6379" not in error_str:
                        self.logger.warning(f"Migrator failed: {migrator_error_msg}")
                        self.logger.warning("Migrator failed - redis-om's find() may not work correctly")
                    else:
                        self.logger.warning(f"Migrator failed due to connection issue: {migrator_error_msg}")
                        self.logger.warning(f"REDIS_OM_URL was: {current_redis_url}")
                        self.logger.warning(f"Expected Redis URL: {self.redis_url}")
                finally:
                    # Restore original REDIS_OM_URL after Migrator runs
                    if original_redis_url is not None:
                        os.environ["REDIS_OM_URL"] = original_redis_url
                    elif "REDIS_OM_URL" in os.environ and self.redis_url:
                        # Only delete if we set it (don't delete if it was already set)
                        del os.environ["REDIS_OM_URL"]

                # Fallback to manual index creation if Migrator fails
                if not migrator_success:
                    self.logger.warning("Falling back to manual index creation (may not work with redis-om's find())")
                    if migrator_error_msg:
                        self.logger.warning(f"Migrator error was: {migrator_error_msg}")
                    for model in models_to_migrate:
                        try:
                            self._create_index_for_model(model)
                        except Exception as model_error:
                            self.logger.debug(f"Manual index creation for {model.__name__} failed: {model_error}")

                self._is_initialized = True
                # Mark all model ODMs as initialized
                for odm in self._model_odms.values():
                    odm._is_initialized = True
            except ConnectionError:
                # Connection issue - don't mark as initialized so we retry
                raise  # Re-raise to be caught by caller
            except Exception as e:
                # If migration fails (e.g., Redis not ready), log warning but continue
                # Operations will still work, but queries requiring indexes may fail
                self.logger.warning(f"Redis migration failed: {e}")
                # Don't mark as initialized if it's a connection error - retry on next operation
                if "Connection refused" in str(e) or "111" in str(e) or "Connection" in str(type(e).__name__):
                    # Connection issue - don't mark as initialized so we retry
                    pass
                else:
                    self._is_initialized = True  # Other errors, continue anyway

    def initialize(self):
        """
        Initialize the Redis connection and run migrations.

        This method runs migrations to create necessary indexes and ensures
        the Redis connection is properly set up. If auto_init was True in __init__,
        this is already done and calling this is a no-op.

        In multi-model mode, child ODMs delegate initialization to the parent
        to ensure all models are initialized together.

        Example:
            .. code-block:: python

                # Auto-initialized in __init__
                backend = RedisMindtraceODM(User, "redis://localhost:6379")
                # Ready to use immediately

                # Or disable auto-init and call manually
                backend = RedisMindtraceODM(User, "redis://localhost:6379", auto_init=False)
                backend.initialize()
        """
        # If this is a child ODM in multi-model mode, delegate to parent
        if self._parent_odm is not None:
            self._parent_odm.initialize()
            return
        self._do_initialize()

    def __getattr__(self, name: str):
        """Support attribute-based access to model-specific ODMs in multi-model mode.

        Example:
            db = RedisMindtraceODM(models={'user': User, 'address': Address}, ...)
            db.user.get(user_id)
            db.address.insert(address)
        """
        if self._models is not None and name in self._model_odms:
            return self._model_odms[name]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def is_async(self) -> bool:
        """
        Determine if this backend operates asynchronously.

        Returns:
            bool: Always returns False as Redis operations are synchronous.

        Example:
            .. code-block:: python

                backend = RedisMindtraceODM(User, "redis://localhost:6379")
                if not backend.is_async():
                    result = backend.insert(user)
        """
        return False

    def insert(self, obj: BaseModel | dict) -> ModelType:
        """
        Insert a new document into the Redis database.

        Args:
            obj (BaseModel | dict): The document object to insert into the database.
                Can be a BaseModel instance or a dict. If dict, will create the document from it.

        Returns:
            ModelType: The inserted document with generated fields populated.

        Raises:
            DuplicateInsertError: If the document violates unique constraints.
            ValueError: If in multi-model mode (use db.model_name.insert() instead).

        Example:
            .. code-block:: python

                user = User(name="John", email="john@example.com")
                try:
                    inserted_user = backend.insert(user)
                    print(f"Inserted user with ID: {inserted_user.pk}")
                except DuplicateInsertError as e:
                    print(f"Duplicate entry: {e}")
        """
        if self._models is not None:
            raise ValueError("Cannot use insert() in multi-model mode. Use db.model_name.insert() instead.")
        self.initialize()
        # Get object data - handle both dict and BaseModel
        if isinstance(obj, dict):
            obj_data = obj.copy()
        else:
            obj_data = obj.model_dump() if hasattr(obj, "model_dump") else obj.__dict__

        # Check for duplicates by email if it exists and is unique
        if "email" in obj_data and obj_data["email"] and hasattr(self.model_cls, "email"):
            try:
                # Try to find existing document with same email
                existing = self.model_cls.find(self.model_cls.email == obj_data["email"]).all()
                if existing:
                    raise DuplicateInsertError(f"Document with email {obj_data['email']} already exists")
            except DuplicateInsertError:
                # Re-raise DuplicateInsertError
                raise
            except Exception:
                # If query fails, try a different approach
                try:
                    all_docs = self.model_cls.find().all()
                    for doc in all_docs:
                        if hasattr(doc, "email") and doc.email == obj_data["email"]:
                            raise DuplicateInsertError(f"Document with email {obj_data['email']} already exists")
                except DuplicateInsertError:
                    # Re-raise DuplicateInsertError
                    raise
                except Exception as e:
                    # If all fails, continue without duplicate check but log warning
                    self.logger.warning(f"Could not check for duplicates: {e}")

        doc = self.model_cls(**obj_data)
        doc.save()

        # After saving, ensure the index is working - if it has 0 docs, recreate it
        # This handles the case where index was created before documents were inserted
        try:
            self._ensure_index_has_documents(self.model_cls)
            # After ensuring index, try running Migrator to make redis-om aware of it
            # This ensures redis-om's find() method can use the index
            try:
                import os

                original_redis_url = os.environ.get("REDIS_OM_URL", None)
                if self.redis_url:
                    os.environ["REDIS_OM_URL"] = self.redis_url
                try:
                    Migrator().run()
                finally:
                    if original_redis_url:
                        os.environ["REDIS_OM_URL"] = original_redis_url
                    elif "REDIS_OM_URL" in os.environ:
                        del os.environ["REDIS_OM_URL"]
            except Exception:
                pass  # Don't fail if Migrator fails
        except Exception:
            pass  # Don't fail insert if index check fails

        return doc

    def get(self, id: str) -> ModelType:
        """
        Retrieve a document by its unique identifier.

        Args:
            id (str): The unique identifier of the document to retrieve.

        Returns:
            ModelType: The retrieved document.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.
            ValueError: If in multi-model mode (use db.model_name.get() instead).

        Example:
            .. code-block:: python

                try:
                    user = backend.get("01234567-89ab-cdef-0123-456789abcdef")
                    print(f"Found user: {user.name}")
                except DocumentNotFoundError:
                    print("User not found")
        """
        if self._models is not None:
            raise ValueError("Cannot use get() in multi-model mode. Use db.model_name.get() instead.")
        self.initialize()
        try:
            doc = self.model_cls.get(id)
            if not doc:
                raise DocumentNotFoundError(f"Object with id {id} not found")
            return doc
        except NotFoundError:
            raise DocumentNotFoundError(f"Object with id {id} not found")

    def update(self, obj: BaseModel) -> ModelType:
        """
        Update an existing document in the Redis database.

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
                user = backend.get("01234567-89ab-cdef-0123-456789abcdef")
                # Modify it
                user.age = 31
                user.name = "John Updated"
                # Save the changes
                updated_user = backend.update(user)
        """
        if self._models is not None:
            raise ValueError("Cannot use update() in multi-model mode. Use db.model_name.update() instead.")
        self.initialize()

        # Check if obj is already a document instance
        if isinstance(obj, self.model_cls):
            # If it's already a document instance, just save it
            if not hasattr(obj, "pk") or not obj.pk:
                raise DocumentNotFoundError("Document must have a pk to be updated")
            obj.save()
            # id property automatically returns pk, no need to set it
            return obj
        else:
            # If it's a BaseModel, we need to get the existing document first
            obj_id = getattr(obj, "pk", None) or getattr(obj, "id", None)
            if not obj_id:
                raise DocumentNotFoundError("Document must have an id or pk to be updated")

            try:
                doc = self.model_cls.get(obj_id)
                if not doc:
                    raise DocumentNotFoundError(f"Object with id {obj_id} not found")
            except NotFoundError:
                raise DocumentNotFoundError(f"Object with id {obj_id} not found")

            # Update the document fields
            obj_data = obj.model_dump() if hasattr(obj, "model_dump") else obj.__dict__
            for key, value in obj_data.items():
                if key not in ("id", "pk"):
                    setattr(doc, key, value)

            doc.save()
            # id property automatically returns pk, no need to set it
            return doc

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
                    backend.delete("01234567-89ab-cdef-0123-456789abcdef")
                    print("User deleted successfully")
                except DocumentNotFoundError:
                    print("User not found")
        """
        if self._models is not None:
            raise ValueError("Cannot use delete() in multi-model mode. Use db.model_name.delete() instead.")
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
        """
        Retrieve all documents from the collection.

        Returns:
            List[ModelType]: A list of all documents in the collection.

        Raises:
            ValueError: If in multi-model mode (use db.model_name.all() instead).

        Example:
            .. code-block:: python

                all_users = backend.all()
                print(f"Found {len(all_users)} users")
                for user in all_users:
                    print(f"- {user.name}")
        """
        if self._models is not None:
            raise ValueError("Cannot use all() in multi-model mode. Use db.model_name.all() instead.")
        # Ensure initialization succeeded - retry if it failed due to connection issues
        if not self._is_initialized:
            self.initialize()
        # If still not initialized (connection issue), try one more time
        if not self._is_initialized:
            self._do_initialize()
        try:
            return self.model_cls.find().all()
        except Exception as e:
            # If "No such index" error, try to create index and retry
            if "No such index" in str(e):
                try:
                    # Try to create the index manually
                    self._create_index_for_model(self.model_cls)
                    # Retry the query
                    return self.model_cls.find().all()
                except Exception as retry_error:
                    self.logger.warning(f"Failed to create index and retry: {retry_error}")
                    return []
            else:
                raise

    def find(self, *args, **kwargs) -> List[ModelType]:
        """
        Find documents matching the specified criteria.

        Args:
            *args: Query conditions and filters.
            **kwargs: Additional query parameters.

        Returns:
            List[ModelType]: A list of documents matching the query criteria.

        Raises:
            ValueError: If in multi-model mode (use db.model_name.find() instead).

        Example:
            .. code-block:: python

                # Find users with specific email
                users = backend.find(User.email == "john@example.com")

                # Find all users if no criteria specified
                all_users = backend.find()
        """
        if self._models is not None:
            raise ValueError("Cannot use find() in multi-model mode. Use db.model_name.find() instead.")
        # Ensure initialization succeeded - retry if it failed due to connection issues
        if not self._is_initialized:
            self.initialize()
        # If still not initialized (connection issue), try one more time
        if not self._is_initialized:
            self._do_initialize()
        try:
            # Try the query
            if args:
                results = self.model_cls.find(*args).all()
            else:
                results = self.model_cls.find().all()

            # If we get 0 results but we know documents exist, try to re-initialize
            # This handles the case where index was created but redis-om doesn't recognize it
            if len(results) == 0:
                # Check if documents actually exist by trying direct FT.SEARCH
                try:
                    index_name = getattr(self.model_cls.Meta, "index_name", None)
                    if index_name:
                        # Try direct search to see if index has documents
                        search_result = self.redis.execute_command("FT.SEARCH", index_name, "*", "LIMIT", "0", "1")
                        if isinstance(search_result, list) and len(search_result) > 1:
                            # Index has documents but find() returned 0 - try re-initializing
                            self.logger.debug(
                                f"Index {index_name} has documents but find() returned 0, trying to re-initialize"
                            )
                            try:
                                # Try running Migrator again to see if it helps
                                import os

                                original_redis_url = os.environ.get("REDIS_OM_URL", None)
                                if self.redis_url:
                                    os.environ["REDIS_OM_URL"] = self.redis_url
                                try:
                                    Migrator().run()
                                finally:
                                    if original_redis_url is not None:
                                        os.environ["REDIS_OM_URL"] = original_redis_url
                                    elif "REDIS_OM_URL" in os.environ:
                                        del os.environ["REDIS_OM_URL"]
                                # Retry the query
                                if args:
                                    results = self.model_cls.find(*args).all()
                                else:
                                    results = self.model_cls.find().all()
                            except Exception:
                                pass  # If re-init fails, return empty results
                except Exception:
                    pass  # If check fails, return empty results

            return results
        except Exception as e:
            # If query fails due to missing index, try to create it and retry
            if "No such index" in str(e):
                try:
                    # Try to create the index using Migrator with environment variable set
                    import os

                    original_redis_url = os.environ.get("REDIS_OM_URL", None)
                    try:
                        # Set environment variable so Migrator uses correct connection
                        os.environ["REDIS_OM_URL"] = self.redis_url
                        get_redis_connection(url=self.redis_url)
                        # Run Migrator to create the missing index
                        migrator = Migrator()
                        migrator.run()
                        # Retry the query
                        if args:
                            return self.model_cls.find(*args).all()
                        else:
                            return self.model_cls.find().all()
                    finally:
                        if original_redis_url is not None:
                            os.environ["REDIS_OM_URL"] = original_redis_url
                        elif "REDIS_OM_URL" in os.environ:
                            del os.environ["REDIS_OM_URL"]
                except Exception as retry_error:
                    self.logger.warning(f"Redis query failed after retry: {retry_error}")
                    return []
            else:
                # If query fails for other reasons, log the error and return empty list
                self.logger.warning(f"Redis query failed: {e}")
                # Try to return all documents if specific query fails
                try:
                    return self.model_cls.find().all()
                except Exception:
                    return []

    def get_raw_model(self) -> Type[ModelType]:
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

    # Asynchronous wrapper methods for compatibility
    async def initialize_async(self):
        """
        Initialize the Redis connection asynchronously (wrapper around sync initialize).

        This method provides an asynchronous interface to the sync initialize method.
        It should be called before performing any database operations in an async context.

        Example:
            .. code-block:: python

                backend = RedisMindtraceODM(User, "redis://localhost:6379")
                await backend.initialize_async()  # Can be called from async code
        """
        # Run blocking initialization in thread pool to avoid blocking event loop
        await asyncio.to_thread(self.initialize)

    async def insert_async(self, obj: BaseModel | dict) -> ModelType:
        """
        Insert a new document asynchronously (wrapper around sync insert).

        Args:
            obj (BaseModel | dict): The document object to insert into the database.
                Can be a BaseModel instance or a dict. If dict, will create the document from it.

        Returns:
            ModelType: The inserted document with generated fields populated.

        Raises:
            DuplicateInsertError: If the document violates unique constraints.

        Example:
            .. code-block:: python

                user = User(name="John", email="john@example.com")
                try:
                    inserted_user = await backend.insert_async(user)
                    print(f"Inserted user with ID: {inserted_user.pk}")
                except DuplicateInsertError as e:
                    print(f"Duplicate entry: {e}")
        """
        return await asyncio.to_thread(self.insert, obj)

    async def get_async(self, id: str) -> ModelType:
        """
        Retrieve a document asynchronously (wrapper around sync get).

        Args:
            id (str): The unique identifier of the document to retrieve.

        Returns:
            ModelType: The retrieved document.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.

        Example:
            .. code-block:: python

                try:
                    user = await backend.get_async("01234567-89ab-cdef-0123-456789abcdef")
                    print(f"Found user: {user.name}")
                except DocumentNotFoundError:
                    print("User not found")
        """
        return await asyncio.to_thread(self.get, id)

    async def delete_async(self, id: str):
        """
        Delete a document asynchronously (wrapper around sync delete).

        Args:
            id (str): The unique identifier of the document to delete.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.

        Example:
            .. code-block:: python

                try:
                    await backend.delete_async("01234567-89ab-cdef-0123-456789abcdef")
                    print("User deleted successfully")
                except DocumentNotFoundError:
                    print("User not found")
        """
        await asyncio.to_thread(self.delete, id)

    async def update_async(self, obj: BaseModel) -> ModelType:
        """
        Update an existing document asynchronously (wrapper around sync update).

        Args:
            obj (BaseModel): The document object with modified fields to save.

        Returns:
            ModelType: The updated document.

        Raises:
            DocumentNotFoundError: If the document doesn't exist in the database.

        Example:
            .. code-block:: python

                # Get the document
                user = await backend.get_async("01234567-89ab-cdef-0123-456789abcdef")
                # Modify it
                user.age = 31
                user.name = "John Updated"
                # Save the changes
                updated_user = await backend.update_async(user)
        """
        return await asyncio.to_thread(self.update, obj)

    async def all_async(self) -> List[ModelType]:
        """
        Retrieve all documents asynchronously (wrapper around sync all).

        Returns:
            List[ModelType]: A list of all documents in the collection.

        Example:
            .. code-block:: python

                all_users = await backend.all_async()
                print(f"Found {len(all_users)} users")
                for user in all_users:
                    print(f"- {user.name}")
        """
        return await asyncio.to_thread(self.all)

    async def find_async(self, *args, **kwargs) -> List[ModelType]:
        """
        Find documents asynchronously (wrapper around sync find).

        Args:
            *args: Query conditions and filters.
            **kwargs: Additional query parameters.

        Returns:
            List[ModelType]: A list of documents matching the query criteria.

        Example:
            .. code-block:: python

                # Find users with specific email
                users = await backend.find_async(User.email == "john@example.com")

                # Find all users if no criteria specified
                all_users = await backend.find_async()
        """
        return await asyncio.to_thread(self.find, *args, **kwargs)
