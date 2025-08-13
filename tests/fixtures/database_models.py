"""Shared database models for testing."""

from typing import Annotated
from pydantic import BaseModel, Field
from beanie import Indexed

from mindtrace.database import (
    MindtraceDocument,
    MindtraceRedisDocument,
    UnifiedMindtraceDocument,
)


class UserModel(BaseModel):
    """Test user model for basic Pydantic tests."""
    name: str
    age: int
    email: str


class MongoDocModel(MindtraceDocument):
    """Test MongoDB document model."""
    name: str
    age: int
    email: Annotated[str, Indexed(unique=True)]

    class Settings:
        name = "test_users"
        use_cache = False


class RedisDocModel(MindtraceRedisDocument):
    """Test Redis document model."""
    name: str = Field(index=True)
    age: int = Field(index=True)
    email: str = Field(index=True)

    class Meta:
        global_key_prefix = "test"


class UnifiedDocModel(UnifiedMindtraceDocument):
    """Test unified document model."""
    name: str = Field(description="User's full name")
    age: int = Field(ge=0, le=150, description="User's age")
    email: str = Field(description="User's email address")

    class Meta:
        collection_name = "test_users"
        global_key_prefix = "test"
        use_cache = False
        indexed_fields = ["name", "age", "email"]
        unique_fields = ["email"] 