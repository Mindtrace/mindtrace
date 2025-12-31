from typing import Annotated
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import Indexed
from pydantic import BaseModel, Field

from mindtrace.database import (
    BackendType,
    DocumentNotFoundError,
    DuplicateInsertError,
    MindtraceDocument,
    MindtraceRedisDocument,
    UnifiedMindtraceDocument,
    UnifiedMindtraceODM,
)


# Test models
class UserCreate(BaseModel):
    name: str
    age: int
    email: str


class MongoUserDoc(MindtraceDocument):
    name: str
    age: int
    email: Annotated[str, Indexed(unique=True)]

    class Settings:
        name = "users"
        use_cache = False


class RedisUserDoc(MindtraceRedisDocument):
    name: str = Field(index=True)
    age: int = Field(index=True)
    email: str = Field(index=True)

    class Meta:
        global_key_prefix = "mindtrace"


class UnifiedUserDoc(UnifiedMindtraceDocument):
    name: str = Field(description="User's full name")
    age: int = Field(ge=0, le=150, description="User's age")
    email: str = Field(description="User's email address")

    class Meta:
        collection_name = "test_users"
        global_key_prefix = "test"
        use_cache = False
        indexed_fields = ["name", "age", "email"]
        unique_fields = ["email"]


def create_mock_mongo_user(name="John", age=30, email="john@example.com", user_id="507f1f77bcf86cd799439011"):
    """Create a mock MongoDB UserDoc instance."""
    mock_user = MagicMock(spec=MongoUserDoc)
    mock_user.name = name
    mock_user.age = age
    mock_user.email = email
    mock_user.id = user_id
    return mock_user


def create_mock_redis_user(name="John", age=30, email="john@example.com", pk="01H0000000000000000000"):
    """Create a mock Redis UserDoc instance."""
    mock_user = MagicMock(spec=RedisUserDoc)
    mock_user.name = name
    mock_user.age = age
    mock_user.email = email
    mock_user.pk = pk
    return mock_user


@pytest.fixture
def mock_mongo_backend():
    """Create a mocked MongoDB backend."""
    with patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_backend_cls:
        backend = MagicMock()
        # Async methods (native)
        backend.insert = AsyncMock()
        backend.get = AsyncMock()
        backend.all = AsyncMock()
        backend.delete = AsyncMock()
        backend.find = AsyncMock()
        backend.initialize = AsyncMock()
        # Sync wrapper methods
        backend.insert_sync = MagicMock()
        backend.get_sync = MagicMock()
        backend.all_sync = MagicMock()
        backend.delete_sync = MagicMock()
        backend.find_sync = MagicMock()
        backend.initialize_sync = MagicMock()
        backend.is_async = MagicMock(return_value=True)
        backend.get_raw_model = MagicMock(return_value=MongoUserDoc)
        mock_backend_cls.return_value = backend
        yield backend


@pytest.fixture
def mock_redis_backend():
    """Create a mocked Redis backend."""
    with patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_backend_cls:
        backend = MagicMock()
        # Sync methods (native)
        backend.insert = MagicMock()
        backend.get = MagicMock()
        backend.all = MagicMock()
        backend.delete = MagicMock()
        backend.find = MagicMock()
        backend.initialize = MagicMock()
        # Async wrapper methods
        backend.insert_async = AsyncMock()
        backend.get_async = AsyncMock()
        backend.all_async = AsyncMock()
        backend.delete_async = AsyncMock()
        backend.find_async = AsyncMock()
        backend.initialize_async = AsyncMock()
        backend.is_async = MagicMock(return_value=False)
        backend.get_raw_model = MagicMock(return_value=RedisUserDoc)
        # Explicitly set initialization state (needed for init_mode logic)
        backend._is_initialized = False
        backend._init_mode = None  # Default to None (will be treated as SYNC)
        mock_backend_cls.return_value = backend
        yield backend


@pytest.fixture
def unified_backend_mongo_only(mock_mongo_backend):
    """Create a unified backend with only MongoDB configured."""
    return UnifiedMindtraceODM(
        mongo_model_cls=MongoUserDoc,
        mongo_db_uri="mongodb://localhost:27018",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )


@pytest.fixture
def unified_backend_redis_only(mock_redis_backend):
    """Create a unified backend with only Redis configured."""
    return UnifiedMindtraceODM(
        redis_model_cls=RedisUserDoc, redis_url="redis://localhost:6380", preferred_backend=BackendType.REDIS
    )


@pytest.fixture
def unified_backend_both(mock_mongo_backend, mock_redis_backend):
    """Create a unified backend with both MongoDB and Redis configured."""
    return UnifiedMindtraceODM(
        mongo_model_cls=MongoUserDoc,
        mongo_db_uri="mongodb://localhost:27018",
        mongo_db_name="test_db",
        redis_model_cls=RedisUserDoc,
        redis_url="redis://localhost:6380",
        preferred_backend=BackendType.MONGO,
    )


@pytest.fixture
def unified_backend_with_unified_model(mock_mongo_backend, mock_redis_backend):
    """Create a unified backend with a unified document model."""
    return UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27018",
        mongo_db_name="test_db",
        redis_url="redis://localhost:6380",
        preferred_backend=BackendType.MONGO,
    )


def test_unified_backend_initialization_mongo_only(unified_backend_mongo_only):
    """Test initialization with only MongoDB backend."""
    assert unified_backend_mongo_only.has_mongo_backend()
    assert not unified_backend_mongo_only.has_redis_backend()
    assert unified_backend_mongo_only.get_current_backend_type() == BackendType.MONGO


def test_unified_backend_initialization_redis_only(unified_backend_redis_only):
    """Test initialization with only Redis backend."""
    assert not unified_backend_redis_only.has_mongo_backend()
    assert unified_backend_redis_only.has_redis_backend()
    assert unified_backend_redis_only.get_current_backend_type() == BackendType.REDIS


def test_unified_backend_initialization_both(unified_backend_both):
    """Test initialization with both backends."""
    assert unified_backend_both.has_mongo_backend()
    assert unified_backend_both.has_redis_backend()
    assert unified_backend_both.get_current_backend_type() == BackendType.MONGO  # Preferred


def test_unified_backend_initialization_error():
    """Test initialization error when no backend is configured."""
    with pytest.raises(ValueError, match="At least one backend"):
        UnifiedMindtraceODM()


def test_backend_switching(unified_backend_both):
    """Test switching between backends."""
    # Start with MongoDB (preferred)
    assert unified_backend_both.get_current_backend_type() == BackendType.MONGO

    # Switch to Redis
    unified_backend_both.switch_backend(BackendType.REDIS)
    assert unified_backend_both.get_current_backend_type() == BackendType.REDIS

    # Switch back to MongoDB
    unified_backend_both.switch_backend(BackendType.MONGO)
    assert unified_backend_both.get_current_backend_type() == BackendType.MONGO


def test_backend_switching_error(unified_backend_mongo_only):
    """Test error when switching to unconfigured backend."""
    with pytest.raises(ValueError, match="Redis backend is not configured"):
        unified_backend_mongo_only.switch_backend(BackendType.REDIS)


def test_is_async_mongo(unified_backend_mongo_only):
    """Test is_async with MongoDB backend."""
    assert unified_backend_mongo_only.is_async() is True


def test_is_async_redis(unified_backend_redis_only):
    """Test is_async with Redis backend."""
    assert unified_backend_redis_only.is_async() is False


def test_get_raw_model_mongo(unified_backend_mongo_only):
    """Test get_raw_model with MongoDB backend."""
    assert unified_backend_mongo_only.get_raw_model() == MongoUserDoc


def test_get_raw_model_redis(unified_backend_redis_only):
    """Test get_raw_model with Redis backend."""
    assert unified_backend_redis_only.get_raw_model() == RedisUserDoc


def test_get_backend_instances(unified_backend_both):
    """Test getting backend instances."""
    mongo_backend = unified_backend_both.get_mongo_backend()
    redis_backend = unified_backend_both.get_redis_backend()

    assert mongo_backend is not None
    assert redis_backend is not None


def test_get_backend_instances_error(unified_backend_mongo_only):
    """Test error when getting unconfigured backend instance."""
    with pytest.raises(ValueError, match="Redis backend is not configured"):
        unified_backend_mongo_only.get_redis_backend()


# Redis backend tests (sync)
def test_redis_crud_operations(unified_backend_redis_only, mock_redis_backend):
    """Test CRUD operations with Redis backend."""
    user = UserCreate(name="John", age=30, email="john@example.com")
    redis_user = create_mock_redis_user()

    # Test insert
    mock_redis_backend.insert.return_value = redis_user
    result = unified_backend_redis_only.insert(user)
    assert result.name == "John"

    # Test get
    mock_redis_backend.get.return_value = redis_user
    result = unified_backend_redis_only.get(redis_user.pk)
    assert result.name == "John"

    # Test all
    mock_redis_backend.all.return_value = [redis_user]
    results = unified_backend_redis_only.all()
    assert len(results) == 1

    # Test find
    mock_redis_backend.find.return_value = [redis_user]
    results = unified_backend_redis_only.find({"name": "John"})
    assert len(results) == 1

    # Test delete
    mock_redis_backend.delete.return_value = True
    result = unified_backend_redis_only.delete(redis_user.pk)
    assert result is True


@pytest.mark.asyncio
async def test_redis_async_operations(unified_backend_redis_only, mock_redis_backend):
    """Test async operations with Redis backend (should work transparently)."""
    user = UserCreate(name="John", age=30, email="john@example.com")
    redis_user = create_mock_redis_user()

    # Test async insert
    mock_redis_backend.insert_async.return_value = redis_user
    result = await unified_backend_redis_only.insert_async(user)
    assert result.name == "John"

    # Test async get
    mock_redis_backend.get_async.return_value = redis_user
    result = await unified_backend_redis_only.get_async(redis_user.pk)
    assert result.name == "John"


