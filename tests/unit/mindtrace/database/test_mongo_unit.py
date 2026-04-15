import builtins
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import Document as BeanieDocument
from bson import ObjectId
from pydantic import BaseModel, Field, field_validator

from mindtrace.database import MindtraceDocument


@pytest.fixture(autouse=True)
def _clear_mongo_beanie_primary_db():
    """Reset ``_BEANIE_INITIALIZED_MODEL_CLASSES`` so each test gets a predictable ``init_beanie`` mock."""
    from mindtrace.database.backends import mongo_odm

    mongo_odm._BEANIE_INITIALIZED_MODEL_CLASSES.clear()
    yield
    mongo_odm._BEANIE_INITIALIZED_MODEL_CLASSES.clear()


class UserCreate(BaseModel):
    name: str
    age: int
    email: str


class UserDoc(MindtraceDocument):
    name: str = Field(index=True)
    age: int = Field(index=True)
    email: str = Field(index=True)

    class Settings:
        name = "users"
        use_cache = False


class MotorDoc(BaseModel):
    """Plain Pydantic model for motor-routing unit tests (avoids Beanie ``__init__`` / collection binding)."""

    name: str
    age: int
    email: str
    id: Optional[str] = None

    @field_validator("id", mode="before")
    @classmethod
    def _id_to_str(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v

    class Settings:
        name = "users"


@pytest.fixture
def mock_mongo_backend():
    """Create a mocked MongoDB backend."""
    with patch("mindtrace.database.MindtraceDocument") as mock_backend:
        backend = mock_backend.return_value
        backend.insert = AsyncMock()
        backend.get = AsyncMock()
        backend.all = AsyncMock()
        backend.delete = AsyncMock()
        backend.find = AsyncMock()
        backend.initialize = AsyncMock()
        backend.is_async = AsyncMock(return_value=True)
        backend.get_raw_model = MagicMock(return_value=UserDoc)
        yield backend


def create_mock_mongo_user(name="John", age=30, email="john@example.com", pk="507f1f77bcf86cd799439011"):
    """Create a mock UserDoc instance without requiring MongoDB connection."""
    mock_user = MagicMock(spec=UserDoc)
    mock_user.name = name
    mock_user.age = age
    mock_user.email = email
    mock_user.pk = pk
    return mock_user


@pytest.fixture(autouse=True)
def mock_mongo_connection():
    """Mock AsyncIOMotorClient for all tests so no real MongoDB is used."""
    with patch("mindtrace.database.backends.mongo_odm.AsyncIOMotorClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        yield mock_client_cls


@pytest.mark.asyncio
async def test_mongo_backend_crud(mock_mongo_backend):
    """Test basic CRUD operations."""
    # Test insert
    user = create_mock_mongo_user()
    mock_mongo_backend.insert.return_value = user
    result = await mock_mongo_backend.insert(user)
    assert result.name == "John"
    assert result.age == 30
    assert result.email == "john@example.com"

    # Test get
    mock_mongo_backend.get.return_value = user
    result = await mock_mongo_backend.get(user.pk)
    assert result.name == "John"

    # Test all
    mock_mongo_backend.all.return_value = [user]
    results = await mock_mongo_backend.all()
    assert len(results) == 1
    assert results[0].name == "John"

    # Test delete
    mock_mongo_backend.delete.return_value = True
    result = await mock_mongo_backend.delete(user.pk)
    assert result is True


@pytest.mark.asyncio
async def test_mongo_backend_duplicate_insert(mock_mongo_backend):
    """Test duplicate insert handling."""
    from mindtrace.database.core.exceptions import DuplicateInsertError

    user = create_mock_mongo_user()
    mock_mongo_backend.insert.side_effect = DuplicateInsertError("Duplicate key error")

    with pytest.raises(DuplicateInsertError):
        await mock_mongo_backend.insert(user)


@pytest.mark.asyncio
async def test_mongo_backend_find(mock_mongo_backend):
    """Test find operations."""
    user = create_mock_mongo_user()
    mock_mongo_backend.find.return_value = [user]

    # Test find with query
    results = await mock_mongo_backend.find({"name": "John"})
    assert len(results) == 1
    assert results[0].name == "John"


@pytest.mark.asyncio
async def test_mongo_backend_initialize(mock_mongo_backend):
    """Test backend initialization."""
    mock_mongo_backend.initialize.assert_not_called()
    await mock_mongo_backend.initialize()
    mock_mongo_backend.initialize.assert_called_once()


@pytest.mark.asyncio
async def test_mongo_backend_is_async():
    """Test that MongoDB backend is async."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
    assert backend.is_async() is True


@pytest.mark.asyncio
async def test_mongo_backend_aggregate():
    """Test aggregate operation."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    # Mock the backend with proper model class
    backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc

    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, "initialize"):
        # Mock the get_motor_collection method
        mock_collection = MagicMock()
        mock_cursor = MagicMock()

        # to_list is async in this context
        async def mock_to_list(*args, **kwargs):
            return [{"_id": 25, "count": 2}]

        mock_cursor.to_list = mock_to_list
        mock_collection.aggregate.return_value = mock_cursor

        with patch.object(UserDoc, "get_motor_collection", return_value=mock_collection):
            pipeline = [{"$group": {"_id": "$age", "count": {"$sum": 1}}}]
            results = await backend.aggregate(pipeline)
            assert len(results) == 1
            assert results[0]["_id"] == 25
            assert results[0]["count"] == 2


@pytest.mark.asyncio
async def test_mongo_backend_aggregate_with_empty_pipeline():
    """Test aggregate operation with empty pipeline."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    # Mock the backend with proper model class
    backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc

    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, "initialize"):
        # Mock the get_motor_collection method
        mock_collection = MagicMock()
        mock_cursor = MagicMock()

        # to_list is async in this context
        async def mock_to_list(*args, **kwargs):
            return []

        mock_cursor.to_list = mock_to_list
        mock_collection.aggregate.return_value = mock_cursor

        with patch.object(UserDoc, "get_motor_collection", return_value=mock_collection):
            pipeline = []
            results = await backend.aggregate(pipeline)
            assert len(results) == 0


@pytest.mark.asyncio
async def test_mongo_backend_aggregate_with_complex_pipeline():
    """Test aggregate operation with complex pipeline."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    # Mock the backend with proper model class
    backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc

    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, "initialize"):
        # Mock the get_motor_collection method
        mock_collection = MagicMock()
        mock_cursor = MagicMock()

        # to_list is async in this context
        async def mock_to_list(*args, **kwargs):
            return [{"_id": 25, "count": 2}, {"_id": 30, "count": 1}]

        mock_cursor.to_list = mock_to_list
        mock_collection.aggregate.return_value = mock_cursor

        with patch.object(UserDoc, "get_motor_collection", return_value=mock_collection):
            pipeline = [{"$group": {"_id": "$age", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
            results = await backend.aggregate(pipeline)
            assert len(results) == 2
            assert results[0]["_id"] == 25
            assert results[0]["count"] == 2
            assert results[1]["_id"] == 30
            assert results[1]["count"] == 1


@pytest.mark.asyncio
async def test_mongo_backend_find_with_complex_query():
    """Test find operation with complex query."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    # Mock the backend with proper model class
    backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc

    # Mock the find method to return results
    user1 = create_mock_mongo_user("John", 30, "john@example.com")
    user2 = create_mock_mongo_user("Jane", 25, "jane@example.com")

    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, "initialize"):
        with patch.object(UserDoc, "find") as mock_find:
            mock_cursor = MagicMock()

            # to_list is async in this context
            async def mock_to_list(*args, **kwargs):
                return [user1, user2]

            mock_cursor.to_list = mock_to_list
            mock_find.return_value = mock_cursor

            # Test complex query
            query = {"age": {"$gte": 25}, "name": {"$regex": "^J"}}
            results = await backend.find(query)
            assert len(results) == 2
            assert results[0].name == "John"
            assert results[1].name == "Jane"


@pytest.mark.asyncio
async def test_mongo_backend_find_with_kwargs():
    """Test find operation with kwargs."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    # Mock the backend with proper model class
    backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc

    # Mock the find method to return results
    user = create_mock_mongo_user("John", 30, "john@example.com")

    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, "initialize"):
        with patch.object(UserDoc, "find") as mock_find:
            mock_cursor = MagicMock()

            # to_list is async in this context
            async def mock_to_list(*args, **kwargs):
                return [user]

            mock_cursor.to_list = mock_to_list
            mock_find.return_value = mock_cursor

            # Test with kwargs
            results = await backend.find(name="John", age=30)
            assert len(results) == 1
            assert results[0].name == "John"


@pytest.mark.asyncio
async def test_mongo_backend_all_with_empty_results():
    """Test all operation with empty results."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    # Mock the backend with proper model class
    backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc

    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, "initialize"):
        with patch.object(UserDoc, "find_all") as mock_find_all:
            mock_cursor = MagicMock()

            # Create an async function that returns empty list
            async def mock_to_list(*args, **kwargs):
                return []

            mock_cursor.to_list = mock_to_list
            mock_find_all.return_value = mock_cursor

            results = await backend.all()
            assert len(results) == 0


@pytest.mark.asyncio
async def test_mongo_backend_all_with_multiple_results():
    """Test all operation with multiple results."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    # Mock the backend with proper model class
    backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc

    # Mock the find_all method to return multiple results
    user1 = create_mock_mongo_user("John", 30, "john@example.com")
    user2 = create_mock_mongo_user("Jane", 25, "jane@example.com")
    user3 = create_mock_mongo_user("Bob", 35, "bob@example.com")

    with patch.object(backend, "initialize"):
        with patch.object(UserDoc, "find_all") as mock_find_all:
            mock_cursor = MagicMock()

            # Create an async function that returns multiple results
            async def mock_to_list(*args, **kwargs):
                return [user1, user2, user3]

            mock_cursor.to_list = mock_to_list
            mock_find_all.return_value = mock_cursor

            results = await backend.all()
            assert len(results) == 3
            assert results[0].name == "John"
            assert results[1].name == "Jane"
            assert results[2].name == "Bob"


@pytest.mark.asyncio
async def test_mongo_backend_insert_with_duplicate_key_error():
    """Test MongoDB insert with DuplicateKeyError."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM
    from mindtrace.database.core.exceptions import DuplicateInsertError

    # Mock the backend with proper model class
    backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc

    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, "initialize"):
        # Test insert with DuplicateKeyError
        with patch.object(UserDoc, "insert") as mock_insert:
            from pymongo.errors import DuplicateKeyError

            mock_insert.side_effect = DuplicateKeyError("Duplicate key error")

            user_data = {"name": "John", "age": 30, "email": "john@example.com"}
            user = UserCreate(**user_data)

            # Mock the UserDoc constructor
            mock_doc = MagicMock()
            mock_doc.insert = mock_insert
            with patch.object(UserDoc, "__new__", return_value=mock_doc):
                with pytest.raises(DuplicateInsertError, match="Duplicate key error"):
                    await backend.insert(user)


@pytest.mark.asyncio
async def test_mongo_backend_insert_with_generic_exception():
    """Test MongoDB insert with generic Exception."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM
    from mindtrace.database.core.exceptions import DuplicateInsertError

    # Mock the backend with proper model class
    backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc

    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, "initialize"):
        # Test insert with generic Exception
        with patch.object(UserDoc, "insert") as mock_insert:
            mock_insert.side_effect = Exception("Generic error")

            user_data = {"name": "John", "age": 30, "email": "john@example.com"}
            user = UserCreate(**user_data)

            # Mock the UserDoc constructor
            mock_doc = MagicMock()
            mock_doc.insert = mock_insert
            with patch.object(UserDoc, "__new__", return_value=mock_doc):
                with pytest.raises(DuplicateInsertError, match="Generic error"):
                    await backend.insert(user)


@pytest.mark.asyncio
async def test_mongo_backend_get_with_not_found():
    """Test MongoDB get with document not found."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM
    from mindtrace.database.core.exceptions import DocumentNotFoundError

    # Mock the backend with proper model class
    backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc

    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, "initialize"):
        # Test get with document not found
        with patch.object(UserDoc, "get") as mock_get:
            mock_get.return_value = None

            with pytest.raises(DocumentNotFoundError, match="Object with id test_id not found"):
                await backend.get("test_id")


@pytest.mark.asyncio
async def test_mongo_backend_delete_with_not_found():
    """Test MongoDB delete with document not found."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM
    from mindtrace.database.core.exceptions import DocumentNotFoundError

    # Mock the backend with proper model class
    backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc

    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, "initialize"):
        # Test delete with document not found
        with patch.object(UserDoc, "get") as mock_get:
            mock_get.return_value = None

            with pytest.raises(DocumentNotFoundError, match="Object with id test_id not found"):
                await backend.delete("test_id")


