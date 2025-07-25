from typing import List
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from mindtrace.database import MindtraceRedisDocument


class UserCreate(BaseModel):
    name: str
    age: int
    email: str

class UserDoc(MindtraceRedisDocument):
    name: str = Field(index=True)
    age: int = Field(index=True)
    email: str = Field(index=True)
    skills: List[str] = Field(index=True, default_factory=list)

    class Meta:
        global_key_prefix = "mindtrace"

@pytest.fixture
def mock_redis_backend():
    """Create a mocked Redis backend."""
    with patch('mindtrace.database.MindtraceRedisDocument') as mock_backend:
        backend = mock_backend.return_value
        backend.insert = MagicMock()
        backend.get = MagicMock()
        backend.all = MagicMock()
        backend.delete = MagicMock()
        backend.find = MagicMock()
        backend.initialize = MagicMock()
        backend.is_async = MagicMock(return_value=False)
        backend.get_raw_model = MagicMock(return_value=UserDoc)
        backend.redis = MagicMock()
        yield backend

def create_mock_redis_user(name="John", age=30, email="john@example.com", pk="01H0000000000000000000"):
    """Create a mock UserDoc instance without requiring Redis connection."""
    mock_user = MagicMock(spec=UserDoc)
    mock_user.name = name
    mock_user.age = age
    mock_user.email = email
    mock_user.pk = pk
    mock_user.skills = []
    return mock_user

def test_redis_backend_crud(mock_redis_backend):
    """Test basic CRUD operations."""
    # Test insert
    user = create_mock_redis_user()
    mock_redis_backend.insert.return_value = user
    result = mock_redis_backend.insert(user)
    assert result.name == "John"
    assert result.age == 30
    assert result.email == "john@example.com"

    # Test get
    mock_redis_backend.get.return_value = user
    result = mock_redis_backend.get(user.pk)
    assert result.name == "John"

    # Test all
    mock_redis_backend.all.return_value = [user]
    results = mock_redis_backend.all()
    assert len(results) == 1
    assert results[0].name == "John"

    # Test delete
    mock_redis_backend.delete.return_value = True
    result = mock_redis_backend.delete(user.pk)
    assert result is True

def test_redis_backend_duplicate_insert(mock_redis_backend):
    """Test duplicate insert handling."""
    user = create_mock_redis_user()
    mock_redis_backend.insert.side_effect = Exception("Duplicate key error")
    
    with pytest.raises(Exception):
        mock_redis_backend.insert(user)

def test_redis_backend_find(mock_redis_backend):
    """Test find operations."""
    user = create_mock_redis_user()
    mock_redis_backend.find.return_value = [user]
    
    # Test find with query
    results = mock_redis_backend.find({"name": "John"})
    assert len(results) == 1
    assert results[0].name == "John"

def test_redis_backend_nonexistent_id(mock_redis_backend):
    """Test get with non-existent ID."""
    mock_redis_backend.get.return_value = None
    
    result = mock_redis_backend.get("nonexistent_id")
    assert result is None

def test_redis_backend_initialize(mock_redis_backend):
    """Test initialize method."""
    mock_redis_backend.initialize()
    mock_redis_backend.initialize.assert_called_once()

def test_redis_backend_is_async(mock_redis_backend):
    """Test is_async property."""
    assert mock_redis_backend.is_async() is False

def test_redis_backend_get_raw_model(mock_redis_backend):
    """Test get_raw_model method."""
    assert mock_redis_backend.get_raw_model() == UserDoc

def test_redis_backend_find_complex(mock_redis_backend):
    """Test find method with complex queries."""
    mock_users = [
        create_mock_redis_user(name="John", age=25, email="john@test.com"),
        create_mock_redis_user(name="Jane", age=25, email="jane@test.com"),
    ]
    mock_redis_backend.find.return_value = mock_users
    
    # Test multiple conditions
    age_25_users = mock_redis_backend.find(
        (UserDoc.age == 25) & (UserDoc.name == "John")
    )
    assert len(age_25_users) == 2
    mock_redis_backend.find.assert_called_once()

def test_redis_backend_all_empty(mock_redis_backend):
    """Test all method with empty database."""
    mock_redis_backend.all.return_value = []
    assert len(mock_redis_backend.all()) == 0

def test_redis_backend_all_multiple(mock_redis_backend):
    """Test all method with multiple documents."""
    mock_users = [
        create_mock_redis_user(name="User1", age=20, email="user1@test.com"),
        create_mock_redis_user(name="User2", age=25, email="user2@test.com"),
        create_mock_redis_user(name="User3", age=30, email="user3@test.com"),
    ]
    mock_redis_backend.all.return_value = mock_users
    
    all_users = mock_redis_backend.all()
    assert len(all_users) == 3
    assert sorted([user.name for user in all_users]) == ["User1", "User2", "User3"] 