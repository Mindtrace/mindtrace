from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from mindtrace.database import RegistryMindtraceODM
from mindtrace.registry import Registry, RegistryBackend


# Test models
class UserCreate(BaseModel):
    name: str
    age: int
    email: str


class UserDoc(BaseModel):
    name: str
    age: int
    email: str
    id: str = None


class ComplexUserDoc(BaseModel):
    name: str
    age: int
    email: str
    preferences: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    is_active: bool = True


@pytest.fixture
def mock_registry_backend():
    """Create a mocked Registry backend."""
    mock_backend = MagicMock(spec=RegistryBackend)
    return mock_backend


@pytest.fixture
def registry_odm(mock_registry_backend):
    """Create a RegistryMindtraceODM instance with mocked registry."""
    with patch("mindtrace.database.backends.registry_odm.Registry") as mock_registry_cls:
        mock_registry = MagicMock(spec=Registry)
        mock_registry_cls.return_value = mock_registry
        backend = RegistryMindtraceODM(backend=mock_registry_backend)
        backend.registry = mock_registry
        return backend


@pytest.fixture
def registry_odm_default():
    """Create a RegistryMindtraceODM instance with default settings."""
    with patch("mindtrace.database.backends.registry_odm.Registry") as mock_registry_cls:
        mock_registry = MagicMock(spec=Registry)
        mock_registry_cls.return_value = mock_registry
        backend = RegistryMindtraceODM()
        backend.registry = mock_registry
        return backend


def create_test_user(name="John", age=30, email="john@example.com"):
    """Create a test user document."""
    return UserCreate(name=name, age=age, email=email)


def create_complex_user(name="Jane", age=25, email="jane@example.com"):
    """Create a complex test user document."""
    return ComplexUserDoc(
        name=name,
        age=age,
        email=email,
        preferences={"theme": "dark", "language": "en"},
        tags=["developer", "admin"],
        is_active=True,
    )


