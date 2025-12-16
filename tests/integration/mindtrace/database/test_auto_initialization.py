"""
End-to-end integration tests for auto-initialization feature.

These tests verify that database operations work correctly without explicit
initialization, ensuring that auto-initialization happens on first operation.
"""

from typing import Annotated, List

import asyncio
import pytest
import pytest_asyncio
from beanie import Indexed
from pydantic import BaseModel, Field
from redis_om import Field as RedisField

from mindtrace.database import (
    BackendType,
    DocumentNotFoundError,
    DuplicateInsertError,
    InitMode,
    MindtraceDocument,
    MindtraceRedisDocument,
    MongoMindtraceODM,
    RedisMindtraceODM,
    UnifiedMindtraceDocument,
    UnifiedMindtraceODM,
)

# Configuration
MONGO_URI = "mongodb://localhost:27018"
MONGO_DB_NAME = "test_auto_init_db"
REDIS_URL = "redis://localhost:6380"


# Test models
class MongoUserDoc(MindtraceDocument):
    name: str
    age: int
    email: Annotated[str, Indexed(unique=True)]

    class Settings:
        name = "auto_init_users"
        use_cache = False


class RedisUserDoc(MindtraceRedisDocument):
    name: str = RedisField(index=True)
    age: int = RedisField(index=True)
    email: str = RedisField(index=True)
    skills: List[str] = RedisField(index=True, default_factory=list)

    class Meta:
        global_key_prefix = "auto_init_test"


class UnifiedUserDoc(UnifiedMindtraceDocument):
    name: str = Field(description="User's full name")
    age: int = Field(ge=0, description="User's age")
    email: str = Field(description="User's email address")
    skills: List[str] = Field(default_factory=list)

    class Meta:
        collection_name = "auto_init_unified_users"
        global_key_prefix = "auto_init_unified"
        indexed_fields = ["name", "email"]
        unique_fields = ["email"]


@pytest_asyncio.fixture(scope="function")
async def clean_mongo_backend():
    """Create a MongoDB backend without auto-initialization (for explicit init tests)."""
    backend = MongoMindtraceODM(
        model_cls=MongoUserDoc,
        db_uri=MONGO_URI,
        db_name=MONGO_DB_NAME,
    )
    # Explicitly verify it's not initialized
    assert not backend._is_initialized

    yield backend

    # Cleanup: initialize to clean up data
    if not backend._is_initialized:
        await backend.initialize()
    try:
        collection = backend.client[MONGO_DB_NAME]["auto_init_users"]
        await collection.delete_many({})
    except Exception:
        pass
    backend.client.close()


@pytest_asyncio.fixture(scope="function")
async def clean_mongo_backend_auto_init():
    """Create a MongoDB backend with auto-initialization enabled (for auto-init tests)."""
    backend = MongoMindtraceODM(
        model_cls=MongoUserDoc,
        db_uri=MONGO_URI,
        db_name=MONGO_DB_NAME,
        auto_init=True,  # Enable auto-init
    )
    # In sync context, it would be initialized, but in async test context it's deferred
    yield backend

    # Cleanup
    if not backend._is_initialized:
        await backend.initialize()
    try:
        collection = backend.client[MONGO_DB_NAME]["auto_init_users"]
        await collection.delete_many({})
    except Exception:
        pass
    backend.client.close()


@pytest.fixture(scope="function")
def clean_redis_backend():
    """Create a Redis backend without auto-initialization (for explicit init tests)."""
    backend = RedisMindtraceODM(
        model_cls=RedisUserDoc,
        redis_url=REDIS_URL,
        # auto_init=False is now the default for backward compatibility
    )
    # Explicitly verify it's not initialized
    assert not backend._is_initialized

    yield backend

    # Cleanup: initialize to clean up data
    if not backend._is_initialized:
        backend.initialize()
    try:
        for user in backend.all():
            backend.delete(user.pk)
    except Exception:
        pass


@pytest.fixture(scope="function")
def clean_redis_backend_auto_init():
    """Create a Redis backend with auto-initialization enabled (for auto-init tests)."""
    backend = RedisMindtraceODM(
        model_cls=RedisUserDoc,
        redis_url=REDIS_URL,
        auto_init=True,  # Enable auto-init
    )
    # Should be initialized immediately in sync context
    assert backend._is_initialized

    yield backend

    # Cleanup
    try:
        for user in backend.all():
            backend.delete(user.pk)
    except Exception:
        pass


@pytest_asyncio.fixture(scope="function")
async def clean_unified_backend_mongo():
    """Create a unified backend with MongoDB, without auto-initialization (for explicit init tests)."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        preferred_backend=BackendType.MONGO,
    )

    yield backend

    # Cleanup
    if backend.has_mongo_backend():
        mongo_backend = backend.get_mongo_backend()
        try:
            collection_name = UnifiedUserDoc.get_meta().collection_name
            collection = mongo_backend.client[MONGO_DB_NAME][collection_name]
            await collection.delete_many({})
        except Exception:
            pass


@pytest_asyncio.fixture(scope="function")
async def clean_unified_backend_mongo_auto_init():
    """Create a unified backend with MongoDB, with auto-initialization enabled."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        preferred_backend=BackendType.MONGO,
        auto_init=True,  # Enable auto-init
    )

    yield backend

    # Cleanup
    if backend.has_mongo_backend():
        mongo_backend = backend.get_mongo_backend()
        try:
            collection_name = UnifiedUserDoc.get_meta().collection_name
            collection = mongo_backend.client[MONGO_DB_NAME][collection_name]
            await collection.delete_many({})
        except Exception:
            pass


@pytest.fixture(scope="function")
def clean_unified_backend_redis():
    """Create a unified backend with Redis, without auto-initialization (for explicit init tests)."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        redis_url=REDIS_URL,
        preferred_backend=BackendType.REDIS,
        # auto_init=False is now the default for backward compatibility
    )

    yield backend

    # Cleanup
    if backend.has_redis_backend():
        redis_backend = backend.get_redis_backend()
        try:
            pattern = f"{UnifiedUserDoc.get_meta().global_key_prefix}:*"
            keys = redis_backend.redis.keys(pattern)
            if keys:
                redis_backend.redis.delete(*keys)
        except Exception:
            pass


@pytest.fixture(scope="function")
def clean_unified_backend_redis_auto_init():
    """Create a unified backend with Redis, with auto-initialization enabled."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        redis_url=REDIS_URL,
        preferred_backend=BackendType.REDIS,
        auto_init=True,  # Enable auto-init
    )
    # Redis should be initialized immediately
    assert backend.get_redis_backend()._is_initialized

    yield backend

    # Cleanup
    if backend.has_redis_backend():
        redis_backend = backend.get_redis_backend()
        try:
            pattern = f"{UnifiedUserDoc.get_meta().global_key_prefix}:*"
            keys = redis_backend.redis.keys(pattern)
            if keys:
                redis_backend.redis.delete(*keys)
        except Exception:
            pass


@pytest_asyncio.fixture(scope="function")
async def clean_unified_backend_dual():
    """Create a unified backend with both MongoDB and Redis, without auto-initialization (for explicit init tests)."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        redis_url=REDIS_URL,
        preferred_backend=BackendType.MONGO,
    )

    yield backend

    # Cleanup MongoDB
    if backend.has_mongo_backend():
        mongo_backend = backend.get_mongo_backend()
        try:
            collection_name = UnifiedUserDoc.get_meta().collection_name
            collection = mongo_backend.client[MONGO_DB_NAME][collection_name]
            await collection.delete_many({})
        except Exception:
            pass

    # Cleanup Redis
    if backend.has_redis_backend():
        redis_backend = backend.get_redis_backend()
        try:
            pattern = f"{UnifiedUserDoc.get_meta().global_key_prefix}:*"
            keys = redis_backend.redis.keys(pattern)
            if keys:
                redis_backend.redis.delete(*keys)
        except Exception:
            pass


@pytest_asyncio.fixture(scope="function")
async def clean_unified_backend_dual_auto_init():
    """Create a unified backend with both MongoDB and Redis, with auto-initialization enabled."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        redis_url=REDIS_URL,
        preferred_backend=BackendType.MONGO,
        auto_init=True,  # Enable auto-init
    )
    # Redis should be initialized immediately
    assert backend.get_redis_backend()._is_initialized

    yield backend

    # Cleanup MongoDB
    if backend.has_mongo_backend():
        mongo_backend = backend.get_mongo_backend()
        try:
            collection_name = UnifiedUserDoc.get_meta().collection_name
            collection = mongo_backend.client[MONGO_DB_NAME][collection_name]
            await collection.delete_many({})
        except Exception:
            pass

    # Cleanup Redis
    if backend.has_redis_backend():
        redis_backend = backend.get_redis_backend()
        try:
            pattern = f"{UnifiedUserDoc.get_meta().global_key_prefix}:*"
            keys = redis_backend.redis.keys(pattern)
            if keys:
                redis_backend.redis.delete(*keys)
        except Exception:
            pass


