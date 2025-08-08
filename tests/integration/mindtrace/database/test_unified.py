from typing import Annotated

import pytest
from beanie import Indexed
from pydantic import BaseModel, Field
from redis_om import Field as RedisField

from mindtrace.database import (
    BackendType,
    DocumentNotFoundError,
    DuplicateInsertError,
    MindtraceDocument,
    MindtraceRedisDocument,
    UnifiedMindtraceDocument,
    UnifiedMindtraceODMBackend,
)

# Configuration
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB_NAME = "test_unified_db"
REDIS_URL = "redis://localhost:6379"


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
        name = "unified_users"
        use_cache = False


class RedisUserDoc(MindtraceRedisDocument):
    name: str = RedisField(index=True)
    age: int = RedisField(index=True)
    email: str = RedisField(index=True)

    class Meta:
        global_key_prefix = "unified_test"


# Unified document model for integration testing - Simple!
class IntegrationUnifiedUserDoc(UnifiedMindtraceDocument):
    name: str = Field(description="User's full name")
    age: int = Field(ge=0, le=150, description="User's age")
    email: str = Field(description="User's email address")

    class Meta:
        collection_name = "integration_users"
        global_key_prefix = "integration_test"
        use_cache = False
        indexed_fields = ["name", "age", "email"]
        unique_fields = ["email"]


@pytest.fixture(scope="function")
async def mongo_unified_backend():
    """Create a unified backend with only MongoDB configured."""
    backend = UnifiedMindtraceODMBackend(
        mongo_model_cls=MongoUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        preferred_backend=BackendType.MONGO,
    )

    # Initialize and clean up existing data
    await backend.initialize_async()
    mongo_backend = backend.get_mongo_backend()
    await mongo_backend.model_cls.delete_all()

    yield backend

    # Cleanup after test
    try:
        await mongo_backend.model_cls.delete_all()
    except Exception:
        pass


@pytest.fixture(scope="function")
def redis_unified_backend():
    """Create a unified backend with only Redis configured."""
    backend = UnifiedMindtraceODMBackend(
        redis_model_cls=RedisUserDoc, redis_url=REDIS_URL, preferred_backend=BackendType.REDIS
    )

    # Initialize and clean up
    backend.initialize_sync()
    redis_backend = backend.get_redis_backend()

    # Clean up any existing data before test
    redis = redis_backend.redis
    pattern = f"{RedisUserDoc.Meta.global_key_prefix}:*"
    keys = redis.keys(pattern)
    if keys:
        redis.delete(*keys)

    yield backend

    # Clean up after test
    keys = redis.keys(pattern)
    if keys:
        redis.delete(*keys)


@pytest.fixture(scope="function")
async def dual_unified_backend():
    """Create a unified backend with both MongoDB and Redis configured."""
    backend = UnifiedMindtraceODMBackend(
        mongo_model_cls=MongoUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        redis_model_cls=RedisUserDoc,
        redis_url=REDIS_URL,
        preferred_backend=BackendType.MONGO,
    )

    # Initialize both backends
    backend.initialize_sync()
    await backend.initialize_async()

    # Clean up existing data
    mongo_backend = backend.get_mongo_backend()
    await mongo_backend.model_cls.delete_all()

    redis_backend = backend.get_redis_backend()
    redis = redis_backend.redis
    pattern = f"{RedisUserDoc.Meta.global_key_prefix}:*"
    keys = redis.keys(pattern)
    if keys:
        redis.delete(*keys)

    yield backend

    # Cleanup after test
    try:
        await mongo_backend.model_cls.delete_all()
    except Exception:
        pass

    # Clean up Redis
    keys = redis.keys(pattern)
    if keys:
        redis.delete(*keys)


@pytest.fixture(scope="function")
async def unified_model_backend():
    """Create a unified backend with unified document model."""
    backend = UnifiedMindtraceODMBackend(
        unified_model_cls=IntegrationUnifiedUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        redis_url=REDIS_URL,
        preferred_backend=BackendType.MONGO,
    )

    # Initialize both backends
    backend.initialize_sync()
    await backend.initialize_async()

    # Clean up existing data
    if backend.has_mongo_backend():
        mongo_backend = backend.get_mongo_backend()
        await mongo_backend.model_cls.delete_all()

    if backend.has_redis_backend():
        redis_backend = backend.get_redis_backend()
        pattern = f"{IntegrationUnifiedUserDoc.get_meta().global_key_prefix}:*"
        keys = redis_backend.redis.keys(pattern)
        if keys:
            redis_backend.redis.delete(*keys)

    yield backend

    # Cleanup after test
    try:
        if backend.has_mongo_backend():
            mongo_backend = backend.get_mongo_backend()
            await mongo_backend.model_cls.delete_all()
    except Exception:
        pass

    # Clean up Redis
    if backend.has_redis_backend():
        redis_backend = backend.get_redis_backend()
        pattern = f"{IntegrationUnifiedUserDoc.get_meta().global_key_prefix}:*"
        keys = redis_backend.redis.keys(pattern)
        if keys:
            redis_backend.redis.delete(*keys)