@pytest.mark.asyncio
async def test_mongo_backend_delete_with_document_found():
    """Test MongoDB delete with document found."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    # Mock the backend with proper model class
    backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc

    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, "initialize"):
        # Test delete with document found
        mock_doc = MagicMock()
        mock_doc.delete = AsyncMock()

        with patch.object(UserDoc, "get") as mock_get:
            mock_get.return_value = mock_doc

            # Should not raise exception
            await backend.delete("test_id")
            mock_doc.delete.assert_called_once()


@pytest.mark.asyncio
async def test_mongo_backend_get_raw_model():
    """Test MongoDB get_raw_model method."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    # Mock the backend with proper model class
    backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc

    # Test get_raw_model method
    model_class = backend.get_raw_model()
    assert model_class == UserDoc


async def test_mongo_backend_get_with_none_result():
    """Test MongoDB backend get method with None result."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM
    from mindtrace.database.core.exceptions import DocumentNotFoundError

    # Mock the backend with proper model class
    with patch("mindtrace.database.backends.mongo_odm.AsyncIOMotorClient") as mock_client:
        mock_client_instance = MagicMock()
        mock_client.return_value = mock_client_instance

        backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
        backend.model_cls = UserDoc
        backend.logger = MagicMock()
        backend._is_initialized = True  # Skip initialization

        # Test get with None result
        with patch.object(UserDoc, "get") as mock_get:
            mock_get.return_value = None

            with pytest.raises(DocumentNotFoundError, match="Object with id test_id not found"):
                await backend.get("test_id")


@patch("mindtrace.database.backends.mongo_odm.init_beanie")
@pytest.mark.asyncio
async def test_mongo_backend_initialize_error_handling(mock_init_beanie):
    """Test MongoDB backend initialization error handling."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    mock_init_beanie.side_effect = Exception("Connection failed")

    backend = MongoMindtraceODM(model_cls=UserDoc, db_uri="mongodb://localhost:27017", db_name="test_db")

    with pytest.raises(Exception, match="Connection failed"):
        await backend.initialize()


