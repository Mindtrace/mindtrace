from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from mindtrace.database import RegistryMindtraceODMBackend
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
def registry_odm_backend(mock_registry_backend):
    """Create a RegistryMindtraceODMBackend instance with mocked registry."""
    with patch('mindtrace.database.backends.registry_odm_backend.Registry') as mock_registry_cls:
        mock_registry = MagicMock(spec=Registry)
        mock_registry_cls.return_value = mock_registry
        backend = RegistryMindtraceODMBackend(backend=mock_registry_backend)
        backend.registry = mock_registry
        return backend


@pytest.fixture
def registry_odm_backend_default():
    """Create a RegistryMindtraceODMBackend instance with default settings."""
    with patch('mindtrace.database.backends.registry_odm_backend.Registry') as mock_registry_cls:
        mock_registry = MagicMock(spec=Registry)
        mock_registry_cls.return_value = mock_registry
        backend = RegistryMindtraceODMBackend()
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
        is_active=True
    )


class TestRegistryMindtraceODMBackend:
    """Test suite for RegistryMindtraceODMBackend."""

    def test_initialization_with_backend(self, mock_registry_backend):
        """Test backend initialization with custom registry backend."""
        with patch('mindtrace.database.backends.registry_odm_backend.Registry') as mock_registry_cls:
            mock_registry = MagicMock(spec=Registry)
            mock_registry_cls.return_value = mock_registry
            
            backend = RegistryMindtraceODMBackend(backend=mock_registry_backend)
            
            mock_registry_cls.assert_called_once_with(backend=mock_registry_backend, version_objects=False)
            assert backend.registry == mock_registry

    def test_initialization_default(self):
        """Test backend initialization with default settings."""
        with patch('mindtrace.database.backends.registry_odm_backend.Registry') as mock_registry_cls:
            mock_registry = MagicMock(spec=Registry)
            mock_registry_cls.return_value = mock_registry
            
            backend = RegistryMindtraceODMBackend()
            
            mock_registry_cls.assert_called_once_with(backend=None, version_objects=False)
            assert backend.registry == mock_registry

    def test_is_async(self, registry_odm_backend):
        """Test that the backend is synchronous."""
        assert registry_odm_backend.is_async() is False

    def test_insert_basic_document(self, registry_odm_backend):
        """Test inserting a basic document."""
        user = create_test_user()
        
        result_id = registry_odm_backend.insert(user)
        
        # Verify the document was stored in registry
        registry_odm_backend.registry.__setitem__.assert_called_once()
        call_args = registry_odm_backend.registry.__setitem__.call_args
        assert call_args[0][1] == user  # The document should be stored
        assert isinstance(result_id, str)  # Should return a string ID

    def test_insert_complex_document(self, registry_odm_backend):
        """Test inserting a complex document with nested data."""
        user = create_complex_user()
        
        result_id = registry_odm_backend.insert(user)
        
        # Verify the complex document was stored
        registry_odm_backend.registry.__setitem__.assert_called_once()
        call_args = registry_odm_backend.registry.__setitem__.call_args
        stored_doc = call_args[0][1]
        assert stored_doc.name == "Jane"
        assert stored_doc.age == 25
        assert stored_doc.preferences == {"theme": "dark", "language": "en"}
        assert stored_doc.tags == ["developer", "admin"]
        assert stored_doc.is_active is True

    def test_get_existing_document(self, registry_odm_backend):
        """Test retrieving an existing document."""
        user = create_test_user()
        test_id = "test-id-123"
        
        # Mock the registry to return our test user
        registry_odm_backend.registry.__getitem__.return_value = user
        
        result = registry_odm_backend.get(test_id)
        
        # Verify the registry was queried with the correct ID
        registry_odm_backend.registry.__getitem__.assert_called_once_with(test_id)
        assert result == user

    def test_get_nonexistent_document(self, registry_odm_backend):
        """Test retrieving a document that doesn't exist."""
        test_id = "nonexistent-id"
        
        # Mock the registry to raise KeyError for nonexistent document
        registry_odm_backend.registry.__getitem__.side_effect = KeyError(test_id)
        
        with pytest.raises(KeyError):
            registry_odm_backend.get(test_id)

    def test_update_existing_document(self, registry_odm_backend):
        """Test updating an existing document."""
        original_user = create_test_user("John", 30, "john@example.com")
        updated_user = create_test_user("John Updated", 31, "john.updated@example.com")
        test_id = "test-id-123"
        
        # Mock the registry to contain the original user
        registry_odm_backend.registry.__contains__.return_value = True
        
        result = registry_odm_backend.update(test_id, updated_user)
        
        # Verify the registry was checked and updated
        registry_odm_backend.registry.__contains__.assert_called_once_with(test_id)
        registry_odm_backend.registry.__setitem__.assert_called_once_with(test_id, updated_user)
        assert result is True

    def test_update_nonexistent_document(self, registry_odm_backend):
        """Test updating a document that doesn't exist."""
        updated_user = create_test_user("John Updated", 31, "john.updated@example.com")
        test_id = "nonexistent-id"
        
        # Mock the registry to not contain the document
        registry_odm_backend.registry.__contains__.return_value = False
        
        result = registry_odm_backend.update(test_id, updated_user)
        
        # Verify the registry was checked but not updated
        registry_odm_backend.registry.__contains__.assert_called_once_with(test_id)
        registry_odm_backend.registry.__setitem__.assert_not_called()
        assert result is False

    def test_delete_existing_document(self, registry_odm_backend):
        """Test deleting an existing document."""
        test_id = "test-id-123"
        
        registry_odm_backend.delete(test_id)
        
        # Verify the registry was called to delete the document
        registry_odm_backend.registry.__delitem__.assert_called_once_with(test_id)

    def test_delete_nonexistent_document(self, registry_odm_backend):
        """Test deleting a document that doesn't exist."""
        test_id = "nonexistent-id"
        
        # Mock the registry to raise KeyError for nonexistent document
        registry_odm_backend.registry.__delitem__.side_effect = KeyError(test_id)
        
        with pytest.raises(KeyError):
            registry_odm_backend.delete(test_id)

    def test_all_documents(self, registry_odm_backend):
        """Test retrieving all documents."""
        user1 = create_test_user("John", 30, "john@example.com")
        user2 = create_test_user("Jane", 25, "jane@example.com")
        expected_documents = [user1, user2]
        
        # Mock the registry to return our test documents
        registry_odm_backend.registry.values.return_value = expected_documents
        
        result = registry_odm_backend.all()
        
        # Verify the registry was queried for all values
        registry_odm_backend.registry.values.assert_called_once()
        assert result == expected_documents

    def test_all_documents_empty(self, registry_odm_backend):
        """Test retrieving all documents when registry is empty."""
        # Mock the registry to return empty list
        registry_odm_backend.registry.values.return_value = []
        
        result = registry_odm_backend.all()
        
        registry_odm_backend.registry.values.assert_called_once()
        assert result == []

    def test_crud_workflow(self, registry_odm_backend):
        """Test a complete CRUD workflow."""
        user = create_test_user("Test User", 28, "test@example.com")
        
        # Insert
        user_id = registry_odm_backend.insert(user)
        assert isinstance(user_id, str)
        
        # Get
        registry_odm_backend.registry.__getitem__.return_value = user
        retrieved_user = registry_odm_backend.get(user_id)
        assert retrieved_user == user
        
        # Update
        updated_user = create_test_user("Updated User", 29, "updated@example.com")
        registry_odm_backend.registry.__contains__.return_value = True
        update_success = registry_odm_backend.update(user_id, updated_user)
        assert update_success is True
        
        # Delete
        registry_odm_backend.delete(user_id)
        registry_odm_backend.registry.__delitem__.assert_called_with(user_id)

    def test_multiple_operations(self, registry_odm_backend):
        """Test multiple operations with different document types."""
        # Insert multiple documents
        user1 = create_test_user("Alice", 25, "alice@example.com")
        user2 = create_complex_user("Bob", 30, "bob@example.com")
        
        id1 = registry_odm_backend.insert(user1)
        id2 = registry_odm_backend.insert(user2)
        
        assert id1 != id2  # IDs should be unique
        
        # Mock registry to return our documents
        registry_odm_backend.registry.__getitem__.side_effect = lambda x: user1 if x == id1 else user2
        
        # Retrieve both documents
        retrieved1 = registry_odm_backend.get(id1)
        retrieved2 = registry_odm_backend.get(id2)
        
        assert retrieved1 == user1
        assert retrieved2 == user2

    def test_document_persistence(self, registry_odm_backend):
        """Test that documents persist across operations."""
        user = create_test_user("Persistent User", 35, "persistent@example.com")
        
        # Insert document
        user_id = registry_odm_backend.insert(user)
        
        # Verify document is stored
        registry_odm_backend.registry.__setitem__.assert_called_once()
        stored_doc = registry_odm_backend.registry.__setitem__.call_args[0][1]
        assert stored_doc.name == "Persistent User"
        assert stored_doc.age == 35
        assert stored_doc.email == "persistent@example.com"

    def test_error_handling(self, registry_odm_backend):
        """Test error handling in various scenarios."""
        # Test get with KeyError
        registry_odm_backend.registry.__getitem__.side_effect = KeyError("test")
        with pytest.raises(KeyError):
            registry_odm_backend.get("nonexistent")
        
        # Test delete with KeyError
        registry_odm_backend.registry.__delitem__.side_effect = KeyError("test")
        with pytest.raises(KeyError):
            registry_odm_backend.delete("nonexistent")

    def test_backend_integration(self, mock_registry_backend):
        """Test integration with actual Registry backend."""
        # Create backend with actual registry backend
        backend = RegistryMindtraceODMBackend(backend=mock_registry_backend)
        
        # Test that the registry was initialized with the provided backend
        assert backend.registry is not None
        # The registry should have been created with the mock backend
        # This is tested indirectly through the registry initialization

    def test_default_backend_integration(self):
        """Test integration with default Registry backend."""
        # Create backend with default settings
        backend = RegistryMindtraceODMBackend()
        
        # Test that the registry was initialized
        assert backend.registry is not None
        # The registry should have been created with default settings
        # This is tested indirectly through the registry initialization 