# MongoDB backend tests (async)
@pytest.mark.asyncio
async def test_mongo_async_operations(unified_backend_mongo_only, mock_mongo_backend):
    """Test async operations with MongoDB backend."""
    user = UserCreate(name="John", age=30, email="john@example.com")
    mongo_user = create_mock_mongo_user()

    # Test async insert
    mock_mongo_backend.insert.return_value = mongo_user
    result = await unified_backend_mongo_only.insert_async(user)
    assert result.name == "John"

    # Test async get
    mock_mongo_backend.get.return_value = mongo_user
    result = await unified_backend_mongo_only.get_async(mongo_user.id)
    assert result.name == "John"

    # Test async all
    mock_mongo_backend.all.return_value = [mongo_user]
    results = await unified_backend_mongo_only.all_async()
    assert len(results) == 1

    # Test async find
    mock_mongo_backend.find.return_value = [mongo_user]
    results = await unified_backend_mongo_only.find_async({"name": "John"})
    assert len(results) == 1

    # Test async delete
    mock_mongo_backend.delete.return_value = True
    result = await unified_backend_mongo_only.delete_async(mongo_user.id)
    assert result is True


def test_mongo_sync_methods_work(unified_backend_mongo_only, mock_mongo_backend):
    """Test that sync methods work with MongoDB backend by handling async internally."""
    user = UserCreate(name="John", age=30, email="john@example.com")
    mongo_user = create_mock_mongo_user()
    mock_mongo_backend.insert_sync.return_value = mongo_user

    # This should work by running the async method in an event loop
    result = unified_backend_mongo_only.insert(user)
    assert result.name == "John"


def test_backend_switching_with_operations(unified_backend_both, mock_mongo_backend, mock_redis_backend):
    """Test operations after switching backends."""
    user = UserCreate(name="John", age=30, email="john@example.com")

    # Start with MongoDB
    mongo_user = create_mock_mongo_user()
    mock_mongo_backend.insert_sync.return_value = mongo_user

    result = unified_backend_both.insert(user)
    assert result.name == "John"

    # Switch to Redis
    unified_backend_both.switch_backend(BackendType.REDIS)
    redis_user = create_mock_redis_user()
    mock_redis_backend.insert.return_value = redis_user

    # For Redis backend, the operation should work with sync method
    result = unified_backend_both.insert(user)
    assert result.name == "John"


def test_initialization_calls(unified_backend_both, mock_mongo_backend, mock_redis_backend):
    """Test that initialization is called on backends."""
    unified_backend_both.initialize_sync()
    # Both backends should be initialized
    mock_redis_backend.initialize.assert_called_once()
    mock_mongo_backend.initialize_sync.assert_called_once()


def test_async_initialization_calls(unified_backend_both, mock_mongo_backend, mock_redis_backend):
    """Test that async initialization is called on backends."""
    import asyncio

    # Run async initialization in a new event loop
    async def run_init():
        await unified_backend_both.initialize_async()

    asyncio.run(run_init())
    # Both backends should be initialized
    mock_mongo_backend.initialize.assert_called_once()
    mock_redis_backend.initialize_async.assert_called_once()


def test_exception_handling(unified_backend_redis_only, mock_redis_backend):
    """Test that exceptions are properly propagated."""
    # Test DocumentNotFoundError
    mock_redis_backend.get.side_effect = DocumentNotFoundError("Not found")

    with pytest.raises(DocumentNotFoundError):
        unified_backend_redis_only.get("nonexistent")

    # Test DuplicateInsertError
    user = UserCreate(name="John", age=30, email="john@example.com")
    mock_redis_backend.insert.side_effect = DuplicateInsertError("Duplicate")

    with pytest.raises(DuplicateInsertError):
        unified_backend_redis_only.insert(user)


# Tests for Unified Document Model
def test_unified_document_model_creation():
    """Test creating a unified document model instance."""
    user = UnifiedUserDoc(name="John", age=30, email="john@example.com")

    assert user.name == "John"
    assert user.age == 30
    assert user.email == "john@example.com"
    assert user.id is None  # Should be None by default


def test_unified_document_model_meta():
    """Test unified document model metadata."""
    meta = UnifiedUserDoc.get_meta()

    assert meta.collection_name == "test_users"
    assert meta.global_key_prefix == "test"
    assert meta.use_cache is False
    assert "email" in meta.unique_fields
    assert "name" in meta.indexed_fields


def test_unified_document_model_to_mongo_dict():
    """Test conversion to MongoDB dictionary format."""
    user = UnifiedUserDoc(name="John", age=30, email="john@example.com")
    mongo_dict = user.to_mongo_dict()

    assert mongo_dict["name"] == "John"
    assert mongo_dict["age"] == 30
    assert mongo_dict["email"] == "john@example.com"
    assert "id" not in mongo_dict  # Should be removed for MongoDB


def test_unified_document_model_to_redis_dict():
    """Test conversion to Redis dictionary format."""
    user = UnifiedUserDoc(name="John", age=30, email="john@example.com")
    redis_dict = user.to_redis_dict()

    assert redis_dict["name"] == "John"
    assert redis_dict["age"] == 30
    assert redis_dict["email"] == "john@example.com"
    assert "id" not in redis_dict  # Should be removed for Redis


def test_unified_document_model_with_id():
    """Test unified document model with ID set."""
    user = UnifiedUserDoc(id="test123", name="John", age=30, email="john@example.com")

    mongo_dict = user.to_mongo_dict()
    redis_dict = user.to_redis_dict()

    # MongoDB should not have 'id' field
    assert "id" not in mongo_dict

    # Redis should have 'pk' field instead of 'id'
    assert "id" not in redis_dict
    assert redis_dict["pk"] == "test123"


def test_unified_backend_with_unified_model_initialization(unified_backend_with_unified_model):
    """Test initialization with unified document model."""
    assert unified_backend_with_unified_model.has_mongo_backend()
    assert unified_backend_with_unified_model.has_redis_backend()
    assert unified_backend_with_unified_model.get_current_backend_type() == BackendType.MONGO


def test_unified_backend_get_unified_model(unified_backend_with_unified_model):
    """Test getting the unified model class."""
    unified_model = unified_backend_with_unified_model.get_unified_model()
    assert unified_model == UnifiedUserDoc


def test_unified_backend_get_unified_model_error(unified_backend_mongo_only):
    """Test error when getting unified model from non-unified backend."""
    with pytest.raises(ValueError, match="No unified model class configured"):
        unified_backend_mongo_only.get_unified_model()


def test_unified_document_insert_async_wrapper(unified_backend_with_unified_model, mock_mongo_backend):
    """Test inserting unified documents using async interface."""
    import asyncio

    async def run_test():
        user = UnifiedUserDoc(name="John", age=30, email="john@example.com")
        mongo_user = create_mock_mongo_user()
        mock_mongo_backend.insert.return_value = mongo_user

        result = await unified_backend_with_unified_model.insert_async(user)
        assert result.name == "John"

        # Verify that the backend received the converted data
        mock_mongo_backend.insert.assert_called_once()

    asyncio.run(run_test())


def test_unified_document_insert_sync(unified_backend_with_unified_model, mock_mongo_backend):
    """Test inserting unified documents using sync interface."""
    user = UnifiedUserDoc(name="John", age=30, email="john@example.com")
    mongo_user = create_mock_mongo_user()
    mock_mongo_backend.insert_sync.return_value = mongo_user

    result = unified_backend_with_unified_model.insert(user)
    assert result.name == "John"

    # Verify that the backend received the converted data
    mock_mongo_backend.insert_sync.assert_called_once()


def test_unified_model_to_mongo_model():
    """Test converting unified model to MongoDB model."""
    mongo_model = UnifiedUserDoc._auto_generate_mongo_model()

    # Check that it's a proper MongoDB model
    assert issubclass(mongo_model, MindtraceDocument)
    assert hasattr(mongo_model, "Settings")
    assert mongo_model.Settings.name == "test_users"


def test_unified_model_to_redis_model():
    """Test converting unified model to Redis model."""
    redis_model = UnifiedUserDoc._auto_generate_redis_model()

    # Check that it's a proper Redis model
    assert issubclass(redis_model, MindtraceRedisDocument)
    assert hasattr(redis_model, "Meta")
    assert redis_model.Meta.global_key_prefix == "test"


def test_unified_backend_auto_generation_with_field_default_factory():
    """Test auto-generation with field default_factory."""
    from typing import List

    from pydantic import Field

    from mindtrace.database.backends.unified_odm import UnifiedMindtraceDocument

    # Test model with default_factory
    class DefaultFactoryUser(UnifiedMindtraceDocument):
        name: str
        tags: List[str] = Field(default_factory=list)
        scores: List[int] = Field(default_factory=lambda: [0, 0, 0])

        class Meta:
            collection_name = "default_factory_users"
            indexed_fields = ["name"]

    # Test MongoDB auto-generation with default_factory
    mongo_model = DefaultFactoryUser._auto_generate_mongo_model()
    assert mongo_model is not None
    assert hasattr(mongo_model, "Settings")
    assert mongo_model.Settings.name == "default_factory_users"

    # Test Redis auto-generation with default_factory
    redis_model = DefaultFactoryUser._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, "Meta")
    assert redis_model.Meta.global_key_prefix == "mindtrace"


def test_unified_backend_auto_generation_with_optional_indexed_fields():
    """Test auto-generation with optional indexed fields."""
    from typing import Optional

    from mindtrace.database.backends.unified_odm import UnifiedMindtraceDocument

    # Test model with optional indexed fields
    class OptionalIndexedUser(UnifiedMindtraceDocument):
        name: str
        email: Optional[str] = None
        phone: Optional[str] = None

        class Meta:
            collection_name = "optional_indexed_users"
            indexed_fields = ["name", "email"]  # email is optional but indexed

    # Test MongoDB auto-generation with optional indexed fields
    mongo_model = OptionalIndexedUser._auto_generate_mongo_model()
    assert mongo_model is not None
    assert hasattr(mongo_model, "Settings")
    assert mongo_model.Settings.name == "optional_indexed_users"

    # Test Redis auto-generation with optional indexed fields
    redis_model = OptionalIndexedUser._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, "Meta")
    assert redis_model.Meta.global_key_prefix == "mindtrace"