@patch("mindtrace.database.backends.mongo_odm.init_beanie")
@pytest.mark.asyncio
async def test_mongo_backend_initialize_second_call(mock_init_beanie):
    """Test MongoDB backend initialization when already initialized."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(model_cls=UserDoc, db_uri="mongodb://localhost:27017", db_name="test_db")

    # First initialization
    await backend.initialize()
    assert backend._is_initialized is True
    mock_init_beanie.assert_called_once()

    # Second initialization (should skip init_beanie)
    await backend.initialize()
    # init_beanie should still be called only once
    mock_init_beanie.assert_called_once()


@pytest.mark.asyncio
async def test_mongo_backend_get_with_document_found():
    """Test MongoDB backend get method when document is found."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    with patch("mindtrace.database.backends.mongo_odm.AsyncIOMotorClient") as mock_client:
        mock_client_instance = MagicMock()
        mock_client.return_value = mock_client_instance

        backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
        backend.model_cls = UserDoc
        backend._is_initialized = True  # Skip initialization

        # Test get with document found
        mock_doc = create_mock_mongo_user()
        with patch.object(UserDoc, "get") as mock_get:
            mock_get.return_value = mock_doc

            result = await backend.get("test_id")
            assert result == mock_doc
            assert result.name == "John"


def test_mongo_backend_sync_wrappers_from_sync_context():
    """Test MongoDB sync wrapper methods when called from sync context (covers asyncio.run paths)."""
    from unittest.mock import AsyncMock, patch

    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    with patch("mindtrace.database.backends.mongo_odm.AsyncIOMotorClient"):
        backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
        backend.model_cls = UserDoc

        # Mock the async methods
        mock_user = create_mock_mongo_user()

        with patch.object(backend, "initialize", new_callable=AsyncMock) as mock_init:
            with patch.object(backend, "insert", new_callable=AsyncMock, return_value=mock_user) as mock_insert:
                # Test insert_sync from sync context (no running loop)
                result = backend.insert_sync(UserCreate(name="John", age=30, email="john@example.com"))
                assert result == mock_user
                mock_insert.assert_called_once()

        with patch.object(backend, "initialize", new_callable=AsyncMock):
            with patch.object(backend, "get", new_callable=AsyncMock, return_value=mock_user) as mock_get:
                # Test get_sync from sync context
                result = backend.get_sync("test_id")
                assert result == mock_user
                mock_get.assert_called_once_with("test_id")

        with patch.object(backend, "initialize", new_callable=AsyncMock):
            with patch.object(backend, "delete", new_callable=AsyncMock) as mock_delete:
                # Test delete_sync from sync context
                backend.delete_sync("test_id")
                mock_delete.assert_called_once_with("test_id")

        with patch.object(backend, "initialize", new_callable=AsyncMock):
            with patch.object(backend, "all", new_callable=AsyncMock, return_value=[mock_user]) as mock_all:
                # Test all_sync from sync context
                result = backend.all_sync()
                assert len(result) == 1
                mock_all.assert_called_once()

        with patch.object(backend, "initialize", new_callable=AsyncMock):
            with patch.object(backend, "find", new_callable=AsyncMock, return_value=[mock_user]) as mock_find:
                # Test find_sync from sync context
                result = backend.find_sync({"name": "John"})
                assert len(result) == 1
                mock_find.assert_called_once_with({"name": "John"})

        with patch.object(backend, "initialize", new_callable=AsyncMock) as mock_init:
            # Test initialize_sync from sync context
            backend.initialize_sync()
            mock_init.assert_called_once()


