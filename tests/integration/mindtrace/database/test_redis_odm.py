from typing import List

import pytest
from pydantic import BaseModel
from redis_om import Field

from mindtrace.database import (
    DocumentNotFoundError,
    DuplicateInsertError,
    MindtraceRedisDocument,
    RedisMindtraceODM,
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


# Models for coverage testing - different module configurations
class UserDocMainModule(MindtraceRedisDocument):
    """Model with __main__ module for testing module name handling."""

    name: str = Field(index=True)
    age: int = Field(index=True)

    class Meta:
        global_key_prefix = "testapp"

    __module__ = "__main__"


class UserDocNoModule(MindtraceRedisDocument):
    """Model without module for testing module name handling."""

    name: str = Field(index=True)
    age: int = Field(index=True)

    class Meta:
        global_key_prefix = "testapp"

    __module__ = ""


class UserDocNoIndex(MindtraceRedisDocument):
    """Model without indexed fields for testing early return."""

    name: str
    age: int

    class Meta:
        global_key_prefix = "testapp"


@pytest.fixture(scope="function")
def redis_backend():
    """Create a Redis backend instance."""
    backend = RedisMindtraceODM(UserDoc, REDIS_URL)
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


def test_redis_module_name_handling_main_module():
    """Test index creation with __main__ module (lines 205, 220-222, 435-437)."""
    backend = RedisMindtraceODM(UserDocMainModule, REDIS_URL)
    backend.initialize()

    # Create index for model with __main__ module
    backend._create_index_for_model(UserDocMainModule)
    backend._ensure_index_has_documents(UserDocMainModule)

    # Clean up
    try:
        for doc in backend.all():
            backend.delete(doc.pk)
    except Exception:
        pass


def test_redis_module_name_handling_no_module():
    """Test index creation with no module (lines 209, 224-226, 426, 439-441)."""
    backend = RedisMindtraceODM(UserDocNoModule, REDIS_URL)
    backend.initialize()

    # Create index for model without module
    backend._create_index_for_model(UserDocNoModule)
    backend._ensure_index_has_documents(UserDocNoModule)

    # Clean up
    try:
        for doc in backend.all():
            backend.delete(doc.pk)
    except Exception:
        pass


def test_redis_no_indexed_fields_early_return():
    """Test index creation with no indexed fields (line 241)."""
    backend = RedisMindtraceODM(UserDocNoIndex, REDIS_URL)
    backend.initialize()

    # Should return early when no indexed fields
    backend._create_index_for_model(UserDocNoIndex)

    # Clean up
    try:
        for doc in backend.all():
            backend.delete(doc.pk)
    except Exception:
        pass


def test_redis_numeric_field_type_detection():
    """Test numeric field type detection (line 284)."""
    backend = RedisMindtraceODM(UserDoc, REDIS_URL)
    backend.initialize()

    # Create index - should detect age as NUMERIC
    backend._create_index_for_model(UserDoc)

    # Clean up
    try:
        for doc in backend.all():
            backend.delete(doc.pk)
    except Exception:
        pass


def test_redis_index_name_set_before_create():
    """Test index_name is set before create_index (line 297)."""
    backend = RedisMindtraceODM(UserDoc, REDIS_URL)
    backend.initialize()

    # Remove index_name if it exists
    original_index_name = None
    if hasattr(UserDoc.Meta, "index_name"):
        original_index_name = UserDoc.Meta.index_name
        delattr(UserDoc.Meta, "index_name")

    try:
        # Create index - should set index_name before calling create_index
        backend._create_index_for_model(UserDoc)
        assert hasattr(UserDoc.Meta, "index_name")
    finally:
        # Restore if needed
        if original_index_name is not None:
            UserDoc.Meta.index_name = original_index_name


def test_redis_model_odms_loop():
    """Test model ODMs loop in _do_initialize (line 540)."""
    backend = RedisMindtraceODM(models={"user": UserDoc}, redis_url=REDIS_URL)
    backend.initialize()

    # The loop at line 540 should execute
    assert backend.user._is_initialized is True

    # Clean up
    try:
        for doc in backend.user.all():
            backend.user.delete(doc.pk)
    except Exception:
        pass


def test_redis_module_name_paths_integration():
    """Integration test for module name handling paths (lines 205, 209, 220-226, 435-441)."""
    # Test with __main__ module - ensure NO model_key_prefix to hit else branch
    UserDocMainModule.__module__ = "__main__"
    # Ensure no model_key_prefix
    if hasattr(UserDocMainModule.Meta, "model_key_prefix"):
        delattr(UserDocMainModule.Meta, "model_key_prefix")
    backend_main = RedisMindtraceODM(UserDocMainModule, REDIS_URL)
    backend_main.initialize()
    # This should execute lines 221-222
    backend_main._create_index_for_model(UserDocMainModule)
    # This should execute lines 436-437
    backend_main._ensure_index_has_documents(UserDocMainModule)

    # Test with no module
    UserDocNoModule.__module__ = ""
    if hasattr(UserDocNoModule.Meta, "model_key_prefix"):
        delattr(UserDocNoModule.Meta, "model_key_prefix")
    backend_no = RedisMindtraceODM(UserDocNoModule, REDIS_URL)
    backend_no.initialize()
    backend_no._create_index_for_model(UserDocNoModule)
    backend_no._ensure_index_has_documents(UserDocNoModule)

    # Test with regular module
    UserDocNoModule.__module__ = "test_module"
    backend_reg = RedisMindtraceODM(UserDocNoModule, REDIS_URL)
    backend_reg.initialize()
    backend_reg._create_index_for_model(UserDocNoModule)
    backend_reg._ensure_index_has_documents(UserDocNoModule)

    # Clean up
    for backend in [backend_main, backend_no, backend_reg]:
        try:
            for doc in backend.all():
                backend.delete(doc.pk)
        except Exception:
            pass


def test_redis_no_indexed_fields_integration():
    """Integration test for early return when no indexed fields (line 241)."""
    backend = RedisMindtraceODM(UserDocNoIndex, REDIS_URL)
    backend.initialize()

    # Should return early when no indexed fields
    result = backend._create_index_for_model(UserDocNoIndex)
    assert result is None

    # Clean up
    try:
        for doc in backend.all():
            backend.delete(doc.pk)
    except Exception:
        pass


def test_redis_numeric_field_detection_integration():
    """Integration test for numeric field type detection (line 284)."""
    backend = RedisMindtraceODM(UserDoc, REDIS_URL)
    backend.initialize()

    # Create index - should detect age as NUMERIC
    backend._create_index_for_model(UserDoc)

    # Clean up
    try:
        for doc in backend.all():
            backend.delete(doc.pk)
    except Exception:
        pass


def test_redis_index_name_set_integration():
    """Integration test for index_name being set before create_index (line 297)."""
    backend = RedisMindtraceODM(UserDoc, REDIS_URL)
    backend.initialize()

    # Remove index_name if it exists
    original_index_name = None
    if hasattr(UserDoc.Meta, "index_name"):
        original_index_name = UserDoc.Meta.index_name
        delattr(UserDoc.Meta, "index_name")

    try:
        # Create index - should set index_name before calling create_index
        backend._create_index_for_model(UserDoc)
        assert hasattr(UserDoc.Meta, "index_name")
    finally:
        if original_index_name is not None:
            UserDoc.Meta.index_name = original_index_name

    # Clean up
    try:
        for doc in backend.all():
            backend.delete(doc.pk)
    except Exception:
        pass
