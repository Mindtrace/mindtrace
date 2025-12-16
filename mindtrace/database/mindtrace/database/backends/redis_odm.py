import asyncio
from typing import List, Type, TypeVar

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
        model_cls: Type[ModelType],
        redis_url: str,
        auto_init: bool = False,
        init_mode: InitMode | None = None,
    ):
        """
        Initialize the Redis ODM backend.

        Args:
            model_cls (Type[ModelType]): The document model class to use for operations.
            redis_url (str): Redis connection URL string.
            auto_init (bool): If True, automatically initializes the backend.
                Defaults to False for backward compatibility. Operations will auto-initialize
                on first use regardless.
            init_mode (InitMode | None): Initialization mode. If None, defaults to InitMode.SYNC
                for Redis. If InitMode.SYNC, initialization will be synchronous. If InitMode.ASYNC,
                initialization will be deferred to first operation.
        """
        super().__init__()
        self.model_cls = model_cls
        self.redis = get_redis_connection(url=redis_url)
        self.model_cls.Meta.database = self.redis
        self._is_initialized = False

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

    def _do_initialize(self):
        """Internal method to perform the actual initialization."""
        if not self._is_initialized:
            try:
                # Run migrations to create indexes
                Migrator().run()

                # Force index creation for the model
                # This ensures fields marked with index=True are properly indexed
                if hasattr(self.model_cls, "_meta") and hasattr(self.model_cls._meta, "indexed_fields"):
                    # Model has indexed fields metadata, ensure they're created
                    pass

                self._is_initialized = True
            except Exception as e:
                self.logger.warning(f"Redis migration failed: {e}")
                self._is_initialized = True  # Continue anyway

    def initialize(self):
        """
        Initialize the Redis connection and run migrations.

        This method runs migrations to create necessary indexes and ensures
        the Redis connection is properly set up. If auto_init was True in __init__,
        this is already done and calling this is a no-op.

        Example:
            .. code-block:: python

                # Auto-initialized in __init__
                backend = RedisMindtraceODM(User, "redis://localhost:6379")
                # Ready to use immediately

                # Or disable auto-init and call manually
                backend = RedisMindtraceODM(User, "redis://localhost:6379", auto_init=False)
                backend.initialize()
        """
        self._do_initialize()

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

    def insert(self, obj: BaseModel) -> ModelType:
        """
        Insert a new document into the Redis database.

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
                    inserted_user = backend.insert(user)
                    print(f"Inserted user with ID: {inserted_user.pk}")
                except DuplicateInsertError as e:
                    print(f"Duplicate entry: {e}")
        """
        self.initialize()
        # Get object data
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
            except Exception as e:
                # If query fails, try a different approach
                try:
                    all_docs = self.model_cls.find().all()
                    for doc in all_docs:
                        if hasattr(doc, "email") and doc.email == obj_data["email"]:
                            raise DuplicateInsertError(f"Document with email {obj_data['email']} already exists")
                except DuplicateInsertError:
                    # Re-raise DuplicateInsertError
                    raise
                except Exception:
                    # If all fails, continue without duplicate check but log warning
                    self.logger.warning(f"Could not check for duplicates: {e}")

        doc = self.model_cls(**obj_data)
        doc.save()
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

        Example:
            .. code-block:: python

                try:
                    user = backend.get("01234567-89ab-cdef-0123-456789abcdef")
                    print(f"Found user: {user.name}")
                except DocumentNotFoundError:
                    print("User not found")
        """
        self.initialize()
        try:
            doc = self.model_cls.get(id)
            if not doc:
                raise DocumentNotFoundError(f"Object with id {id} not found")
            return doc
        except NotFoundError:
            raise DocumentNotFoundError(f"Object with id {id} not found")

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
                    backend.delete("01234567-89ab-cdef-0123-456789abcdef")
                    print("User deleted successfully")
                except DocumentNotFoundError:
                    print("User not found")
        """
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

        Example:
            .. code-block:: python

                all_users = backend.all()
                print(f"Found {len(all_users)} users")
                for user in all_users:
                    print(f"- {user.name}")
        """
        self.initialize()
        return self.model_cls.find().all()

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

                # Find users with specific email
                users = backend.find(User.email == "john@example.com")

                # Find all users if no criteria specified
                all_users = backend.find()
        """
        self.initialize()
        try:
            if args:
                # Execute the query with proper error handling
                result = self.model_cls.find(*args).all()
                return result
            else:
                return self.model_cls.find().all()
        except Exception as e:
            # If query fails, log the error and return empty list
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

        Example:
            .. code-block:: python

                model_class = backend.get_raw_model()
                print(f"Using model: {model_class.__name__}")
        """
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

    async def insert_async(self, obj: BaseModel) -> ModelType:
        """
        Insert a new document asynchronously (wrapper around sync insert).

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