# ============================================================================
# Tests for init_mode and initialization coverage
# ============================================================================


@patch("mindtrace.database.backends.mongo_odm.init_beanie")
def test_mongo_init_mode_sync_in_sync_context(mock_init_beanie):
    """Test MongoDB __init__ with InitMode.SYNC in sync context."""
    import asyncio

    from mindtrace.database.backends.mindtrace_odm import InitMode
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    # Ensure no running loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            pytest.skip("Cannot test sync init in async context")
    except RuntimeError:
        pass

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=True,
        init_mode=InitMode.SYNC,
    )

    # Should be initialized immediately (sync mode in sync context)
    assert backend._is_initialized is True
    mock_init_beanie.assert_called_once()


@patch("mindtrace.database.backends.mongo_odm.init_beanie")
def test_mongo_init_mode_sync_uses_asyncio_run(mock_init_beanie):
    """Test MongoDB __init__ with InitMode.SYNC uses asyncio.run() for sync initialization.

    This test verifies that sync initialization works correctly using asyncio.run()
    instead of manual event loop management. The old code path (get_event_loop/new_event_loop)
    has been replaced with the simpler asyncio.run() approach.
    """
    import asyncio

    from mindtrace.database.backends.mindtrace_odm import InitMode
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    # Ensure no running loop
    try:
        asyncio.get_running_loop()
        pytest.skip("Cannot test sync init in async context")
    except RuntimeError:
        pass

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=True,
        init_mode=InitMode.SYNC,
    )

    # Should be initialized immediately (sync mode in sync context using asyncio.run())
    assert backend._is_initialized is True
    mock_init_beanie.assert_called_once()


@patch("mindtrace.database.backends.mongo_odm.init_beanie")
@pytest.mark.asyncio
async def test_mongo_init_mode_async_in_async_context(mock_init_beanie):
    """Test MongoDB __init__ with InitMode.ASYNC in async context."""
    from mindtrace.database.backends.mindtrace_odm import InitMode
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=True,
        init_mode=InitMode.ASYNC,
    )

    # Should defer initialization (async context)
    assert backend._is_initialized is False
    assert backend._needs_init is True
    mock_init_beanie.assert_not_called()


@patch("mindtrace.database.backends.mongo_odm.init_beanie")
def test_mongo_init_mode_async_in_sync_context(mock_init_beanie):
    """Test MongoDB __init__ with InitMode.ASYNC in sync context."""
    from mindtrace.database.backends.mindtrace_odm import InitMode
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=True,
        init_mode=InitMode.ASYNC,
    )

    # Should defer initialization (ASYNC mode in sync context)
    assert backend._is_initialized is False
    assert backend._needs_init is True
    mock_init_beanie.assert_not_called()


@patch("mindtrace.database.backends.mongo_odm.init_beanie")
@pytest.mark.asyncio
async def test_mongo_initialize_with_allow_index_dropping(mock_init_beanie):
    """Test MongoDB initialize() with allow_index_dropping parameter."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=False,
    )

    # Initialize with allow_index_dropping=True
    await backend.initialize(allow_index_dropping=True)
    assert backend._is_initialized is True
    assert backend._allow_index_dropping is True
    mock_init_beanie.assert_called_once_with(
        database=backend.client["test_db"],
        document_models=[UserDoc],
        allow_index_dropping=True,
    )


@patch("mindtrace.database.backends.mongo_odm.init_beanie")
def test_mongo_initialize_sync_already_initialized(mock_init_beanie):
    """Test MongoDB initialize_sync() when already initialized."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=False,
    )

    # Initialize first
    backend._is_initialized = True
    mock_init_beanie.reset_mock()

    # Call initialize_sync again - should return early
    backend.initialize_sync()
    # Should not call init_beanie again
    mock_init_beanie.assert_not_called()


@pytest.mark.asyncio
async def test_mongo_backend_update_with_document_instance():
    """Test MongoDB update method with document instance."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=False,
    )
    backend._is_initialized = True

    # Create a mock document instance
    mock_doc = MagicMock(spec=UserDoc)
    mock_doc.id = "507f1f77bcf86cd799439011"
    mock_doc.save = AsyncMock(return_value=mock_doc)

    result = await backend.update(mock_doc)

    assert result == mock_doc
    mock_doc.save.assert_called_once()


@pytest.mark.asyncio
async def test_mongo_backend_update_auto_initializes():
    """Test MongoDB update method auto-initializes when not initialized."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=False,
    )
    backend._is_initialized = False

    # Create a mock document instance
    mock_doc = MagicMock(spec=UserDoc)
    mock_doc.id = "507f1f77bcf86cd799439011"
    mock_doc.save = AsyncMock(return_value=mock_doc)

    with patch.object(backend, "initialize", new_callable=AsyncMock) as mock_init:
        result = await backend.update(mock_doc)

        mock_init.assert_called_once()
        assert result == mock_doc
        mock_doc.save.assert_called_once()