@pytest.mark.asyncio
async def test_mongo_unified_backend_crud(mongo_unified_backend):
    """Test basic CRUD operations with MongoDB through unified backend."""
    user = UserCreate(name="Alice", age=30, email="alice@unified.com")

    # Test insert
    inserted = await mongo_unified_backend.insert_async(user)
    assert inserted.name == "Alice"
    assert inserted.age == 30
    assert inserted.email == "alice@unified.com"

    # Test get
    fetched = await mongo_unified_backend.get_async(str(inserted.id))
    assert fetched.name == "Alice"
    assert fetched.age == 30
    assert fetched.email == "alice@unified.com"

    # Test all
    all_users = await mongo_unified_backend.all_async()
    assert len(all_users) >= 1

    # Test delete
    await mongo_unified_backend.delete_async(str(inserted.id))

    with pytest.raises(DocumentNotFoundError):
        await mongo_unified_backend.get_async(str(inserted.id))


@pytest.mark.asyncio
async def test_mongo_unified_backend_find(mongo_unified_backend):
    """Test find operations with MongoDB through unified backend."""
    # Insert test data
    users = [
        UserCreate(name="Alice", age=30, email="alice@unified.com"),
        UserCreate(name="Bob", age=25, email="bob@unified.com"),
        UserCreate(name="Charlie", age=35, email="charlie@unified.com"),
    ]

    for user in users:
        await mongo_unified_backend.insert_async(user)

    # Test find with filter
    young_users = await mongo_unified_backend.find_async({"age": {"$lt": 30}})
    assert len(young_users) == 1
    assert young_users[0].name == "Bob"

    # Test find with multiple conditions
    adult_users = await mongo_unified_backend.find_async({"age": {"$gte": 30}})
    assert len(adult_users) == 2
    names = {user.name for user in adult_users}
    assert names == {"Alice", "Charlie"}


@pytest.mark.asyncio
async def test_mongo_unified_backend_duplicate_insert(mongo_unified_backend):
    """Test duplicate insert handling with MongoDB through unified backend."""
    # Insert first user
    user1 = UserCreate(name="Alice", age=30, email="alice@unified.com")
    await mongo_unified_backend.insert_async(user1)

    # Try to insert another user with the same email
    user2 = UserCreate(name="Alice2", age=31, email="alice@unified.com")
    with pytest.raises(DuplicateInsertError):
        await mongo_unified_backend.insert_async(user2)


def test_redis_unified_backend_crud(redis_unified_backend):
    """Test basic CRUD operations with Redis through unified backend."""
    user = UserCreate(name="Alice", age=30, email="alice@unified.com")

    # Test insert
    inserted = redis_unified_backend.insert(user)
    assert inserted.name == "Alice"
    assert inserted.age == 30
    assert inserted.email == "alice@unified.com"

    # Test get
    fetched = redis_unified_backend.get(inserted.pk)
    assert fetched.name == "Alice"
    assert fetched.age == 30
    assert fetched.email == "alice@unified.com"

    # Test all
    all_users = redis_unified_backend.all()
    assert len(all_users) >= 1

    # Test delete
    redis_unified_backend.delete(inserted.pk)

    with pytest.raises(DocumentNotFoundError):
        redis_unified_backend.get(inserted.pk)


def test_redis_unified_backend_find(redis_unified_backend):
    """Test find operations with Redis through unified backend."""
    # Insert test data
    users = [
        UserCreate(name="Charlie", age=35, email="charlie@unified.com"),
        UserCreate(name="David", age=35, email="david@unified.com"),
        UserCreate(name="Eve", age=40, email="eve@unified.com"),
    ]

    for user in users:
        redis_unified_backend.insert(user)

    # Test find by age
    age_35_users = redis_unified_backend.find(RedisUserDoc.age == 35)
    assert len(age_35_users) == 2

    # Test find by name
    charlie_users = redis_unified_backend.find(RedisUserDoc.name == "Charlie")
    assert len(charlie_users) == 1
    assert charlie_users[0].email == "charlie@unified.com"


