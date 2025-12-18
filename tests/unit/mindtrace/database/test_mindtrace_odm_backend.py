"""Tests for the abstract base class MindtraceODM."""

import pytest
from pydantic import BaseModel

from mindtrace.database import (
    DocumentNotFoundError,
    MindtraceODM,
)


class UserModel(BaseModel):
    name: str
    age: int
    email: str


# Test concrete implementation of abstract base class
class ConcreteBackend(MindtraceODM):
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


class AsyncConcreteBackend(MindtraceODM):
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


# Tests for abstract base class
class TestMindtraceODM:
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


# Tests for async backend
class TestAsyncMindtraceODM:
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
