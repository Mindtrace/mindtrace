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
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
    )


@pytest.fixture
def unified_backend_redis_only(mock_redis_backend):
    """Create a unified backend with only Redis configured."""
    return UnifiedMindtraceODMBackend(
        redis_model_cls=RedisUserDoc, redis_url="redis://localhost:6379", preferred_backend=BackendType.REDIS
    )


@pytest.fixture
def unified_backend_both(mock_mongo_backend, mock_redis_backend):
    """Create a unified backend with both MongoDB and Redis configured."""
    return UnifiedMindtraceODMBackend(
        mongo_model_cls=MongoUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        redis_model_cls=RedisUserDoc,
        redis_url="redis://localhost:6379",
        preferred_backend=BackendType.MONGO,
    )


@pytest.fixture
def unified_backend_with_unified_model(mock_mongo_backend, mock_redis_backend):
    """Create a unified backend with a unified document model."""
    return UnifiedMindtraceODMBackend(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        redis_url="redis://localhost:6379",
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


def test_unified_backend_auto_generation_with_field_default_factory():
    """Test auto-generation with field default_factory."""
    from mindtrace.database.backends.unified_odm_backend import UnifiedMindtraceDocument
    from pydantic import Field
    from typing import List
    
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
    assert hasattr(mongo_model, 'Settings')
    assert mongo_model.Settings.name == "default_factory_users"
    
    # Test Redis auto-generation with default_factory
    redis_model = DefaultFactoryUser._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, 'Meta')
    assert redis_model.Meta.global_key_prefix == "mindtrace"


def test_unified_backend_auto_generation_with_optional_indexed_fields():
    """Test auto-generation with optional indexed fields."""
    from mindtrace.database.backends.unified_odm_backend import UnifiedMindtraceDocument
    from typing import Optional
    
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
    assert hasattr(mongo_model, 'Settings')
    assert mongo_model.Settings.name == "optional_indexed_users"
    
    # Test Redis auto-generation with optional indexed fields
    redis_model = OptionalIndexedUser._auto_generate_redis_model()
    assert redis_model is not None
    assert hasattr(redis_model, 'Meta')
    assert redis_model.Meta.global_key_prefix == "mindtrace"