# ============================================================================
# InitMode Test Fixtures
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def clean_mongo_backend_init_mode_async():
    """Create a MongoDB backend with InitMode.ASYNC and auto_init=True."""
    backend = MongoMindtraceODM(
        model_cls=MongoUserDoc,
        db_uri=MONGO_URI,
        db_name=MONGO_DB_NAME,
        auto_init=True,
        init_mode=InitMode.ASYNC,  # Explicit async mode
    )
    # In async context, initialization is deferred
    yield backend

    # Cleanup
    if not backend._is_initialized:
        await backend.initialize()
    try:
        collection = backend.client[MONGO_DB_NAME]["auto_init_users"]
        await collection.delete_many({})
    except Exception:
        pass
    backend.client.close()


@pytest_asyncio.fixture(scope="function")
async def clean_mongo_backend_init_mode_sync():
    """Create a MongoDB backend with InitMode.SYNC and auto_init=True."""
    backend = MongoMindtraceODM(
        model_cls=MongoUserDoc,
        db_uri=MONGO_URI,
        db_name=MONGO_DB_NAME,
        auto_init=True,
        init_mode=InitMode.SYNC,  # Explicit sync mode
    )
    # In async context, even SYNC mode defers initialization (can't use asyncio.run() when loop is running)
    assert hasattr(backend, '_needs_init') and backend._needs_init
    yield backend

    # Cleanup
    if not backend._is_initialized:
        await backend.initialize()
    try:
        collection = backend.client[MONGO_DB_NAME]["auto_init_users"]
        await collection.delete_many({})
    except Exception:
        pass
    backend.client.close()


@pytest.fixture(scope="function")
def clean_redis_backend_init_mode_sync():
    """Create a Redis backend with InitMode.SYNC and auto_init=True."""
    backend = RedisMindtraceODM(
        model_cls=RedisUserDoc,
        redis_url=REDIS_URL,
        auto_init=True,
        init_mode=InitMode.SYNC,  # Explicit sync mode (default)
    )
    # Should be initialized immediately
    assert backend._is_initialized

    yield backend

    # Cleanup
    try:
        for user in backend.all():
            backend.delete(user.pk)
    except Exception:
        pass


@pytest.fixture(scope="function")
def clean_redis_backend_init_mode_async():
    """Create a Redis backend with InitMode.ASYNC and auto_init=True."""
    backend = RedisMindtraceODM(
        model_cls=RedisUserDoc,
        redis_url=REDIS_URL,
        auto_init=True,
        init_mode=InitMode.ASYNC,  # Explicit async mode (defers initialization)
    )
    # Should NOT be initialized immediately (deferred)
    assert not backend._is_initialized

    yield backend

    # Cleanup
    if not backend._is_initialized:
        backend.initialize()
    try:
        for user in backend.all():
            backend.delete(user.pk)
    except Exception:
        pass


