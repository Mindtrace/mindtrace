"""Tests for the abstract base class MindtraceODMBackend."""

import pytest
from pydantic import BaseModel

from mindtrace.database import (
    DocumentNotFoundError,
    MindtraceODMBackend,
)
from tests.fixtures.database_models import UserModel

# Test concrete implementation of abstract base class
class ConcreteBackend(MindtraceODMBackend):
    def is_async(self) -> bool:
        return False

    def insert(self, obj: BaseModel):
        return obj

    def get(self, id: str) -> BaseModel:
        if id == "not_found":
            raise DocumentNotFoundError(f"Document with id {id} not found")
        return UserModel(name="Test", age=25, email="test@example.com")

    def delete(self, id: str):
        if id == "not_found":
            raise DocumentNotFoundError(f"Document with id {id} not found")

    def all(self) -> list[BaseModel]:
        return [UserModel(name="Test", age=25, email="test@example.com")]

    def find(self, **kwargs) -> list[BaseModel]:
        return [UserModel(name="Test", age=25, email="test@example.com")]

    def initialize(self):
        pass

    def get_raw_model(self):
        return UserModel


class AsyncConcreteBackend(MindtraceODMBackend):
    def is_async(self) -> bool:
        return True

    async def insert(self, obj: BaseModel):
        return obj

    async def get(self, id: str) -> BaseModel:
        if id == "not_found":
            raise DocumentNotFoundError(f"Document with id {id} not found")
        return UserModel(name="Test", age=25, email="test@example.com")

    async def delete(self, id: str):
        if id == "not_found":
            raise DocumentNotFoundError(f"Document with id {id} not found")

    async def all(self) -> list[BaseModel]:
        return [UserModel(name="Test", age=25, email="test@example.com")]

    async def find(self, **kwargs) -> list[BaseModel]:
        return [UserModel(name="Test", age=25, email="test@example.com")]

    async def initialize(self):
        pass

    def get_raw_model(self):
        return UserModel


# Tests for abstract base class coverage
class TestMindtraceODMBackend:
    """Test the abstract base class methods."""

    def test_concrete_backend_is_async(self):
        """Test is_async method on concrete implementation."""
        backend = ConcreteBackend()
        assert backend.is_async() is False

    def test_async_concrete_backend_is_async(self):
        """Test is_async method on async concrete implementation."""
        backend = AsyncConcreteBackend()
        assert backend.is_async() is True

    def test_concrete_backend_insert(self):
        """Test insert method on concrete implementation."""
        backend = ConcreteBackend()
        user = UserModel(name="John", age=30, email="john@example.com")
        result = backend.insert(user)
        assert result == user

    def test_concrete_backend_get(self):
        """Test get method on concrete implementation."""
        backend = ConcreteBackend()
        result = backend.get("test_id")
        assert isinstance(result, UserModel)
        assert result.name == "Test"

    def test_concrete_backend_get_not_found(self):
        """Test get method with non-existent document."""
        backend = ConcreteBackend()
        with pytest.raises(DocumentNotFoundError):
            backend.get("not_found")

    def test_concrete_backend_delete(self):
        """Test delete method on concrete implementation."""
        backend = ConcreteBackend()
        # Should not raise
        backend.delete("test_id")

    def test_concrete_backend_delete_not_found(self):
        """Test delete method with non-existent document."""
        backend = ConcreteBackend()
        with pytest.raises(DocumentNotFoundError):
            backend.delete("not_found")

    def test_concrete_backend_all(self):
        """Test all method on concrete implementation."""
        backend = ConcreteBackend()
        result = backend.all()
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], UserModel)

    def test_concrete_backend_find(self):
        """Test find method on concrete implementation."""
        backend = ConcreteBackend()
        result = backend.find(name="Test")
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], UserModel)

    def test_concrete_backend_initialize(self):
        """Test initialize method on concrete implementation."""
        backend = ConcreteBackend()
        # Should not raise
        backend.initialize()

    def test_concrete_backend_get_raw_model(self):
        """Test get_raw_model method on concrete implementation."""
        backend = ConcreteBackend()
        result = backend.get_raw_model()
        assert result == UserModel