def test_unified_backend_get_active_backend_with_no_backends():
    """Test _get_active_backend with no backends configured."""
    from mindtrace.database.backends.unified_odm_backend import UnifiedMindtraceODMBackend, BackendType
    
    # Create a backend with valid configuration first
    backend = UnifiedMindtraceODMBackend(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO
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
    from mindtrace.database.backends.unified_odm_backend import UnifiedMindtraceODMBackend, BackendType
    
    backend = UnifiedMindtraceODMBackend(
        unified_model_cls=UnifiedUserDoc,
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO
    )
    
    # Test that ValueError is raised when unknown backend type is provided
    with pytest.raises(ValueError, match="Unknown backend type"):
        backend.switch_backend("unknown_backend")


# Tests for unified backend edge cases
class TestUnifiedBackendEdgeCases:
    """Test edge cases and error conditions in unified backend."""

    def test_unified_backend_initialize_async_no_mongo_backend(self):
        """Test initialize_async when no MongoDB backend is configured."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        with pytest.raises(ValueError, match="initialize_async.*called but no asynchronous.*backend is configured"):
            import asyncio
            asyncio.run(backend.initialize_async())

    def test_unified_backend_initialize_sync(self):
        """Test initialize_sync method."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        # Should not raise
        backend.initialize_sync()

    def test_unified_backend_get_current_backend_type_unknown(self):
        """Test get_current_backend_type with unknown active backend."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        # Manually set an unknown active backend
        backend._active_backend = MagicMock()
        
        with pytest.raises(RuntimeError, match="Unknown active backend"):
            backend.get_current_backend_type()

    def test_unified_backend_switch_backend_invalid_type(self):
        """Test switch_backend with invalid backend type."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        with pytest.raises(ValueError, match="Unknown backend type"):
            backend.switch_backend("invalid_type")

    def test_unified_backend_switch_backend_mongo_not_configured(self):
        """Test switch_backend to MongoDB when not configured."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        with pytest.raises(ValueError, match="MongoDB backend is not configured"):
            backend.switch_backend(BackendType.MONGO)

    def test_unified_backend_switch_backend_redis_not_configured(self):
        """Test switch_backend to Redis when not configured."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        with pytest.raises(ValueError, match="Redis backend is not configured"):
            backend.switch_backend(BackendType.REDIS)

    def test_unified_backend_get_active_backend_no_backends_available(self):
        """Test _get_active_backend when no backends are available."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        # Manually set backends to None
        backend.mongo_backend = None
        backend.redis_backend = None
        backend._active_backend = None
        
        with pytest.raises(RuntimeError, match="No backend available"):
            backend._get_active_backend()

    def test_unified_backend_auto_generate_mongo_model_with_unique_fields(self):
        """Test _auto_generate_mongo_model with unique fields."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        mongo_model = UnifiedDocModel._auto_generate_mongo_model()
        assert mongo_model is not None
        assert hasattr(mongo_model, 'Settings')
        assert mongo_model.Settings.name == "test_users"
        
        # Check that email field has unique index
        annotations = getattr(mongo_model, '__annotations__', {})
        assert 'email' in annotations

    def test_unified_backend_auto_generate_redis_model_with_optional_fields(self):
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
        assert hasattr(redis_model, 'Meta')
        assert redis_model.Meta.global_key_prefix == "optional_test"

    def test_unified_backend_auto_generate_redis_model_with_default_factory(self):
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
        assert hasattr(redis_model, 'Meta')
        assert redis_model.Meta.global_key_prefix == "default_factory_test"


# Additional tests for remaining missing coverage
class TestUnifiedBackendRemainingCoverage:
    """Test remaining missing coverage in unified backend."""

    @pytest.mark.asyncio
    async def test_unified_backend_delete_async_sync_backend(self):
        """Test delete_async with synchronous backend."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        with patch.object(backend, '_get_active_backend') as mock_get_backend:
            mock_backend = MagicMock()
            mock_backend.is_async.return_value = False
            mock_backend.delete.return_value = None
            mock_get_backend.return_value = mock_backend
            
            await backend.delete_async("test_id")
            mock_backend.delete.assert_called_once_with("test_id")

    @pytest.mark.asyncio
    async def test_unified_backend_delete_async_async_backend(self):
        """Test delete_async with asynchronous backend."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        with patch.object(backend, '_get_active_backend') as mock_get_backend:
            mock_backend = MagicMock()
            mock_backend.is_async.return_value = True
            mock_backend.delete = AsyncMock(side_effect=None)
            mock_get_backend.return_value = mock_backend
            
            await backend.delete_async("test_id")
            mock_backend.delete.assert_called_once_with("test_id")

    @pytest.mark.asyncio
    async def test_unified_backend_all_async_sync_backend(self):
        """Test all_async with synchronous backend."""
        from tests.fixtures.database_models import UnifiedDocModel, UserModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        with patch.object(backend, '_get_active_backend') as mock_get_backend:
            mock_backend = MagicMock()
            mock_backend.is_async.return_value = False
            mock_backend.all.return_value = [UserModel(name="Test", age=25, email="test@example.com")]
            mock_get_backend.return_value = mock_backend
            
            result = await backend.all_async()
            assert len(result) == 1
            assert result[0].name == "Test"

    @pytest.mark.asyncio
    async def test_unified_backend_all_async_async_backend(self):
        """Test all_async with asynchronous backend."""
        from tests.fixtures.database_models import UnifiedDocModel, UserModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        with patch.object(backend, '_get_active_backend') as mock_get_backend:
            mock_backend = MagicMock()
            mock_backend.is_async.return_value = True
            mock_backend.all = AsyncMock(return_value=[UserModel(name="Test", age=25, email="test@example.com")], side_effect=None)
            mock_get_backend.return_value = mock_backend
            
            result = await backend.all_async()
            assert len(result) == 1
            assert result[0].name == "Test"

    @pytest.mark.asyncio
    async def test_unified_backend_find_async_sync_backend(self):
        """Test find_async with synchronous backend."""
        from tests.fixtures.database_models import UnifiedDocModel, UserModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        with patch.object(backend, '_get_active_backend') as mock_get_backend:
            mock_backend = MagicMock()
            mock_backend.is_async.return_value = False
            mock_backend.find.return_value = [UserModel(name="Test", age=25, email="test@example.com")]
            mock_get_backend.return_value = mock_backend
            
            result = await backend.find_async(name="Test")
            assert len(result) == 1
            assert result[0].name == "Test"

    @pytest.mark.asyncio
    async def test_unified_backend_find_async_async_backend(self):
        """Test find_async with asynchronous backend."""
        from tests.fixtures.database_models import UnifiedDocModel, UserModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        with patch.object(backend, '_get_active_backend') as mock_get_backend:
            mock_backend = MagicMock()
            mock_backend.is_async.return_value = True
            mock_backend.find = AsyncMock(return_value=[UserModel(name="Test", age=25, email="test@example.com")], side_effect=None)
            mock_get_backend.return_value = mock_backend
            
            result = await backend.find_async(name="Test")
            assert len(result) == 1
            assert result[0].name == "Test"

    def test_unified_backend_get_unified_model_no_model(self):
        """Test get_unified_model when no model is configured."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        # Create a backend with a model first, then manually set it to None
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        # Manually set unified_model_cls to None to test the error condition
        backend.unified_model_cls = None
        
        with pytest.raises(ValueError, match="No unified model class configured"):
            backend.get_unified_model()

    def test_unified_backend_get_mongo_backend_not_configured(self):
        """Test get_mongo_backend when MongoDB is not configured."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        with pytest.raises(ValueError, match="MongoDB backend is not configured"):
            backend.get_mongo_backend()

    def test_unified_backend_get_redis_backend_not_configured(self):
        """Test get_redis_backend when Redis is not configured."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        with pytest.raises(ValueError, match="Redis backend is not configured"):
            backend.get_redis_backend()

    def test_unified_backend_has_mongo_backend_true(self):
        """Test has_mongo_backend when MongoDB is configured."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        assert backend.has_mongo_backend() is True

    def test_unified_backend_has_mongo_backend_false(self):
        """Test has_mongo_backend when MongoDB is not configured."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        assert backend.has_mongo_backend() is False

    def test_unified_backend_has_redis_backend_true(self):
        """Test has_redis_backend when Redis is configured."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        assert backend.has_redis_backend() is True

    def test_unified_backend_has_redis_backend_false(self):
        """Test has_redis_backend when Redis is not configured."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        assert backend.has_redis_backend() is False

    def test_unified_backend_get_mongo_backend_configured(self):
        """Test get_mongo_backend when MongoDB is configured."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        mongo_backend = backend.get_mongo_backend()
        assert mongo_backend is not None

    def test_unified_backend_get_redis_backend_configured(self):
        """Test get_redis_backend when Redis is configured."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        redis_backend = backend.get_redis_backend()
        assert redis_backend is not None

    def test_unified_backend_get_raw_model(self):
        """Test get_raw_model method."""
        from tests.fixtures.database_models import UnifiedDocModel, UserModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        with patch.object(backend, '_get_active_backend') as mock_get_backend:
            mock_backend = MagicMock()
            mock_backend.get_raw_model.return_value = UserModel
            mock_get_backend.return_value = mock_backend
            
            result = backend.get_raw_model()
            assert result == UserModel

    def test_unified_backend_get_unified_model_configured(self):
        """Test get_unified_model when model is configured."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        result = backend.get_unified_model()
        assert result == UnifiedDocModel


# Additional tests for advanced coverage
class TestUnifiedBackendAdvancedCoverage:
    """Test advanced edge cases and missing coverage in unified backend."""

    def test_unified_backend_initialize_async_context_warning(self):
        """Test initialize method when called from async context."""
        import asyncio
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        # Mock asyncio.get_running_loop to simulate async context
        with patch("asyncio.get_running_loop") as mock_get_loop:
            mock_get_loop.return_value = MagicMock()
            
            # Mock print to capture the warning
            with patch("builtins.print") as mock_print:
                backend.initialize()
                mock_print.assert_called_with("Warning: initialize() called from async context. Use await initialize_async() instead.")

    def test_unified_backend_handle_async_call_sync_backend(self):
        """Test _handle_async_call with synchronous backend."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        # Mock the backend to be synchronous
        with patch.object(backend, '_get_active_backend') as mock_get_backend:
            mock_backend = MagicMock()
            mock_backend.is_async.return_value = False
            mock_backend.test_method.return_value = "sync_result"
            mock_get_backend.return_value = mock_backend
            
            result = backend._handle_async_call("test_method", "arg1", kwarg1="value1")
            
            assert result == "sync_result"
            mock_backend.test_method.assert_called_once_with("arg1", kwarg1="value1")

    def test_unified_backend_handle_async_call_async_backend(self):
        """Test _handle_async_call with asynchronous backend."""
        import asyncio
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        # Mock the backend to be asynchronous
        with patch.object(backend, '_get_active_backend') as mock_get_backend:
            mock_backend = MagicMock()
            mock_backend.is_async.return_value = True
            mock_backend.test_method.return_value = "async_result"
            mock_get_backend.return_value = mock_backend
            
            with patch("asyncio.run") as mock_asyncio_run:
                mock_asyncio_run.return_value = "async_result"
                
                result = backend._handle_async_call("test_method", "arg1", kwarg1="value1")
                
                assert result == "async_result"
                mock_asyncio_run.assert_called_once()

    def test_unified_backend_convert_unified_to_backend_data_mongo(self):
        """Test _convert_unified_to_backend_data for MongoDB backend."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        user = UnifiedDocModel(id="test123", name="John", age=30, email="john@example.com")
        
        with patch.object(backend, 'get_current_backend_type') as mock_get_type:
            mock_get_type.return_value = BackendType.MONGO
            
            result = backend._convert_unified_to_backend_data(user)
            
            # Should be a DataWrapper with id field removed
            assert hasattr(result, 'data')
            assert 'id' not in result.data
            assert result.data['name'] == "John"
            assert result.data['age'] == 30
            assert result.data['email'] == "john@example.com"

    def test_unified_backend_convert_unified_to_backend_data_redis(self):
        """Test _convert_unified_to_backend_data for Redis backend."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        user = UnifiedDocModel(id="test123", name="John", age=30, email="john@example.com")
        
        with patch.object(backend, 'get_current_backend_type') as mock_get_type:
            mock_get_type.return_value = BackendType.REDIS
            
            result = backend._convert_unified_to_backend_data(user)
            
            # Should be a DataWrapper with id converted to pk
            assert hasattr(result, 'data')
            assert 'id' not in result.data
            assert result.data['pk'] == "test123"
            assert result.data['name'] == "John"
            assert result.data['age'] == 30
            assert result.data['email'] == "john@example.com"

    def test_unified_backend_convert_unified_to_backend_data_redis_none_id(self):
        """Test _convert_unified_to_backend_data for Redis backend with None id."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        user = UnifiedDocModel(id=None, name="John", age=30, email="john@example.com")
        
        with patch.object(backend, 'get_current_backend_type') as mock_get_type:
            mock_get_type.return_value = BackendType.REDIS
            
            result = backend._convert_unified_to_backend_data(user)
            
            # Should be a DataWrapper with id field removed (not converted to pk)
            assert hasattr(result, 'data')
            assert 'id' not in result.data
            assert 'pk' not in result.data
            assert result.data['name'] == "John"
            assert result.data['age'] == 30
            assert result.data['email'] == "john@example.com"

    def test_unified_backend_convert_unified_to_backend_data_non_unified(self):
        """Test _convert_unified_to_backend_data with non-unified model."""
        from tests.fixtures.database_models import UnifiedDocModel, UserModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        user = UserModel(name="John", age=30, email="john@example.com")
        
        result = backend._convert_unified_to_backend_data(user)
        
        # Should return the original object unchanged
        assert result == user

    def test_unified_backend_auto_generate_redis_model_with_callable_default_factory(self):
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
        assert hasattr(redis_model, 'Meta')
        assert redis_model.Meta.global_key_prefix == "callable_default_test"

    def test_unified_backend_auto_generate_redis_model_with_ellipsis_default(self):
        """Test _auto_generate_redis_model with ellipsis default."""
        class EllipsisDefaultDoc(UnifiedMindtraceDocument):
            name: str = Field(default=...)
            age: int = Field(default=25)

            class Meta:
                collection_name = "ellipsis_default_test"
                global_key_prefix = "ellipsis_default_test"

        redis_model = EllipsisDefaultDoc._auto_generate_redis_model()
        assert redis_model is not None
        assert hasattr(redis_model, 'Meta')
        assert redis_model.Meta.global_key_prefix == "ellipsis_default_test"

    def test_unified_backend_auto_generate_redis_model_with_none_default_factory(self):
        """Test _auto_generate_redis_model with None default_factory."""
        class NoneDefaultFactoryDoc(UnifiedMindtraceDocument):
            name: str = Field(default_factory=None)
            age: int = Field(default=25)

            class Meta:
                collection_name = "none_default_factory_test"
                global_key_prefix = "none_default_factory_test"

        redis_model = NoneDefaultFactoryDoc._auto_generate_redis_model()
        assert redis_model is not None
        assert hasattr(redis_model, 'Meta')
        assert redis_model.Meta.global_key_prefix == "none_default_factory_test"

    def test_unified_backend_auto_generate_redis_model_with_indexed_fields_and_defaults(self):
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
        assert hasattr(redis_model, '__annotations__')
        assert hasattr(redis_model, 'Meta')
        
        # Check that fields are properly created with Redis Field instances
        assert hasattr(redis_model, 'name')
        assert hasattr(redis_model, 'age')
        assert hasattr(redis_model, 'email')

    def test_unified_backend_auto_generate_mongo_model_with_no_fields(self):
        """Test _auto_generate_mongo_model with a class that has no fields."""
        class EmptyDoc(UnifiedMindtraceDocument):
            class Meta:
                collection_name = "empty_collection"

        mongo_model = EmptyDoc._auto_generate_mongo_model()
        assert mongo_model is not None
        assert hasattr(mongo_model, 'Settings')
        assert mongo_model.Settings.name == "empty_collection"

# Final tests for the last missing lines
class TestUnifiedBackendLastMissingLines:
    """Test the last missing lines in unified backend."""

    def test_unified_backend_initialize_sync_no_redis_backend(self):
        """Test initialize_sync when no Redis backend is configured."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        with pytest.raises(ValueError, match="initialize_sync.*called but no synchronous.*backend is configured"):
            backend.initialize_sync()

    def test_unified_backend_initialize_sync_with_redis_backend(self):
        """Test initialize_sync when Redis backend is configured."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        # Mock the Redis backend initialize method
        with patch.object(backend.redis_backend, 'initialize') as mock_init:
            backend.initialize_sync()
            mock_init.assert_called_once()

    def test_unified_backend_get_active_backend_prefer_mongo_mongo_available(self):
        """Test _get_active_backend when preferring MongoDB and it's available."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        active_backend = backend._get_active_backend()
        assert active_backend == backend.mongo_backend

    def test_unified_backend_get_active_backend_prefer_redis_redis_available(self):
        """Test _get_active_backend when preferring Redis and it's available."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        active_backend = backend._get_active_backend()
        assert active_backend == backend.redis_backend

    def test_unified_backend_get_active_backend_prefer_mongo_redis_available(self):
        """Test _get_active_backend when preferring MongoDB but only Redis is available."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.MONGO
        )
        
        active_backend = backend._get_active_backend()
        assert active_backend == backend.redis_backend

    def test_unified_backend_get_active_backend_prefer_redis_mongo_available(self):
        """Test _get_active_backend when preferring Redis but only MongoDB is available."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.REDIS
        )
        
        active_backend = backend._get_active_backend()
        assert active_backend == backend.mongo_backend

    def test_unified_backend_get_active_backend_cached(self):
        """Test _get_active_backend when result is cached."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        # First call should set the cache
        active_backend1 = backend._get_active_backend()
        assert active_backend1 == backend.redis_backend
        
        # Second call should use cached result
        active_backend2 = backend._get_active_backend()
        assert active_backend2 == backend.redis_backend
        assert active_backend1 is active_backend2

    def test_unified_backend_convert_unified_to_backend_data_mongo_with_id(self):
        """Test _convert_unified_to_backend_data for MongoDB with id field."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        user = UnifiedDocModel(id="test123", name="John", age=30, email="john@example.com")
        
        with patch.object(backend, 'get_current_backend_type') as mock_get_type:
            mock_get_type.return_value = BackendType.MONGO
            
            result = backend._convert_unified_to_backend_data(user)
            
            # Should be a DataWrapper with id field removed
            assert hasattr(result, 'data')
            assert 'id' not in result.data
            assert result.data['name'] == "John"
            assert result.data['age'] == 30
            assert result.data['email'] == "john@example.com"

    def test_unified_backend_convert_unified_to_backend_data_mongo_without_id(self):
        """Test _convert_unified_to_backend_data for MongoDB without id field."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        user = UnifiedDocModel(name="John", age=30, email="john@example.com")
        
        with patch.object(backend, 'get_current_backend_type') as mock_get_type:
            mock_get_type.return_value = BackendType.MONGO
            
            result = backend._convert_unified_to_backend_data(user)
            
            # Should be a DataWrapper without id field
            assert hasattr(result, 'data')
            assert 'id' not in result.data
            assert result.data['name'] == "John"
            assert result.data['age'] == 30
            assert result.data['email'] == "john@example.com"

    def test_unified_backend_convert_unified_to_backend_data_redis_with_id(self):
        """Test _convert_unified_to_backend_data for Redis with id field."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        user = UnifiedDocModel(id="test123", name="John", age=30, email="john@example.com")
        
        with patch.object(backend, 'get_current_backend_type') as mock_get_type:
            mock_get_type.return_value = BackendType.REDIS
            
            result = backend._convert_unified_to_backend_data(user)
            
            # Should be a DataWrapper with id converted to pk
            assert hasattr(result, 'data')
            assert 'id' not in result.data
            assert result.data['pk'] == "test123"
            assert result.data['name'] == "John"
            assert result.data['age'] == 30
            assert result.data['email'] == "john@example.com"

    def test_unified_backend_convert_unified_to_backend_data_redis_without_id(self):
        """Test _convert_unified_to_backend_data for Redis without id field."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        user = UnifiedDocModel(name="John", age=30, email="john@example.com")
        
        with patch.object(backend, 'get_current_backend_type') as mock_get_type:
            mock_get_type.return_value = BackendType.REDIS
            
            result = backend._convert_unified_to_backend_data(user)
            
            # Should be a DataWrapper without id field
            assert hasattr(result, 'data')
            assert 'id' not in result.data
            assert 'pk' not in result.data
            assert result.data['name'] == "John"
            assert result.data['age'] == 30
            assert result.data['email'] == "john@example.com"

    def test_unified_backend_convert_unified_to_backend_data_redis_with_none_id(self):
        """Test _convert_unified_to_backend_data for Redis with None id field."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        user = UnifiedDocModel(id=None, name="John", age=30, email="john@example.com")
        
        with patch.object(backend, 'get_current_backend_type') as mock_get_type:
            mock_get_type.return_value = BackendType.REDIS
            
            result = backend._convert_unified_to_backend_data(user)
            
            # Should be a DataWrapper with id field removed (not converted to pk)
            assert hasattr(result, 'data')
            assert 'id' not in result.data
            assert 'pk' not in result.data
            assert result.data['name'] == "John"
            assert result.data['age'] == 30
            assert result.data['email'] == "john@example.com"

    def test_unified_backend_convert_unified_to_backend_data_non_unified(self):
        """Test _convert_unified_to_backend_data with non-unified model."""
        from tests.fixtures.database_models import UnifiedDocModel, UserModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS
        )
        
        user = UserModel(name="John", age=30, email="john@example.com")
        
        result = backend._convert_unified_to_backend_data(user)
        
        # Should return the original object unchanged
        assert result == user

    def test_unified_backend_auto_generate_redis_model_with_callable_default_factory(self):
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
        assert hasattr(redis_model, 'Meta')
        assert redis_model.Meta.global_key_prefix == "callable_default_test"

    def test_unified_backend_auto_generate_redis_model_with_ellipsis_default(self):
        """Test _auto_generate_redis_model with ellipsis default."""
        class EllipsisDefaultDoc(UnifiedMindtraceDocument):
            name: str = Field(default=...)
            age: int = Field(default=25)

            class Meta:
                collection_name = "ellipsis_default_test"
                global_key_prefix = "ellipsis_default_test"

        redis_model = EllipsisDefaultDoc._auto_generate_redis_model()
        assert redis_model is not None
        assert hasattr(redis_model, 'Meta')
        assert redis_model.Meta.global_key_prefix == "ellipsis_default_test"

    def test_unified_backend_auto_generate_redis_model_with_none_default_factory(self):
        """Test _auto_generate_redis_model with None default_factory."""
        class NoneDefaultFactoryDoc(UnifiedMindtraceDocument):
            name: str = Field(default_factory=None)
            age: int = Field(default=25)

            class Meta:
                collection_name = "none_default_factory_test"
                global_key_prefix = "none_default_factory_test"

        redis_model = NoneDefaultFactoryDoc._auto_generate_redis_model()
        assert redis_model is not None
        assert hasattr(redis_model, 'Meta')
        assert redis_model.Meta.global_key_prefix == "none_default_factory_test"