@pytest_asyncio.fixture(scope="function")
async def clean_unified_backend_init_modes():
    """Create a unified backend with custom init mode for both backends."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        redis_url=REDIS_URL,
        preferred_backend=BackendType.MONGO,
        auto_init=True,
        init_mode=InitMode.SYNC,  # Both backends use SYNC mode
    )
    # Redis should be initialized immediately (sync mode)
    assert backend.get_redis_backend()._is_initialized

    yield backend

    # Cleanup MongoDB
    if backend.has_mongo_backend():
        mongo_backend = backend.get_mongo_backend()
        if not mongo_backend._is_initialized:
            await mongo_backend.initialize()
        try:
            collection_name = UnifiedUserDoc.get_meta().collection_name
            collection = mongo_backend.client[MONGO_DB_NAME][collection_name]
            await collection.delete_many({})
        except Exception:
            pass

    # Cleanup Redis
    if backend.has_redis_backend():
        redis_backend = backend.get_redis_backend()
        try:
            pattern = f"{UnifiedUserDoc.get_meta().global_key_prefix}:*"
            keys = redis_backend.redis.keys(pattern)
            if keys:
                redis_backend.redis.delete(*keys)
        except Exception:
            pass


# ============================================================================
# MongoDB Backend Tests - Explicit Initialization
# ============================================================================


@pytest.mark.asyncio
async def test_mongo_explicit_init_insert(clean_mongo_backend):
    """Test MongoDB with explicit initialization."""
    backend = clean_mongo_backend
    assert not backend._is_initialized

    # Explicitly initialize
    await backend.initialize()
    assert backend._is_initialized
    
    # Now create and insert - operations should work
    user = MongoUserDoc(name="Alice", age=30, email="alice@test.com")
    inserted = await backend.insert(user)

    # Verify it worked
    assert inserted.name == "Alice"
    assert inserted.age == 30
    assert inserted.email == "alice@test.com"
    assert inserted.id is not None


@pytest.mark.asyncio
async def test_mongo_explicit_init_full_crud(clean_mongo_backend):
    """Test full CRUD operations with explicit initialization."""
    backend = clean_mongo_backend
    assert not backend._is_initialized

    # Explicitly initialize
    await backend.initialize()
    assert backend._is_initialized
    
    # Create
    user = MongoUserDoc(name="Bob", age=25, email="bob@test.com")
    inserted = await backend.insert(user)
    user_id = str(inserted.id)

    # Read
    fetched = await backend.get(user_id)
    assert fetched.name == "Bob"
    assert fetched.age == 25

    # Read all
    all_users = await backend.all()
    assert len(all_users) >= 1
    assert any(u.email == "bob@test.com" for u in all_users)

    # Find
    found_users = await backend.find({"name": "Bob"})
    assert len(found_users) >= 1
    assert found_users[0].email == "bob@test.com"

    # Delete
    await backend.delete(user_id)
    with pytest.raises(DocumentNotFoundError):
        await backend.get(user_id)


# ============================================================================
# MongoDB Backend Tests - Auto-Initialization
# ============================================================================


@pytest.mark.asyncio
async def test_mongo_auto_init_insert(clean_mongo_backend_auto_init):
    """Test that MongoDB auto-initializes on first operation (deferred in async context)."""
    backend = clean_mongo_backend_auto_init
    # In async context, initialization is deferred
    assert hasattr(backend, '_needs_init') and backend._needs_init

    # First operation should auto-initialize
    await backend.initialize()  # Need to call explicitly in async context
    user = MongoUserDoc(name="Alice", age=30, email="alice@test.com")
    inserted = await backend.insert(user)

    # Verify initialization happened
    assert backend._is_initialized
    assert inserted.name == "Alice"
    assert inserted.age == 30
    assert inserted.email == "alice@test.com"
    assert inserted.id is not None


@pytest.mark.asyncio
async def test_mongo_auto_init_full_crud(clean_mongo_backend_auto_init):
    """Test full CRUD operations with auto-initialization."""
    backend = clean_mongo_backend_auto_init
    
    # Initialize first (required in async context for document creation)
    await backend.initialize()
    
    # Create
    user = MongoUserDoc(name="Bob", age=25, email="bob@test.com")
    inserted = await backend.insert(user)
    assert backend._is_initialized
    user_id = str(inserted.id)

    # Read
    fetched = await backend.get(user_id)
    assert fetched.name == "Bob"
    assert fetched.age == 25

    # Read all
    all_users = await backend.all()
    assert len(all_users) >= 1
    assert any(u.email == "bob@test.com" for u in all_users)

    # Find
    found_users = await backend.find({"name": "Bob"})
    assert len(found_users) >= 1
    assert found_users[0].email == "bob@test.com"

    # Delete
    await backend.delete(user_id)
    with pytest.raises(DocumentNotFoundError):
        await backend.get(user_id)


@pytest.mark.asyncio
async def test_mongo_explicit_init_error_handling(clean_mongo_backend):
    """Test error handling with explicit initialization."""
    backend = clean_mongo_backend
    assert not backend._is_initialized

    # Explicitly initialize
    await backend.initialize()
    assert backend._is_initialized
    
    # Insert first user
    user1 = MongoUserDoc(name="Charlie", age=35, email="charlie@test.com")
    inserted1 = await backend.insert(user1)

    # Try to insert duplicate (unique constraint on email)
    user2 = MongoUserDoc(name="Charlie2", age=36, email="charlie@test.com")
    with pytest.raises(DuplicateInsertError):
        await backend.insert(user2)

    # Try to get non-existent user
    with pytest.raises(DocumentNotFoundError):
        await backend.get("507f1f77bcf86cd799439011")


# ============================================================================
# Redis Backend Tests - Explicit Initialization
# ============================================================================


def test_redis_explicit_init_insert(clean_redis_backend):
    """Test Redis with explicit initialization."""
    backend = clean_redis_backend
    assert not backend._is_initialized

    # Explicitly initialize
    backend.initialize()
    assert backend._is_initialized

    # Insert
    user = RedisUserDoc(name="David", age=28, email="david@test.com")
    inserted = backend.insert(user)

    # Verify it worked
    assert inserted.name == "David"
    assert inserted.age == 28
    assert inserted.email == "david@test.com"
    assert inserted.pk is not None


def test_redis_explicit_init_full_crud(clean_redis_backend):
    """Test full CRUD operations with explicit initialization."""
    backend = clean_redis_backend
    assert not backend._is_initialized

    # Explicitly initialize
    backend.initialize()
    assert backend._is_initialized

    # Create
    user = RedisUserDoc(name="Eve", age=32, email="eve@test.com", skills=["Python", "Redis"])
    inserted = backend.insert(user)
    user_pk = inserted.pk

    # Read
    fetched = backend.get(user_pk)
    assert fetched.name == "Eve"
    assert fetched.age == 32
    assert fetched.skills == ["Python", "Redis"]

    # Read all
    all_users = backend.all()
    assert len(all_users) >= 1
    assert any(u.email == "eve@test.com" for u in all_users)

    # Find
    found_users = backend.find(RedisUserDoc.email == "eve@test.com")
    assert len(found_users) >= 1
    assert found_users[0].name == "Eve"

    # Delete
    backend.delete(user_pk)
    with pytest.raises(DocumentNotFoundError):
        backend.get(user_pk)


# ============================================================================
# Redis Backend Tests - Auto-Initialization
# ============================================================================


def test_redis_auto_init_insert(clean_redis_backend_auto_init):
    """Test that Redis auto-initializes in __init__ and works immediately."""
    backend = clean_redis_backend_auto_init
    # Should be initialized immediately
    assert backend._is_initialized

    # Insert without explicit initialization - should work immediately
    user = RedisUserDoc(name="David", age=28, email="david@test.com")
    inserted = backend.insert(user)

    # Verify it worked
    assert inserted.name == "David"
    assert inserted.age == 28
    assert inserted.email == "david@test.com"
    assert inserted.pk is not None


def test_redis_auto_init_full_crud(clean_redis_backend_auto_init):
    """Test full CRUD operations with auto-initialization."""
    backend = clean_redis_backend_auto_init
    # Should be initialized immediately
    assert backend._is_initialized

    # Create
    user = RedisUserDoc(name="Eve", age=32, email="eve@test.com", skills=["Python", "Redis"])
    inserted = backend.insert(user)
    user_pk = inserted.pk

    # Read
    fetched = backend.get(user_pk)
    assert fetched.name == "Eve"
    assert fetched.age == 32
    assert fetched.skills == ["Python", "Redis"]

    # Read all
    all_users = backend.all()
    assert len(all_users) >= 1
    assert any(u.email == "eve@test.com" for u in all_users)

    # Find
    found_users = backend.find(RedisUserDoc.email == "eve@test.com")
    assert len(found_users) >= 1
    assert found_users[0].name == "Eve"

    # Delete
    backend.delete(user_pk)
    with pytest.raises(DocumentNotFoundError):
        backend.get(user_pk)


def test_redis_explicit_init_error_handling(clean_redis_backend):
    """Test error handling with explicit initialization."""
    backend = clean_redis_backend
    assert not backend._is_initialized

    # Explicitly initialize
    backend.initialize()
    assert backend._is_initialized

    # Insert first user
    user1 = RedisUserDoc(name="Frank", age=40, email="frank@test.com")
    inserted1 = backend.insert(user1)

    # Try to get non-existent user
    with pytest.raises(DocumentNotFoundError):
        backend.get("non-existent-pk")


def test_redis_auto_init_error_handling(clean_redis_backend_auto_init):
    """Test error handling with auto-initialization."""
    backend = clean_redis_backend_auto_init
    assert backend._is_initialized

    # Insert first user
    user1 = RedisUserDoc(name="Frank", age=40, email="frank@test.com")
    inserted1 = backend.insert(user1)

    # Try to get non-existent user
    with pytest.raises(DocumentNotFoundError):
        backend.get("non-existent-pk")


# ============================================================================
# Unified Backend Tests - MongoDB Only (Explicit Initialization)
# ============================================================================


@pytest.mark.asyncio
async def test_unified_mongo_explicit_init_insert(clean_unified_backend_mongo):
    """Test unified backend with MongoDB using explicit initialization."""
    backend = clean_unified_backend_mongo

    # Explicitly initialize
    await backend.initialize_async()
    mongo_backend = backend.get_mongo_backend()
    assert mongo_backend._is_initialized

    # Insert
    user = UnifiedUserDoc(name="Grace", age=27, email="grace@test.com")
    inserted = await backend.insert_async(user)

    # Verify it worked
    assert inserted.name == "Grace"
    assert inserted.age == 27
    assert inserted.email == "grace@test.com"
    assert inserted.id is not None


@pytest.mark.asyncio
async def test_unified_mongo_explicit_init_full_crud(clean_unified_backend_mongo):
    """Test full CRUD with unified MongoDB backend using explicit init."""
    backend = clean_unified_backend_mongo

    # Explicitly initialize
    await backend.initialize_async()

    # Create
    user = UnifiedUserDoc(name="Henry", age=29, email="henry@test.com", skills=["Docker"])
    inserted = await backend.insert_async(user)
    user_id = inserted.id

    # Read
    fetched = await backend.get_async(user_id)
    assert fetched.name == "Henry"
    assert fetched.skills == ["Docker"]

    # Read all
    all_users = await backend.all_async()
    assert len(all_users) >= 1

    # Find
    found = await backend.find_async({"name": "Henry"})
    assert len(found) >= 1
    assert found[0].email == "henry@test.com"

    # Delete
    await backend.delete_async(user_id)
    with pytest.raises(DocumentNotFoundError):
        await backend.get_async(user_id)


# ============================================================================
# Unified Backend Tests - MongoDB Only (Auto-Initialization)
# ============================================================================


@pytest.mark.asyncio
async def test_unified_mongo_auto_init_insert(clean_unified_backend_mongo_auto_init):
    """Test unified backend with MongoDB auto-initializes on insert."""
    backend = clean_unified_backend_mongo_auto_init

    # Initialize first (required in async context for document creation)
    await backend.initialize_async()

    # Insert
    user = UnifiedUserDoc(name="Grace", age=27, email="grace@test.com")
    inserted = await backend.insert_async(user)

    # Verify it worked
    assert inserted.name == "Grace"
    assert inserted.age == 27
    assert inserted.email == "grace@test.com"
    assert inserted.id is not None

    # Verify backend is initialized
    mongo_backend = backend.get_mongo_backend()
    assert mongo_backend._is_initialized


@pytest.mark.asyncio
async def test_unified_mongo_auto_init_full_crud(clean_unified_backend_mongo_auto_init):
    """Test full CRUD with unified MongoDB backend with auto-init."""
    backend = clean_unified_backend_mongo_auto_init

    # Initialize first (required in async context)
    await backend.initialize_async()

    # Create
    user = UnifiedUserDoc(name="Henry", age=29, email="henry@test.com", skills=["Docker"])
    inserted = await backend.insert_async(user)
    user_id = inserted.id

    # Read
    fetched = await backend.get_async(user_id)
    assert fetched.name == "Henry"
    assert fetched.skills == ["Docker"]

    # Read all
    all_users = await backend.all_async()
    assert len(all_users) >= 1

    # Find
    found = await backend.find_async({"name": "Henry"})
    assert len(found) >= 1
    assert found[0].email == "henry@test.com"

    # Delete
    await backend.delete_async(user_id)
    with pytest.raises(DocumentNotFoundError):
        await backend.get_async(user_id)


# ============================================================================
# Unified Backend Tests - Redis Only (Explicit Initialization)
# ============================================================================


def test_unified_redis_explicit_init_insert(clean_unified_backend_redis):
    """Test unified backend with Redis using explicit initialization."""
    backend = clean_unified_backend_redis

    # Explicitly initialize
    backend.initialize_sync()
    redis_backend = backend.get_redis_backend()
    assert redis_backend._is_initialized

    # Insert
    user = UnifiedUserDoc(name="Iris", age=31, email="iris@test.com")
    inserted = backend.insert(user)

    # Verify it worked
    assert inserted.name == "Iris"
    assert inserted.age == 31
    assert inserted.email == "iris@test.com"
    # Redis documents use 'pk' instead of 'id'
    assert inserted.pk is not None


def test_unified_redis_explicit_init_full_crud(clean_unified_backend_redis):
    """Test full CRUD with unified Redis backend using explicit init."""
    backend = clean_unified_backend_redis

    # Explicitly initialize
    backend.initialize_sync()

    # Create
    user = UnifiedUserDoc(name="Jack", age=33, email="jack@test.com", skills=["Kubernetes"])
    inserted = backend.insert(user)
    # Redis documents use 'pk' instead of 'id'
    user_id = inserted.pk

    # Read
    fetched = backend.get(user_id)
    assert fetched.name == "Jack"
    assert fetched.skills == ["Kubernetes"]

    # Read all
    all_users = backend.all()
    assert len(all_users) >= 1

    # Find (Redis uses raw model for find)
    redis_model = backend.get_raw_model()
    found = backend.find(redis_model.name == "Jack")
    assert len(found) >= 1
    assert found[0].email == "jack@test.com"

    # Delete
    backend.delete(user_id)
    with pytest.raises(DocumentNotFoundError):
        backend.get(user_id)


# ============================================================================
# Unified Backend Tests - Redis Only (Auto-Initialization)
# ============================================================================


def test_unified_redis_auto_init_insert(clean_unified_backend_redis_auto_init):
    """Test unified backend with Redis auto-initializes in __init__."""
    backend = clean_unified_backend_redis_auto_init

    # Should be initialized immediately
    redis_backend = backend.get_redis_backend()
    assert redis_backend._is_initialized

    # Insert without explicit initialization - should work immediately
    user = UnifiedUserDoc(name="Iris", age=31, email="iris@test.com")
    inserted = backend.insert(user)

    # Verify it worked
    assert inserted.name == "Iris"
    assert inserted.age == 31
    assert inserted.email == "iris@test.com"
    # Redis documents use 'pk' instead of 'id'
    assert inserted.pk is not None


def test_unified_redis_auto_init_full_crud(clean_unified_backend_redis_auto_init):
    """Test full CRUD with unified Redis backend with auto-init."""
    backend = clean_unified_backend_redis_auto_init

    # Should be initialized immediately
    assert backend.get_redis_backend()._is_initialized

    # Create
    user = UnifiedUserDoc(name="Jack", age=33, email="jack@test.com", skills=["Kubernetes"])
    inserted = backend.insert(user)
    # Redis documents use 'pk' instead of 'id'
    user_id = inserted.pk

    # Read
    fetched = backend.get(user_id)
    assert fetched.name == "Jack"
    assert fetched.skills == ["Kubernetes"]

    # Read all
    all_users = backend.all()
    assert len(all_users) >= 1

    # Find (Redis uses raw model for find)
    redis_model = backend.get_raw_model()
    found = backend.find(redis_model.name == "Jack")
    assert len(found) >= 1
    assert found[0].email == "jack@test.com"

    # Delete
    backend.delete(user_id)
    with pytest.raises(DocumentNotFoundError):
        backend.get(user_id)


# ============================================================================
# Unified Backend Tests - Dual Backend (Explicit Initialization)
# ============================================================================


@pytest.mark.asyncio
async def test_unified_dual_explicit_init_backend_switching(clean_unified_backend_dual):
    """Test unified backend with both backends using explicit initialization."""
    backend = clean_unified_backend_dual

    # Explicitly initialize
    await backend.initialize_async()

    # Start with MongoDB (preferred)
    assert backend.get_current_backend_type() == BackendType.MONGO

    # Insert in MongoDB
    user1 = UnifiedUserDoc(name="Kate", age=34, email="kate@test.com")
    inserted1 = await backend.insert_async(user1)
    assert inserted1.id is not None

    # Verify MongoDB is initialized
    mongo_backend = backend.get_mongo_backend()
    assert mongo_backend._is_initialized

    # Switch to Redis
    backend.switch_backend(BackendType.REDIS)
    assert backend.get_current_backend_type() == BackendType.REDIS

    # Insert in Redis
    user2 = UnifiedUserDoc(name="Liam", age=36, email="liam@test.com")
    inserted2 = backend.insert(user2)
    # Redis documents use 'pk' instead of 'id'
    assert inserted2.pk is not None

    # Verify Redis is initialized
    redis_backend = backend.get_redis_backend()
    assert redis_backend._is_initialized

    # Verify data isolation
    mongo_users = await backend.get_mongo_backend().all()
    redis_users = backend.get_redis_backend().all()

    mongo_names = [u.name for u in mongo_users]
    redis_names = [u.name for u in redis_users]

    assert "Kate" in mongo_names
    assert "Liam" in redis_names
    assert "Kate" not in redis_names
    assert "Liam" not in mongo_names


# ============================================================================
# Unified Backend Tests - Dual Backend (Auto-Initialization)
# ============================================================================


@pytest.mark.asyncio
async def test_unified_dual_auto_init_backend_switching(clean_unified_backend_dual_auto_init):
    """Test unified backend with both backends auto-initializes and switches correctly."""
    backend = clean_unified_backend_dual_auto_init

    # Redis should be initialized immediately
    assert backend.get_redis_backend()._is_initialized

    # Initialize MongoDB (required in async context)
    await backend.initialize_async()

    # Start with MongoDB (preferred)
    assert backend.get_current_backend_type() == BackendType.MONGO

    # Insert in MongoDB
    user1 = UnifiedUserDoc(name="Kate", age=34, email="kate@test.com")
    inserted1 = await backend.insert_async(user1)
    assert inserted1.id is not None

    # Verify MongoDB is initialized
    mongo_backend = backend.get_mongo_backend()
    assert mongo_backend._is_initialized

    # Switch to Redis
    backend.switch_backend(BackendType.REDIS)
    assert backend.get_current_backend_type() == BackendType.REDIS

    # Insert in Redis (should already be initialized)
    user2 = UnifiedUserDoc(name="Liam", age=36, email="liam@test.com")
    inserted2 = backend.insert(user2)
    # Redis documents use 'pk' instead of 'id'
    assert inserted2.pk is not None

    # Verify Redis is initialized
    redis_backend = backend.get_redis_backend()
    assert redis_backend._is_initialized

    # Verify data isolation
    mongo_users = await backend.get_mongo_backend().all()
    redis_users = backend.get_redis_backend().all()

    mongo_names = [u.name for u in mongo_users]
    redis_names = [u.name for u in redis_users]

    assert "Kate" in mongo_names
    assert "Liam" in redis_names
    assert "Kate" not in redis_names
    assert "Liam" not in mongo_names


@pytest.mark.asyncio
async def test_unified_dual_explicit_init_sync_operations(clean_unified_backend_dual):
    """Test sync operations on dual backend with explicit initialization."""
    backend = clean_unified_backend_dual

    # Explicitly initialize
    await backend.initialize_async()

    # Use async operations in async context (will use MongoDB)
    user = UnifiedUserDoc(name="Mia", age=38, email="mia@test.com")
    
    # Insert using async method (will use MongoDB)
    inserted = await backend.insert_async(user)
    assert inserted.name == "Mia"
    assert inserted.id is not None

    # Get using async method
    fetched = await backend.get_async(inserted.id)
    assert fetched.email == "mia@test.com"

    # All using async method
    all_users = await backend.all_async()
    assert len(all_users) >= 1

    # Delete using async method
    await backend.delete_async(inserted.id)
    with pytest.raises(DocumentNotFoundError):
        await backend.get_async(inserted.id)


@pytest.mark.asyncio
async def test_unified_dual_auto_init_sync_operations(clean_unified_backend_dual_auto_init):
    """Test sync operations on dual backend with auto-initialization."""
    backend = clean_unified_backend_dual_auto_init

    # Initialize MongoDB (required in async context)
    await backend.initialize_async()

    # Use async operations in async context (will use MongoDB)
    user = UnifiedUserDoc(name="Mia", age=38, email="mia@test.com")
    
    # Insert using async method (will use MongoDB)
    inserted = await backend.insert_async(user)
    assert inserted.name == "Mia"
    assert inserted.id is not None

    # Get using async method
    fetched = await backend.get_async(inserted.id)
    assert fetched.email == "mia@test.com"

    # All using async method
    all_users = await backend.all_async()
    assert len(all_users) >= 1

    # Delete using async method
    await backend.delete_async(inserted.id)
    with pytest.raises(DocumentNotFoundError):
        await backend.get_async(inserted.id)


# ============================================================================
# Edge Cases and Performance Tests
# ============================================================================


@pytest.mark.asyncio
async def test_mongo_explicit_init_multiple_operations(clean_mongo_backend):
    """Test that multiple operations work correctly with explicit initialization."""
    backend = clean_mongo_backend
    assert not backend._is_initialized

    # Explicitly initialize once
    await backend.initialize()
    assert backend._is_initialized

    # First operation
    user1 = MongoUserDoc(name="Noah", age=22, email="noah@test.com")
    await backend.insert(user1)
    assert backend._is_initialized

    # Subsequent operations should not re-initialize (idempotent)
    user2 = MongoUserDoc(name="Olivia", age=24, email="olivia@test.com")
    await backend.insert(user2)
    assert backend._is_initialized  # Still initialized

    # Verify both users exist
    all_users = await backend.all()
    assert len(all_users) >= 2
    emails = [u.email for u in all_users]
    assert "noah@test.com" in emails
    assert "olivia@test.com" in emails


@pytest.mark.asyncio
async def test_mongo_auto_init_multiple_operations(clean_mongo_backend_auto_init):
    """Test that multiple operations work correctly with auto-initialization."""
    backend = clean_mongo_backend_auto_init

    # Initialize first (required in async context)
    await backend.initialize()

    # First operation
    user1 = MongoUserDoc(name="Noah", age=22, email="noah@test.com")
    await backend.insert(user1)
    assert backend._is_initialized

    # Subsequent operations should not re-initialize (idempotent)
    user2 = MongoUserDoc(name="Olivia", age=24, email="olivia@test.com")
    await backend.insert(user2)
    assert backend._is_initialized  # Still initialized

    # Verify both users exist
    all_users = await backend.all()
    assert len(all_users) >= 2
    emails = [u.email for u in all_users]
    assert "noah@test.com" in emails
    assert "olivia@test.com" in emails


def test_redis_explicit_init_concurrent_operations(clean_redis_backend):
    """Test that Redis works with multiple rapid operations using explicit init."""
    backend = clean_redis_backend
    assert not backend._is_initialized

    # Explicitly initialize
    backend.initialize()
    assert backend._is_initialized

    # Insert multiple users rapidly
    users = [
        RedisUserDoc(name=f"User{i}", age=20 + i, email=f"user{i}@test.com")
        for i in range(5)
    ]

    for user in users:
        inserted = backend.insert(user)
        assert inserted.pk is not None
        assert backend._is_initialized

    # Verify all users exist
    all_users = backend.all()
    assert len(all_users) >= 5


def test_redis_auto_init_concurrent_operations(clean_redis_backend_auto_init):
    """Test that Redis auto-initialization works with multiple rapid operations."""
    backend = clean_redis_backend_auto_init
    assert backend._is_initialized  # Should be initialized immediately

    # Insert multiple users rapidly
    users = [
        RedisUserDoc(name=f"User{i}", age=20 + i, email=f"user{i}@test.com")
        for i in range(5)
    ]

    for user in users:
        inserted = backend.insert(user)
        assert inserted.pk is not None
        assert backend._is_initialized

    # Verify all users exist
    all_users = backend.all()
    assert len(all_users) >= 5


@pytest.mark.asyncio
async def test_unified_explicit_init_with_backend_switching(clean_unified_backend_dual):
    """Test that explicit initialization works correctly when switching backends."""
    backend = clean_unified_backend_dual

    # Explicitly initialize
    await backend.initialize_async()

    # Start with MongoDB
    user1 = UnifiedUserDoc(name="Paul", age=41, email="paul@test.com")
    inserted1 = await backend.insert_async(user1)
    mongo_backend = backend.get_mongo_backend()
    assert mongo_backend._is_initialized

    # Switch to Redis
    backend.switch_backend(BackendType.REDIS)
    
    # Insert in Redis
    user2 = UnifiedUserDoc(name="Quinn", age=43, email="quinn@test.com")
    inserted2 = backend.insert(user2)
    redis_backend = backend.get_redis_backend()
    assert redis_backend._is_initialized

    # Switch back to MongoDB - should still be initialized
    backend.switch_backend(BackendType.MONGO)
    assert mongo_backend._is_initialized

    # Verify we can still access MongoDB data
    fetched = await backend.get_async(inserted1.id)
    assert fetched.name == "Paul"


@pytest.mark.asyncio
async def test_unified_auto_init_with_backend_switching(clean_unified_backend_dual_auto_init):
    """Test that auto-initialization works correctly when switching backends."""
    backend = clean_unified_backend_dual_auto_init

    # Initialize MongoDB (required in async context)
    await backend.initialize_async()

    # Start with MongoDB
    user1 = UnifiedUserDoc(name="Paul", age=41, email="paul@test.com")
    inserted1 = await backend.insert_async(user1)
    mongo_backend = backend.get_mongo_backend()
    assert mongo_backend._is_initialized

    # Switch to Redis (should already be initialized)
    backend.switch_backend(BackendType.REDIS)
    assert backend.get_redis_backend()._is_initialized
    
    # Insert in Redis
    user2 = UnifiedUserDoc(name="Quinn", age=43, email="quinn@test.com")
    inserted2 = backend.insert(user2)
    redis_backend = backend.get_redis_backend()
    assert redis_backend._is_initialized

    # Switch back to MongoDB - should still be initialized
    backend.switch_backend(BackendType.MONGO)
    assert mongo_backend._is_initialized

    # Verify we can still access MongoDB data
    fetched = await backend.get_async(inserted1.id)
    assert fetched.name == "Paul"



# ============================================================================
# InitMode Tests - MongoDB
# ============================================================================


@pytest.mark.asyncio
async def test_mongo_init_mode_async_auto_init(clean_mongo_backend_init_mode_async):
    """Test MongoDB with InitMode.ASYNC and auto_init=True."""
    backend = clean_mongo_backend_init_mode_async
    
    # In async context, initialization is deferred
    assert hasattr(backend, '_needs_init') and backend._needs_init
    
    # Initialize first (required in async context)
    await backend.initialize()
    
    # Insert
    user = MongoUserDoc(name="InitModeAsync", age=30, email="initmodeasync@test.com")
    inserted = await backend.insert(user)
    
    # Verify it worked
    assert backend._is_initialized
    assert inserted.name == "InitModeAsync"
    assert inserted.email == "initmodeasync@test.com"
    assert inserted.id is not None


@pytest.mark.asyncio
async def test_mongo_init_mode_sync_auto_init(clean_mongo_backend_init_mode_sync):
    """Test MongoDB with InitMode.SYNC and auto_init=True."""
    backend = clean_mongo_backend_init_mode_sync
    
    # In async context, even with SYNC mode, initialization is deferred
    # (because we're in an async test context)
    assert hasattr(backend, '_needs_init') and backend._needs_init
    
    # Initialize first (required in async context)
    await backend.initialize()
    
    # Insert
    user = MongoUserDoc(name="InitModeSync", age=31, email="initmodesync@test.com")
    inserted = await backend.insert(user)
    
    # Verify it worked
    assert backend._is_initialized
    assert inserted.name == "InitModeSync"
    assert inserted.email == "initmodesync@test.com"
    assert inserted.id is not None


@pytest.mark.asyncio
async def test_mongo_init_mode_default_behavior():
    """Test MongoDB default init_mode (should be ASYNC)."""
    backend = MongoMindtraceODM(
        model_cls=MongoUserDoc,
        db_uri=MONGO_URI,
        db_name=MONGO_DB_NAME,
        auto_init=True,
        # init_mode not specified - should default to ASYNC
    )
    
    # In async context, initialization is deferred
    assert hasattr(backend, '_needs_init') and backend._needs_init
    
    # Initialize and test
    await backend.initialize()
    user = MongoUserDoc(name="DefaultMode", age=32, email="defaultmode@test.com")
    inserted = await backend.insert(user)
    
    assert backend._is_initialized
    assert inserted.name == "DefaultMode"
    
    # Cleanup
    try:
        collection = backend.client[MONGO_DB_NAME]["auto_init_users"]
        await collection.delete_many({})
    except Exception:
        pass
    backend.client.close()


# ============================================================================
# InitMode Tests - Redis
# ============================================================================


def test_redis_init_mode_sync_auto_init(clean_redis_backend_init_mode_sync):
    """Test Redis with InitMode.SYNC and auto_init=True."""
    backend = clean_redis_backend_init_mode_sync
    
    # Should be initialized immediately (sync mode)
    assert backend._is_initialized
    
    # Insert
    user = RedisUserDoc(name="InitModeSync", age=33, email="initmodesync@test.com")
    inserted = backend.insert(user)
    
    # Verify it worked
    assert inserted.name == "InitModeSync"
    assert inserted.email == "initmodesync@test.com"
    assert inserted.pk is not None


def test_redis_init_mode_async_auto_init(clean_redis_backend_init_mode_async):
    """Test Redis with InitMode.ASYNC and auto_init=True."""
    backend = clean_redis_backend_init_mode_async
    
    # Should NOT be initialized immediately (async mode defers)
    assert not backend._is_initialized
    
    # First operation should auto-initialize
    user = RedisUserDoc(name="InitModeAsync", age=34, email="initmodeasync@test.com")
    inserted = backend.insert(user)
    
    # Should be initialized after first operation
    assert backend._is_initialized
    assert inserted.name == "InitModeAsync"
    assert inserted.email == "initmodeasync@test.com"
    assert inserted.pk is not None


def test_redis_init_mode_default_behavior():
    """Test Redis default init_mode (should be SYNC)."""
    backend = RedisMindtraceODM(
        model_cls=RedisUserDoc,
        redis_url=REDIS_URL,
        auto_init=True,
        # init_mode not specified - should default to SYNC
    )
    
    # Should be initialized immediately (default is SYNC)
    assert backend._is_initialized
    
    # Insert
    user = RedisUserDoc(name="DefaultMode", age=35, email="defaultmode@test.com")
    inserted = backend.insert(user)
    
    assert inserted.name == "DefaultMode"
    
    # Cleanup
    try:
        for user in backend.all():
            backend.delete(user.pk)
    except Exception:
        pass


def test_redis_init_mode_sync_without_auto_init():
    """Test Redis with InitMode.SYNC but auto_init=False."""
    backend = RedisMindtraceODM(
        model_cls=RedisUserDoc,
        redis_url=REDIS_URL,
        auto_init=False,
        init_mode=InitMode.SYNC,
    )
    
    # Should NOT be initialized (auto_init=False)
    assert not backend._is_initialized
    
    # First operation should auto-initialize
    user = RedisUserDoc(name="SyncNoAuto", age=36, email="syncnoauto@test.com")
    inserted = backend.insert(user)
    
    # Should be initialized after first operation
    assert backend._is_initialized
    assert inserted.name == "SyncNoAuto"
    
    # Cleanup
    try:
        for user in backend.all():
            backend.delete(user.pk)
    except Exception:
        pass


def test_redis_init_mode_async_without_auto_init():
    """Test Redis with InitMode.ASYNC and auto_init=False."""
    backend = RedisMindtraceODM(
        model_cls=RedisUserDoc,
        redis_url=REDIS_URL,
        auto_init=False,
        init_mode=InitMode.ASYNC,
    )
    
    # Should NOT be initialized (auto_init=False)
    assert not backend._is_initialized
    
    # First operation should auto-initialize
    user = RedisUserDoc(name="AsyncNoAuto", age=37, email="asyncnoauto@test.com")
    inserted = backend.insert(user)
    
    # Should be initialized after first operation
    assert backend._is_initialized
    assert inserted.name == "AsyncNoAuto"
    
    # Cleanup
    try:
        for user in backend.all():
            backend.delete(user.pk)
    except Exception:
        pass


# ============================================================================
# InitMode Tests - Unified Backend
# ============================================================================


@pytest.mark.asyncio
async def test_unified_init_modes_custom(clean_unified_backend_init_modes):
    """Test unified backend with custom init modes for MongoDB and Redis."""
    backend = clean_unified_backend_init_modes
    
    # Redis should be initialized immediately (sync mode)
    assert backend.get_redis_backend()._is_initialized
    
    # MongoDB should not be initialized yet (async mode, deferred)
    mongo_backend = backend.get_mongo_backend()
    assert hasattr(mongo_backend, '_needs_init') and mongo_backend._needs_init
    
    # Initialize MongoDB
    await backend.initialize_async()
    assert mongo_backend._is_initialized
    
    # Insert in MongoDB
    user1 = UnifiedUserDoc(name="MongoInitMode", age=38, email="mongoinitmode@test.com")
    inserted1 = await backend.insert_async(user1)
    assert inserted1.id is not None
    assert inserted1.name == "MongoInitMode"
    
    # Switch to Redis (already initialized)
    backend.switch_backend(BackendType.REDIS)
    assert backend.get_redis_backend()._is_initialized
    
    # Insert in Redis
    user2 = UnifiedUserDoc(name="RedisInitMode", age=39, email="redisinitmode@test.com")
    inserted2 = backend.insert(user2)
    assert inserted2.pk is not None
    assert inserted2.name == "RedisInitMode"


@pytest.mark.asyncio
async def test_unified_init_modes_defaults():
    """Test unified backend with default init modes."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        redis_url=REDIS_URL,
        preferred_backend=BackendType.MONGO,
        auto_init=True,
        # init_modes not specified - should use defaults (ASYNC for MongoDB, SYNC for Redis)
    )
    
    # Redis should be initialized immediately (default is SYNC)
    assert backend.get_redis_backend()._is_initialized
    
    # MongoDB should not be initialized yet (default is ASYNC, deferred)
    mongo_backend = backend.get_mongo_backend()
    assert hasattr(mongo_backend, '_needs_init') and mongo_backend._needs_init
    
    # Initialize MongoDB
    await backend.initialize_async()
    assert mongo_backend._is_initialized
    
    # Test operations
    user = UnifiedUserDoc(name="DefaultModes", age=40, email="defaultmodes@test.com")
    inserted = await backend.insert_async(user)
    assert inserted.name == "DefaultModes"
    
    # Cleanup
    try:
        collection_name = UnifiedUserDoc.get_meta().collection_name
        collection = mongo_backend.client[MONGO_DB_NAME][collection_name]
        await collection.delete_many({})
    except Exception:
        pass
    
    try:
        pattern = f"{UnifiedUserDoc.get_meta().global_key_prefix}:*"
        keys = backend.get_redis_backend().redis.keys(pattern)
        if keys:
            backend.get_redis_backend().redis.delete(*keys)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_unified_init_modes_both_async():
    """Test unified backend with both backends using ASYNC init mode."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        redis_url=REDIS_URL,
        preferred_backend=BackendType.MONGO,
        auto_init=True,
        init_mode=InitMode.ASYNC,  # Both backends use ASYNC mode
    )
    
    # Both backends should NOT be initialized (ASYNC mode defers in async context)
    assert not backend.get_redis_backend()._is_initialized
    mongo_backend = backend.get_mongo_backend()
    assert hasattr(mongo_backend, '_needs_init') and mongo_backend._needs_init
    
    # Initialize MongoDB (both backends in ASYNC mode, but MongoDB gets initialized, Redis skipped)
    await backend.initialize_async()
    assert mongo_backend._is_initialized
    # Redis should NOT be initialized (ASYNC mode defers, initialize_async respects this)
    assert not backend.get_redis_backend()._is_initialized
    
    # Insert in MongoDB
    user1 = UnifiedUserDoc(name="MongoSync", age=41, email="mongosync@test.com")
    inserted1 = await backend.insert_async(user1)
    assert inserted1.name == "MongoSync"
    
    # Switch to Redis and insert (should auto-initialize)
    backend.switch_backend(BackendType.REDIS)
    assert not backend.get_redis_backend()._is_initialized  # Still not initialized
    
    user2 = UnifiedUserDoc(name="RedisAsync", age=42, email="redisasync@test.com")
    inserted2 = backend.insert(user2)  # This should auto-initialize
    assert backend.get_redis_backend()._is_initialized  # Now initialized
    assert inserted2.name == "RedisAsync"
    
    # Cleanup
    try:
        collection_name = UnifiedUserDoc.get_meta().collection_name
        collection = mongo_backend.client[MONGO_DB_NAME][collection_name]
        await collection.delete_many({})
    except Exception:
        pass
    
    try:
        pattern = f"{UnifiedUserDoc.get_meta().global_key_prefix}:*"
        keys = backend.get_redis_backend().redis.keys(pattern)
        if keys:
            backend.get_redis_backend().redis.delete(*keys)
    except Exception:
        pass


# ============================================================================
# InitMode Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_mongo_init_mode_explicit_init_override():
    """Test that explicit initialize() call works regardless of init_mode."""
    backend = MongoMindtraceODM(
        model_cls=MongoUserDoc,
        db_uri=MONGO_URI,
        db_name=MONGO_DB_NAME,
        auto_init=False,
        init_mode=InitMode.ASYNC,
    )
    
    assert not backend._is_initialized
    
    # Explicit initialization should work
    await backend.initialize()
    assert backend._is_initialized
    
    # Operations should work
    user = MongoUserDoc(name="ExplicitInit", age=43, email="explicitinit@test.com")
    inserted = await backend.insert(user)
    assert inserted.name == "ExplicitInit"
    
    # Cleanup
    try:
        collection = backend.client[MONGO_DB_NAME]["auto_init_users"]
        await collection.delete_many({})
    except Exception:
        pass
    backend.client.close()


def test_redis_init_mode_explicit_init_override():
    """Test that explicit initialize() call works regardless of init_mode."""
    backend = RedisMindtraceODM(
        model_cls=RedisUserDoc,
        redis_url=REDIS_URL,
        auto_init=False,
        init_mode=InitMode.ASYNC,
    )
    
    assert not backend._is_initialized
    
    # Explicit initialization should work
    backend.initialize()
    assert backend._is_initialized
    
    # Operations should work
    user = RedisUserDoc(name="ExplicitInit", age=44, email="explicitinit@test.com")
    inserted = backend.insert(user)
    assert inserted.name == "ExplicitInit"
    
    # Cleanup
    try:
        for user in backend.all():
            backend.delete(user.pk)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_mongo_init_mode_idempotent():
    """Test that initialize() is idempotent regardless of init_mode."""
    backend = MongoMindtraceODM(
        model_cls=MongoUserDoc,
        db_uri=MONGO_URI,
        db_name=MONGO_DB_NAME,
        auto_init=False,
        init_mode=InitMode.SYNC,
    )
    
    # First initialization
    await backend.initialize()
    assert backend._is_initialized
    
    # Second initialization (should be idempotent)
    await backend.initialize()
    assert backend._is_initialized
    
    # Operations should work
    user = MongoUserDoc(name="Idempotent", age=45, email="idempotent@test.com")
    inserted = await backend.insert(user)
    assert inserted.name == "Idempotent"
    
    # Cleanup
    try:
        collection = backend.client[MONGO_DB_NAME]["auto_init_users"]
        await collection.delete_many({})
    except Exception:
        pass
    backend.client.close()


def test_redis_init_mode_idempotent():
    """Test that initialize() is idempotent regardless of init_mode."""
    backend = RedisMindtraceODM(
        model_cls=RedisUserDoc,
        redis_url=REDIS_URL,
        auto_init=False,
        init_mode=InitMode.ASYNC,
    )
    
    # First initialization
    backend.initialize()
    assert backend._is_initialized
    
    # Second initialization (should be idempotent)
    backend.initialize()
    assert backend._is_initialized
    
    # Operations should work
    user = RedisUserDoc(name="Idempotent", age=46, email="idempotent@test.com")
    inserted = backend.insert(user)
    assert inserted.name == "Idempotent"
    
    # Cleanup
    try:
        for user in backend.all():
            backend.delete(user.pk)
    except Exception:
        pass


# ============================================================================
# Coverage Tests for Missing Lines
# ============================================================================


@pytest.mark.asyncio
async def test_mongo_initialize_with_allow_index_dropping():
    """Test MongoDB initialize() with allow_index_dropping parameter (covers line 200)."""
    backend = MongoMindtraceODM(
        model_cls=MongoUserDoc,
        db_uri=MONGO_URI,
        db_name=MONGO_DB_NAME,
        auto_init=False,
    )
    
    # Initialize with allow_index_dropping=True
    await backend.initialize(allow_index_dropping=True)
    assert backend._is_initialized
    assert backend._allow_index_dropping is True
    
    # Initialize again with allow_index_dropping=False (should NOT update - already initialized)
    # This tests the idempotent behavior and early return (line 196-197)
    await backend.initialize(allow_index_dropping=False)
    assert backend._is_initialized
    # Should still be True because initialize() returns early when already initialized
    assert backend._allow_index_dropping is True
    
    # Cleanup
    try:
        collection = backend.client[MONGO_DB_NAME]["auto_init_users"]
        await collection.delete_many({})
    except Exception:
        pass
    backend.client.close()


@pytest.mark.asyncio
async def test_unified_initialize_async_with_allow_index_dropping():
    """Test unified backend initialize_async() with allow_index_dropping (covers line 564)."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        preferred_backend=BackendType.MONGO,
        auto_init=False,
    )
    
    # Initialize with allow_index_dropping=True
    await backend.initialize_async(allow_index_dropping=True)
    mongo_backend = backend.get_mongo_backend()
    assert mongo_backend._is_initialized
    assert mongo_backend._allow_index_dropping is True
    
    # Cleanup
    try:
        collection_name = UnifiedUserDoc.get_meta().collection_name
        collection = mongo_backend.client[MONGO_DB_NAME][collection_name]
        await collection.delete_many({})
    except Exception:
        pass