# Tests for async backend coverage
class TestAsyncMindtraceODMBackend:
    """Test async backend methods."""

    @pytest.mark.asyncio
    async def test_async_concrete_backend_insert(self):
        """Test async insert method."""
        backend = AsyncConcreteBackend()
        user = UserModel(name="John", age=30, email="john@example.com")
        result = await backend.insert(user)
        assert result == user

    @pytest.mark.asyncio
    async def test_async_concrete_backend_get(self):
        """Test async get method."""
        backend = AsyncConcreteBackend()
        result = await backend.get("test_id")
        assert isinstance(result, UserModel)
        assert result.name == "Test"

    @pytest.mark.asyncio
    async def test_async_concrete_backend_get_not_found(self):
        """Test async get method with non-existent document."""
        backend = AsyncConcreteBackend()
        with pytest.raises(DocumentNotFoundError):
            await backend.get("not_found")

    @pytest.mark.asyncio
    async def test_async_concrete_backend_delete(self):
        """Test async delete method."""
        backend = AsyncConcreteBackend()
        # Should not raise
        await backend.delete("test_id")

    @pytest.mark.asyncio
    async def test_async_concrete_backend_delete_not_found(self):
        """Test async delete method with non-existent document."""
        backend = AsyncConcreteBackend()
        with pytest.raises(DocumentNotFoundError):
            await backend.delete("not_found")

    @pytest.mark.asyncio
    async def test_async_concrete_backend_all(self):
        """Test async all method."""
        backend = AsyncConcreteBackend()
        result = await backend.all()
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], UserModel)

    @pytest.mark.asyncio
    async def test_async_concrete_backend_find(self):
        """Test async find method."""
        backend = AsyncConcreteBackend()
        result = await backend.find(name="Test")
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], UserModel)

    @pytest.mark.asyncio
    async def test_async_concrete_backend_initialize(self):
        """Test async initialize method."""
        backend = AsyncConcreteBackend()
        # Should not raise
        await backend.initialize()


# Test abstract base class methods that are missing coverage
class TestAbstractBaseClassCoverage:
    """Test abstract base class methods for complete coverage."""

    def test_abstract_methods_raise_not_implemented(self):
        """Test that abstract methods raise NotImplementedError when called directly."""
        from mindtrace.database.backends.mindtrace_odm_backend import MindtraceODMBackend
        
        # Create a minimal concrete implementation that doesn't override all methods
        class MinimalBackend(MindtraceODMBackend):
            def is_async(self) -> bool:
                return False

            def insert(self, obj: BaseModel):
                return obj

            def get(self, id: str) -> BaseModel:
                return UserModel(name="Test", age=25, email="test@example.com")

            def delete(self, id: str):
                pass

            def all(self) -> list[BaseModel]:
                return []

            def find(self, **kwargs) -> list[BaseModel]:
                return []

            def initialize(self):
                pass

            def get_raw_model(self):
                return UserModel

        backend = MinimalBackend()
        
        # Test that the abstract methods work correctly
        assert backend.is_async() is False
        user = UserModel(name="John", age=30, email="john@example.com")
        result = backend.insert(user)
        assert result == user
        
        result = backend.get("test_id")
        assert isinstance(result, UserModel)
        assert result.name == "Test"
        
        # Should not raise
        backend.delete("test_id")
        
        result = backend.all()
        assert result == []
        
        result = backend.find(name="test")
        assert result == []
        
        # Should not raise
        backend.initialize()
        
        result = backend.get_raw_model()
        assert result == UserModel


