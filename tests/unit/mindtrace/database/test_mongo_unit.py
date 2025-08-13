from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from mindtrace.database import MindtraceDocument


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


# Fix the failing test cases
@pytest.mark.asyncio
async def test_mongo_backend_is_async():
    """Test that MongoDB backend is async."""
    from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
    
    backend = MongoMindtraceODMBackend(UserDoc, "mongodb://localhost:27017", "test_db")
    assert backend.is_async() is True


@pytest.mark.asyncio
async def test_mongo_backend_aggregate():
    """Test aggregate operation."""
    from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
    
    # Mock the backend with proper model class
    backend = MongoMindtraceODMBackend(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc
    
    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, 'initialize') as mock_init:
        # Mock the get_motor_collection method
        mock_collection = MagicMock()
        mock_cursor = MagicMock()
        # to_list is async in this context
        async def mock_to_list(*args, **kwargs):
            return [{"_id": 25, "count": 2}]
        mock_cursor.to_list = mock_to_list
        mock_collection.aggregate.return_value = mock_cursor
        
        with patch.object(UserDoc, 'get_motor_collection', return_value=mock_collection):
            pipeline = [{"$group": {"_id": "$age", "count": {"$sum": 1}}}]
            results = await backend.aggregate(pipeline)
            assert len(results) == 1
            assert results[0]["_id"] == 25
            assert results[0]["count"] == 2


@pytest.mark.asyncio
async def test_mongo_backend_aggregate_with_empty_pipeline():
    """Test aggregate operation with empty pipeline."""
    from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
    
    # Mock the backend with proper model class
    backend = MongoMindtraceODMBackend(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc
    
    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, 'initialize') as mock_init:
        # Mock the get_motor_collection method
        mock_collection = MagicMock()
        mock_cursor = MagicMock()
        # to_list is async in this context
        async def mock_to_list(*args, **kwargs):
            return []
        mock_cursor.to_list = mock_to_list
        mock_collection.aggregate.return_value = mock_cursor
        
        with patch.object(UserDoc, 'get_motor_collection', return_value=mock_collection):
            pipeline = []
            results = await backend.aggregate(pipeline)
            assert len(results) == 0


