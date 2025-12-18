"""Integration tests for RegistryMindtraceODM backend.

These tests verify the actual functionality of the Registry-based ODM backend
with real file system operations using temporary directories.
"""

import shutil
import tempfile
from pathlib import Path
from typing import Any, ClassVar, Tuple, Type

import pytest
from pydantic import BaseModel, Field
from zenml.enums import ArtifactType

from mindtrace.database import RegistryMindtraceODM
from mindtrace.registry import Archiver, LocalRegistryBackend, Registry


# Test models
class User(BaseModel):
    """Simple user model for testing."""

    name: str
    email: str


class UserWithAge(BaseModel):
    """User model with age field for filtering tests."""

    name: str
    email: str
    age: int


class ComplexUser(BaseModel):
    """Complex user model with nested data structures."""

    name: str
    email: str
    age: int
    preferences: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    is_active: bool = True


# Custom Archiver for User model
class UserArchiver(Archiver):
    """Custom archiver for User model that saves to JSON files."""

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (User,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def save(self, user: User):
        """Save user to a JSON file."""
        with open(Path(self.uri) / "user.json", "w") as f:
            f.write(user.model_dump_json())

    def load(self, data_type: Type[Any]) -> User:
        """Load user from a JSON file."""
        with open(Path(self.uri) / "user.json", "r") as f:
            return User.model_validate_json(f.read())


class UserWithAgeArchiver(Archiver):
    """Custom archiver for UserWithAge model."""

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (UserWithAge,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def save(self, user: UserWithAge):
        """Save user to a JSON file."""
        with open(Path(self.uri) / "user_with_age.json", "w") as f:
            f.write(user.model_dump_json())

    def load(self, data_type: Type[Any]) -> UserWithAge:
        """Load user from a JSON file."""
        with open(Path(self.uri) / "user_with_age.json", "r") as f:
            return UserWithAge.model_validate_json(f.read())


class ComplexUserArchiver(Archiver):
    """Custom archiver for ComplexUser model."""

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (ComplexUser,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def save(self, user: ComplexUser):
        """Save user to a JSON file."""
        with open(Path(self.uri) / "complex_user.json", "w") as f:
            f.write(user.model_dump_json())

    def load(self, data_type: Type[Any]) -> ComplexUser:
        """Load user from a JSON file."""
        with open(Path(self.uri) / "complex_user.json", "r") as f:
            return ComplexUser.model_validate_json(f.read())


# Register the custom archivers
Registry.register_default_materializer(User, UserArchiver)
Registry.register_default_materializer(UserWithAge, UserWithAgeArchiver)
Registry.register_default_materializer(ComplexUser, ComplexUserArchiver)


@pytest.fixture(scope="function")
def temp_registry_dir():
    """Create a temporary directory for registry storage."""
    temp_dir = tempfile.mkdtemp(prefix="registry_odm_test_")
    yield Path(temp_dir)
    # Cleanup after test
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def registry_backend(temp_registry_dir):
    """Create a RegistryMindtraceODM instance with a local backend."""
    local_backend = LocalRegistryBackend(uri=temp_registry_dir)
    backend = RegistryMindtraceODM(backend=local_backend)
    yield backend


@pytest.fixture(scope="function")
def registry_backend_default():
    """Create a RegistryMindtraceODM instance with default settings."""
    temp_dir = tempfile.mkdtemp(prefix="registry_odm_default_test_")
    local_backend = LocalRegistryBackend(uri=Path(temp_dir))
    backend = RegistryMindtraceODM(backend=local_backend)
    yield backend
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestRegistryMindtraceODMBasicOperations:
    """Test basic CRUD operations."""

    def test_insert_and_get(self, registry_backend):
        """Test inserting and retrieving a document."""
        user = User(name="John Doe", email="john.doe@example.com")

        # Insert
        inserted_user = registry_backend.insert(user)
        assert inserted_user == user
        assert hasattr(inserted_user, "id")
        user_id = inserted_user.id
        assert isinstance(user_id, str)
        assert len(user_id) > 0

        # Get
        retrieved_user = registry_backend.get(user_id)
        assert retrieved_user.name == "John Doe"
        assert retrieved_user.email == "john.doe@example.com"
        assert hasattr(retrieved_user, "id")

    def test_insert_multiple_documents(self, registry_backend):
        """Test inserting multiple documents."""
        users = [
            User(name="Alice", email="alice@example.com"),
            User(name="Bob", email="bob@example.com"),
            User(name="Charlie", email="charlie@example.com"),
        ]

        user_ids = []
        for user in users:
            inserted_user = registry_backend.insert(user)
            assert hasattr(inserted_user, "id")
            user_ids.append(inserted_user.id)

        # Verify all IDs are unique
        assert len(set(user_ids)) == len(user_ids)

        # Verify all documents can be retrieved
        for idx, user_id in enumerate(user_ids):
            retrieved = registry_backend.get(user_id)
            assert retrieved.name == users[idx].name
            assert retrieved.email == users[idx].email
            assert hasattr(retrieved, "id")

    def test_update_document(self, registry_backend):
        """Test updating an existing document."""
        user = User(name="John Doe", email="john.doe@example.com")

        # Insert
        inserted_user = registry_backend.insert(user)
        user_id = inserted_user.id

        # Update
        updated_user = User(name="John Doe Updated", email="john.updated@example.com")
        result = registry_backend.update(user_id, updated_user)
        assert result is True

        # Verify update
        retrieved = registry_backend.get(user_id)
        assert retrieved.name == "John Doe Updated"
        assert retrieved.email == "john.updated@example.com"
        assert hasattr(retrieved, "id")

    def test_update_nonexistent_document(self, registry_backend):
        """Test updating a document that doesn't exist."""
        user = User(name="Nonexistent", email="nonexistent@example.com")
        result = registry_backend.update("nonexistent-id", user)
        assert result is False

    def test_delete_document(self, registry_backend):
        """Test deleting a document."""
        user = User(name="John Doe", email="john.doe@example.com")

        # Insert
        inserted_user = registry_backend.insert(user)
        user_id = inserted_user.id

        # Delete
        registry_backend.delete(user_id)

        # Verify deletion
        with pytest.raises(KeyError):
            registry_backend.get(user_id)

    def test_delete_nonexistent_document(self, registry_backend):
        """Test deleting a document that doesn't exist."""
        with pytest.raises(KeyError):
            registry_backend.delete("nonexistent-id")

    def test_get_nonexistent_document(self, registry_backend):
        """Test retrieving a document that doesn't exist."""
        with pytest.raises(KeyError):
            registry_backend.get("nonexistent-id")


class TestRegistryMindtraceODMAllAndFind:
    """Test all() and find() operations."""

    def test_all_empty(self, registry_backend):
        """Test all() when registry is empty."""
        result = registry_backend.all()
        assert result == []

    def test_all_with_documents(self, registry_backend):
        """Test all() returns all documents."""
        users = [
            User(name="Alice", email="alice@example.com"),
            User(name="Bob", email="bob@example.com"),
            User(name="Charlie", email="charlie@example.com"),
        ]

        for user in users:
            registry_backend.insert(user)

        result = registry_backend.all()
        assert len(result) == 3

        names = {user.name for user in result}
        assert names == {"Alice", "Bob", "Charlie"}

        # Verify all documents have id attribute set
        for doc in result:
            assert hasattr(doc, "id")

    def test_find_no_criteria(self, registry_backend):
        """Test find() with no criteria returns all documents."""
        users = [
            User(name="Alice", email="alice@example.com"),
            User(name="Bob", email="bob@example.com"),
        ]

        for user in users:
            registry_backend.insert(user)

        result = registry_backend.find()
        assert len(result) == 2

    def test_find_with_kwargs_single_field(self, registry_backend):
        """Test find() with single field matching."""
        users = [
            UserWithAge(name="Alice", email="alice@example.com", age=30),
            UserWithAge(name="Bob", email="bob@example.com", age=25),
            UserWithAge(name="Charlie", email="charlie@example.com", age=30),
        ]

        for user in users:
            registry_backend.insert(user)

        result = registry_backend.find(age=30)
        assert len(result) == 2

        names = {user.name for user in result}
        assert names == {"Alice", "Charlie"}

    def test_find_with_kwargs_multiple_fields(self, registry_backend):
        """Test find() with multiple field matching."""
        users = [
            UserWithAge(name="Alice", email="alice@example.com", age=30),
            UserWithAge(name="Alice", email="alice2@example.com", age=25),
            UserWithAge(name="Bob", email="bob@example.com", age=30),
        ]

        for user in users:
            registry_backend.insert(user)

        result = registry_backend.find(name="Alice", age=30)
        assert len(result) == 1
        assert result[0].email == "alice@example.com"

    def test_find_no_matches(self, registry_backend):
        """Test find() when no documents match."""
        users = [
            UserWithAge(name="Alice", email="alice@example.com", age=30),
            UserWithAge(name="Bob", email="bob@example.com", age=25),
        ]

        for user in users:
            registry_backend.insert(user)

        result = registry_backend.find(age=99)
        assert result == []

    def test_find_with_args_returns_empty(self, registry_backend):
        """Test find() with args (unsupported) returns empty list."""
        users = [
            User(name="Alice", email="alice@example.com"),
        ]

        for user in users:
            registry_backend.insert(user)

        # Args-based queries are not supported, should return empty
        result = registry_backend.find("some_query")
        assert result == []


class TestRegistryMindtraceODMComplexDocuments:
    """Test operations with complex documents."""

    def test_complex_document_insert_and_get(self, registry_backend):
        """Test inserting and retrieving complex documents."""
        user = ComplexUser(
            name="Jane Doe",
            email="jane.doe@example.com",
            age=28,
            preferences={"theme": "dark", "language": "en", "notifications": True},
            tags=["developer", "admin", "premium"],
            is_active=True,
        )

        inserted_user = registry_backend.insert(user)
        user_id = inserted_user.id
        retrieved = registry_backend.get(user_id)

        assert retrieved.name == "Jane Doe"
        assert retrieved.email == "jane.doe@example.com"
        assert retrieved.age == 28
        assert retrieved.preferences == {"theme": "dark", "language": "en", "notifications": True}
        assert retrieved.tags == ["developer", "admin", "premium"]
        assert retrieved.is_active is True

    def test_complex_document_update(self, registry_backend):
        """Test updating complex documents."""
        user = ComplexUser(
            name="Jane Doe",
            email="jane.doe@example.com",
            age=28,
            preferences={"theme": "light"},
            tags=["user"],
            is_active=True,
        )

        inserted_user = registry_backend.insert(user)
        user_id = inserted_user.id

        # Update with new values
        updated_user = ComplexUser(
            name="Jane Doe",
            email="jane.doe@example.com",
            age=29,
            preferences={"theme": "dark", "language": "fr"},
            tags=["user", "premium"],
            is_active=False,
        )

        result = registry_backend.update(user_id, updated_user)
        assert result is True

        retrieved = registry_backend.get(user_id)
        assert retrieved.age == 29
        assert retrieved.preferences == {"theme": "dark", "language": "fr"}
        assert retrieved.tags == ["user", "premium"]
        assert retrieved.is_active is False

    def test_find_complex_documents(self, registry_backend):
        """Test find() with complex documents."""
        users = [
            ComplexUser(name="Alice", email="alice@example.com", age=25, is_active=True),
            ComplexUser(name="Bob", email="bob@example.com", age=30, is_active=False),
            ComplexUser(name="Charlie", email="charlie@example.com", age=35, is_active=True),
        ]

        for user in users:
            registry_backend.insert(user)

        result = registry_backend.find(is_active=True)
        assert len(result) == 2

        names = {user.name for user in result}
        assert names == {"Alice", "Charlie"}


class TestRegistryMindtraceODMBackendProperties:
    """Test backend properties and metadata."""

    def test_is_async_returns_false(self, registry_backend):
        """Test that is_async() returns False."""
        assert registry_backend.is_async() is False

    def test_get_raw_model_returns_base_model(self, registry_backend):
        """Test that get_raw_model() returns BaseModel."""
        from pydantic import BaseModel as PydanticBaseModel

        result = registry_backend.get_raw_model()
        assert result is PydanticBaseModel


class TestRegistryMindtraceODMWorkflow:
    """Test complete workflow scenarios."""

    def test_crud_workflow(self, registry_backend):
        """Test a complete CRUD workflow."""
        # Create
        user = User(name="Test User", email="test@example.com")
        inserted_user = registry_backend.insert(user)
        assert hasattr(inserted_user, "id")
        user_id = inserted_user.id
        assert isinstance(user_id, str)

        # Read
        retrieved = registry_backend.get(user_id)
        assert retrieved.name == "Test User"

        # Update
        updated_user = User(name="Updated User", email="updated@example.com")
        result = registry_backend.update(user_id, updated_user)
        assert result is True

        retrieved = registry_backend.get(user_id)
        assert retrieved.name == "Updated User"
        assert retrieved.email == "updated@example.com"

        # Delete
        registry_backend.delete(user_id)

        with pytest.raises(KeyError):
            registry_backend.get(user_id)

    def test_multiple_document_types(self, registry_backend):
        """Test working with multiple document types."""
        simple_user = User(name="Simple", email="simple@example.com")
        complex_user = ComplexUser(
            name="Complex",
            email="complex@example.com",
            age=30,
            preferences={"key": "value"},
            tags=["tag1"],
        )

        inserted_simple = registry_backend.insert(simple_user)
        inserted_complex = registry_backend.insert(complex_user)
        simple_id = inserted_simple.id
        complex_id = inserted_complex.id

        # Verify both can be retrieved
        retrieved_simple = registry_backend.get(simple_id)
        retrieved_complex = registry_backend.get(complex_id)

        assert retrieved_simple.name == "Simple"
        assert retrieved_complex.name == "Complex"
        assert retrieved_complex.preferences == {"key": "value"}

    def test_persistence_across_operations(self, temp_registry_dir):
        """Test that documents persist across operations."""
        local_backend = LocalRegistryBackend(uri=temp_registry_dir)

        # Create first backend instance and insert data
        backend1 = RegistryMindtraceODM(backend=local_backend)
        user = User(name="Persistent User", email="persistent@example.com")
        inserted_user = backend1.insert(user)
        user_id = inserted_user.id

        # Create second backend instance pointing to same location
        local_backend2 = LocalRegistryBackend(uri=temp_registry_dir)
        backend2 = RegistryMindtraceODM(backend=local_backend2)

        # Verify data persists
        retrieved = backend2.get(user_id)
        assert retrieved.name == "Persistent User"
        assert retrieved.email == "persistent@example.com"


class TestRegistryMindtraceODMEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_name_field(self, registry_backend):
        """Test handling documents with empty string fields."""
        user = User(name="", email="empty@example.com")

        inserted_user = registry_backend.insert(user)
        user_id = inserted_user.id
        retrieved = registry_backend.get(user_id)

        assert retrieved.name == ""
        assert retrieved.email == "empty@example.com"

    def test_special_characters_in_fields(self, registry_backend):
        """Test handling documents with special characters."""
        user = User(
            name="John O'Connor-Smith",
            email="john.o'connor+test@example.com",
        )

        inserted_user = registry_backend.insert(user)
        user_id = inserted_user.id
        retrieved = registry_backend.get(user_id)

        assert retrieved.name == "John O'Connor-Smith"
        assert retrieved.email == "john.o'connor+test@example.com"

    def test_unicode_in_fields(self, registry_backend):
        """Test handling documents with unicode characters."""
        user = User(
            name="日本語テスト 🎉",
            email="unicode@example.com",
        )

        inserted_user = registry_backend.insert(user)
        user_id = inserted_user.id
        retrieved = registry_backend.get(user_id)

        assert retrieved.name == "日本語テスト 🎉"

    def test_large_document(self, registry_backend):
        """Test handling documents with large content."""
        large_tags = [f"tag_{i}" for i in range(100)]
        large_preferences = {f"key_{i}": f"value_{i}" for i in range(50)}

        user = ComplexUser(
            name="Large Document User",
            email="large@example.com",
            age=30,
            preferences=large_preferences,
            tags=large_tags,
        )

        inserted_user = registry_backend.insert(user)
        user_id = inserted_user.id
        retrieved = registry_backend.get(user_id)

        assert len(retrieved.tags) == 100
        assert len(retrieved.preferences) == 50

    def test_find_case_sensitive(self, registry_backend):
        """Test that find() is case sensitive."""
        users = [
            User(name="John", email="john@example.com"),
            User(name="john", email="john2@example.com"),
            User(name="JOHN", email="john3@example.com"),
        ]

        for user in users:
            registry_backend.insert(user)

        result = registry_backend.find(name="John")
        assert len(result) == 1
        assert result[0].email == "john@example.com"

    def test_all_after_delete(self, registry_backend):
        """Test all() after deleting some documents."""
        users = [
            User(name="Alice", email="alice@example.com"),
            User(name="Bob", email="bob@example.com"),
            User(name="Charlie", email="charlie@example.com"),
        ]

        user_ids = []
        for user in users:
            inserted_user = registry_backend.insert(user)
            user_ids.append(inserted_user.id)

        # Delete middle user
        registry_backend.delete(user_ids[1])

        result = registry_backend.all()
        assert len(result) == 2

        names = {user.name for user in result}
        assert "Bob" not in names
        assert names == {"Alice", "Charlie"}