@pytest.mark.asyncio
async def test_mongo_backend_update_with_document_instance_no_id():
    """Test MongoDB update method with document instance without id."""
    from mindtrace.database import DocumentNotFoundError
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=False,
    )
    backend._is_initialized = True

    # Create a mock document instance without id
    mock_doc = MagicMock(spec=UserDoc)
    mock_doc.id = None

    with pytest.raises(DocumentNotFoundError, match="Document must have an id to be updated"):
        await backend.update(mock_doc)


@pytest.mark.asyncio
async def test_mongo_backend_insert_with_datawrapper():
    """Test MongoDB insert with DataWrapper object."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM
    from mindtrace.database.backends.unified_odm import DataWrapper

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=False,
    )
    backend._is_initialized = True

    # Create a DataWrapper object
    data_wrapper = DataWrapper({"name": "DataWrapper User", "age": 30, "email": "datawrapper@test.com"})

    # Mock the document creation and insert
    mock_doc = MagicMock(spec=UserDoc)
    mock_doc.id = "507f1f77bcf86cd799439011"
    mock_doc.name = "DataWrapper User"
    mock_doc.age = 30
    mock_doc.email = "datawrapper@test.com"
    mock_doc.insert = AsyncMock(return_value=mock_doc)

    # Mock model_cls as a callable that returns our mock document
    # This bypasses the actual Beanie Document instantiation
    mock_model_cls = MagicMock(return_value=mock_doc)

    with patch.object(backend, "model_cls", new=mock_model_cls):
        result = await backend.insert(data_wrapper)

        # Verify the result
        assert result == mock_doc
        mock_doc.insert.assert_called_once()

        # Verify model_cls was called with the correct data (id/_id should be removed)
        call_kwargs = mock_model_cls.call_args[1] if mock_model_cls.call_args else {}
        assert "id" not in call_kwargs
        assert "_id" not in call_kwargs
        assert call_kwargs.get("name") == "DataWrapper User"
        assert call_kwargs.get("age") == 30
        assert call_kwargs.get("email") == "datawrapper@test.com"


@pytest.mark.asyncio
async def test_mongo_backend_insert_with_dict_containing_id():
    """Test MongoDB insert with dict containing id/_id fields."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=False,
    )
    backend._is_initialized = True

    # Create a dict with id and _id (should be removed)
    user_data = {
        "name": "Dict User",
        "age": 25,
        "email": "dict@test.com",
        "id": "should_be_removed",
        "_id": "should_be_removed_too",
    }

    # Mock the insert operation
    mock_doc = MagicMock(spec=UserDoc)
    mock_doc.id = None  # Should be set to None
    mock_doc.insert = AsyncMock(return_value=mock_doc)

    # Track what kwargs were passed to model_cls instantiation
    call_kwargs = {}

    def mock_model_init(*args, **kwargs):
        call_kwargs.update(kwargs)
        return mock_doc

    # Mock model_cls as a callable that returns our mock document
    mock_model_cls = MagicMock(side_effect=mock_model_init)

    with patch.object(backend, "model_cls", new=mock_model_cls):
        result = await backend.insert(user_data)

        # Verify the result
        assert result == mock_doc
        mock_doc.insert.assert_called_once()

        # Verify that id and _id were removed from the data passed to model_cls
        assert "id" not in call_kwargs
        assert "_id" not in call_kwargs
        assert call_kwargs.get("name") == "Dict User"
        assert call_kwargs.get("age") == 25
        assert call_kwargs.get("email") == "dict@test.com"


@pytest.mark.asyncio
async def test_mongo_backend_update_with_basemodel():
    """Test MongoDB update method with BaseModel."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=False,
    )
    backend._is_initialized = True

    # Create a BaseModel instance
    user_data = UserCreate(name="John Updated", age=31, email="john@example.com")
    object.__setattr__(user_data, "id", "507f1f77bcf86cd799439011")

    # Mock the get method
    mock_doc = MagicMock(spec=UserDoc)
    mock_doc.save = AsyncMock(return_value=mock_doc)
    mock_doc.model_dump = MagicMock(return_value={"name": "John Updated", "age": 31, "email": "john@example.com"})

    with patch.object(backend.model_cls, "get", new_callable=AsyncMock, return_value=mock_doc):
        result = await backend.update(user_data)

        assert result == mock_doc
        backend.model_cls.get.assert_called_once_with("507f1f77bcf86cd799439011")
        mock_doc.save.assert_called_once()


@pytest.mark.asyncio
async def test_mongo_backend_update_with_basemodel_no_id():
    """Test MongoDB update method with BaseModel without id."""
    from mindtrace.database import DocumentNotFoundError
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=False,
    )
    backend._is_initialized = True

    # Create a BaseModel instance without id
    user_data = UserCreate(name="John Updated", age=31, email="john@example.com")

    with pytest.raises(DocumentNotFoundError, match="Document must have an id to be updated"):
        await backend.update(user_data)


@pytest.mark.asyncio
async def test_mongo_backend_update_with_basemodel_not_found():
    """Test MongoDB update method with BaseModel when document not found."""
    from mindtrace.database import DocumentNotFoundError
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=False,
    )
    backend._is_initialized = True

    # Create a BaseModel instance
    user_data = UserCreate(name="John Updated", age=31, email="john@example.com")
    object.__setattr__(user_data, "id", "507f1f77bcf86cd799439011")

    # Mock the get method to return None
    with patch.object(backend.model_cls, "get", new_callable=AsyncMock, return_value=None):
        with pytest.raises(DocumentNotFoundError, match="Object with id 507f1f77bcf86cd799439011 not found"):
            await backend.update(user_data)


def test_mongo_backend_update_sync():
    """Test MongoDB update_sync method."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=False,
    )
    backend._is_initialized = True

    # Create a mock document instance
    mock_doc = MagicMock(spec=UserDoc)
    mock_doc.id = "507f1f77bcf86cd799439011"
    mock_doc.save = AsyncMock(return_value=mock_doc)

    async def mock_update(obj):
        return mock_doc

    with patch.object(backend, "update", side_effect=mock_update):
        with patch("asyncio.run", return_value=mock_doc) as mock_run:
            result = backend.update_sync(mock_doc)

            mock_run.assert_called_once()
            assert result == mock_doc