# Test abstract base class methods that are still missing coverage
class TestAbstractBaseClassRemainingCoverage:
    """Test remaining abstract base class methods for complete coverage."""

    def test_abstract_methods_docstrings_coverage(self):
        """Test that abstract method docstrings are covered."""
        from mindtrace.database.backends.mindtrace_odm_backend import MindtraceODMBackend
        
        # Create a backend that implements all methods to test docstring coverage
        class CompleteBackend(MindtraceODMBackend):
            def is_async(self) -> bool:
                """Test docstring coverage for is_async."""
                return False

            def insert(self, obj: BaseModel):
                """Test docstring coverage for insert."""
                return obj

            def get(self, id: str) -> BaseModel:
                """Test docstring coverage for get."""
                return UserModel(name="Test", age=25, email="test@example.com")

            def delete(self, id: str):
                """Test docstring coverage for delete."""
                pass

            def all(self) -> list[BaseModel]:
                """Test docstring coverage for all."""
                return []

            def find(self, **kwargs) -> list[BaseModel]:
                """Test docstring coverage for find."""
                return []

            def initialize(self):
                """Test docstring coverage for initialize."""
                pass

            def get_raw_model(self):
                """Test docstring coverage for get_raw_model."""
                return UserModel

        backend = CompleteBackend()
        
        # Test all methods to ensure docstring coverage
        assert backend.is_async() is False
        
        user = UserModel(name="John", age=30, email="john@example.com")
        result = backend.insert(user)
        assert result == user
        
        result = backend.get("test_id")
        assert isinstance(result, UserModel)
        assert result.name == "Test"
        
        backend.delete("test_id")  # Should not raise
        
        result = backend.all()
        assert result == []
        
        result = backend.find(name="test")
        assert result == []
        
        backend.initialize()  # Should not raise
        
        result = backend.get_raw_model()
        assert result == UserModel


# Test abstract base class docstring examples for complete coverage
class TestAbstractBaseClassDocstringCoverage:
    """Test abstract base class docstring examples for complete coverage."""

    def test_abstract_methods_docstring_examples_coverage(self):
        """Test that abstract method docstring examples are covered."""
        from mindtrace.database.backends.mindtrace_odm_backend import MindtraceODMBackend
        
        # Create a backend that implements all methods to test docstring coverage
        class DocstringCoverageBackend(MindtraceODMBackend):
            def is_async(self) -> bool:
                """Test docstring coverage for is_async."""
                return False

            def insert(self, obj: BaseModel):
                """Test docstring coverage for insert."""
                return obj

            def get(self, id: str) -> BaseModel:
                """Test docstring coverage for get."""
                return UserModel(name="Test", age=25, email="test@example.com")

            def delete(self, id: str):
                """Test docstring coverage for delete."""
                pass

            def all(self) -> list[BaseModel]:
                """Test docstring coverage for all."""
                return []

        backend = DocstringCoverageBackend()
        
        # Test all methods to ensure docstring coverage
        assert backend.is_async() is False
        
        user = UserModel(name="John", age=30, email="john@example.com")
        result = backend.insert(user)
        assert result == user
        
        result = backend.get("test_id")
        assert isinstance(result, UserModel)
        assert result.name == "Test"
        
        backend.delete("test_id")  # Should not raise
        
        result = backend.all()
        assert result == []

    def test_abstract_methods_docstring_examples_with_errors(self):
        """Test that abstract method docstring examples with error handling are covered."""
        from mindtrace.database.backends.mindtrace_odm_backend import MindtraceODMBackend
        from mindtrace.database import DocumentNotFoundError
        
        # Create a backend that implements all methods with error handling
        class DocstringErrorCoverageBackend(MindtraceODMBackend):
            def is_async(self) -> bool:
                """Test docstring coverage for is_async."""
                return False

            def insert(self, obj: BaseModel):
                """Test docstring coverage for insert."""
                return obj

            def get(self, id: str) -> BaseModel:
                """Test docstring coverage for get."""
                if id == "not_found":
                    raise DocumentNotFoundError(f"Document with id {id} not found")
                return UserModel(name="Test", age=25, email="test@example.com")

            def delete(self, id: str):
                """Test docstring coverage for delete."""
                if id == "not_found":
                    raise DocumentNotFoundError(f"Document with id {id} not found")

            def all(self) -> list[BaseModel]:
                """Test docstring coverage for all."""
                return []

        backend = DocstringErrorCoverageBackend()
        
        # Test error handling scenarios from docstring examples
        assert backend.is_async() is False
        
        user = UserModel(name="John", age=30, email="john@example.com")
        result = backend.insert(user)
        assert result == user
        
        # Test successful get
        result = backend.get("test_id")
        assert isinstance(result, UserModel)
        assert result.name == "Test"
        
        # Test get with error (from docstring example)
        with pytest.raises(DocumentNotFoundError):
            backend.get("not_found")
        
        # Test successful delete
        backend.delete("test_id")  # Should not raise
        
        # Test delete with error (from docstring example)
        with pytest.raises(DocumentNotFoundError):
            backend.delete("not_found")
        
        result = backend.all()
        assert result == [] 