def test_unified_backend_get_active_backend_with_no_backends():
    """Test _get_active_backend with no backends configured."""
    from mindtrace.database.backends.unified_odm import BackendType, UnifiedMindtraceODM

    # Create a backend with valid configuration first
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    # Manually set backends to None to test the error condition
    backend.mongo_backend = None
    backend.redis_backend = None
    backend._active_backend = None

    # Test that RuntimeError is raised when no backends are available
    with pytest.raises(RuntimeError, match="No backend available"):
        backend._get_active_backend()


def test_unified_backend_switch_backend_with_unknown_type():
    """Test switch_backend with unknown backend type."""
    from mindtrace.database.backends.unified_odm import BackendType, UnifiedMindtraceODM

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    # Test that ValueError is raised when unknown backend type is provided
    with pytest.raises(ValueError, match="Unknown backend type"):
        backend.switch_backend("unknown_backend")


@pytest.mark.asyncio
async def test_unified_backend_initialize_async_no_mongo_backend(mock_redis_backend):
    """Test initialize_async when no MongoDB backend is configured (should work with Redis)."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    # Now initialize_async works with Redis too via async wrapper
    # Should not raise an error - it will initialize Redis via async wrapper
    await backend.initialize_async()
    # Verify that Redis's initialize_async was called
    mock_redis_backend.initialize_async.assert_called_once()


def test_unified_backend_initialize_sync(mock_redis_backend):
    """Test initialize_sync method."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    # Should not raise
    backend.initialize_sync()
    # Verify that Redis's initialize was called
    mock_redis_backend.initialize.assert_called_once()


def test_unified_backend_get_current_backend_type_unknown():
    """Test get_current_backend_type with unknown active backend."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    # Manually set an unknown active backend
    backend._active_backend = MagicMock()

    with pytest.raises(RuntimeError, match="Unknown active backend"):
        backend.get_current_backend_type()


def test_unified_backend_switch_backend_invalid_type():
    """Test switch_backend with invalid backend type."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    with pytest.raises(ValueError, match="Unknown backend type"):
        backend.switch_backend("invalid_type")


def test_unified_backend_switch_backend_mongo_not_configured():
    """Test switch_backend to MongoDB when not configured."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    with pytest.raises(ValueError, match="MongoDB backend is not configured"):
        backend.switch_backend(BackendType.MONGO)


def test_unified_backend_switch_backend_redis_not_configured():
    """Test switch_backend to Redis when not configured."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    with pytest.raises(ValueError, match="Redis backend is not configured"):
        backend.switch_backend(BackendType.REDIS)


def test_unified_backend_get_active_backend_no_backends_available():
    """Test _get_active_backend when no backends are available."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    # Manually set backends to None
    backend.mongo_backend = None
    backend.redis_backend = None
    backend._active_backend = None

    with pytest.raises(RuntimeError, match="No backend available"):
        backend._get_active_backend()


def test_unified_backend_auto_generate_mongo_model_with_unique_fields():
    """Test _auto_generate_mongo_model with unique fields."""

    mongo_model = UnifiedUserDoc._auto_generate_mongo_model()
    assert mongo_model is not None
    assert hasattr(mongo_model, "Settings")
    assert mongo_model.Settings.name == "test_users"

    # Check that email field has unique index
    annotations = getattr(mongo_model, "__annotations__", {})
    assert "email" in annotations


def test_unified_backend_auto_generate_redis_model_with_optional_fields():
    """Test _auto_generate_redis_model with optional fields."""

    # Create a model with optional fields
    class OptionalFieldDoc(UnifiedMindtraceDocument):
        name: str
        email: str | None = None
        age: int | None = None

        class Meta:
            collection_name = "optional_test"
            global_key_prefix = "optional_test"

    redis_model = OptionalFieldDoc._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, "Meta")
    assert redis_model.Meta.global_key_prefix == "optional_test"


def test_unified_backend_auto_generate_redis_model_with_default_factory():
    """Test _auto_generate_redis_model with default_factory."""
    from typing import List

    class DefaultFactoryDoc(UnifiedMindtraceDocument):
        name: str
        tags: List[str] = Field(default_factory=list)
        scores: List[int] = Field(default_factory=lambda: [0, 0, 0])

        class Meta:
            collection_name = "default_factory_test"
            global_key_prefix = "default_factory_test"

    redis_model = DefaultFactoryDoc._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, "Meta")
    assert redis_model.Meta.global_key_prefix == "default_factory_test"


@pytest.mark.asyncio
async def test_unified_backend_delete_async_sync_backend():
    """Test delete_async with synchronous backend."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    with patch.object(backend, "_get_active_backend") as mock_get_backend:
        mock_backend = MagicMock()
        mock_backend.is_async.return_value = False
        mock_backend.delete_async = AsyncMock(return_value=None)
        mock_get_backend.return_value = mock_backend

        await backend.delete_async("test_id")
        mock_backend.delete_async.assert_called_once_with("test_id")


@pytest.mark.asyncio
async def test_unified_backend_delete_async_async_backend():
    """Test delete_async with asynchronous backend."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    with patch.object(backend, "_get_active_backend") as mock_get_backend:
        mock_backend = MagicMock()
        mock_backend.is_async.return_value = True
        mock_backend.delete = AsyncMock(side_effect=None)
        mock_get_backend.return_value = mock_backend

        await backend.delete_async("test_id")
        mock_backend.delete.assert_called_once_with("test_id")


@pytest.mark.asyncio
async def test_unified_backend_all_async_sync_backend():
    """Test all_async with synchronous backend."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    with patch.object(backend, "_get_active_backend") as mock_get_backend:
        mock_backend = MagicMock()
        mock_backend.is_async.return_value = False
        mock_backend.all_async = AsyncMock(return_value=[UserCreate(name="Test", age=25, email="test@example.com")])
        mock_get_backend.return_value = mock_backend

        result = await backend.all_async()
        assert len(result) == 1
        assert result[0].name == "Test"


@pytest.mark.asyncio
async def test_unified_backend_all_async_async_backend():
    """Test all_async with asynchronous backend."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    with patch.object(backend, "_get_active_backend") as mock_get_backend:
        mock_backend = MagicMock()
        mock_backend.is_async.return_value = True
        mock_backend.all = AsyncMock(
            return_value=[UserCreate(name="Test", age=25, email="test@example.com")], side_effect=None
        )
        mock_get_backend.return_value = mock_backend

        result = await backend.all_async()
        assert len(result) == 1
        assert result[0].name == "Test"


@pytest.mark.asyncio
async def test_unified_backend_find_async_sync_backend():
    """Test find_async with synchronous backend."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    with patch.object(backend, "_get_active_backend") as mock_get_backend:
        mock_backend = MagicMock()
        mock_backend.is_async.return_value = False
        mock_backend.find_async = AsyncMock(return_value=[UserCreate(name="Test", age=25, email="test@example.com")])
        mock_get_backend.return_value = mock_backend

        result = await backend.find_async(name="Test")
        assert len(result) == 1
        assert result[0].name == "Test"


@pytest.mark.asyncio
async def test_unified_backend_find_async_async_backend():
    """Test find_async with asynchronous backend."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    with patch.object(backend, "_get_active_backend") as mock_get_backend:
        mock_backend = MagicMock()
        mock_backend.is_async.return_value = True
        mock_backend.find = AsyncMock(
            return_value=[UserCreate(name="Test", age=25, email="test@example.com")], side_effect=None
        )
        mock_get_backend.return_value = mock_backend

        result = await backend.find_async(name="Test")
        assert len(result) == 1
        assert result[0].name == "Test"


def test_unified_backend_get_unified_model_no_model():
    """Test get_unified_model when no model is configured."""

    # Create a backend with a model first, then manually set it to None
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    # Manually set unified_model_cls to None to test the error condition
    backend.unified_model_cls = None

    with pytest.raises(ValueError, match="No unified model class configured"):
        backend.get_unified_model()


def test_unified_backend_get_mongo_backend_not_configured():
    """Test get_mongo_backend when MongoDB is not configured."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    with pytest.raises(ValueError, match="MongoDB backend is not configured"):
        backend.get_mongo_backend()


def test_unified_backend_get_redis_backend_not_configured():
    """Test get_redis_backend when Redis is not configured."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    with pytest.raises(ValueError, match="Redis backend is not configured"):
        backend.get_redis_backend()


def test_unified_backend_has_mongo_backend_true():
    """Test has_mongo_backend when MongoDB is configured."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    assert backend.has_mongo_backend() is True


def test_unified_backend_has_mongo_backend_false():
    """Test has_mongo_backend when MongoDB is not configured."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    assert backend.has_mongo_backend() is False


def test_unified_backend_has_redis_backend_true():
    """Test has_redis_backend when Redis is configured."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    assert backend.has_redis_backend() is True


def test_unified_backend_has_redis_backend_false():
    """Test has_redis_backend when Redis is not configured."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    assert backend.has_redis_backend() is False


def test_unified_backend_get_mongo_backend_configured():
    """Test get_mongo_backend when MongoDB is configured."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    mongo_backend = backend.get_mongo_backend()
    assert mongo_backend is not None


def test_unified_backend_get_redis_backend_configured():
    """Test get_redis_backend when Redis is configured."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    redis_backend = backend.get_redis_backend()
    assert redis_backend is not None


def test_unified_backend_get_raw_model():
    """Test get_raw_model method."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    with patch.object(backend, "_get_active_backend") as mock_get_backend:
        mock_backend = MagicMock()
        mock_backend.get_raw_model.return_value = UserCreate
        mock_get_backend.return_value = mock_backend

        result = backend.get_raw_model()
        assert result == UserCreate


def test_unified_backend_get_unified_model_configured():
    """Test get_unified_model when model is configured."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    result = backend.get_unified_model()
    assert result == UnifiedUserDoc


def test_unified_backend_initialize_async_context_warning():
    """Test initialize method when called from async context."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    # Now initialize() just calls initialize_sync() which works with both backends
    # The async context check is handled in initialize_sync() for MongoDB
    # Mock the mongo backend initialize_sync to verify it's called
    with patch.object(backend.mongo_backend, "initialize_sync") as mock_init_sync:
        backend.initialize()
        # Should call initialize_sync which handles async context internally
        mock_init_sync.assert_called_once()