def test_mongo_backend_update_sync_from_async_context():
    """Test MongoDB update_sync method from async context raises error."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=False,
    )
    backend._is_initialized = True

    # Create a mock document instance
    mock_doc = MagicMock(spec=UserDoc)
    mock_doc.id = "507f1f77bcf86cd799439011"

    # Mock asyncio.get_running_loop to raise RuntimeError with "no running event loop"
    with patch("asyncio.get_running_loop", side_effect=RuntimeError("no running event loop")):
        with patch("asyncio.run") as mock_run:
            with patch.object(backend, "update", new_callable=AsyncMock, return_value=mock_doc):
                # Should not raise, but use asyncio.run
                backend.update_sync(mock_doc)
                mock_run.assert_called_once()


def test_mongo_backend_update_sync_from_async_context_raises_error():
    """Test MongoDB update_sync method from async context raises RuntimeError."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(
        model_cls=UserDoc,
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        auto_init=False,
    )
    backend._is_initialized = True

    # Create a mock document instance
    mock_doc = MagicMock(spec=UserDoc)
    mock_doc.id = "507f1f77bcf86cd799439011"

    # Mock asyncio.get_running_loop to return a loop (simulating async context)
    mock_loop = MagicMock()
    with patch("asyncio.get_running_loop", return_value=mock_loop):
        with pytest.raises(RuntimeError, match="update_sync\\(\\) called from async context"):
            backend.update_sync(mock_doc)


def test_mindtrace_database_unknown_attribute_raises():
    """``__getattr__`` fallback raises for unknown exports (covers ``__init__.py``)."""
    import mindtrace.database as md

    with pytest.raises(AttributeError, match="has no attribute"):
        getattr(md, "NotARealExport999")


@patch("mindtrace.database.backends.mongo_odm.init_beanie")
@pytest.mark.asyncio
async def test_second_odm_same_model_uses_motor_routing_and_single_init_beanie(mock_init_beanie):
    """Only the first ``MongoMindtraceODM`` per ``model_cls`` calls ``init_beanie``; the second uses Motor."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    b1 = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "db1")
    await b1.initialize()
    assert b1._motor_routing is False
    mock_init_beanie.assert_called_once()

    b2 = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "db2")
    await b2.initialize()
    assert b2._motor_routing is True
    mock_init_beanie.assert_called_once()


def test_mongo_odm_helpers_and_to_object_id():
    """Cover static helpers and ``_mongo_doc_to_model`` edge cases."""
    from beanie import PydanticObjectId

    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
    backend._is_initialized = True

    oid = ObjectId()
    assert MongoMindtraceODM._to_object_id(oid) is oid
    pid = PydanticObjectId()
    assert MongoMindtraceODM._to_object_id(pid) == ObjectId(str(pid))
    assert MongoMindtraceODM._to_object_id(str(oid)) == oid

    from mindtrace.database import DocumentNotFoundError

    with pytest.raises(DocumentNotFoundError, match="Invalid document id"):
        MongoMindtraceODM._to_object_id("not-a-valid-object-id")

    assert backend._mongo_doc_to_model(None) is None


@pytest.mark.asyncio
async def test_motor_insert_non_beanie_model_uses_model_dump_and_motor_collection():
    """Motor insert path for plain ``BaseModel`` uses ``model_dump`` + Motor ``insert_one`` / ``find_one``."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    backend._is_initialized = True
    backend._motor_routing = True

    oid = ObjectId()
    stored = {"_id": oid, "name": "A", "age": 1, "email": "a@b.com"}

    mock_coll = MagicMock()
    mock_coll.insert_one = AsyncMock(return_value=MagicMock(inserted_id=oid))
    mock_coll.find_one = AsyncMock(return_value=stored)

    user_in = UserCreate(name="A", age=1, email="a@b.com")

    with patch.object(backend, "_motor_collection", return_value=mock_coll):
        out = await backend.insert(user_in)
        assert out.name == "A"
        assert str(out.id) == str(oid)


def test_motor_patch_fields_basemodel():
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    u = UserCreate(name="U", age=1, email="e@e.com")
    object.__setattr__(u, "id", "507f1f77bcf86cd799439011")
    pm = backend._motor_patch_fields(u)
    assert "id" not in pm
    assert pm["name"] == "U"


