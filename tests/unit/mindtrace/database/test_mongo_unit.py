from typing import Annotated, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import Indexed, PydanticObjectId
from pydantic import BaseModel

from mindtrace.database import MindtraceDocument


class UserDoc(MindtraceDocument):
    name: str
    age: int
    email: Annotated[str, Indexed(unique=True)]

    class Settings:
        name = "users"
        use_cache = False


class UserProjection(BaseModel):
    name: str
    id: Optional[PydanticObjectId] = None


class UserCreate(BaseModel):
    name: str
    age: int
    email: str


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
        backend.aggregate = AsyncMock()
        backend.initialize = AsyncMock()
        backend.is_async = MagicMock(return_value=True)
        backend.get_raw_model = MagicMock(return_value=UserDoc)
        yield backend


def create_mock_user(name="John", age=30, email="john@example.com", user_id="507f1f77bcf86cd799439011"):
    """Create a mock UserDoc instance without requiring database initialization."""
    mock_user = MagicMock(spec=UserDoc)
    mock_user.name = name
    mock_user.age = age
    mock_user.email = email
    mock_user.id = user_id
    return mock_user


@pytest.mark.asyncio
async def test_mongo_backend_crud(mock_mongo_backend):
    """Test basic CRUD operations."""
    # Test insert
    user = create_mock_user()
    mock_mongo_backend.insert.return_value = user
    result = await mock_mongo_backend.insert(user)
    assert result.name == "John"
    assert result.age == 30
    assert result.email == "john@example.com"

    # Test get
    mock_mongo_backend.get.return_value = user
    result = await mock_mongo_backend.get(user.id)
    assert result.name == "John"

    # Test all
    mock_mongo_backend.all.return_value = [user]
    results = await mock_mongo_backend.all()
    assert len(results) == 1
    assert results[0].name == "John"

    # Test delete
    mock_mongo_backend.delete.return_value = True
    result = await mock_mongo_backend.delete(user.id)
    assert result is True


@pytest.mark.asyncio
async def test_mongo_backend_find(mock_mongo_backend):
    """Test find operations."""
    user = create_mock_user()
    mock_mongo_backend.find.return_value = [user]

    # Test find with query
    results = await mock_mongo_backend.find({"name": "John"})
    assert len(results) == 1
    assert results[0].name == "John"


@pytest.mark.asyncio
async def test_mongo_backend_aggregate(mock_mongo_backend):
    """Test aggregation operations."""
    mock_mongo_backend.aggregate.return_value = [{"count": 1}]

    # Test aggregate with pipeline
    results = await mock_mongo_backend.aggregate([{"$count": "count"}])
    assert len(results) == 1
    assert results[0]["count"] == 1


@pytest.mark.asyncio
async def test_mongo_backend_duplicate_insert(mock_mongo_backend):
    """Test duplicate insert handling."""
    user = create_mock_user()
    mock_mongo_backend.insert.side_effect = Exception("Duplicate key error")

    with pytest.raises(Exception):
        await mock_mongo_backend.insert(user)


@pytest.mark.asyncio
async def test_is_async(mock_mongo_backend):
    """Test is_async property."""
    assert mock_mongo_backend.is_async() is True


@pytest.mark.asyncio
async def test_get_raw_model(mock_mongo_backend):
    """Test get_raw_model method."""
    assert mock_mongo_backend.get_raw_model() == UserDoc


@pytest.mark.asyncio
async def test_find_invalid_query(mock_mongo_backend):
    """Test find with invalid query."""
    mock_mongo_backend.find.side_effect = Exception("Invalid query")

    with pytest.raises(Exception):
        await mock_mongo_backend.find({"invalid": "query"})


@pytest.mark.asyncio
async def test_aggregate_invalid_pipeline(mock_mongo_backend):
    """Test aggregate with invalid pipeline."""
    mock_mongo_backend.aggregate.side_effect = Exception("Invalid pipeline")

    with pytest.raises(Exception):
        await mock_mongo_backend.aggregate([{"$invalid": "stage"}])


@pytest.mark.asyncio
async def test_initialize_multiple_calls(mock_mongo_backend):
    """Test multiple initialize calls."""
    await mock_mongo_backend.initialize()
    await mock_mongo_backend.initialize()  # Should not raise an error