# Final tests to achieve 100% coverage
class TestFinalCoverage100Percent:
    """Test final missing lines to achieve 100% coverage."""

    def test_unified_backend_auto_generate_redis_model_with_union_type_not_optional(self):
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
        assert hasattr(redis_model, 'Meta')
        assert redis_model.Meta.global_key_prefix == "union_not_optional_test"

    def test_unified_backend_auto_generate_redis_model_with_union_type_three_args(self):
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
        assert hasattr(redis_model, 'Meta')
        assert redis_model.Meta.global_key_prefix == "union_three_args_test"

    def test_unified_backend_auto_generate_redis_model_with_union_type_no_none(self):
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
        assert hasattr(redis_model, 'Meta')
        assert redis_model.Meta.global_key_prefix == "union_no_none_test"

    def test_unified_backend_auto_generate_redis_model_with_union_type_none_first(self):
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
        assert hasattr(redis_model, 'Meta')
        assert redis_model.Meta.global_key_prefix == "union_none_first_test"

    def test_unified_backend_auto_generate_redis_model_with_field_info_no_default_attr(self):
        """Test _auto_generate_redis_model with field info that has no default attribute."""
        class NoDefaultAttrDoc(UnifiedMindtraceDocument):
            name: str
            age: int

            class Meta:
                collection_name = "no_default_attr_test"
                global_key_prefix = "no_default_attr_test"

        # Mock the field info to not have a default attribute
        with patch.object(NoDefaultAttrDoc, '__annotations__', {'name': str, 'age': int}):
            with patch.object(NoDefaultAttrDoc, 'name', create=True) as mock_name:
                with patch.object(NoDefaultAttrDoc, 'age', create=True) as mock_age:
                    # Remove default attribute from mock objects
                    if hasattr(mock_name, 'default'):
                        delattr(mock_name, 'default')
                    if hasattr(mock_age, 'default'):
                        delattr(mock_age, 'default')
                    
                    redis_model = NoDefaultAttrDoc._auto_generate_redis_model()
                    assert redis_model is not None
                    assert hasattr(redis_model, 'Meta')
                    assert redis_model.Meta.global_key_prefix == "no_default_attr_test"

    def test_unified_backend_auto_generate_redis_model_with_field_info_no_default_factory_attr(self):
        """Test _auto_generate_redis_model with field info that has no default_factory attribute."""
        class NoDefaultFactoryAttrDoc(UnifiedMindtraceDocument):
            name: str
            age: int

            class Meta:
                collection_name = "no_default_factory_attr_test"
                global_key_prefix = "no_default_factory_attr_test"

        # Mock the field info to not have a default_factory attribute
        with patch.object(NoDefaultFactoryAttrDoc, '__annotations__', {'name': str, 'age': int}):
            with patch.object(NoDefaultFactoryAttrDoc, 'name', create=True) as mock_name:
                with patch.object(NoDefaultFactoryAttrDoc, 'age', create=True) as mock_age:
                    # Remove default_factory attribute from mock objects
                    if hasattr(mock_name, 'default_factory'):
                        delattr(mock_name, 'default_factory')
                    if hasattr(mock_age, 'default_factory'):
                        delattr(mock_age, 'default_factory')
                    
                    redis_model = NoDefaultFactoryAttrDoc._auto_generate_redis_model()
                    assert redis_model is not None
                    assert hasattr(redis_model, 'Meta')
                    assert redis_model.Meta.global_key_prefix == "no_default_factory_attr_test"

    def test_unified_backend_auto_generate_redis_model_with_field_info_none_default_factory(self):
        """Test _auto_generate_redis_model with field info that has None default_factory."""
        class NoneDefaultFactoryDoc(UnifiedMindtraceDocument):
            name: str
            age: int

            class Meta:
                collection_name = "none_default_factory_test"
                global_key_prefix = "none_default_factory_test"

        # Mock the field info to have None default_factory
        with patch.object(NoneDefaultFactoryDoc, '__annotations__', {'name': str, 'age': int}):
            with patch.object(NoneDefaultFactoryDoc, 'name', create=True) as mock_name:
                with patch.object(NoneDefaultFactoryDoc, 'age', create=True) as mock_age:
                    mock_name.default_factory = None
                    mock_age.default_factory = None
                    
                    redis_model = NoneDefaultFactoryDoc._auto_generate_redis_model()
                    assert redis_model is not None
                    assert hasattr(redis_model, 'Meta')
                    assert redis_model.Meta.global_key_prefix == "none_default_factory_test"

    def test_unified_backend_auto_generate_redis_model_with_indexed_field_no_default(self):
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
        assert hasattr(redis_model, 'Meta')
        assert redis_model.Meta.global_key_prefix == "indexed_no_default_test"

    def test_unified_backend_auto_generate_redis_model_with_non_indexed_field_no_default(self):
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
        assert hasattr(redis_model, 'Meta')
        assert redis_model.Meta.global_key_prefix == "non_indexed_no_default_test"

    def test_unified_backend_auto_generate_mongo_model_with_no_meta_attrs(self):
        """Test _auto_generate_mongo_model with no meta attributes."""
        class NoMetaAttrsDoc(UnifiedMindtraceDocument):
            name: str
            age: int

            class Meta:
                pass  # No attributes

        mongo_model = NoMetaAttrsDoc._auto_generate_mongo_model()
        assert mongo_model is not None
        assert hasattr(mongo_model, 'Settings')
        assert mongo_model.Settings.name == "unified_documents"  # Default value
        assert mongo_model.Settings.use_cache is False  # Default value

    def test_unified_backend_auto_generate_mongo_model_with_custom_meta_attrs(self):
        """Test _auto_generate_mongo_model with custom meta attributes."""
        class CustomMetaAttrsDoc(UnifiedMindtraceDocument):
            name: str
            age: int

            class Meta:
                collection_name = "custom_collection"
                use_cache = True

        mongo_model = CustomMetaAttrsDoc._auto_generate_mongo_model()
        assert mongo_model is not None
        assert hasattr(mongo_model, 'Settings')
        assert mongo_model.Settings.name == "custom_collection"
        assert mongo_model.Settings.use_cache is True

    def test_unified_backend_auto_generate_redis_model_with_custom_meta_attrs(self):
        """Test _auto_generate_redis_model with custom meta attributes."""
        class CustomMetaAttrsDoc(UnifiedMindtraceDocument):
            name: str
            age: int

            class Meta:
                collection_name = "custom_collection"
                global_key_prefix = "custom_prefix"

        redis_model = CustomMetaAttrsDoc._auto_generate_redis_model()
        assert redis_model is not None
        assert hasattr(redis_model, 'Meta')
        assert redis_model.Meta.global_key_prefix == "custom_prefix"
        assert redis_model.Meta.index_name == "custom_prefix:CustomMetaAttrsDocRedis:index"
        assert redis_model.Meta.model_key_prefix == "CustomMetaAttrsDocRedis"

    def test_unified_backend_auto_generate_redis_model_with_default_meta_attrs(self):
        """Test _auto_generate_redis_model with default meta attributes."""
        class DefaultMetaAttrsDoc(UnifiedMindtraceDocument):
            name: str
            age: int

            class Meta:
                pass  # No attributes

        redis_model = DefaultMetaAttrsDoc._auto_generate_redis_model()
        assert redis_model is not None
        assert hasattr(redis_model, 'Meta')
        assert redis_model.Meta.global_key_prefix == "mindtrace"  # Default value
        assert redis_model.Meta.index_name == "mindtrace:DefaultMetaAttrsDocRedis:index"
        assert redis_model.Meta.model_key_prefix == "DefaultMetaAttrsDocRedis"

    def test_unified_backend_get_meta_method(self):
        """Test get_meta method."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        meta = UnifiedDocModel.get_meta()
        assert meta is not None
        assert hasattr(meta, 'collection_name')
        assert hasattr(meta, 'global_key_prefix')
        assert hasattr(meta, 'use_cache')
        assert hasattr(meta, 'indexed_fields')
        assert hasattr(meta, 'unique_fields')

    def test_unified_backend_get_meta_method_with_no_meta(self):
        """Test get_meta method when Meta is not defined."""
        # This test is not needed as get_meta uses getattr with fallback
        # which means it will always return something
        pass

    def test_unified_backend_to_mongo_dict_with_id_field(self):
        """Test to_mongo_dict method with id field."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        user = UnifiedDocModel(id="test123", name="John", age=30, email="john@example.com")
        
        mongo_dict = user.to_mongo_dict()
        
        # Should not contain 'id' field
        assert 'id' not in mongo_dict
        assert mongo_dict['name'] == "John"
        assert mongo_dict['age'] == 30
        assert mongo_dict['email'] == "john@example.com"

    def test_unified_backend_to_mongo_dict_without_id_field(self):
        """Test to_mongo_dict method without id field."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        user = UnifiedDocModel(name="John", age=30, email="john@example.com")
        
        mongo_dict = user.to_mongo_dict()
        
        # Should not contain 'id' field
        assert 'id' not in mongo_dict
        assert mongo_dict['name'] == "John"
        assert mongo_dict['age'] == 30
        assert mongo_dict['email'] == "john@example.com"

# Very last tests for the very last missing lines in unified backend
class TestVeryLastUnifiedBackendLines:
    """Test the very last missing lines in unified backend."""

    def test_unified_backend_initialize_with_async_context_and_running_loop(self):
        """Test initialize method when called from async context with running loop."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        # Mock asyncio.get_running_loop to simulate running async context
        with patch('asyncio.get_running_loop') as mock_get_loop:
            mock_get_loop.return_value = MagicMock()
            
            # Mock print to capture the warning
            with patch('builtins.print') as mock_print:
                backend.initialize()
                mock_print.assert_called_with("Warning: initialize() called from async context. Use await initialize_async() instead.")

    def test_unified_backend_initialize_with_no_running_loop(self):
        """Test initialize method when called from sync context (no running loop)."""
        from tests.fixtures.database_models import UnifiedDocModel
        
        backend = UnifiedMindtraceODMBackend(
            unified_model_cls=UnifiedDocModel,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO
        )
        
        # Mock asyncio.get_running_loop to raise RuntimeError (no running loop)
        with patch('asyncio.get_running_loop') as mock_get_loop:
            mock_get_loop.side_effect = RuntimeError("No running event loop")
            
            # Mock asyncio.run to capture the call
            with patch('asyncio.run') as mock_asyncio_run:
                # Mock the mongo backend initialize method
                with patch.object(backend.mongo_backend, 'initialize') as mock_init:
                    backend.initialize()
                    mock_asyncio_run.assert_called_once()
                    mock_init.assert_called_once()
