from typing import List

import pytest
from pydantic import BaseModel
from redis_om import Field
from redis_om.connections import get_redis_connection

from mindtrace.database import (
    DocumentNotFoundError,
    DuplicateInsertError,
    MindtraceRedisDocument,
    RedisMindtraceODMBackend,
)

REDIS_URL = "redis://localhost:6380"


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
        database = get_redis_connection(url=REDIS_URL)


@pytest.fixture(scope="function")
def redis_backend():
    """Create a Redis backend instance."""
    backend = RedisMindtraceODMBackend(UserDoc, REDIS_URL)
    backend.initialize()

    # Clean up any existing data before test
    for user in backend.all():
        backend.delete(user.pk)

    yield backend

    # Clean up after test
    for user in backend.all():
        backend.delete(user.pk)


def test_redis_backend_crud(redis_backend):
    """Test basic CRUD operations."""
    user = UserCreate(name="Alice", age=30, email="alice@test.com")

    inserted = redis_backend.insert(user)

    fetched = redis_backend.get(inserted.pk)

    assert fetched.name == "Alice"
    assert fetched.age == 30
    assert fetched.email == "alice@test.com"

    all_users = redis_backend.all()
    assert len(all_users) == 1

    redis_backend.delete(inserted.pk)

    with pytest.raises(DocumentNotFoundError):
        redis_backend.get(inserted.pk)


def test_redis_backend_duplicate_insert(redis_backend):
    """Test duplicate insert handling."""
    user = UserCreate(name="Bob", age=25, email="bob@test.com")
    redis_backend.insert(user)

    # Try to insert another user with same email
    with pytest.raises(DuplicateInsertError):
        redis_backend.insert(user)


def test_redis_backend_find(redis_backend):
    """Test find operations."""
    # Insert test data
    users = [
        UserCreate(name="Charlie", age=35, email="charlie@test.com"),
        UserCreate(name="David", age=35, email="david@test.com"),
        UserCreate(name="Eve", age=40, email="eve@test.com"),
    ]
    for user in users:
        redis_backend.insert(user)

    # Test find by age
    age_35_users = redis_backend.find(UserDoc.age == 35)
    assert len(age_35_users) == 2

    # Test find by name
    charlie_users = redis_backend.find(UserDoc.name == "Charlie")
    assert len(charlie_users) == 1
    assert charlie_users[0].email == "charlie@test.com"


def test_is_async(redis_backend):
    """Test is_async method."""
    assert redis_backend.is_async() is False


def test_redis_backend_get_not_found(redis_backend):
    """Test get method with non-existent ID."""
    with pytest.raises(DocumentNotFoundError):
        redis_backend.get("non_existent_id")


def test_redis_backend_delete_not_found(redis_backend):
    """Test delete method with non-existent ID."""
    with pytest.raises(DocumentNotFoundError):
        redis_backend.delete("non_existent_id")


def test_redis_backend_all_empty(redis_backend):
    """Test all method with empty database."""
    assert len(redis_backend.all()) == 0


def test_redis_backend_all_multiple(redis_backend):
    """Test all method with multiple documents."""
    users = [
        UserCreate(name="User1", age=20, email="user1@test.com"),
        UserCreate(name="User2", age=25, email="user2@test.com"),
        UserCreate(name="User3", age=30, email="user3@test.com"),
    ]

    for user in users:
        redis_backend.insert(user)

    all_users = redis_backend.all()
    assert len(all_users) == 3
    assert sorted([user.name for user in all_users]) == ["User1", "User2", "User3"]


def test_redis_backend_find_complex(redis_backend):
    """Test find method with complex queries."""
    users = [
        UserCreate(name="John", age=25, email="john@test.com"),
        UserCreate(name="Jane", age=25, email="jane@test.com"),
        UserCreate(name="Jack", age=30, email="jack@test.com"),
        UserCreate(name="Jill", age=30, email="jill@test.com"),
    ]

    for user in users:
        redis_backend.insert(user)

    # Test multiple conditions
    age_25_users = redis_backend.find((UserDoc.age == 25) & (UserDoc.name == "John"))
    assert len(age_25_users) == 1
    assert age_25_users[0].name == "John"

    # Test OR condition
    age_30_users = redis_backend.find((UserDoc.age == 30) | (UserDoc.name == "Jane"))
    assert len(age_30_users) == 3
    names = sorted([user.name for user in age_30_users])
    assert names == ["Jack", "Jane", "Jill"]