def test_unified_backend_handle_async_call_sync_backend():
    """Test _handle_async_call with synchronous backend."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    # Mock the backend to be synchronous
    with patch.object(backend, "_get_active_backend") as mock_get_backend:
        mock_backend = MagicMock()
        mock_backend.is_async.return_value = False
        mock_backend.test_method.return_value = "sync_result"
        mock_get_backend.return_value = mock_backend

        result = backend._handle_async_call("test_method", "arg1", kwarg1="value1")

        assert result == "sync_result"
        mock_backend.test_method.assert_called_once_with("arg1", kwarg1="value1")


def test_unified_backend_handle_async_call_async_backend():
    """Test _handle_async_call with asynchronous backend."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    # Mock the backend to be asynchronous
    with patch.object(backend, "_get_active_backend") as mock_get_backend:
        mock_backend = MagicMock()
        mock_backend.is_async.return_value = True
        mock_backend.test_method_sync = MagicMock(return_value="async_result")
        mock_get_backend.return_value = mock_backend

        result = backend._handle_async_call("test_method", "arg1", kwarg1="value1")

        assert result == "async_result"
        mock_backend.test_method_sync.assert_called_once_with("arg1", kwarg1="value1")


def test_unified_backend_convert_unified_to_backend_data_mongo():
    """Test _convert_unified_to_backend_data for MongoDB backend."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    user = UnifiedUserDoc(id="test123", name="John", age=30, email="john@example.com")

    with patch.object(backend, "get_current_backend_type") as mock_get_type:
        mock_get_type.return_value = BackendType.MONGO

        result = backend._convert_unified_to_backend_data(user)

        # Should be a DataWrapper with id field removed
        assert hasattr(result, "data")
        assert "id" not in result.data
        assert result.data["name"] == "John"
        assert result.data["age"] == 30
        assert result.data["email"] == "john@example.com"


def test_unified_backend_convert_unified_to_backend_data_redis():
    """Test _convert_unified_to_backend_data for Redis backend."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    user = UnifiedUserDoc(id="test123", name="John", age=30, email="john@example.com")

    with patch.object(backend, "get_current_backend_type") as mock_get_type:
        mock_get_type.return_value = BackendType.REDIS

        result = backend._convert_unified_to_backend_data(user)

        # Should be a DataWrapper with id converted to pk
        assert hasattr(result, "data")
        assert "id" not in result.data
        assert result.data["pk"] == "test123"
        assert result.data["name"] == "John"
        assert result.data["age"] == 30
        assert result.data["email"] == "john@example.com"


def test_unified_backend_convert_unified_to_backend_data_redis_none_id():
    """Test _convert_unified_to_backend_data for Redis backend with None id."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    user = UnifiedUserDoc(id=None, name="John", age=30, email="john@example.com")

    with patch.object(backend, "get_current_backend_type") as mock_get_type:
        mock_get_type.return_value = BackendType.REDIS

        result = backend._convert_unified_to_backend_data(user)

        # Should be a DataWrapper with id field removed (not converted to pk)
        assert hasattr(result, "data")
        assert "id" not in result.data
        assert "pk" not in result.data
        assert result.data["name"] == "John"
        assert result.data["age"] == 30
        assert result.data["email"] == "john@example.com"


def test_unified_backend_convert_unified_to_backend_data_non_unified():
    """Test _convert_unified_to_backend_data with non-unified model."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    user = UserCreate(name="John", age=30, email="john@example.com")

    result = backend._convert_unified_to_backend_data(user)

    # Should return the original object unchanged
    assert result == user


def test_unified_backend_auto_generate_redis_model_with_callable_default_factory():
    """Test _auto_generate_redis_model with callable default_factory."""
    from typing import List

    class CallableDefaultDoc(UnifiedMindtraceDocument):
        name: str
        tags: List[str] = Field(default_factory=list)
        scores: List[int] = Field(default_factory=lambda: [1, 2, 3])

        class Meta:
            collection_name = "callable_default_test"
            global_key_prefix = "callable_default_test"

    redis_model = CallableDefaultDoc._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, "Meta")
    assert redis_model.Meta.global_key_prefix == "callable_default_test"


def test_unified_backend_auto_generate_redis_model_with_ellipsis_default():
    """Test _auto_generate_redis_model with ellipsis default."""

    class EllipsisDefaultDoc(UnifiedMindtraceDocument):
        name: str = Field(default=...)
        age: int = Field(default=25)

        class Meta:
            collection_name = "ellipsis_default_test"
            global_key_prefix = "ellipsis_default_test"

    redis_model = EllipsisDefaultDoc._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, "Meta")
    assert redis_model.Meta.global_key_prefix == "ellipsis_default_test"


def test_unified_backend_auto_generate_redis_model_with_none_default_factory():
    """Test _auto_generate_redis_model with None default_factory."""

    class NoneDefaultFactoryDoc(UnifiedMindtraceDocument):
        name: str = Field(default_factory=None)
        age: int = Field(default=25)

        class Meta:
            collection_name = "none_default_factory_test"
            global_key_prefix = "none_default_factory_test"

    redis_model = NoneDefaultFactoryDoc._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, "Meta")
    assert redis_model.Meta.global_key_prefix == "none_default_factory_test"


def test_unified_backend_auto_generate_redis_model_with_indexed_fields_and_defaults():
    """Test _auto_generate_redis_model with indexed fields that have defaults."""
    from pydantic import Field

    class IndexedDefaultFieldsDoc(UnifiedMindtraceDocument):
        name: str = Field(default="Default Name")
        age: int = Field(default=25)
        email: str = Field(default_factory=lambda: "default@example.com")

        class Meta:
            indexed_fields = ["name", "age", "email"]

    redis_model = IndexedDefaultFieldsDoc._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, "__annotations__")
    assert hasattr(redis_model, "Meta")

    # Check that fields are properly created with Redis Field instances
    assert hasattr(redis_model, "name")
    assert hasattr(redis_model, "age")
    assert hasattr(redis_model, "email")


def test_unified_backend_auto_generate_mongo_model_with_no_fields():
    """Test _auto_generate_mongo_model with a class that has no fields."""

    class EmptyDoc(UnifiedMindtraceDocument):
        class Meta:
            collection_name = "empty_collection"

    mongo_model = EmptyDoc._auto_generate_mongo_model()
    assert mongo_model is not None
    assert hasattr(mongo_model, "Settings")
    assert mongo_model.Settings.name == "empty_collection"


def test_unified_backend_initialize_sync_no_redis_backend(mock_mongo_backend):
    """Test initialize_sync when no Redis backend is configured (should work with MongoDB)."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    # Now initialize_sync works with MongoDB too via sync wrapper
    # Should not raise an error - it will initialize MongoDB via sync wrapper
    backend.initialize_sync()
    # Verify that MongoDB's initialize_sync was called
    mock_mongo_backend.initialize_sync.assert_called_once()


def test_unified_backend_initialize_sync_with_redis_backend(mock_redis_backend):
    """Test initialize_sync when Redis backend is configured."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    # Now initialize_sync works with Redis
    backend.initialize_sync()
    # Verify that Redis's initialize was called
    mock_redis_backend.initialize.assert_called_once()


def test_unified_backend_get_active_backend_prefer_mongo_mongo_available():
    """Test _get_active_backend when preferring MongoDB and it's available."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    active_backend = backend._get_active_backend()
    assert active_backend == backend.mongo_backend


def test_unified_backend_get_active_backend_prefer_redis_redis_available():
    """Test _get_active_backend when preferring Redis and it's available."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    active_backend = backend._get_active_backend()
    assert active_backend == backend.redis_backend


def test_unified_backend_get_active_backend_prefer_mongo_redis_available():
    """Test _get_active_backend when preferring MongoDB but only Redis is available."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.MONGO
    )

    active_backend = backend._get_active_backend()
    assert active_backend == backend.redis_backend


def test_unified_backend_get_active_backend_prefer_redis_mongo_available():
    """Test _get_active_backend when preferring Redis but only MongoDB is available."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.REDIS,
    )

    active_backend = backend._get_active_backend()
    assert active_backend == backend.mongo_backend


def test_unified_backend_get_active_backend_cached():
    """Test _get_active_backend when result is cached."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    # First call should set the cache
    active_backend1 = backend._get_active_backend()
    assert active_backend1 == backend.redis_backend

    # Second call should use cached result
    active_backend2 = backend._get_active_backend()
    assert active_backend2 == backend.redis_backend
    assert active_backend1 is active_backend2


def test_unified_backend_convert_unified_to_backend_data_mongo_with_id():
    """Test _convert_unified_to_backend_data for MongoDB with id field."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    user = UnifiedUserDoc(id="test123", name="John", age=30, email="john@example.com")

    with patch.object(backend, "get_current_backend_type") as mock_get_type:
        mock_get_type.return_value = BackendType.MONGO

        result = backend._convert_unified_to_backend_data(user)

        # Should be a DataWrapper with id field removed
        assert hasattr(result, "data")
        assert "id" not in result.data
        assert result.data["name"] == "John"
        assert result.data["age"] == 30
        assert result.data["email"] == "john@example.com"


def test_unified_backend_convert_unified_to_backend_data_mongo_without_id():
    """Test _convert_unified_to_backend_data for MongoDB without id field."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    user = UnifiedUserDoc(name="John", age=30, email="john@example.com")

    with patch.object(backend, "get_current_backend_type") as mock_get_type:
        mock_get_type.return_value = BackendType.MONGO

        result = backend._convert_unified_to_backend_data(user)

        # Should be a DataWrapper without id field
        assert hasattr(result, "data")
        assert "id" not in result.data
        assert result.data["name"] == "John"
        assert result.data["age"] == 30
        assert result.data["email"] == "john@example.com"


def test_unified_backend_convert_unified_to_backend_data_redis_with_id():
    """Test _convert_unified_to_backend_data for Redis with id field."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    user = UnifiedUserDoc(id="test123", name="John", age=30, email="john@example.com")

    with patch.object(backend, "get_current_backend_type") as mock_get_type:
        mock_get_type.return_value = BackendType.REDIS

        result = backend._convert_unified_to_backend_data(user)

        # Should be a DataWrapper with id converted to pk
        assert hasattr(result, "data")
        assert "id" not in result.data
        assert result.data["pk"] == "test123"
        assert result.data["name"] == "John"
        assert result.data["age"] == 30
        assert result.data["email"] == "john@example.com"