def test_redis_unified_backend_duplicate_insert(redis_unified_backend):
    """Test duplicate insert handling with Redis through unified backend."""
    user = UserCreate(name="Bob", age=25, email="bob@unified.com")
    redis_unified_backend.insert(user)

    # Try to insert another user with same email
    with pytest.raises(DuplicateInsertError):
        redis_unified_backend.insert(user)


@pytest.mark.asyncio
async def test_redis_unified_backend_async_operations(redis_unified_backend):
    """Test async operations with Redis through unified backend."""
    user = UserCreate(name="Alice", age=30, email="alice@unified.com")

    # Test async insert (should work transparently)
    inserted = await redis_unified_backend.insert_async(user)
    assert inserted.name == "Alice"

    # Test async get
    fetched = await redis_unified_backend.get_async(inserted.pk)
    assert fetched.name == "Alice"

    # Test async all
    all_users = await redis_unified_backend.all_async()
    assert len(all_users) >= 1

    # Test async find
    found_users = await redis_unified_backend.find_async(RedisUserDoc.name == "Alice")
    assert len(found_users) == 1

    # Test async delete
    await redis_unified_backend.delete_async(inserted.pk)


@pytest.mark.asyncio
async def test_dual_backend_switching(dual_unified_backend):
    """Test switching between backends in a dual configuration."""
    user = UserCreate(name="Switch", age=30, email="switch@unified.com")

    # Start with MongoDB (preferred)
    assert dual_unified_backend.get_current_backend_type() == BackendType.MONGO

    # Insert with MongoDB
    mongo_inserted = await dual_unified_backend.insert_async(user)
    assert mongo_inserted.name == "Switch"

    # Switch to Redis
    dual_unified_backend.switch_backend(BackendType.REDIS)
    assert dual_unified_backend.get_current_backend_type() == BackendType.REDIS

    # Insert with Redis (different user to avoid duplicate)
    user2 = UserCreate(name="Switch2", age=31, email="switch2@unified.com")
    redis_inserted = await dual_unified_backend.insert_async(user2)
    assert redis_inserted.name == "Switch2"

    # Switch back to MongoDB
    dual_unified_backend.switch_backend(BackendType.MONGO)
    assert dual_unified_backend.get_current_backend_type() == BackendType.MONGO

    # Verify MongoDB data is still there
    mongo_fetched = await dual_unified_backend.get_async(str(mongo_inserted.id))
    assert mongo_fetched.name == "Switch"


def test_dual_backend_configuration(dual_unified_backend):
    """Test dual backend configuration features."""
    # Check that both backends are configured
    assert dual_unified_backend.has_mongo_backend()
    assert dual_unified_backend.has_redis_backend()

    # Check that backend instances can be retrieved
    mongo_backend = dual_unified_backend.get_mongo_backend()
    redis_backend = dual_unified_backend.get_redis_backend()

    assert mongo_backend is not None
    assert redis_backend is not None

    # Check that raw models are correct
    dual_unified_backend.switch_backend(BackendType.MONGO)
    assert dual_unified_backend.get_raw_model() == MongoUserDoc

    dual_unified_backend.switch_backend(BackendType.REDIS)
    assert dual_unified_backend.get_raw_model() == RedisUserDoc


def test_unified_backend_is_async_property(dual_unified_backend):
    """Test is_async property changes with backend switching."""
    # MongoDB is async
    dual_unified_backend.switch_backend(BackendType.MONGO)
    assert dual_unified_backend.is_async() is True

    # Redis is sync
    dual_unified_backend.switch_backend(BackendType.REDIS)
    assert dual_unified_backend.is_async() is False


@pytest.mark.asyncio
async def test_unified_backend_initialization(dual_unified_backend):
    """Test unified backend initialization."""
    # Test async initialization
    await dual_unified_backend.initialize_async()

    # Test sync initialization
    dual_unified_backend.initialize_sync()

    # Test general initialization
    dual_unified_backend.initialize()


def test_unified_backend_error_handling(mongo_unified_backend):
    """Test error handling in unified backend."""
    # Test error when trying to get unconfigured backend
    with pytest.raises(ValueError, match="Redis backend is not configured"):
        mongo_unified_backend.get_redis_backend()

    # Test error when trying to switch to unconfigured backend
    with pytest.raises(ValueError, match="Redis backend is not configured"):
        mongo_unified_backend.switch_backend(BackendType.REDIS)


