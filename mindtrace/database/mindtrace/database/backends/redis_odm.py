import asyncio
import inspect
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel
from redis_om import JsonModel, Migrator, get_redis_connection
from redis_om.model.model import ExpressionProxy, NotFoundError

from mindtrace.database.backends.mindtrace_odm import InitMode, MindtraceODM
from mindtrace.database.core.exceptions import DocumentNotFoundError, DuplicateInsertError, QueryNotSupported


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


def _ensure_redis_model_indexed(model: Type[ModelType]) -> None:
    """Ensure a Redis model has index=True for redis-om v1.0.6+.

    Sets model_config['index'] = True and ExpressionProxy on each field so key(),
    find(), create_index(), and expression queries (e.g. Model.age > 25) work.
    Call this for any model_cls passed to RedisMindtraceODM.
    """
    if not isinstance(model, type) or not issubclass(model, MindtraceRedisDocument):
        return
    config = getattr(model, "model_config", None)
    if isinstance(config, dict):
        if config.get("index") is not True:
            config["index"] = True
    elif hasattr(model, "Config") and hasattr(model.Config, "index"):
        if model.Config.index is not True:
            model.Config.index = True

    try:
        model_fields = getattr(model, "model_fields", None) or getattr(model, "__fields__", None)
        if model_fields:
            for field_name, field in model_fields.items():
                if getattr(field, "name", None) != field_name:
                    setattr(field, "name", field_name)
                setattr(model, field_name, ExpressionProxy(field, []))
    except Exception:
        pass

    # Redis OM Migrator discovers models from the global model registry.
    # Models created without `class X(..., index=True)` are not auto-registered,
    # so ensure they are present for startup migrations.
    try:
        is_indexed = False
        if isinstance(config, dict):
            is_indexed = config.get("index") is True
        elif hasattr(model, "Config") and hasattr(model.Config, "index"):
            is_indexed = model.Config.index is True

        meta = getattr(model, "Meta", None)
        is_embedded = bool(getattr(meta, "embedded", False))
        if is_indexed and not is_embedded and not inspect.isabstract(model):
            from redis_om.model.model import model_registry

            key = f"{model.__module__}.{model.__qualname__}"
            model_registry[key] = model
    except Exception:
        pass


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
                _ensure_redis_model_indexed(model)
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
            _ensure_redis_model_indexed(model_cls)
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

    @staticmethod
    def _index_name_for_model(model: Type[ModelType]) -> str:
        """Derive the RediSearch index name for *model*."""
        if hasattr(model.Meta, "index_name") and model.Meta.index_name:
            return model.Meta.index_name
        prefix = getattr(model.Meta, "global_key_prefix", "mindtrace")
        model_module = getattr(model, "__module__", "")
        model_name = model.__name__
        if model_module == "__main__":
            full = f"__main__.{model_name}"
        elif model_module:
            full = f"{model_module}.{model_name}"
        else:
            full = model_name
        return f"{prefix}:{full}:index"

    def _ensure_index_ready(self, model: Type[ModelType], timeout: float = 5.0):
        """Wait for an index to finish background population (best-effort).

        Calls FT.INFO to verify the index exists and checks the ``indexing``
        flag (1 = still populating).  Waits up to *timeout* seconds, polling
        every 0.1 s.  Logs a warning if still indexing after the deadline.

        Does **not** drop/recreate indexes — that is Migrator's job at init
        time.  All exceptions are caught so this is never fatal.
        """
        import time

        try:
            model_redis = model.Meta.database
            index_name = self._index_name_for_model(model)
            step = 0.1
            waited = 0.0
            while waited < timeout:
                try:
                    info = model_redis.execute_command("FT.INFO", index_name)
                    if isinstance(info, list) and "indexing" in info:
                        idx = info.index("indexing")
                        indexing = info[idx + 1] if idx + 1 < len(info) else 0
                        if str(indexing) != "1":
                            return  # Index is ready
                    else:
                        return  # No indexing flag, assume ready
                except Exception:
                    return  # Index doesn't exist or can't check — nothing to wait for
                time.sleep(step)
                waited += step
            self.logger.warning(f"Index {index_name} still indexing after {timeout}s")
        except Exception:
            pass  # Best-effort — never fatal

    def _do_initialize(self):
        """Internal method to perform startup initialization.

        Initialization is startup-driven and fail-fast: bind model connections,
        run redis-om Migrator once, then wait for index population.
        """
        if self._is_initialized:
            return

        # Test connection first so connection issues fail clearly.
        try:
            self.redis.ping()
        except Exception as conn_error:
            raise ConnectionError(f"Redis connection failed: {conn_error}") from conn_error

        models_to_migrate: list[Type[ModelType]] = []
        if self._models is not None:
            for model in self._models.values():
                model.Meta.database = self.redis
                models_to_migrate.append(model)
            for odm in self._model_odms.values():
                if odm.model_cls:
                    odm.model_cls.Meta.database = self.redis
                    if odm.model_cls not in models_to_migrate:
                        models_to_migrate.append(odm.model_cls)
        elif self.model_cls:
            self.model_cls.Meta.database = self.redis
            models_to_migrate.append(self.model_cls)

        # Ensure every active model is pinned to this backend connection.
        for model in models_to_migrate:
            model.Meta.database = self.redis

        if models_to_migrate:
            try:
                migrator = Migrator()
                migrator.run()
            except Exception as migrator_error:
                raise RuntimeError(
                    f"Redis initialization failed during migration: {migrator_error}"
                ) from migrator_error

        for model in models_to_migrate:
            self._ensure_index_ready(model)

        self._is_initialized = True
        for odm in self._model_odms.values():
            odm._is_initialized = True

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
        models = self.__dict__.get("_models")
        model_odms = self.__dict__.get("_model_odms", {})
        if models is not None and name in model_odms:
            return model_odms[name]
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

    def insert_one(self, obj: BaseModel | dict) -> ModelType:
        """Insert one document into Redis. Returns the inserted document."""
        if self._models is not None:
            raise ValueError("Cannot use insert() in multi-model mode. Use db.model_name.insert() instead.")
        self.initialize()
        # Get object data - handle both dict and BaseModel
        if isinstance(obj, dict):
            obj_data = obj.copy()
        else:
            obj_data = obj.model_dump() if hasattr(obj, "model_dump") else obj.__dict__

        doc = self.model_cls(**obj_data)  # __init__ auto-derives pk from natural keys if present

        if self._natural_key_fields():
            result = doc.save(nx=True)
            if result is None:
                raise DuplicateInsertError(
                    f"Document with pk={doc.pk} already exists"
                )
        else:
            doc.save()

        return doc

    def get(self, id: str) -> ModelType:
        """Legacy: retrieve a document by id. Prefer ``find_one``."""
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
        """Legacy: full-document save by id/pk. Prefer ``update_one``."""
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
        """Legacy: delete a document by id. Prefer ``delete_one``."""
        if self._models is not None:
            raise ValueError("Cannot use delete() in multi-model mode. Use db.model_name.delete() instead.")
        self.initialize()
        try:
            # delete() builds the exact model-scoped key via make_primary_key,
            # so only the target document is removed — no wildcard patterns.
            deleted = self.model_cls.delete(id)
            if isinstance(deleted, int) and deleted == 0:
                raise DocumentNotFoundError(f"Object with id {id} not found")
        except NotFoundError:
            raise DocumentNotFoundError(f"Object with id {id} not found")

    def all(self) -> List[ModelType]:
        """Legacy: retrieve all documents. Prefer ``find()``."""
        if self._models is not None:
            raise ValueError("Cannot use all() in multi-model mode. Use db.model_name.all() instead.")
        return self.find()

    def _dict_to_find_expressions(self, query_dict: dict):
        """Convert a dict query to redis-om expression(s) so find(dict) works.

        Supports:
        - Flat equality: {"field": value}
        - List-as-IN: {"field": [v1, v2]} → Model.field << [v1, v2]
        - $or: {"$or": [{clause1}, {clause2}]} → (clause1) | (clause2)
        """
        if not query_dict:
            return []
        model = self.model_cls
        expressions = []

        for key, value in query_dict.items():
            if key == "$or":
                or_exprs = []
                for clause in value:
                    clause_exprs = self._dict_to_find_expressions(clause)
                    if clause_exprs:
                        combined = clause_exprs[0]
                        for e in clause_exprs[1:]:
                            combined = combined & e
                        or_exprs.append(combined)
                if or_exprs:
                    or_combined = or_exprs[0]
                    for e in or_exprs[1:]:
                        or_combined = or_combined | e
                    expressions.append(or_combined)
                continue

            if key.startswith("$"):
                raise QueryNotSupported(
                    f"Unsupported query operator '{key}'. "
                    f"Supported: $or, scalar equality, list-as-IN."
                )

            attr = getattr(model, key, None)
            if attr is None:
                raise QueryNotSupported(
                    f"Field '{key}' does not exist on model {model.__name__}."
                )

            if isinstance(value, (list, tuple)):
                expr = attr << list(value)
            elif isinstance(value, dict):
                raise QueryNotSupported(
                    f"Dict-style operators on field '{key}' are not supported. "
                    f"Use list-as-IN or scalar equality instead."
                )
            else:
                expr = attr == value

            if getattr(expr, "op", None) is not None:
                expressions.append(expr)

        return expressions

    def _natural_key_fields(self) -> List[str]:
        """Return configured natural-key fields for this model."""
        meta = getattr(self.model_cls, "Meta", None)
        fields = getattr(meta, "natural_key_fields", []) if meta is not None else []
        if not isinstance(fields, (list, tuple)):
            return []
        return [f for f in fields if isinstance(f, str) and f]

    # ── FT helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _ft_escape_tag(value: str) -> str:
        """Escape special characters for RediSearch TAG queries."""
        special = r',.<>{}[]"\':;!@#$%^&*()-+=~/ '
        return "".join(f"\\{c}" if c in special else c for c in str(value))

    def _build_ft_filter(self, where: dict) -> str:
        """Translate a portable ``where`` dict to an FT.AGGREGATE query string."""

        def _build_clause(clause: dict) -> str:
            parts: list[str] = []
            for key, value in clause.items():
                if key == "$or":
                    if not isinstance(value, list):
                        raise QueryNotSupported("$or value must be a list of clauses.")
                    or_parts = []
                    for sub in value:
                        if not isinstance(sub, dict):
                            raise QueryNotSupported("$or clauses must be dicts.")
                        built = _build_clause(sub)
                        if built and built != "*":
                            or_parts.append(built)
                    if or_parts:
                        parts.append(f"({' | '.join(or_parts)})")
                    continue
                if key.startswith("$"):
                    raise QueryNotSupported(
                        f"Unsupported query operator '{key}'. Supported: $or, scalar equality, list-as-IN."
                    )
                if isinstance(value, dict):
                    raise QueryNotSupported(
                        f"Dict-style operators on field '{key}' are not supported. "
                        f"Use list-as-IN or scalar equality instead."
                    )
                if isinstance(value, (list, tuple)):
                    in_terms = [f"@{key}:{{{self._ft_escape_tag(str(v))}}}" for v in value]
                    if in_terms:
                        parts.append(f"({' | '.join(in_terms)})")
                else:
                    parts.append(f"@{key}:{{{self._ft_escape_tag(str(value))}}}")
            return " ".join(parts) if parts else "*"

        return _build_clause(where or {})

    def find(
        self,
        where: dict | None = None,
        sort: list[tuple[str, int]] | None = None,
        limit: int | None = None,
        **kwargs,
    ) -> List[ModelType]:
        """Find documents matching a portable filter.

        Args:
            where: Portable filter dict. Supported operators are equality,
                list-as-IN, and ``$or``.
            sort: List of ``(field, direction)`` pairs (1 asc, -1 desc).
            limit: Maximum number of results.

        Raises:
            QueryNotSupported: If the filter cannot be represented portably.
        """
        if self._models is not None:
            raise ValueError("Cannot use find() in multi-model mode. Use db.model_name.find() instead.")

        # Legacy compat: if `where` is a redis-om expression (not a dict),
        # pass it straight through as a positional arg to model_cls.find().
        if where is not None and not isinstance(where, dict):
            args = (where,)
            query_dict = {}
        else:
            args = tuple()
            query_dict = where or {}

        # All dict queries go through redis-om expressions (supports $or, list-IN, equality).
        if query_dict:
            args = tuple(self._dict_to_find_expressions(query_dict))
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

            if sort:
                for field_name, direction in reversed(sort):
                    results.sort(
                        key=lambda d: (getattr(d, field_name, None) is None, getattr(d, field_name, None)),
                        reverse=direction < 0,
                    )
            if limit is not None:
                results = results[: max(0, limit)]
            return results
        except Exception as e:
            # Query-time index repair is intentionally disabled.
            # Index creation/repair belongs to initialize().
            self.logger.warning(f"Redis query failed: {e}")
            return []

    def insert(self, obj: BaseModel | dict) -> ModelType:
        """Legacy: insert a document. Prefer ``insert_one``."""
        return self.insert_one(obj)

    def find_one(self, where: dict, sort: list[tuple[str, int]] | None = None) -> ModelType | None:
        """Find first document matching *where*. Returns None when empty."""
        results = self.find(where=where, sort=sort, limit=1)
        return results[0] if results else None

    def update_one(
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
            return_document:
                ``"none"``   - return a backend update-result object.
                ``"before"`` - return document snapshot before update (or None).
                ``"after"``  - return document snapshot after update (or None).
        """
        if self._models is not None:
            raise ValueError("Cannot use update_one() in multi-model mode. Use db.model_name.update_one() instead.")
        if return_document not in {"none", "before", "after"}:
            raise ValueError("return_document must be one of: 'none', 'before', 'after'")
        self.initialize()

        matches = self.find(where=where, limit=1)
        modified_count = 0
        upserted_id = None

        if matches:
            doc = matches[0]
            old_doc = doc.model_dump()
            for field, value in set_fields.items():
                setattr(doc, field, value)
            doc.save()
            modified_count = 1
            if return_document == "before":
                return old_doc
            if return_document == "after":
                return doc.model_dump()
        elif upsert:
            if any(isinstance(v, (list, tuple, dict, set)) for v in where.values()):
                raise ValueError("Cannot upsert with non-equality where values.")
            payload = {**where, **set_fields}
            inserted = self.insert_one(payload)
            upserted_id = getattr(inserted, "pk", None) or getattr(inserted, "id", None)
            if return_document == "before":
                return None
            if return_document == "after":
                return inserted.model_dump() if hasattr(inserted, "model_dump") else inserted
        elif return_document in {"before", "after"}:
            return None

        class _UpdateResult:
            pass

        result = _UpdateResult()
        result.modified_count = modified_count
        result.upserted_id = upserted_id
        return result

    def delete_one(self, where: dict) -> int:
        """Delete exactly one matching document. Returns 0 or 1."""
        if self._models is not None:
            raise ValueError("Cannot use delete_one() in multi-model mode. Use db.model_name.delete_one() instead.")
        self.initialize()

        if not where:
            docs = self.model_cls.find().all()
        else:
            exprs = self._dict_to_find_expressions(where)
            if not exprs:
                return 0
            docs = self.model_cls.find(*exprs).all()
        if not docs:
            return 0
        self.model_cls.delete(docs[0].pk)
        return 1

    def delete_many(self, where: dict) -> int:
        """Delete all matching documents. Returns deleted count."""
        if self._models is not None:
            raise ValueError("Cannot use delete_many() in multi-model mode. Use db.model_name.delete_many() instead.")
        self.initialize()

        if not where:
            return self.model_cls.find().delete()
        exprs = self._dict_to_find_expressions(where)
        if exprs:
            return self.model_cls.find(*exprs).delete()
        return 0

    def distinct(self, field: str, where: dict | None = None) -> list[Any]:
        """Return distinct values for *field* among documents matching *where*."""
        if self._models is not None:
            raise ValueError("Cannot use distinct() in multi-model mode. Use db.model_name.distinct() instead.")
        self.initialize()

        # Try FT.AGGREGATE for efficient distinct
        index_name = getattr(self.model_cls.Meta, "index_name", None)
        if index_name:
            try:
                ft_filter = self._build_ft_filter(where) if where else "*"
                result = self.redis.execute_command(
                    "FT.AGGREGATE", index_name, ft_filter,
                    "GROUPBY", "1", f"@{field}",
                )
                values = []
                for row in result[1:]:
                    if isinstance(row, list) and len(row) >= 2:
                        val = row[1]
                        if isinstance(val, bytes):
                            val = val.decode()
                        values.append(val)
                return sorted(values)
            except Exception:
                pass  # Fall through to scan

        # Fallback: indexed find
        values = {getattr(doc, field, None) for doc in self.find(where=where or {})}
        return sorted(v for v in values if v is not None)

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
        """Async wrapper around insert."""
        return await asyncio.to_thread(self.insert, obj)

    async def get_async(self, id: str) -> ModelType:
        """Async wrapper around get."""
        return await asyncio.to_thread(self.get, id)

    async def delete_async(self, id: str):
        """Async wrapper around delete."""
        await asyncio.to_thread(self.delete, id)

    async def update_async(self, obj: BaseModel) -> ModelType:
        """Async wrapper around update."""
        return await asyncio.to_thread(self.update, obj)

    async def all_async(self) -> List[ModelType]:
        """Async wrapper around all."""
        return await asyncio.to_thread(self.all)

    async def find_async(self, *args, **kwargs) -> List[ModelType]:
        """Async wrapper around find."""
        return await asyncio.to_thread(self.find, *args, **kwargs)

    async def insert_one_async(self, doc: BaseModel | dict) -> ModelType:
        """Async wrapper around insert_one."""
        return await asyncio.to_thread(self.insert_one, doc)

    async def find_one_async(self, where: dict, sort: list[tuple[str, int]] | None = None) -> ModelType | None:
        """Async wrapper around find_one."""
        return await asyncio.to_thread(self.find_one, where, sort)

    async def update_one_async(
        self,
        where: dict,
        set_fields: dict,
        upsert: bool = False,
        return_document: str = "none",
    ) -> Any:
        """Async wrapper around update_one."""
        return await asyncio.to_thread(self.update_one, where, set_fields, upsert, return_document)

    async def delete_one_async(self, where: dict) -> int:
        """Async wrapper around delete_one."""
        return await asyncio.to_thread(self.delete_one, where)

    async def delete_many_async(self, where: dict) -> int:
        """Async wrapper around delete_many."""
        return await asyncio.to_thread(self.delete_many, where)

    async def distinct_async(self, field: str, where: dict | None = None) -> list[Any]:
        """Async wrapper around distinct."""
        return await asyncio.to_thread(self.distinct, field, where)