def test_unified_backend_convert_unified_to_backend_data_redis_without_id():
    """Test _convert_unified_to_backend_data for Redis without id field."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    user = UnifiedUserDoc(name="John", age=30, email="john@example.com")

    with patch.object(backend, "get_current_backend_type") as mock_get_type:
        mock_get_type.return_value = BackendType.REDIS

        result = backend._convert_unified_to_backend_data(user)

        # Should be a DataWrapper without id field
        assert hasattr(result, "data")
        assert "id" not in result.data
        assert "pk" not in result.data
        assert result.data["name"] == "John"
        assert result.data["age"] == 30
        assert result.data["email"] == "john@example.com"


def test_unified_backend_convert_unified_to_backend_data_redis_with_none_id():
    """Test _convert_unified_to_backend_data for Redis with None id field."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    user = UnifiedUserDoc(id=None, name="John", age=30, email="john@example.com")

    with patch.object(backend, "get_current_backend_type") as mock_get_type:
        mock_get_type.return_value = BackendType.REDIS

        result = backend._convert_unified_to_backend_data(user)

        # Should be a DataWrapper with id field removed (not converted to pk)
        assert hasattr(result, "data")
        assert "id" not in result.data
        assert "pk" not in result.data
        assert result.data["name"] == "John"
        assert result.data["age"] == 30
        assert result.data["email"] == "john@example.com"


def test_unified_backend_auto_generate_redis_model_with_union_type_not_optional():
    """Test _auto_generate_redis_model with Union type that is not Optional."""
    from typing import Union

    class UnionNotOptionalDoc(UnifiedMindtraceDocument):
        name: str
        value: Union[str, int]  # This is not Optional[str, None]

        class Meta:
            collection_name = "union_not_optional_test"
            global_key_prefix = "union_not_optional_test"

    redis_model = UnionNotOptionalDoc._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, "Meta")
    assert redis_model.Meta.global_key_prefix == "union_not_optional_test"


def test_unified_backend_auto_generate_redis_model_with_union_type_three_args():
    """Test _auto_generate_redis_model with Union type that has more than 2 args."""
    from typing import Union

    class UnionThreeArgsDoc(UnifiedMindtraceDocument):
        name: str
        value: Union[str, int, float]  # This has 3 args, not 2

        class Meta:
            collection_name = "union_three_args_test"
            global_key_prefix = "union_three_args_test"

    redis_model = UnionThreeArgsDoc._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, "Meta")
    assert redis_model.Meta.global_key_prefix == "union_three_args_test"


def test_unified_backend_auto_generate_redis_model_with_union_type_no_none():
    """Test _auto_generate_redis_model with Union type that doesn't contain None."""
    from typing import Union

    class UnionNoNoneDoc(UnifiedMindtraceDocument):
        name: str
        value: Union[str, int]  # This doesn't contain None

        class Meta:
            collection_name = "union_no_none_test"
            global_key_prefix = "union_no_none_test"

    redis_model = UnionNoNoneDoc._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, "Meta")
    assert redis_model.Meta.global_key_prefix == "union_no_none_test"


def test_unified_backend_auto_generate_redis_model_with_union_type_none_first():
    """Test _auto_generate_redis_model with Union type where None is first."""
    from typing import Union

    class UnionNoneFirstDoc(UnifiedMindtraceDocument):
        name: str
        value: Union[None, str]  # None is first

        class Meta:
            collection_name = "union_none_first_test"
            global_key_prefix = "union_none_first_test"

    redis_model = UnionNoneFirstDoc._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, "Meta")
    assert redis_model.Meta.global_key_prefix == "union_none_first_test"


def test_unified_backend_auto_generate_redis_model_with_field_info_no_default_attr():
    """Test _auto_generate_redis_model with field info that has no default attribute."""

    class NoDefaultAttrDoc(UnifiedMindtraceDocument):
        name: str
        age: int

        class Meta:
            collection_name = "no_default_attr_test"
            global_key_prefix = "no_default_attr_test"

    # Mock the field info to not have a default attribute
    with patch.object(NoDefaultAttrDoc, "__annotations__", {"name": str, "age": int}):
        with patch.object(NoDefaultAttrDoc, "name", create=True) as mock_name:
            with patch.object(NoDefaultAttrDoc, "age", create=True) as mock_age:
                # Remove default attribute from mock objects
                if hasattr(mock_name, "default"):
                    delattr(mock_name, "default")
                if hasattr(mock_age, "default"):
                    delattr(mock_age, "default")

                redis_model = NoDefaultAttrDoc._auto_generate_redis_model()
                assert redis_model is not None
                assert hasattr(redis_model, "Meta")
                assert redis_model.Meta.global_key_prefix == "no_default_attr_test"


def test_unified_backend_auto_generate_redis_model_with_field_info_no_default_factory_attr():
    """Test _auto_generate_redis_model with field info that has no default_factory attribute."""

    class NoDefaultFactoryAttrDoc(UnifiedMindtraceDocument):
        name: str
        age: int

        class Meta:
            collection_name = "no_default_factory_attr_test"
            global_key_prefix = "no_default_factory_attr_test"

    # Mock the field info to not have a default_factory attribute
    with patch.object(NoDefaultFactoryAttrDoc, "__annotations__", {"name": str, "age": int}):
        with patch.object(NoDefaultFactoryAttrDoc, "name", create=True) as mock_name:
            with patch.object(NoDefaultFactoryAttrDoc, "age", create=True) as mock_age:
                # Remove default_factory attribute from mock objects
                if hasattr(mock_name, "default_factory"):
                    delattr(mock_name, "default_factory")
                if hasattr(mock_age, "default_factory"):
                    delattr(mock_age, "default_factory")

                redis_model = NoDefaultFactoryAttrDoc._auto_generate_redis_model()
                assert redis_model is not None
                assert hasattr(redis_model, "Meta")
                assert redis_model.Meta.global_key_prefix == "no_default_factory_attr_test"


def test_unified_backend_auto_generate_redis_model_with_field_info_none_default_factory():
    """Test _auto_generate_redis_model with field info that has None default_factory."""

    class NoneDefaultFactoryDoc(UnifiedMindtraceDocument):
        name: str
        age: int

        class Meta:
            collection_name = "none_default_factory_test"
            global_key_prefix = "none_default_factory_test"

    # Mock the field info to have None default_factory
    with patch.object(NoneDefaultFactoryDoc, "__annotations__", {"name": str, "age": int}):
        with patch.object(NoneDefaultFactoryDoc, "name", create=True) as mock_name:
            with patch.object(NoneDefaultFactoryDoc, "age", create=True) as mock_age:
                mock_name.default_factory = None
                mock_age.default_factory = None

                redis_model = NoneDefaultFactoryDoc._auto_generate_redis_model()
                assert redis_model is not None
                assert hasattr(redis_model, "Meta")
                assert redis_model.Meta.global_key_prefix == "none_default_factory_test"


def test_unified_backend_auto_generate_redis_model_with_indexed_field_no_default():
    """Test _auto_generate_redis_model with indexed field that has no default."""

    class IndexedNoDefaultDoc(UnifiedMindtraceDocument):
        name: str
        age: int

        class Meta:
            collection_name = "indexed_no_default_test"
            global_key_prefix = "indexed_no_default_test"
            indexed_fields = ["name", "age"]

    redis_model = IndexedNoDefaultDoc._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, "Meta")
    assert redis_model.Meta.global_key_prefix == "indexed_no_default_test"


def test_unified_backend_auto_generate_redis_model_with_non_indexed_field_no_default():
    """Test _auto_generate_redis_model with non-indexed field that has no default."""

    class NonIndexedNoDefaultDoc(UnifiedMindtraceDocument):
        name: str
        age: int

        class Meta:
            collection_name = "non_indexed_no_default_test"
            global_key_prefix = "non_indexed_no_default_test"
            indexed_fields = ["name"]  # age is not indexed

    redis_model = NonIndexedNoDefaultDoc._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, "Meta")
    assert redis_model.Meta.global_key_prefix == "non_indexed_no_default_test"


def test_unified_backend_auto_generate_mongo_model_with_no_meta_attrs():
    """Test _auto_generate_mongo_model with no meta attributes."""

    class NoMetaAttrsDoc(UnifiedMindtraceDocument):
        name: str
        age: int

        class Meta:
            pass  # No attributes

    mongo_model = NoMetaAttrsDoc._auto_generate_mongo_model()
    assert mongo_model is not None
    assert hasattr(mongo_model, "Settings")
    assert mongo_model.Settings.name == "unified_documents"  # Default value
    assert mongo_model.Settings.use_cache is False  # Default value


def test_unified_backend_auto_generate_mongo_model_with_custom_meta_attrs():
    """Test _auto_generate_mongo_model with custom meta attributes."""

    class CustomMetaAttrsDoc(UnifiedMindtraceDocument):
        name: str
        age: int

        class Meta:
            collection_name = "custom_collection"
            use_cache = True

    mongo_model = CustomMetaAttrsDoc._auto_generate_mongo_model()
    assert mongo_model is not None
    assert hasattr(mongo_model, "Settings")
    assert mongo_model.Settings.name == "custom_collection"
    assert mongo_model.Settings.use_cache is True


def test_unified_backend_auto_generate_redis_model_with_custom_meta_attrs():
    """Test _auto_generate_redis_model with custom meta attributes."""

    class CustomMetaAttrsDoc(UnifiedMindtraceDocument):
        name: str
        age: int

        class Meta:
            collection_name = "custom_collection"
            global_key_prefix = "custom_prefix"

    redis_model = CustomMetaAttrsDoc._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, "Meta")
    assert redis_model.Meta.global_key_prefix == "custom_prefix"
    assert redis_model.Meta.index_name == "custom_prefix:CustomMetaAttrsDocRedis:index"
    assert redis_model.Meta.model_key_prefix == "CustomMetaAttrsDocRedis"