def test_redis_backend_find_no_results(redis_backend):
    """Test find method with no matching results."""
    users = [
        UserCreate(name="Test1", age=25, email="test1@test.com"),
        UserCreate(name="Test2", age=30, email="test2@test.com"),
    ]

    for user in users:
        redis_backend.insert(user)

    # Search for non-existent age
    age_50_users = redis_backend.find(UserDoc.age == 50)
    assert len(age_50_users) == 0

    # Search for non-existent name
    name_users = redis_backend.find(UserDoc.name == "NonExistent")
    assert len(name_users) == 0


def test_redis_backend_get_raw_model(redis_backend):
    """Test get_raw_model method."""
    model_cls = redis_backend.get_raw_model()
    assert model_cls == UserDoc

    # Verify the model class can be used to create instances
    user = model_cls(name="Test", age=25, email="test@test.com")
    assert isinstance(user, UserDoc)
    assert isinstance(user, MindtraceRedisDocument)


def test_redis_backend_initialization(redis_backend):
    """Test backend initialization."""
    # Test that initialization is idempotent
    redis_backend.initialize()
    redis_backend.initialize()  # Should not raise any errors

    # Test that operations work after multiple initializations
    user = UserCreate(name="Test", age=25, email="test@test.com")
    doc = redis_backend.insert(user)
    assert doc.name == "Test"


def test_redis_backend_raw_model_features(redis_backend):
    """Test Redis OM raw model features that are accessible through the raw model."""
    # Create a test user
    user = UserCreate(name="Test", age=25, email="test@test.com")
    doc = redis_backend.insert(user)

    # Get the raw model
    model_cls = redis_backend.get_raw_model()

    # Test key() method to get Redis key
    raw_doc = model_cls.get(doc.pk)
    assert raw_doc.key().startswith(f"{model_cls.Meta.global_key_prefix}:")

    # Test expire() method
    raw_doc.expire(10)  # Expire in 10 seconds
    ttl = model_cls.db().ttl(raw_doc.key())
    assert 0 < ttl <= 10

    # Test JSON path access using redis-py
    json_data = model_cls.db().json().get(raw_doc.key(), "$.name")
    assert json_data == ["Test"]

    # Test direct Redis commands through db()
    model_cls.db().set("test_key", "test_value")
    value = model_cls.db().get("test_key")
    assert value == "test_value"
    model_cls.db().delete("test_key")


def test_redis_backend_json_operations(redis_backend):
    """Test Redis OM's JSON operations through raw model."""
    user = UserCreate(name="Test", age=25, email="test@test.com")
    doc = redis_backend.insert(user)

    # Get raw model class
    model_cls = redis_backend.get_raw_model()
    raw_doc = model_cls.get(doc.pk)

    # Test JSON array append
    redis = model_cls.db()
    redis.json().arrappend(raw_doc.key(), "$.skills", "python")

    # Verify the append worked
    updated_doc = model_cls.get(doc.pk)
    assert len(updated_doc.skills) > 0
    assert "python" in updated_doc.skills

    # Test JSON number increment
    redis.json().numincrby(raw_doc.key(), "$.age", 1)

    # Verify the increment worked
    updated_doc = model_cls.get(doc.pk)
    assert updated_doc.age == 26


def test_redis_backend_search_features(redis_backend):
    """Test Redis OM's advanced search features through raw model."""
    # Create test data
    users = [
        UserCreate(name="John", age=25, email="john@test.com"),
        UserCreate(name="Jane", age=30, email="jane@test.com"),
        UserCreate(name="Jack", age=35, email="jack@test.com"),
    ]
    for user in users:
        redis_backend.insert(user)

    model_cls = redis_backend.get_raw_model()

    # Test count() method
    count = model_cls.find(model_cls.age >= 30).count()
    assert count == 2

    # Test first() method
    first_user = model_cls.find(model_cls.name == "John").first()
    assert first_user.name == "John"

    # Test sort_by with slice
    sorted_users = list(model_cls.find().sort_by("age"))[:2]
    assert len(sorted_users) == 2
    assert sorted_users[0].age == 25  # John
    assert sorted_users[1].age == 30  # Jane