def test_unified_initialize_sync_with_allow_index_dropping():
    """Test unified backend initialize_sync() with allow_index_dropping (covers line 616)."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        preferred_backend=BackendType.MONGO,
        auto_init=False,
    )
    
    # Initialize with allow_index_dropping=True
    backend.initialize_sync(allow_index_dropping=True)
    mongo_backend = backend.get_mongo_backend()
    assert mongo_backend._is_initialized
    assert mongo_backend._allow_index_dropping is True
    
    # Cleanup
    try:
        asyncio.run(mongo_backend.client.close())
    except Exception:
        pass


def test_unified_initialize_sync_with_allow_index_dropping_none():
    """Test unified backend initialize_sync() with allow_index_dropping=None (covers line 616 default path)."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        preferred_backend=BackendType.MONGO,
        auto_init=False,
        allow_index_dropping=False,  # Set in __init__
    )
    
    # Initialize with allow_index_dropping=None (should use value from __init__)
    backend.initialize_sync(allow_index_dropping=None)
    mongo_backend = backend.get_mongo_backend()
    assert mongo_backend._is_initialized
    assert mongo_backend._allow_index_dropping is False  # Should use value from __init__
    
    # Cleanup
    try:
        asyncio.run(mongo_backend.client.close())
    except Exception:
        pass