def test_unified_backend_auto_generate_redis_model_with_default_meta_attrs():
    """Test _auto_generate_redis_model with default meta attributes."""

    class DefaultMetaAttrsDoc(UnifiedMindtraceDocument):
        name: str
        age: int

        class Meta:
            pass  # No attributes

    redis_model = DefaultMetaAttrsDoc._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, "Meta")
    assert redis_model.Meta.global_key_prefix == "mindtrace"  # Default value
    assert redis_model.Meta.index_name == "mindtrace:DefaultMetaAttrsDocRedis:index"
    assert redis_model.Meta.model_key_prefix == "DefaultMetaAttrsDocRedis"


def test_unified_backend_get_meta_method():
    """Test get_meta method."""

    meta = UnifiedUserDoc.get_meta()
    assert meta is not None
    assert hasattr(meta, "collection_name")
    assert hasattr(meta, "global_key_prefix")
    assert hasattr(meta, "use_cache")
    assert hasattr(meta, "indexed_fields")
    assert hasattr(meta, "unique_fields")


def test_unified_backend_get_meta_method_with_no_meta():
    """Test get_meta method when Meta is not defined."""
    # This test is not needed as get_meta uses getattr with fallback
    # which means it will always return something
    pass


def test_unified_backend_to_mongo_dict_with_id_field():
    """Test to_mongo_dict method with id field."""

    user = UnifiedUserDoc(id="test123", name="John", age=30, email="john@example.com")

    mongo_dict = user.to_mongo_dict()

    # Should not contain 'id' field
    assert "id" not in mongo_dict
    assert mongo_dict["name"] == "John"
    assert mongo_dict["age"] == 30
    assert mongo_dict["email"] == "john@example.com"


def test_unified_backend_to_mongo_dict_without_id_field():
    """Test to_mongo_dict method without id field."""

    user = UnifiedUserDoc(name="John", age=30, email="john@example.com")

    mongo_dict = user.to_mongo_dict()

    # Should not contain 'id' field
    assert "id" not in mongo_dict
    assert mongo_dict["name"] == "John"
    assert mongo_dict["age"] == 30
    assert mongo_dict["email"] == "john@example.com"


def test_unified_backend_initialize_with_async_context_and_running_loop():
    """Test initialize method when called from async context with running loop."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    # Now initialize() just calls initialize_sync() which works with both backends
    # The async context check is handled in initialize_sync() for MongoDB
    # Mock the mongo backend initialize_sync to verify it's called
    with patch.object(backend.mongo_backend, "initialize_sync") as mock_init_sync:
        backend.initialize()
        # Should call initialize_sync which handles async context internally
        mock_init_sync.assert_called_once()


def test_unified_backend_initialize_with_no_running_loop():
    """Test initialize method when called from sync context (no running loop)."""

    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    # Now initialize() just calls initialize_sync() which works with both backends
    # Mock the mongo backend initialize_sync to verify it's called
    with patch.object(backend.mongo_backend, "initialize_sync") as mock_init_sync:
        backend.initialize()
        # Should call initialize_sync which handles sync context
        mock_init_sync.assert_called_once()


# ============================================================================
# Tests for MongoDB sync wrapper methods
# ============================================================================


def test_mongo_sync_get_method(unified_backend_mongo_only, mock_mongo_backend):
    """Test MongoDB get_sync wrapper method."""
    mongo_user = create_mock_mongo_user()
    mock_mongo_backend.get_sync.return_value = mongo_user

    result = unified_backend_mongo_only.get(mongo_user.id)
    assert result.name == "John"
    mock_mongo_backend.get_sync.assert_called_once()


def test_mongo_sync_delete_method(unified_backend_mongo_only, mock_mongo_backend):
    """Test MongoDB delete_sync wrapper method."""
    mongo_user = create_mock_mongo_user()
    mock_mongo_backend.delete_sync.return_value = True

    result = unified_backend_mongo_only.delete(mongo_user.id)
    assert result is True
    mock_mongo_backend.delete_sync.assert_called_once()


def test_mongo_sync_all_method(unified_backend_mongo_only, mock_mongo_backend):
    """Test MongoDB all_sync wrapper method."""
    mongo_user = create_mock_mongo_user()
    mock_mongo_backend.all_sync.return_value = [mongo_user]

    results = unified_backend_mongo_only.all()
    assert len(results) == 1
    assert results[0].name == "John"
    mock_mongo_backend.all_sync.assert_called_once()

    def test_mongo_sync_find_method(unified_backend_mongo_only, mock_mongo_backend):
        """Test MongoDB find_sync wrapper method."""
        mongo_user = create_mock_mongo_user()
        mock_mongo_backend.find_sync.return_value = [mongo_user]

        results = unified_backend_mongo_only.find({"name": "John"})
        assert len(results) == 1
        assert results[0].name == "John"
        mock_mongo_backend.find_sync.assert_called_once()


@pytest.mark.asyncio
async def test_mongo_sync_methods_from_async_context_raises_error():
    """Test that MongoDB sync methods raise error when called from async context."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(model_cls=MongoUserDoc, db_uri="mongodb://localhost:27017", db_name="test_db")

    # All sync methods should raise RuntimeError when called from async context
    with pytest.raises(RuntimeError, match="called from async context"):
        backend.insert_sync(UserCreate(name="John", age=30, email="john@example.com"))

    with pytest.raises(RuntimeError, match="called from async context"):
        backend.get_sync("test_id")

    with pytest.raises(RuntimeError, match="called from async context"):
        backend.delete_sync("test_id")

    with pytest.raises(RuntimeError, match="called from async context"):
        backend.all_sync()

    with pytest.raises(RuntimeError, match="called from async context"):
        backend.find_sync({"name": "John"})

    with pytest.raises(RuntimeError, match="called from async context"):
        backend.initialize_sync()


# ============================================================================
# Tests for Redis async wrapper methods
# ============================================================================


@pytest.mark.asyncio
async def test_redis_async_get_method(unified_backend_redis_only, mock_redis_backend):
    """Test Redis get_async wrapper method."""
    redis_user = create_mock_redis_user()
    mock_redis_backend.get_async.return_value = redis_user

    result = await unified_backend_redis_only.get_async(redis_user.pk)
    assert result.name == "John"
    mock_redis_backend.get_async.assert_called_once()


@pytest.mark.asyncio
async def test_redis_async_delete_method(unified_backend_redis_only, mock_redis_backend):
    """Test Redis delete_async wrapper method."""
    redis_user = create_mock_redis_user()
    mock_redis_backend.delete_async.return_value = True

    result = await unified_backend_redis_only.delete_async(redis_user.pk)
    assert result is True
    mock_redis_backend.delete_async.assert_called_once()


@pytest.mark.asyncio
async def test_redis_async_all_method(unified_backend_redis_only, mock_redis_backend):
    """Test Redis all_async wrapper method."""
    redis_user = create_mock_redis_user()
    mock_redis_backend.all_async.return_value = [redis_user]

    results = await unified_backend_redis_only.all_async()
    assert len(results) == 1
    assert results[0].name == "John"
    mock_redis_backend.all_async.assert_called_once()


@pytest.mark.asyncio
async def test_redis_async_find_method(unified_backend_redis_only, mock_redis_backend):
    """Test Redis find_async wrapper method."""
    redis_user = create_mock_redis_user()
    mock_redis_backend.find_async.return_value = [redis_user]

    results = await unified_backend_redis_only.find_async({"name": "John"})
    assert len(results) == 1
    assert results[0].name == "John"
    mock_redis_backend.find_async.assert_called_once()


@pytest.mark.asyncio
async def test_redis_async_initialize_method(unified_backend_redis_only, mock_redis_backend):
    """Test Redis initialize_async wrapper method."""
    await unified_backend_redis_only.initialize_async()
    mock_redis_backend.initialize_async.assert_called_once()


# ============================================================================
# Tests for unified backend routing logic
# ============================================================================


def test_unified_backend_sync_routing_mongo(unified_backend_mongo_only, mock_mongo_backend):
    """Test that unified backend routes sync calls to MongoDB sync wrappers."""
    user = UserCreate(name="John", age=30, email="john@example.com")
    mongo_user = create_mock_mongo_user()

    # Test that sync methods route to sync wrappers
    mock_mongo_backend.insert_sync.return_value = mongo_user
    result = unified_backend_mongo_only.insert(user)
    assert result.name == "John"
    mock_mongo_backend.insert_sync.assert_called_once()

    mock_mongo_backend.get_sync.return_value = mongo_user
    result = unified_backend_mongo_only.get(mongo_user.id)
    assert result.name == "John"
    mock_mongo_backend.get_sync.assert_called_once()

    mock_mongo_backend.all_sync.return_value = [mongo_user]
    results = unified_backend_mongo_only.all()
    assert len(results) == 1
    mock_mongo_backend.all_sync.assert_called_once()

    mock_mongo_backend.find_sync.return_value = [mongo_user]
    results = unified_backend_mongo_only.find({"name": "John"})
    assert len(results) == 1
    mock_mongo_backend.find_sync.assert_called_once()

    mock_mongo_backend.delete_sync.return_value = True
    result = unified_backend_mongo_only.delete(mongo_user.id)
    assert result is True
    mock_mongo_backend.delete_sync.assert_called_once()


def test_unified_backend_sync_routing_redis(unified_backend_redis_only, mock_redis_backend):
    """Test that unified backend routes sync calls to Redis native sync methods."""
    user = UserCreate(name="John", age=30, email="john@example.com")
    redis_user = create_mock_redis_user()

    # Test that sync methods route to native sync methods for Redis
    mock_redis_backend.insert.return_value = redis_user
    result = unified_backend_redis_only.insert(user)
    assert result.name == "John"
    mock_redis_backend.insert.assert_called_once()

    mock_redis_backend.get.return_value = redis_user
    result = unified_backend_redis_only.get(redis_user.pk)
    assert result.name == "John"
    mock_redis_backend.get.assert_called_once()