def test_motor_model_dump_delegates_get_dict_for_document():
    """``isinstance(..., Document)`` selects ``get_dict``; covered without a live Beanie collection."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(UserDoc, "mongodb://localhost:27017", "test_db")
    fake_doc = MagicMock()
    fake_doc.get_settings.return_value.keep_nulls = True

    real_isinstance = builtins.isinstance

    def fake_isinstance(obj, cls):
        if obj is fake_doc and cls is BeanieDocument:
            return True
        return real_isinstance(obj, cls)

    with patch("builtins.isinstance", fake_isinstance):
        with patch("mindtrace.database.backends.mongo_odm.get_dict", return_value={"name": "Z"}) as mock_get_dict:
            dumped = backend._motor_model_dump(fake_doc)
            assert dumped == {"name": "Z"}
            mock_get_dict.assert_called_once_with(fake_doc, to_db=True, keep_nulls=True)


def test_motor_patch_fields_document_branch():
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    fake_doc = MagicMock()
    fake_doc.model_fields = {"name": None, "age": None, "email": None, "id": None}
    fake_doc.name = "N"
    fake_doc.age = 3
    fake_doc.email = "e@e.com"
    fake_doc.id = "507f1f77bcf86cd799439011"

    real_isinstance = builtins.isinstance

    def fake_isinstance(obj, cls):
        if obj is fake_doc and cls is BeanieDocument:
            return True
        return real_isinstance(obj, cls)

    with patch("builtins.isinstance", fake_isinstance):
        patch_map = backend._motor_patch_fields(fake_doc)
        assert "id" not in patch_map
        assert patch_map["name"] == "N"


@pytest.mark.asyncio
async def test_motor_insert_inserted_none_raises_duplicate_insert_error():
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM
    from mindtrace.database.core.exceptions import DuplicateInsertError

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    backend._is_initialized = True
    backend._motor_routing = True

    oid = ObjectId()
    mock_coll = MagicMock()
    mock_coll.insert_one = AsyncMock(return_value=MagicMock(inserted_id=oid))
    mock_coll.find_one = AsyncMock(return_value=None)

    with patch.object(backend, "_motor_collection", return_value=mock_coll):
        with pytest.raises(DuplicateInsertError, match="did not persist"):
            await backend.insert(UserCreate(name="A", age=1, email="x@y.com"))


@pytest.mark.asyncio
async def test_motor_insert_mongo_doc_to_model_none_raises():
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM
    from mindtrace.database.core.exceptions import DuplicateInsertError

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    backend._is_initialized = True
    backend._motor_routing = True

    oid = ObjectId()
    mock_coll = MagicMock()
    mock_coll.insert_one = AsyncMock(return_value=MagicMock(inserted_id=oid))
    mock_coll.find_one = AsyncMock(return_value={"_id": oid, "name": "A", "age": 1, "email": "x@y.com"})

    with patch.object(backend, "_motor_collection", return_value=mock_coll):
        with patch.object(backend, "_mongo_doc_to_model", return_value=None):
            with pytest.raises(DuplicateInsertError, match="Could not deserialize"):
                await backend.insert(UserCreate(name="A", age=1, email="x@y.com"))


@pytest.mark.asyncio
async def test_motor_get_find_delete_all_aggregate():
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    backend._is_initialized = True
    backend._motor_routing = True

    oid = ObjectId()
    row = {"_id": oid, "name": "A", "age": 1, "email": "a@b.com"}

    mock_coll = MagicMock()
    mock_coll.find_one = AsyncMock(return_value=row)
    mock_coll.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[row])))
    mock_coll.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    mock_agg = MagicMock()
    mock_agg.to_list = AsyncMock(return_value=[{"_id": 1}])
    mock_coll.aggregate = MagicMock(return_value=mock_agg)

    with patch.object(backend, "_motor_collection", return_value=mock_coll):
        got = await backend.get(str(oid))
        assert got.email == "a@b.com"

        all_rows = await backend.all()
        assert len(all_rows) == 1

        found = await backend.find({"name": "A"})
        assert len(found) == 1

        agg = await backend.aggregate([{"$group": {"_id": "$name"}}])
        assert agg == [{"_id": 1}]

    mock_coll = MagicMock()
    mock_coll.find_one = AsyncMock(return_value=None)
    with patch.object(backend, "_motor_collection", return_value=mock_coll):
        from mindtrace.database import DocumentNotFoundError

        with pytest.raises(DocumentNotFoundError):
            await backend.get(str(oid))

    mock_coll = MagicMock()
    mock_coll.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))
    with patch.object(backend, "_motor_collection", return_value=mock_coll):
        with pytest.raises(DocumentNotFoundError):
            await backend.delete(str(oid))


@pytest.mark.asyncio
async def test_motor_get_fetch_links_not_implemented():
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    backend._is_initialized = True
    backend._motor_routing = True

    with pytest.raises(NotImplementedError, match="fetch_links"):
        await backend.get("507f1f77bcf86cd799439011", fetch_links=True)


@pytest.mark.asyncio
async def test_motor_find_not_implemented_for_expression_query():
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    backend._is_initialized = True
    backend._motor_routing = True

    with pytest.raises(NotImplementedError, match="single dict filter"):
        await backend.find({"name": "x"}, skip=1)

    with pytest.raises(NotImplementedError, match="fetch_links"):
        await backend.find({"name": "x"}, fetch_links=True)


@pytest.mark.asyncio
async def test_motor_update_document_and_basemodel_merge():
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    backend._is_initialized = True
    backend._motor_routing = True

    oid = ObjectId()
    existing = {"_id": oid, "name": "A", "age": 1, "email": "a@b.com"}
    mock_coll = MagicMock()
    mock_coll.replace_one = AsyncMock()

    doc = MotorDoc(name="A", age=1, email="a@b.com", id=str(oid))

    with patch.object(backend, "_motor_collection", return_value=mock_coll):
        with patch.object(backend, "_motor_model_dump", return_value=dict(existing)):
            out = await backend.update(doc)
            assert out.id == str(oid)
            mock_coll.replace_one.assert_awaited()

    mock_coll = MagicMock()
    mock_coll.find_one = AsyncMock(return_value=existing)
    mock_coll.replace_one = AsyncMock()
    patch_obj = UserCreate(name="B", age=2, email="b@b.com")
    object.__setattr__(patch_obj, "id", str(oid))

    with patch.object(backend, "_motor_collection", return_value=mock_coll):
        with patch.object(
            backend, "_mongo_doc_to_model", return_value=MotorDoc(name="A", age=1, email="a@b.com", id=str(oid))
        ):
            with patch.object(backend, "_motor_model_dump", return_value=dict(existing)):
                out = await backend.update(patch_obj)
                assert out.name == "B"
                mock_coll.replace_one.assert_awaited()


@pytest.mark.asyncio
async def test_motor_update_basemodel_existing_not_found():
    from mindtrace.database import DocumentNotFoundError
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    backend._is_initialized = True
    backend._motor_routing = True

    oid = ObjectId()
    patch_obj = UserCreate(name="B", age=2, email="b@b.com")
    object.__setattr__(patch_obj, "id", str(oid))

    mock_coll = MagicMock()
    mock_coll.find_one = AsyncMock(return_value=None)

    with patch.object(backend, "_motor_collection", return_value=mock_coll):
        with pytest.raises(DocumentNotFoundError):
            await backend.update(patch_obj)


@pytest.mark.asyncio
async def test_motor_get_mongo_doc_to_model_returns_none_raises():
    from mindtrace.database import DocumentNotFoundError
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    backend._is_initialized = True
    backend._motor_routing = True

    oid = ObjectId()
    mock_coll = MagicMock()
    mock_coll.find_one = AsyncMock(return_value={"_id": oid})

    with patch.object(backend, "_motor_collection", return_value=mock_coll):
        with patch.object(backend, "_mongo_doc_to_model", return_value=None):
            with pytest.raises(DocumentNotFoundError, match="not found"):
                await backend.get(str(oid))


def test_multi_model_parent_collection_name_and_motor_collection():
    """Parent ODM in multi-model mode has ``model_cls is None`` for internal helpers."""
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    parent = MongoMindtraceODM(models={"u": UserDoc}, db_uri="mongodb://localhost:27017", db_name="test_db")
    with pytest.raises(ValueError, match="model_cls is required"):
        parent._collection_name()

    leaf = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    mc = leaf._motor_collection()
    assert mc is not None


@pytest.mark.asyncio
async def test_motor_update_document_without_id_raises():
    from mindtrace.database import DocumentNotFoundError
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    backend._is_initialized = True
    backend._motor_routing = True

    doc = MotorDoc(name="A", age=1, email="a@a.com", id=None)
    with pytest.raises(DocumentNotFoundError, match="must have an id"):
        await backend.update(doc)


@pytest.mark.asyncio
async def test_motor_update_merge_missing_id_on_patch_object_raises():
    from mindtrace.database import DocumentNotFoundError
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    backend._is_initialized = True
    backend._motor_routing = True

    with pytest.raises(DocumentNotFoundError, match="must have an id"):
        await backend.update(UserCreate(name="A", age=1, email="a@a.com"))


@pytest.mark.asyncio
async def test_motor_update_merge_existing_not_found_raises():
    from mindtrace.database import DocumentNotFoundError
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    backend._is_initialized = True
    backend._motor_routing = True

    patch_obj = UserCreate(name="B", age=2, email="b@b.com")
    object.__setattr__(patch_obj, "id", "507f1f77bcf86cd799439011")

    mock_coll = MagicMock()
    mock_coll.find_one = AsyncMock(return_value=None)

    with patch.object(backend, "_motor_collection", return_value=mock_coll):
        with pytest.raises(DocumentNotFoundError, match="not found"):
            await backend.update(patch_obj)


@pytest.mark.asyncio
async def test_motor_update_merge_mongo_doc_to_model_none_raises():
    from mindtrace.database import DocumentNotFoundError
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    backend._is_initialized = True
    backend._motor_routing = True

    oid = ObjectId()
    patch_obj = UserCreate(name="B", age=2, email="b@b.com")
    object.__setattr__(patch_obj, "id", str(oid))

    mock_coll = MagicMock()
    mock_coll.find_one = AsyncMock(return_value={"_id": oid})

    with patch.object(backend, "_motor_collection", return_value=mock_coll):
        with patch.object(backend, "_mongo_doc_to_model", return_value=None):
            with pytest.raises(DocumentNotFoundError, match="not found"):
                await backend.update(patch_obj)


@pytest.mark.asyncio
async def test_motor_delete_deleted_count_zero_raises():
    from mindtrace.database import DocumentNotFoundError
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    backend._is_initialized = True
    backend._motor_routing = True

    class _DelResult:
        deleted_count = 0

    mock_coll = MagicMock()
    mock_coll.delete_one = AsyncMock(return_value=_DelResult())

    with patch.object(backend, "_motor_collection", return_value=mock_coll):
        with pytest.raises(DocumentNotFoundError, match="not found"):
            await backend.delete("507f1f77bcf86cd799439011")


@pytest.mark.asyncio
async def test_motor_delete_success_returns_none():
    from mindtrace.database.backends.mongo_odm import MongoMindtraceODM

    backend = MongoMindtraceODM(MotorDoc, "mongodb://localhost:27017", "test_db")
    backend._is_initialized = True
    backend._motor_routing = True

    class _DelResult:
        deleted_count = 1

    mock_coll = MagicMock()
    mock_coll.delete_one = AsyncMock(return_value=_DelResult())

    with patch.object(backend, "_motor_collection", return_value=mock_coll):
        assert await backend.delete("507f1f77bcf86cd799439011") is None