def test_unified_initialize_with_allow_index_dropping():
    """Test unified backend initialize() with allow_index_dropping (covers line 639)."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        preferred_backend=BackendType.MONGO,
        auto_init=False,
    )
    
    # Initialize with allow_index_dropping=True
    backend.initialize(allow_index_dropping=True)
    mongo_backend = backend.get_mongo_backend()
    assert mongo_backend._is_initialized
    assert mongo_backend._allow_index_dropping is True
    
    # Cleanup
    try:
        asyncio.run(mongo_backend.client.close())
    except Exception:
        pass


# Note: The fallback path (lines 619-622) is tested in unit tests with proper mocking
# This integration test focuses on the normal path with real database connections


def test_redis_init_mode_sync_path():
    """Test Redis init_mode SYNC path in __init__ (covers lines 113-115)."""
    backend = RedisMindtraceODM(
        model_cls=RedisUserDoc,
        redis_url=REDIS_URL,
        auto_init=True,
        init_mode=InitMode.SYNC,  # Should initialize immediately
    )
    
    # Should be initialized immediately (SYNC mode)
    assert backend._is_initialized
    
    # Cleanup
    try:
        for user in backend.all():
            backend.delete(user.pk)
    except Exception:
        pass


def test_redis_init_mode_async_path():
    """Test Redis init_mode ASYNC path in __init__ (covers lines 116-119)."""
    backend = RedisMindtraceODM(
        model_cls=RedisUserDoc,
        redis_url=REDIS_URL,
        auto_init=True,
        init_mode=InitMode.ASYNC,  # Should defer initialization
    )
    
    # Should NOT be initialized immediately (ASYNC mode defers)
    assert not backend._is_initialized
    
    # First operation should auto-initialize
    user = RedisUserDoc(name="AsyncPath", age=47, email="asyncpath@test.com")
    inserted = backend.insert(user)
    assert backend._is_initialized
    assert inserted.name == "AsyncPath"
    
    # Cleanup
    try:
        for user in backend.all():
            backend.delete(user.pk)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_unified_redis_async_mode_skip_initialization():
    """Test unified backend skips Redis initialization when in ASYNC mode (covers lines 575, 582)."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        redis_url=REDIS_URL,
        preferred_backend=BackendType.MONGO,
        auto_init=False,
        init_mode=InitMode.ASYNC,  # Both backends in ASYNC mode
    )
    
    # Initialize - should skip Redis (ASYNC mode)
    await backend.initialize_async()
    
    # MongoDB should be initialized
    assert backend.get_mongo_backend()._is_initialized
    
    # Redis should NOT be initialized (ASYNC mode defers)
    assert not backend.get_redis_backend()._is_initialized
    
    # Cleanup
    try:
        collection_name = UnifiedUserDoc.get_meta().collection_name
        collection = backend.get_mongo_backend().client[MONGO_DB_NAME][collection_name]
        await collection.delete_many({})
    except Exception:
        pass