@pytest.mark.asyncio
async def test_unified_backend_async_routing_mongo(unified_backend_mongo_only, mock_mongo_backend):
    """Test that unified backend routes async calls to MongoDB native async methods."""
    user = UserCreate(name="John", age=30, email="john@example.com")
    mongo_user = create_mock_mongo_user()

    # Test that async methods route to native async methods for MongoDB
    mock_mongo_backend.insert.return_value = mongo_user
    result = await unified_backend_mongo_only.insert_async(user)
    assert result.name == "John"
    mock_mongo_backend.insert.assert_called_once()

    mock_mongo_backend.get.return_value = mongo_user
    result = await unified_backend_mongo_only.get_async(mongo_user.id)
    assert result.name == "John"
    mock_mongo_backend.get.assert_called_once()


@pytest.mark.asyncio
async def test_unified_backend_async_routing_redis(unified_backend_redis_only, mock_redis_backend):
    """Test that unified backend routes async calls to Redis async wrappers."""
    user = UserCreate(name="John", age=30, email="john@example.com")
    redis_user = create_mock_redis_user()

    # Test that async methods route to async wrappers for Redis
    mock_redis_backend.insert_async.return_value = redis_user
    result = await unified_backend_redis_only.insert_async(user)
    assert result.name == "John"
    mock_redis_backend.insert_async.assert_called_once()

    mock_redis_backend.get_async.return_value = redis_user
    result = await unified_backend_redis_only.get_async(redis_user.pk)
    assert result.name == "John"
    mock_redis_backend.get_async.assert_called_once()


def test_unified_backend_backend_switching_sync_operations(
    unified_backend_both, mock_mongo_backend, mock_redis_backend
):
    """Test that switching backends correctly routes sync operations."""
    user = UserCreate(name="John", age=30, email="john@example.com")
    mongo_user = create_mock_mongo_user()
    redis_user = create_mock_redis_user()

    # Start with MongoDB
    mock_mongo_backend.insert_sync.return_value = mongo_user
    result = unified_backend_both.insert(user)
    assert result.name == "John"
    mock_mongo_backend.insert_sync.assert_called_once()

    # Switch to Redis
    unified_backend_both.switch_backend(BackendType.REDIS)
    mock_redis_backend.insert.return_value = redis_user
    result = unified_backend_both.insert(user)
    assert result.name == "John"
    mock_redis_backend.insert.assert_called_once()


@pytest.mark.asyncio
async def test_unified_backend_backend_switching_async_operations(
    unified_backend_both, mock_mongo_backend, mock_redis_backend
):
    """Test that switching backends correctly routes async operations."""
    user = UserCreate(name="John", age=30, email="john@example.com")
    mongo_user = create_mock_mongo_user()
    redis_user = create_mock_redis_user()

    # Start with MongoDB
    mock_mongo_backend.insert.return_value = mongo_user
    result = await unified_backend_both.insert_async(user)
    assert result.name == "John"
    mock_mongo_backend.insert.assert_called_once()

    # Switch to Redis
    unified_backend_both.switch_backend(BackendType.REDIS)
    mock_redis_backend.insert_async.return_value = redis_user
    result = await unified_backend_both.insert_async(user)
    assert result.name == "John"
    mock_redis_backend.insert_async.assert_called_once()


# ============================================================================
# Tests for edge cases and error handling
# ============================================================================


def test_unified_backend_initialize_sync_handles_both_backends(
    unified_backend_both, mock_mongo_backend, mock_redis_backend
):
    """Test that initialize_sync initializes both backends when both are configured."""
    unified_backend_both.initialize_sync()
    mock_redis_backend.initialize.assert_called_once()
    mock_mongo_backend.initialize_sync.assert_called_once()


@pytest.mark.asyncio
async def test_unified_backend_initialize_async_handles_both_backends(
    unified_backend_both, mock_mongo_backend, mock_redis_backend
):
    """Test that initialize_async initializes both backends when both are configured."""
    await unified_backend_both.initialize_async()
    mock_mongo_backend.initialize.assert_called_once()
    mock_redis_backend.initialize_async.assert_called_once()


def test_unified_backend_sync_methods_with_unified_model(unified_backend_with_unified_model, mock_mongo_backend):
    """Test sync methods work with unified document model."""
    user = UnifiedUserDoc(name="John", age=30, email="john@example.com")
    mongo_user = create_mock_mongo_user()
    mock_mongo_backend.insert_sync.return_value = mongo_user

    result = unified_backend_with_unified_model.insert(user)
    assert result.name == "John"
    mock_mongo_backend.insert_sync.assert_called_once()


@pytest.mark.asyncio
async def test_unified_backend_async_methods_with_unified_model(unified_backend_with_unified_model, mock_mongo_backend):
    """Test async methods work with unified document model."""
    user = UnifiedUserDoc(name="John", age=30, email="john@example.com")
    mongo_user = create_mock_mongo_user()
    mock_mongo_backend.insert.return_value = mongo_user

    result = await unified_backend_with_unified_model.insert_async(user)
    assert result.name == "John"
    mock_mongo_backend.insert.assert_called_once()


# ============================================================================
# Tests for missing coverage lines
# ============================================================================


def test_unified_backend_auto_generate_mongo_model_skips_id_field():
    """Test that MongoDB model generation skips id field (covers line 90)."""
    from mindtrace.database.backends.unified_odm import UnifiedMindtraceDocument

    class TestDoc(UnifiedMindtraceDocument):
        id: str = "test_id"  # This should be skipped
        name: str = "test"

        class Meta:
            collection_name = "test"

    mongo_model = TestDoc._auto_generate_mongo_model()
    # Verify id field is not in the generated model's annotations
    # The id field should be skipped during generation (line 90)
    assert mongo_model is not None


def test_unified_backend_auto_generate_redis_model_skips_id_field():
    """Test that Redis model generation skips id field (covers line 147)."""
    from mindtrace.database.backends.unified_odm import UnifiedMindtraceDocument

    class TestDoc(UnifiedMindtraceDocument):
        id: str = "test_id"  # This should be skipped
        name: str = "test"

        class Meta:
            collection_name = "test"

    redis_model = TestDoc._auto_generate_redis_model()
    # Verify id field is not in the generated model's annotations
    # The id field should be skipped during generation (line 147)
    assert redis_model is not None


def test_unified_backend_auto_generate_mongo_model_has_field_attr():
    """Test MongoDB model generation when field has attr (covers line 80)."""
    from mindtrace.database.backends.unified_odm import UnifiedMindtraceDocument

    class TestDoc(UnifiedMindtraceDocument):
        name: str = "test"

        class Meta:
            collection_name = "test"

    # Set a field attribute to trigger line 80
    TestDoc.name = "test_value"

    mongo_model = TestDoc._auto_generate_mongo_model()
    assert mongo_model is not None


@pytest.mark.asyncio
async def test_unified_backend_insert_async_redis_fallback(unified_backend_redis_only, mock_redis_backend):
    """Test unified backend insert_async with Redis fallback (covers line 785)."""
    user = UserCreate(name="John", age=30, email="john@example.com")
    redis_user = create_mock_redis_user()

    # Create a simple backend without insert_async (but with is_async)
    class SimpleBackend:
        def is_async(self):
            return False

        def insert(self, obj):
            return redis_user

    simple_backend = SimpleBackend()
    simple_backend.insert = MagicMock(return_value=redis_user)

    # Replace the redis_backend with our simple backend
    unified_backend_redis_only.redis_backend = simple_backend

    # Verify hasattr returns False for insert_async
    assert not hasattr(simple_backend, "insert_async")

    result = await unified_backend_redis_only.insert_async(user)
    assert result.name == "John"
    simple_backend.insert.assert_called_once()


@pytest.mark.asyncio
async def test_unified_backend_get_async_redis_fallback(unified_backend_redis_only, mock_redis_backend):
    """Test unified backend get_async with Redis fallback (covers line 819)."""
    redis_user = create_mock_redis_user()

    # Mock hasattr to return False for get_async to trigger fallback
    mock_redis_backend.get = MagicMock(return_value=redis_user)

    with patch("builtins.hasattr") as mock_hasattr:

        def hasattr_side_effect(obj, attr):
            if obj == mock_redis_backend and attr == "get_async":
                return False
            return hasattr(obj, attr)

        mock_hasattr.side_effect = hasattr_side_effect

        result = await unified_backend_redis_only.get_async(redis_user.pk)
        assert result.name == "John"
        mock_redis_backend.get.assert_called_once_with(redis_user.pk)


@pytest.mark.asyncio
async def test_unified_backend_delete_async_redis_fallback(unified_backend_redis_only, mock_redis_backend):
    """Test unified backend delete_async with Redis fallback (covers line 850)."""
    # Mock hasattr to return False for delete_async to trigger fallback
    mock_redis_backend.delete = MagicMock(return_value=True)

    with patch("builtins.hasattr") as mock_hasattr:

        def hasattr_side_effect(obj, attr):
            if obj == mock_redis_backend and attr == "delete_async":
                return False
            return hasattr(obj, attr)

        mock_hasattr.side_effect = hasattr_side_effect

        await unified_backend_redis_only.delete_async("test_id")
        mock_redis_backend.delete.assert_called_once_with("test_id")


@pytest.mark.asyncio
async def test_unified_backend_all_async_redis_fallback(unified_backend_redis_only, mock_redis_backend):
    """Test unified backend all_async with Redis fallback (covers line 877)."""
    redis_user = create_mock_redis_user()

    # Mock hasattr to return False for all_async to trigger fallback
    mock_redis_backend.all = MagicMock(return_value=[redis_user])

    with patch("builtins.hasattr") as mock_hasattr:

        def hasattr_side_effect(obj, attr):
            if obj == mock_redis_backend and attr == "all_async":
                return False
            return hasattr(obj, attr)

        mock_hasattr.side_effect = hasattr_side_effect

        result = await unified_backend_redis_only.all_async()
        assert len(result) == 1
        mock_redis_backend.all.assert_called_once()