@pytest.mark.asyncio
async def test_unified_backend_document_not_found(mongo_unified_backend):
    """Test handling of non-existent document retrieval."""
    with pytest.raises(DocumentNotFoundError):
        await mongo_unified_backend.get_async("507f1f77bcf86cd799439011")  # Random ObjectId


@pytest.mark.asyncio
async def test_unified_backend_find_no_results(mongo_unified_backend):
    """Test find operation with no matching results."""
    # Insert test data
    user = UserCreate(name="Alice", age=30, email="alice@unified.com")
    await mongo_unified_backend.insert_async(user)

    # Test with non-existent field (should return empty list)
    result = await mongo_unified_backend.find_async({"non_existent_field": "value"})
    assert len(result) == 0

    # Test with non-matching condition
    result = await mongo_unified_backend.find_async({"age": 999})
    assert len(result) == 0


def test_unified_backend_redis_find_no_results(redis_unified_backend):
    """Test Redis find operation with no matching results."""
    # Insert test data
    user = UserCreate(name="Test", age=25, email="test@unified.com")
    redis_unified_backend.insert(user)

    # Search for non-existent age
    age_99_users = redis_unified_backend.find(RedisUserDoc.age == 99)
    assert len(age_99_users) == 0

    # Search for non-existent name
    name_users = redis_unified_backend.find(RedisUserDoc.name == "NonExistent")
    assert len(name_users) == 0


@pytest.mark.asyncio
async def test_unified_backend_cross_backend_data_isolation(dual_unified_backend):
    """Test that data is isolated between backends."""
    user1 = UserCreate(name="MongoUser", age=30, email="mongo@unified.com")
    user2 = UserCreate(name="RedisUser", age=31, email="redis@unified.com")

    # Insert into MongoDB
    dual_unified_backend.switch_backend(BackendType.MONGO)
    await dual_unified_backend.insert_async(user1)

    # Insert into Redis
    dual_unified_backend.switch_backend(BackendType.REDIS)
    await dual_unified_backend.insert_async(user2)

    # Check MongoDB data is not in Redis
    dual_unified_backend.switch_backend(BackendType.REDIS)
    redis_all = await dual_unified_backend.all_async()
    redis_names = [user.name for user in redis_all]
    assert "MongoUser" not in redis_names
    assert "RedisUser" in redis_names

    # Check Redis data is not in MongoDB
    dual_unified_backend.switch_backend(BackendType.MONGO)
    mongo_all = await dual_unified_backend.all_async()
    mongo_names = [user.name for user in mongo_all]
    assert "RedisUser" not in mongo_names
    assert "MongoUser" in mongo_names


# Integration tests for Unified Document Model
@pytest.mark.asyncio
async def test_unified_model_crud_mongodb(unified_model_backend):
    """Test basic backend selection and configuration with MongoDB."""
    # Ensure we're using MongoDB
    unified_model_backend.switch_backend(BackendType.MONGO)

    # Test that the backend is properly configured
    assert unified_model_backend.get_current_backend_type() == BackendType.MONGO
    assert unified_model_backend.is_async() is True

    # Test that we can get the raw model (it will be auto-generated from unified model)
    mongo_model = unified_model_backend.get_raw_model()
    assert issubclass(mongo_model, MindtraceDocument)

    # Test backend switching works
    if unified_model_backend.has_redis_backend():
        unified_model_backend.switch_backend(BackendType.REDIS)
        assert unified_model_backend.get_current_backend_type() == BackendType.REDIS
        assert unified_model_backend.is_async() is False

        # Switch back
        unified_model_backend.switch_backend(BackendType.MONGO)
        assert unified_model_backend.get_current_backend_type() == BackendType.MONGO


@pytest.mark.asyncio
async def test_unified_model_backend_switching(unified_model_backend):
    """Test backend switching functionality."""
    # Test initial state
    initial_backend = unified_model_backend.get_current_backend_type()
    assert initial_backend in [BackendType.MONGO, BackendType.REDIS]

    # Test switching to different backends
    if unified_model_backend.has_mongo_backend():
        unified_model_backend.switch_backend(BackendType.MONGO)
        assert unified_model_backend.get_current_backend_type() == BackendType.MONGO
        mongo_backend = unified_model_backend.get_mongo_backend()
        assert mongo_backend is not None

    if unified_model_backend.has_redis_backend():
        unified_model_backend.switch_backend(BackendType.REDIS)
        assert unified_model_backend.get_current_backend_type() == BackendType.REDIS
        redis_backend = unified_model_backend.get_redis_backend()
        assert redis_backend is not None

    # Test error handling for non-configured backend
    try:
        if not unified_model_backend.has_redis_backend():
            unified_model_backend.switch_backend(BackendType.REDIS)
            assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Redis backend is not configured" in str(e)