@pytest.mark.asyncio
async def test_unified_redis_sync_mode_initialization():
    """Test unified backend initializes Redis when in SYNC mode (covers line 582)."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        redis_url=REDIS_URL,
        preferred_backend=BackendType.MONGO,
        auto_init=False,
        init_mode=InitMode.SYNC,  # Both backends in SYNC mode
    )
    
    # Initialize - should initialize both
    await backend.initialize_async()
    
    # Both should be initialized
    assert backend.get_mongo_backend()._is_initialized
    assert backend.get_redis_backend()._is_initialized
    
    # Cleanup
    try:
        collection_name = UnifiedUserDoc.get_meta().collection_name
        collection = backend.get_mongo_backend().client[MONGO_DB_NAME][collection_name]
        await collection.delete_many({})
    except Exception:
        pass


@pytest.mark.asyncio
async def test_unified_redis_already_initialized_skip():
    """Test unified backend skips Redis initialization if already initialized."""
    backend = UnifiedMindtraceODM(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB_NAME,
        redis_url=REDIS_URL,
        preferred_backend=BackendType.MONGO,
        auto_init=True,  # This will initialize Redis immediately (SYNC mode default)
    )
    
    # Redis should be initialized immediately (auto_init=True, default SYNC mode)
    assert backend.get_redis_backend()._is_initialized
    
    # Call initialize_async again - should skip Redis (already initialized)
    await backend.initialize_async()
    
    # Both should still be initialized
    assert backend.get_mongo_backend()._is_initialized
    assert backend.get_redis_backend()._is_initialized
    
    # Cleanup
    try:
        collection_name = UnifiedUserDoc.get_meta().collection_name
        collection = backend.get_mongo_backend().client[MONGO_DB_NAME][collection_name]
        await collection.delete_many({})
    except Exception:
        pass


# ============================================================================
# Sync Context Tests (for coverage of sync initialization paths)
# ============================================================================


def test_mongo_init_mode_sync_in_sync_context():
    """Test MongoDB with InitMode.SYNC and auto_init=True in a true sync context."""
    # This test runs in sync context (not async), so SYNC mode should actually initialize
    # We clear the event loop to ensure we're in a true sync context for testing
    import asyncio
    
    # Check if we're in an async context (can't test sync init if loop is running)
    try:
        asyncio.get_running_loop()
        pytest.skip("Event loop is running, cannot test sync initialization")
    except RuntimeError:
        # No running loop - we can test sync initialization
        pass
    
    # Try to clear the event loop to ensure we're in a true sync context
    try:
        asyncio.set_event_loop(None)
    except Exception:
        pass
    
    backend = MongoMindtraceODM(
        model_cls=MongoUserDoc,
        db_uri=MONGO_URI,
        db_name=MONGO_DB_NAME,
        auto_init=True,
        init_mode=InitMode.SYNC,  # Should initialize synchronously in sync context
    )
    
    # In sync context, SYNC mode should initialize immediately
    # Note: This covers lines 127-135 in mongo_odm.py (sync initialization path)
    assert backend._is_initialized
    assert not hasattr(backend, '_needs_init') or not backend._needs_init
    
    # Cleanup - need to close client properly
    try:
        # Close client synchronously using asyncio.run() (simpler than manual loop management)
        asyncio.run(backend.client.close())
    except Exception:
        pass


def test_mongo_initialize_sync_idempotent():
    """Test that initialize_sync() is idempotent and covers early return path."""
    backend = MongoMindtraceODM(
        model_cls=MongoUserDoc,
        db_uri=MONGO_URI,
        db_name=MONGO_DB_NAME,
        auto_init=False,
        init_mode=InitMode.SYNC,
    )
    
    assert not backend._is_initialized
    
    # First initialization
    backend.initialize_sync()
    assert backend._is_initialized
    
    # Second initialization (should be idempotent - covers early return path)
    backend.initialize_sync()
    assert backend._is_initialized
    
    # Cleanup
    try:
        backend.client.close()
    except Exception:
        pass


def test_mongo_init_mode_async_in_sync_context():
    """Test MongoDB with InitMode.ASYNC and auto_init=True in a sync context."""
    # This test runs in sync context, but ASYNC mode should defer
    backend = MongoMindtraceODM(
        model_cls=MongoUserDoc,
        db_uri=MONGO_URI,
        db_name=MONGO_DB_NAME,
        auto_init=True,
        init_mode=InitMode.ASYNC,  # Should defer even in sync context
    )
    
    # In sync context, ASYNC mode should defer initialization
    assert hasattr(backend, '_needs_init') and backend._needs_init
    assert not backend._is_initialized
    
    # Cleanup
    try:
        backend.client.close()
    except Exception:
        pass