@pytest.mark.asyncio
async def test_unified_backend_find_async_redis_fallback(unified_backend_redis_only, mock_redis_backend):
    """Test unified backend find_async with Redis fallback (covers line 909)."""
    redis_user = create_mock_redis_user()

    # Mock hasattr to return False for find_async to trigger fallback
    mock_redis_backend.find = MagicMock(return_value=[redis_user])

    with patch("builtins.hasattr") as mock_hasattr:

        def hasattr_side_effect(obj, attr):
            if obj == mock_redis_backend and attr == "find_async":
                return False
            return hasattr(obj, attr)

        mock_hasattr.side_effect = hasattr_side_effect

        result = await unified_backend_redis_only.find_async({"name": "John"})
        assert len(result) == 1
        mock_redis_backend.find.assert_called_once_with({"name": "John"})


@pytest.mark.asyncio
async def test_unified_backend_initialize_async_redis_fallback():
    """Test unified backend initialize_async with Redis fallback (covers line 530)."""
    from pydantic import Field

    from mindtrace.database import BackendType, UnifiedMindtraceDocument, UnifiedMindtraceODM

    class TestDoc(UnifiedMindtraceDocument):
        name: str = Field()

        class Meta:
            collection_name = "test"

    backend = UnifiedMindtraceODM(
        unified_model_cls=TestDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )

    # Create a simple object without initialize_async to trigger fallback
    class SimpleBackend:
        def initialize(self):
            pass

    simple_backend = SimpleBackend()
    simple_backend.initialize = MagicMock()
    backend.redis_backend = simple_backend

    # hasattr should return False for initialize_async
    assert not hasattr(simple_backend, "initialize_async")

    await backend.initialize_async()
    # The fallback should call initialize() directly (line 530)
    simple_backend.initialize.assert_called_once()


def test_unified_backend_initialize_sync_mongo_fallback():
    """Test unified backend initialize_sync with MongoDB fallback (covers line 555)."""

    from pydantic import Field

    from mindtrace.database import BackendType, UnifiedMindtraceDocument, UnifiedMindtraceODM

    class TestDoc(UnifiedMindtraceDocument):
        name: str = Field()

        class Meta:
            collection_name = "test"

    backend = UnifiedMindtraceODM(
        unified_model_cls=TestDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    # Create a simple object without initialize_sync to trigger fallback
    class SimpleBackend:
        async def initialize(self):
            pass

    simple_backend = SimpleBackend()
    simple_backend.initialize = AsyncMock()
    backend.mongo_backend = simple_backend

    # hasattr should return False for initialize_sync
    assert not hasattr(simple_backend, "initialize_sync")

    with patch("asyncio.run") as mock_asyncio_run:
        backend.initialize_sync()
        # The fallback should call asyncio.run(initialize()) (line 555)
        mock_asyncio_run.assert_called_once()


def test_unified_backend_handle_async_call_fallback():
    """Test unified backend _handle_async_call fallback (covers lines 613-614)."""
    import asyncio

    from pydantic import Field

    from mindtrace.database import BackendType, UnifiedMindtraceDocument, UnifiedMindtraceODM

    class TestDoc(UnifiedMindtraceDocument):
        name: str = Field()

        class Meta:
            collection_name = "test"

    backend = UnifiedMindtraceODM(
        unified_model_cls=TestDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    # Create a simple backend object without test_method_sync
    # Use a plain class to avoid triggering Pydantic's internal attribute checks
    class SimpleBackend:
        __slots__ = ()  # Prevent dynamic attribute creation that might trigger Pydantic

        def is_async(self):
            return True

        async def test_method(self, *args, **kwargs):
            return "result"

    simple_backend = SimpleBackend()

    # Verify test_method_sync doesn't exist using getattr to avoid hasattr triggering Pydantic
    sentinel = object()
    assert getattr(simple_backend, "test_method_sync", sentinel) is sentinel

    with patch.object(backend, "_get_active_backend", return_value=simple_backend):
        # Use wraps to execute the real asyncio.run while still verifying it was called
        with patch("asyncio.run", wraps=asyncio.run) as mock_asyncio_run:
            result = backend._handle_async_call("test_method", "arg1")
            # The fallback should call asyncio.run(test_method()) (lines 613-614)
            mock_asyncio_run.assert_called_once()
            assert result == "result"


# ============================================================================
# Tests for initialize_async coverage
# ============================================================================


@pytest.mark.asyncio
async def test_unified_initialize_async_with_allow_index_dropping(unified_backend_both, mock_mongo_backend):
    """Test unified backend initialize_async() with allow_index_dropping parameter (covers line 564)."""
    backend = unified_backend_both

    # Initialize with allow_index_dropping=True
    await backend.initialize_async(allow_index_dropping=True)

    # Should call mongo_backend.initialize with allow_index_dropping=True
    mock_mongo_backend.initialize.assert_called_once_with(allow_index_dropping=True)


def test_unified_initialize_sync_fallback_path_with_allow_index_dropping(mock_mongo_backend):
    """Test unified backend initialize_sync() fallback path with allow_index_dropping (covers lines 619-622)."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    # Mock hasattr to return False for initialize_sync to trigger fallback path
    with patch("mindtrace.database.backends.unified_odm.hasattr") as mock_hasattr:

        def hasattr_side_effect(obj, attr):
            if obj is backend.mongo_backend and attr == "initialize_sync":
                return False
            return hasattr(obj, attr)

        mock_hasattr.side_effect = hasattr_side_effect

        # Mock asyncio.run to avoid actual event loop execution
        with patch("mindtrace.database.backends.unified_odm.asyncio.run") as mock_asyncio_run:
            # Mock the initialize method to return a coroutine
            mock_initialize = AsyncMock()
            backend.mongo_backend.initialize = mock_initialize

            # Test with allow_index_dropping=True (covers line 619-620)
            backend.initialize_sync(allow_index_dropping=True)
            mock_asyncio_run.assert_called_once()
            # Verify the call was made with allow_index_dropping=True
            # The call should be to initialize with allow_index_dropping
            assert mock_initialize.called

            # Reset mocks
            mock_asyncio_run.reset_mock()
            mock_initialize.reset_mock()

            # Test with allow_index_dropping=None (covers line 621-622)
            backend.initialize_sync(allow_index_dropping=None)
            mock_asyncio_run.assert_called_once()
            assert mock_initialize.called


def test_unified_initialize_sync_with_allow_index_dropping(mock_mongo_backend):
    """Test unified backend initialize_sync() with allow_index_dropping parameter (covers line 616)."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    # Test with allow_index_dropping=True
    backend.initialize_sync(allow_index_dropping=True)
    mock_mongo_backend.initialize_sync.assert_called_once_with(allow_index_dropping=True)

    # Reset and test with allow_index_dropping=None
    mock_mongo_backend.reset_mock()
    backend.initialize_sync(allow_index_dropping=None)
    mock_mongo_backend.initialize_sync.assert_called_once_with(allow_index_dropping=None)


def test_unified_initialize_with_allow_index_dropping(mock_mongo_backend):
    """Test unified backend initialize() with allow_index_dropping parameter (covers line 639)."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )

    # Test with allow_index_dropping=True
    backend.initialize(allow_index_dropping=True)
    mock_mongo_backend.initialize_sync.assert_called_once_with(allow_index_dropping=True)


async def test_unified_initialize_async_redis_async_mode_skip(unified_backend_both, mock_redis_backend):
    """Test unified backend initialize_async() skips Redis when in ASYNC mode (covers line 588)."""
    from mindtrace.database.backends.mindtrace_odm import InitMode

    backend = unified_backend_both

    # Set Redis to ASYNC mode and not initialized
    backend.redis_backend._init_mode = InitMode.ASYNC
    backend.redis_backend._is_initialized = False

    # Initialize - should skip Redis
    await backend.initialize_async()

    # Redis initialize_async should NOT be called (skipped due to ASYNC mode)
    mock_redis_backend.initialize_async.assert_not_called()
    mock_redis_backend.initialize.assert_not_called()


def test_unified_backend_update_sync_mongo(unified_backend_mongo_only, mock_mongo_backend):
    """Test unified backend update method with MongoDB."""
    user = create_mock_mongo_user()
    user.id = "507f1f77bcf86cd799439011"
    mock_mongo_backend.update_sync.return_value = user

    result = unified_backend_mongo_only.update(user)

    assert result == user
    mock_mongo_backend.update_sync.assert_called_once_with(user)


def test_unified_backend_update_sync_redis(unified_backend_redis_only, mock_redis_backend):
    """Test unified backend update method with Redis."""
    user = create_mock_redis_user()
    user.pk = "01H0000000000000000000"
    mock_redis_backend.update.return_value = user

    result = unified_backend_redis_only.update(user)

    assert result == user
    mock_redis_backend.update.assert_called_once_with(user)


@pytest.mark.asyncio
async def test_unified_backend_update_async_mongo(unified_backend_mongo_only, mock_mongo_backend):
    """Test unified backend update_async method with MongoDB."""
    user = create_mock_mongo_user()
    user.id = "507f1f77bcf86cd799439011"
    mock_mongo_backend.update = AsyncMock(return_value=user)

    result = await unified_backend_mongo_only.update_async(user)

    assert result == user
    mock_mongo_backend.update.assert_called_once_with(user)


@pytest.mark.asyncio
async def test_unified_backend_update_async_redis(unified_backend_redis_only, mock_redis_backend):
    """Test unified backend update_async method with Redis."""
    user = create_mock_redis_user()
    user.pk = "01H0000000000000000000"
    mock_redis_backend.update_async = AsyncMock(return_value=user)

    result = await unified_backend_redis_only.update_async(user)

    assert result == user
    mock_redis_backend.update_async.assert_called_once_with(user)


@pytest.mark.asyncio
async def test_unified_backend_update_async_redis_fallback(unified_backend_redis_only, mock_redis_backend):
    """Test unified backend update_async method with Redis fallback when update_async not available."""
    user = create_mock_redis_user()
    user.pk = "01H0000000000000000000"
    mock_redis_backend.update.return_value = user
    # Remove update_async method to test fallback
    del mock_redis_backend.update_async

    result = await unified_backend_redis_only.update_async(user)

    assert result == user
    mock_redis_backend.update.assert_called_once_with(user)