@pytest.mark.asyncio
async def test_mongo_backend_aggregate_with_complex_pipeline():
    """Test aggregate operation with complex pipeline."""
    from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
    
    # Mock the backend with proper model class
    backend = MongoMindtraceODMBackend(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc
    
    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, 'initialize') as mock_init:
        # Mock the get_motor_collection method
        mock_collection = MagicMock()
        mock_cursor = MagicMock()
        # to_list is async in this context
        async def mock_to_list(*args, **kwargs):
            return [
                {"_id": 25, "count": 2},
                {"_id": 30, "count": 1}
            ]
        mock_cursor.to_list = mock_to_list
        mock_collection.aggregate.return_value = mock_cursor
        
        with patch.object(UserDoc, 'get_motor_collection', return_value=mock_collection):
            pipeline = [
                {"$group": {"_id": "$age", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            results = await backend.aggregate(pipeline)
            assert len(results) == 2
            assert results[0]["_id"] == 25
            assert results[0]["count"] == 2
            assert results[1]["_id"] == 30
            assert results[1]["count"] == 1


@pytest.mark.asyncio
async def test_mongo_backend_find_with_complex_query():
    """Test find operation with complex query."""
    from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
    
    # Mock the backend with proper model class
    backend = MongoMindtraceODMBackend(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc
    
    # Mock the find method to return results
    user1 = create_mock_mongo_user("John", 30, "john@example.com")
    user2 = create_mock_mongo_user("Jane", 25, "jane@example.com")
    
    with patch.object(UserDoc, 'find') as mock_find:
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
    from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
    
    # Mock the backend with proper model class
    backend = MongoMindtraceODMBackend(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc
    
    # Mock the find method to return results
    user = create_mock_mongo_user("John", 30, "john@example.com")
    
    with patch.object(UserDoc, 'find') as mock_find:
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
    from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
    
    # Mock the backend with proper model class
    backend = MongoMindtraceODMBackend(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc
    
    # Mock the find_all method to return empty results
    with patch.object(UserDoc, 'find_all') as mock_find_all:
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
    from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
    
    # Mock the backend with proper model class
    backend = MongoMindtraceODMBackend(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc
    
    # Mock the find_all method to return multiple results
    user1 = create_mock_mongo_user("John", 30, "john@example.com")
    user2 = create_mock_mongo_user("Jane", 25, "jane@example.com")
    user3 = create_mock_mongo_user("Bob", 35, "bob@example.com")
    
    with patch.object(UserDoc, 'find_all') as mock_find_all:
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

# Add comprehensive test cases to cover missing lines
@pytest.mark.asyncio
async def test_mongo_backend_insert_with_duplicate_key_error():
    """Test MongoDB insert with DuplicateKeyError."""
    from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
    from mindtrace.database.core.exceptions import DuplicateInsertError
    
    # Mock the backend with proper model class
    backend = MongoMindtraceODMBackend(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc
    
    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, 'initialize') as mock_init:
        # Test insert with DuplicateKeyError
        with patch.object(UserDoc, 'insert') as mock_insert:
            from pymongo.errors import DuplicateKeyError
            mock_insert.side_effect = DuplicateKeyError("Duplicate key error")
            
            user_data = {"name": "John", "age": 30, "email": "john@example.com"}
            user = UserCreate(**user_data)
            
            # Mock the UserDoc constructor
            mock_doc = MagicMock()
            mock_doc.insert = mock_insert
            with patch.object(UserDoc, '__new__', return_value=mock_doc):
                with pytest.raises(DuplicateInsertError, match="Duplicate key error"):
                    await backend.insert(user)


@pytest.mark.asyncio
async def test_mongo_backend_insert_with_generic_exception():
    """Test MongoDB insert with generic Exception."""
    from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
    from mindtrace.database.core.exceptions import DuplicateInsertError
    
    # Mock the backend with proper model class
    backend = MongoMindtraceODMBackend(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc
    
    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, 'initialize') as mock_init:
        # Test insert with generic Exception
        with patch.object(UserDoc, 'insert') as mock_insert:
            mock_insert.side_effect = Exception("Generic error")
            
            user_data = {"name": "John", "age": 30, "email": "john@example.com"}
            user = UserCreate(**user_data)
            
            # Mock the UserDoc constructor
            mock_doc = MagicMock()
            mock_doc.insert = mock_insert
            with patch.object(UserDoc, '__new__', return_value=mock_doc):
                with pytest.raises(DuplicateInsertError, match="Generic error"):
                    await backend.insert(user)


@pytest.mark.asyncio
async def test_mongo_backend_get_with_not_found():
    """Test MongoDB get with document not found."""
    from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
    from mindtrace.database.core.exceptions import DocumentNotFoundError
    
    # Mock the backend with proper model class
    backend = MongoMindtraceODMBackend(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc
    
    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, 'initialize') as mock_init:
        # Test get with document not found
        with patch.object(UserDoc, 'get') as mock_get:
            mock_get.return_value = None
            
            with pytest.raises(DocumentNotFoundError, match="Object with id test_id not found"):
                await backend.get("test_id")


@pytest.mark.asyncio
async def test_mongo_backend_delete_with_not_found():
    """Test MongoDB delete with document not found."""
    from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
    from mindtrace.database.core.exceptions import DocumentNotFoundError
    
    # Mock the backend with proper model class
    backend = MongoMindtraceODMBackend(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc
    
    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, 'initialize') as mock_init:
        # Test delete with document not found
        with patch.object(UserDoc, 'get') as mock_get:
            mock_get.return_value = None
            
            with pytest.raises(DocumentNotFoundError, match="Object with id test_id not found"):
                await backend.delete("test_id")


@pytest.mark.asyncio
async def test_mongo_backend_delete_with_document_found():
    """Test MongoDB delete with document found."""
    from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
    
    # Mock the backend with proper model class
    backend = MongoMindtraceODMBackend(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc
    
    # Mock the initialize method to avoid actual MongoDB connections
    with patch.object(backend, 'initialize') as mock_init:
        # Test delete with document found
        mock_doc = MagicMock()
        mock_doc.delete = AsyncMock()
        
        with patch.object(UserDoc, 'get') as mock_get:
            mock_get.return_value = mock_doc
            
            # Should not raise exception
            await backend.delete("test_id")
            mock_doc.delete.assert_called_once()


@pytest.mark.asyncio
async def test_mongo_backend_get_raw_model():
    """Test MongoDB get_raw_model method."""
    from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
    
    # Mock the backend with proper model class
    backend = MongoMindtraceODMBackend(UserDoc, "mongodb://localhost:27017", "test_db")
    backend.model_cls = UserDoc
    
    # Test get_raw_model method
    model_class = backend.get_raw_model()
    assert model_class == UserDoc


async def test_mongo_backend_get_with_none_result():
    """Test MongoDB backend get method with None result."""
    from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
    from mindtrace.database.core.exceptions import DocumentNotFoundError
    
    # Mock the backend with proper model class
    with patch('mindtrace.database.backends.mongo_odm_backend.AsyncIOMotorClient') as mock_client:
        mock_client_instance = MagicMock()
        mock_client.return_value = mock_client_instance
        
        backend = MongoMindtraceODMBackend(UserDoc, "mongodb://localhost:27017", "test_db")
        backend.model_cls = UserDoc
        backend.logger = MagicMock()
        backend._is_initialized = True  # Skip initialization
        
        # Test get with None result
        with patch.object(UserDoc, 'get') as mock_get:
            mock_get.return_value = None
            
            with pytest.raises(DocumentNotFoundError, match="Object with id test_id not found"):
                await backend.get("test_id")