class TestRegistryMindtraceODM:
    """Test suite for RegistryMindtraceODM."""

    def test_initialization_with_backend(self, mock_registry_backend):
        """Test backend initialization with custom registry backend."""
        with patch("mindtrace.database.backends.registry_odm.Registry") as mock_registry_cls:
            mock_registry = MagicMock(spec=Registry)
            mock_registry_cls.return_value = mock_registry

            backend = RegistryMindtraceODM(backend=mock_registry_backend)

            mock_registry_cls.assert_called_once_with(backend=mock_registry_backend, version_objects=False)
            assert backend.registry == mock_registry

    def test_initialization_default(self):
        """Test backend initialization with default settings."""
        with patch("mindtrace.database.backends.registry_odm.Registry") as mock_registry_cls:
            mock_registry = MagicMock(spec=Registry)
            mock_registry_cls.return_value = mock_registry

            backend = RegistryMindtraceODM()

            mock_registry_cls.assert_called_once_with(backend=None, version_objects=False)
            assert backend.registry == mock_registry

    def test_is_async(self, registry_odm):
        """Test that the backend is synchronous."""
        assert registry_odm.is_async() is False

    def test_insert_basic_document(self, registry_odm):
        """Test inserting a basic document."""
        user = create_test_user()

        result_id = registry_odm.insert(user)

        # Verify the document was stored in registry
        registry_odm.registry.__setitem__.assert_called_once()
        call_args = registry_odm.registry.__setitem__.call_args
        assert call_args[0][1] == user  # The document should be stored
        assert isinstance(result_id, str)  # Should return a string ID

    def test_insert_complex_document(self, registry_odm):
        """Test inserting a complex document with nested data."""
        user = create_complex_user()

        result_id = registry_odm.insert(user)
        assert isinstance(result_id, str)

        # Verify the complex document was stored
        registry_odm.registry.__setitem__.assert_called_once()
        call_args = registry_odm.registry.__setitem__.call_args
        stored_doc = call_args[0][1]
        assert stored_doc.name == "Jane"
        assert stored_doc.age == 25
        assert stored_doc.preferences == {"theme": "dark", "language": "en"}
        assert stored_doc.tags == ["developer", "admin"]
        assert stored_doc.is_active is True

    def test_get_existing_document(self, registry_odm):
        """Test retrieving an existing document."""
        user = create_test_user()
        test_id = "test-id-123"

        # Mock the registry to return our test user
        registry_odm.registry.__getitem__.return_value = user

        result = registry_odm.get(test_id)

        # Verify the registry was queried with the correct ID
        registry_odm.registry.__getitem__.assert_called_once_with(test_id)
        assert result == user

    def test_get_nonexistent_document(self, registry_odm):
        """Test retrieving a document that doesn't exist."""
        test_id = "nonexistent-id"

        # Mock the registry to raise KeyError for nonexistent document
        registry_odm.registry.__getitem__.side_effect = KeyError(test_id)

        with pytest.raises(KeyError):
            registry_odm.get(test_id)

    def test_update_existing_document(self, registry_odm):
        """Test updating an existing document."""
        updated_user = create_test_user("John Updated", 31, "john.updated@example.com")
        test_id = "test-id-123"

        # Mock the registry to contain the original user
        registry_odm.registry.__contains__.return_value = True

        result = registry_odm.update(test_id, updated_user)

        # Verify the registry was checked and updated
        registry_odm.registry.__contains__.assert_called_once_with(test_id)
        registry_odm.registry.__setitem__.assert_called_once_with(test_id, updated_user)
        assert result is True

    def test_update_nonexistent_document(self, registry_odm):
        """Test updating a document that doesn't exist."""
        updated_user = create_test_user("John Updated", 31, "john.updated@example.com")
        test_id = "nonexistent-id"

        # Mock the registry to not contain the document
        registry_odm.registry.__contains__.return_value = False

        result = registry_odm.update(test_id, updated_user)

        # Verify the registry was checked but not updated
        registry_odm.registry.__contains__.assert_called_once_with(test_id)
        registry_odm.registry.__setitem__.assert_not_called()
        assert result is False

    def test_delete_existing_document(self, registry_odm):
        """Test deleting an existing document."""
        test_id = "test-id-123"

        registry_odm.delete(test_id)

        # Verify the registry was called to delete the document
        registry_odm.registry.__delitem__.assert_called_once_with(test_id)

    def test_delete_nonexistent_document(self, registry_odm):
        """Test deleting a document that doesn't exist."""
        test_id = "nonexistent-id"

        # Mock the registry to raise KeyError for nonexistent document
        registry_odm.registry.__delitem__.side_effect = KeyError(test_id)

        with pytest.raises(KeyError):
            registry_odm.delete(test_id)

    def test_all_documents(self, registry_odm):
        """Test retrieving all documents."""
        user1 = create_test_user("John", 30, "john@example.com")
        user2 = create_test_user("Jane", 25, "jane@example.com")
        expected_documents = [user1, user2]

        # Mock the registry to return our test documents
        registry_odm.registry.values.return_value = expected_documents

        result = registry_odm.all()

        # Verify the registry was queried for all values
        registry_odm.registry.values.assert_called_once()
        assert result == expected_documents

    def test_all_documents_empty(self, registry_odm):
        """Test retrieving all documents when registry is empty."""
        # Mock the registry to return empty list
        registry_odm.registry.values.return_value = []

        result = registry_odm.all()

        registry_odm.registry.values.assert_called_once()
        assert result == []

    def test_crud_workflow(self, registry_odm):
        """Test a complete CRUD workflow."""
        user = create_test_user("Test User", 28, "test@example.com")

        # Insert
        user_id = registry_odm.insert(user)
        assert isinstance(user_id, str)

        # Get
        registry_odm.registry.__getitem__.return_value = user
        retrieved_user = registry_odm.get(user_id)
        assert retrieved_user == user

        # Update
        updated_user = create_test_user("Updated User", 29, "updated@example.com")
        registry_odm.registry.__contains__.return_value = True
        update_success = registry_odm.update(user_id, updated_user)
        assert update_success is True

        # Delete
        registry_odm.delete(user_id)
        registry_odm.registry.__delitem__.assert_called_with(user_id)

    def test_multiple_operations(self, registry_odm):
        """Test multiple operations with different document types."""
        # Insert multiple documents
        user1 = create_test_user("Alice", 25, "alice@example.com")
        user2 = create_complex_user("Bob", 30, "bob@example.com")

        id1 = registry_odm.insert(user1)
        id2 = registry_odm.insert(user2)

        assert id1 != id2  # IDs should be unique

        # Mock registry to return our documents
        registry_odm.registry.__getitem__.side_effect = lambda x: user1 if x == id1 else user2

        # Retrieve both documents
        retrieved1 = registry_odm.get(id1)
        retrieved2 = registry_odm.get(id2)

        assert retrieved1 == user1
        assert retrieved2 == user2

    def test_document_persistence(self, registry_odm):
        """Test that documents persist across operations."""
        user = create_test_user("Persistent User", 35, "persistent@example.com")

        # Insert document
        user_id = registry_odm.insert(user)
        assert isinstance(user_id, str)

        # Verify document is stored
        registry_odm.registry.__setitem__.assert_called_once()
        stored_doc = registry_odm.registry.__setitem__.call_args[0][1]
        assert stored_doc.name == "Persistent User"
        assert stored_doc.age == 35
        assert stored_doc.email == "persistent@example.com"

    def test_error_handling(self, registry_odm):
        """Test error handling in various scenarios."""
        # Test get with KeyError
        registry_odm.registry.__getitem__.side_effect = KeyError("test")
        with pytest.raises(KeyError):
            registry_odm.get("nonexistent")

        # Test delete with KeyError
        registry_odm.registry.__delitem__.side_effect = KeyError("test")
        with pytest.raises(KeyError):
            registry_odm.delete("nonexistent")

    def test_backend_integration(self, mock_registry_backend):
        """Test integration with actual Registry backend."""
        # Create backend with actual registry backend
        backend = RegistryMindtraceODM(backend=mock_registry_backend)

        # Test that the registry was initialized with the provided backend
        assert backend.registry is not None
        # The registry should have been created with the mock backend
        # This is tested indirectly through the registry initialization

    def test_default_backend_integration(self):
        """Test integration with default Registry backend."""
        # Create backend with default settings
        backend = RegistryMindtraceODM()

        # Test that the registry was initialized
        assert backend.registry is not None
        # The registry should have been created with default settings
        # This is tested indirectly through the registry initialization

    # Tests for find() method
    def test_find_no_criteria(self, registry_odm):
        """Test find() with no criteria returns all documents."""
        user1 = create_test_user("John", 30, "john@example.com")
        user2 = create_test_user("Jane", 25, "jane@example.com")
        expected_documents = [user1, user2]

        # Mock the registry to return our test documents
        registry_odm.registry.values.return_value = expected_documents

        result = registry_odm.find()

        # Verify the registry was queried for all values
        registry_odm.registry.values.assert_called_once()
        assert result == expected_documents

    def test_find_with_kwargs_single_match(self, registry_odm):
        """Test find() with kwargs matching a single document."""
        user1 = create_test_user("John", 30, "john@example.com")
        user2 = create_test_user("Jane", 25, "jane@example.com")
        all_documents = [user1, user2]

        # Mock the registry to return all documents
        registry_odm.registry.values.return_value = all_documents

        result = registry_odm.find(name="John")

        # Should return only the matching document
        assert len(result) == 1
        assert result[0] == user1
        assert result[0].name == "John"

    def test_find_with_kwargs_multiple_fields(self, registry_odm):
        """Test find() with multiple kwargs fields."""
        user1 = create_test_user("John", 30, "john@example.com")
        user2 = create_test_user("John", 25, "jane@example.com")
        user3 = create_test_user("Jane", 30, "jane2@example.com")
        all_documents = [user1, user2, user3]

        # Mock the registry to return all documents
        registry_odm.registry.values.return_value = all_documents

        result = registry_odm.find(name="John", age=30)

        # Should return only user1 (matches both name and age)
        assert len(result) == 1
        assert result[0] == user1
        assert result[0].name == "John"
        assert result[0].age == 30

    def test_find_with_kwargs_no_match(self, registry_odm):
        """Test find() with kwargs that match no documents."""
        user1 = create_test_user("John", 30, "john@example.com")
        user2 = create_test_user("Jane", 25, "jane@example.com")
        all_documents = [user1, user2]

        # Mock the registry to return all documents
        registry_odm.registry.values.return_value = all_documents

        result = registry_odm.find(name="Bob")

        # Should return empty list
        assert result == []

    def test_find_with_kwargs_partial_match(self, registry_odm):
        """Test find() where some fields match but not all."""
        user1 = create_test_user("John", 30, "john@example.com")
        user2 = create_test_user("John", 25, "jane@example.com")
        all_documents = [user1, user2]

        # Mock the registry to return all documents
        registry_odm.registry.values.return_value = all_documents

        result = registry_odm.find(name="John", age=30)

        # Should return only user1 (matches both criteria)
        assert len(result) == 1
        assert result[0] == user1

    def test_find_with_kwargs_missing_field(self, registry_odm):
        """Test find() with kwargs for a field that doesn't exist on documents."""
        user1 = create_test_user("John", 30, "john@example.com")
        all_documents = [user1]

        # Mock the registry to return all documents
        registry_odm.registry.values.return_value = all_documents

        result = registry_odm.find(nonexistent_field="value")

        # Should return empty list (field doesn't exist)
        assert result == []

    def test_find_with_kwargs_complex_document(self, registry_odm):
        """Test find() with kwargs on complex documents."""
        user1 = create_complex_user("Jane", 25, "jane@example.com")
        user2 = create_complex_user("Bob", 30, "bob@example.com")
        all_documents = [user1, user2]

        # Mock the registry to return all documents
        registry_odm.registry.values.return_value = all_documents

        result = registry_odm.find(name="Jane", is_active=True)

        # Should return only user1
        assert len(result) == 1
        assert result[0] == user1
        assert result[0].name == "Jane"
        assert result[0].is_active is True

    def test_find_with_args_only(self, registry_odm):
        """Test find() with args only (not supported, should warn and return empty)."""
        user1 = create_test_user("John", 30, "john@example.com")
        all_documents = [user1]

        # Mock the registry to return all documents
        registry_odm.registry.values.return_value = all_documents

        # Mock logger to capture warning
        with patch.object(registry_odm.logger, "warning") as mock_warning:
            result = registry_odm.find("some_query")

            # Should log a warning
            mock_warning.assert_called_once()
            assert "does not support complex query syntax" in mock_warning.call_args[0][0]
            # Should return empty list (covers the final return statement on line 220)
            assert result == []
            assert isinstance(result, list)
            assert len(result) == 0

    def test_find_with_args_only_no_kwargs_explicit(self, registry_odm):
        """Test find() with args only, explicitly testing the final return path."""
        user1 = create_test_user("John", 30, "john@example.com")
        all_documents = [user1]

        # Mock the registry to return all documents
        registry_odm.registry.values.return_value = all_documents

        # Mock logger to capture warning
        with patch.object(registry_odm.logger, "warning") as mock_warning:
            # Call with args but no kwargs - this should hit the final return []
            result = registry_odm.find("query1", "query2")

            # Should log a warning
            mock_warning.assert_called_once()
            # Should return empty list - this ensures line 220 is covered
            assert result == []
            # Verify it's the exact empty list return
            assert result is not None
            assert isinstance(result, list)

    def test_find_with_args_and_kwargs(self, registry_odm):
        """Test find() with both args and kwargs (should use kwargs)."""
        user1 = create_test_user("John", 30, "john@example.com")
        user2 = create_test_user("Jane", 25, "jane@example.com")
        all_documents = [user1, user2]

        # Mock the registry to return all documents
        registry_odm.registry.values.return_value = all_documents

        result = registry_odm.find("some_query", name="John")

        # Should use kwargs and return matching document
        assert len(result) == 1
        assert result[0] == user1
        assert result[0].name == "John"

    def test_find_with_empty_registry(self, registry_odm):
        """Test find() when registry is empty."""
        # Mock the registry to return empty list
        registry_odm.registry.values.return_value = []

        result = registry_odm.find(name="John")

        # Should return empty list
        assert result == []

    def test_find_with_kwargs_multiple_matches(self, registry_odm):
        """Test find() with kwargs that match multiple documents."""
        user1 = create_test_user("John", 30, "john@example.com")
        user2 = create_test_user("John", 25, "john2@example.com")
        user3 = create_test_user("Jane", 30, "jane@example.com")
        all_documents = [user1, user2, user3]

        # Mock the registry to return all documents
        registry_odm.registry.values.return_value = all_documents

        result = registry_odm.find(name="John")

        # Should return both John documents
        assert len(result) == 2
        assert all(user.name == "John" for user in result)
        assert user1 in result
        assert user2 in result
        assert user3 not in result

    def test_find_with_kwargs_case_sensitive(self, registry_odm):
        """Test find() with kwargs is case sensitive."""
        user1 = create_test_user("John", 30, "john@example.com")
        all_documents = [user1]

        # Mock the registry to return all documents
        registry_odm.registry.values.return_value = all_documents

        result = registry_odm.find(name="john")  # lowercase

        # Should return empty (case sensitive)
        assert result == []

    # Tests for get_raw_model() method
    def test_get_raw_model_returns_base_model(self, registry_odm):
        """Test get_raw_model() returns BaseModel."""
        result = registry_odm.get_raw_model()

        # Should return BaseModel class
        assert result == BaseModel
        assert result is BaseModel

    def test_get_raw_model_type(self, registry_odm):
        """Test get_raw_model() returns correct type."""

        result = registry_odm.get_raw_model()

        # Should be a class type
        assert isinstance(result, type)
        assert issubclass(result, BaseModel)

    def test_get_raw_model_callable(self, registry_odm):
        """Test get_raw_model() returns a callable class."""
        result = registry_odm.get_raw_model()

        # Should be callable (can instantiate)
        assert callable(result)

    def test_get_raw_model_consistency(self, registry_odm):
        """Test get_raw_model() returns consistent result."""
        result1 = registry_odm.get_raw_model()
        result2 = registry_odm.get_raw_model()

        # Should always return the same BaseModel class
        assert result1 == result2
        assert result1 is result2