@pytest.mark.asyncio
async def test_unified_model_find_operations(unified_model_backend):
    """Test unified backend model access and configuration."""
    # Test unified model access
    unified_model = unified_model_backend.get_unified_model()
    assert unified_model == IntegrationUnifiedUserDoc

    # Test metadata access
    meta = unified_model.get_meta()
    assert hasattr(meta, "collection_name")
    assert hasattr(meta, "global_key_prefix")

    # Test model generation capabilities
    if unified_model_backend.has_mongo_backend():
        mongo_model = unified_model._auto_generate_mongo_model()
        assert issubclass(mongo_model, MindtraceDocument)

    if unified_model_backend.has_redis_backend():
        redis_model = unified_model._auto_generate_redis_model()
        assert issubclass(redis_model, MindtraceRedisDocument)

    # Test document conversion methods
    test_doc = unified_model(name="Test User", age=30, email="test@example.com")

    mongo_dict = test_doc.to_mongo_dict()
    assert "name" in mongo_dict
    assert "age" in mongo_dict
    assert "email" in mongo_dict

    redis_dict = test_doc.to_redis_dict()
    assert "name" in redis_dict
    assert "age" in redis_dict
    assert "email" in redis_dict


@pytest.mark.asyncio
async def test_unified_model_crud_redis(unified_model_backend):
    """Test basic backend selection and configuration with Redis."""
    # Switch to Redis backend
    unified_model_backend.switch_backend(BackendType.REDIS)

    # Test that the backend is properly configured
    assert unified_model_backend.get_current_backend_type() == BackendType.REDIS
    assert unified_model_backend.is_async() is False

    # Test that we can get the raw model (it will be auto-generated from unified model)
    redis_model = unified_model_backend.get_raw_model()
    assert issubclass(redis_model, MindtraceRedisDocument)

    # Test backend switching works
    if unified_model_backend.has_mongo_backend():
        unified_model_backend.switch_backend(BackendType.MONGO)
        assert unified_model_backend.get_current_backend_type() == BackendType.MONGO
        assert unified_model_backend.is_async() is True

        # Switch back
        unified_model_backend.switch_backend(BackendType.REDIS)
        assert unified_model_backend.get_current_backend_type() == BackendType.REDIS


def test_unified_model_backend_configuration(unified_model_backend):
    """Test unified model backend configuration."""
    # Verify the unified model is configured
    unified_model = unified_model_backend.get_unified_model()
    assert unified_model == IntegrationUnifiedUserDoc

    # Verify both backends are available
    assert unified_model_backend.has_mongo_backend()
    assert unified_model_backend.has_redis_backend()

    # Test initial configuration
    initial_backend = unified_model_backend.get_current_backend_type()
    assert initial_backend == BackendType.MONGO  # Should be the preferred backend

    # Test backend instances
    mongo_backend = unified_model_backend.get_mongo_backend()
    assert mongo_backend is not None

    redis_backend = unified_model_backend.get_redis_backend()
    assert redis_backend is not None


@pytest.mark.asyncio
async def test_unified_model_document_conversion(unified_model_backend):
    """Test document conversion between unified and backend formats."""
    user = IntegrationUnifiedUserDoc(id="test123", name="Convert User", age=35, email="convert@test.com")

    # Test MongoDB conversion
    mongo_dict = user.to_mongo_dict()
    assert "id" not in mongo_dict  # ID should be removed for MongoDB
    assert mongo_dict["name"] == "Convert User"
    assert mongo_dict["age"] == 35
    assert mongo_dict["email"] == "convert@test.com"

    # Test Redis conversion
    redis_dict = user.to_redis_dict()
    assert "id" not in redis_dict  # ID should be removed
    assert redis_dict["pk"] == "test123"  # Should have pk field
    assert redis_dict["name"] == "Convert User"
    assert redis_dict["age"] == 35
    assert redis_dict["email"] == "convert@test.com"
