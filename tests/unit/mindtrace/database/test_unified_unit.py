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
    UnifiedMindtraceODMBackend,
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


# Unified document model for testing - Simple!
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
    with patch("mindtrace.database.backends.unified_odm_backend.MongoMindtraceODMBackend") as mock_backend_cls:
        backend = MagicMock()
        backend.insert = AsyncMock()
        backend.get = AsyncMock()
        backend.all = AsyncMock()
        backend.delete = AsyncMock()
        backend.find = AsyncMock()
        backend.initialize = AsyncMock()
        backend.is_async = MagicMock(return_value=True)
        backend.get_raw_model = MagicMock(return_value=MongoUserDoc)
        mock_backend_cls.return_value = backend
        yield backend


@pytest.fixture
def mock_redis_backend():
    """Create a mocked Redis backend."""
    with patch("mindtrace.database.backends.unified_odm_backend.RedisMindtraceODMBackend") as mock_backend_cls:
        backend = MagicMock()
        backend.insert = MagicMock()
        backend.get = MagicMock()
        backend.all = MagicMock()
        backend.delete = MagicMock()
        backend.find = MagicMock()
        backend.initialize = MagicMock()
        backend.is_async = MagicMock(return_value=False)
        backend.get_raw_model = MagicMock(return_value=RedisUserDoc)
        mock_backend_cls.return_value = backend
        yield backend


@pytest.fixture
def unified_backend_mongo_only(mock_mongo_backend):
    """Create a unified backend with only MongoDB configured."""
    return UnifiedMindtraceODMBackend(
        mongo_model_cls=MongoUserDoc,
        mongo_db_uri="mongodb://localhost:27018",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )


@pytest.fixture
def unified_backend_redis_only(mock_redis_backend):
    """Create a unified backend with only Redis configured."""
    return UnifiedMindtraceODMBackend(
        redis_model_cls=RedisUserDoc, redis_url="redis://localhost:6380", preferred_backend=BackendType.REDIS
    )


@pytest.fixture
def unified_backend_both(mock_mongo_backend, mock_redis_backend):
    """Create a unified backend with both MongoDB and Redis configured."""
    return UnifiedMindtraceODMBackend(
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
    return UnifiedMindtraceODMBackend(
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
        UnifiedMindtraceODMBackend()


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
    mock_redis_backend.insert.return_value = redis_user
    result = await unified_backend_redis_only.insert_async(user)
    assert result.name == "John"

    # Test async get
    mock_redis_backend.get.return_value = redis_user
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
    mock_mongo_backend.insert.return_value = mongo_user

    # This should work by running the async method in an event loop
    result = unified_backend_mongo_only.insert(user)
    assert result.name == "John"


def test_backend_switching_with_operations(unified_backend_both, mock_mongo_backend, mock_redis_backend):
    """Test operations after switching backends."""
    user = UserCreate(name="John", age=30, email="john@example.com")

    # Start with MongoDB
    mongo_user = create_mock_mongo_user()
    mock_mongo_backend.insert.return_value = mongo_user

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
    mock_redis_backend.initialize.assert_called_once()


def test_async_initialization_calls(unified_backend_both, mock_mongo_backend, mock_redis_backend):
    """Test that async initialization is called on backends."""
    import asyncio

    # Run async initialization in a new event loop
    async def run_init():
        await unified_backend_both.initialize_async()

    asyncio.run(run_init())
    mock_mongo_backend.initialize.assert_called_once()


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
    mock_mongo_backend.insert.return_value = mongo_user

    result = unified_backend_with_unified_model.insert(user)
    assert result.name == "John"

    # Verify that the backend received the converted data
    mock_mongo_backend.insert.assert_called_once()


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
