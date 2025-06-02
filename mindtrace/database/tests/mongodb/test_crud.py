import pytest
from pydantic import BaseModel
from mindtrace.database import MindtraceDocument
from mindtrace.database import DocumentNotFoundError
from beanie import Indexed, PydanticObjectId
from typing import Optional, Annotated

# Shared test models
class UserDoc(MindtraceDocument):
    name: str
    age: int
    email: Annotated[str, Indexed(unique=True)]

    class Settings:
        name = "users"
        use_cache = False

class UserCreate(BaseModel):
    name: str
    age: int
    email: str

class UserProjection(BaseModel):
    name: str
    id: Optional[PydanticObjectId] = None

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_create(mongo_backend):
    """Test document creation."""
    user = UserCreate(name="Alice", age=30, email="alice@test.com")
    inserted = await mongo_backend.insert(user)
    assert inserted.name == "Alice"
    assert inserted.age == 30
    assert inserted.email == "alice@test.com"

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_read(mongo_backend):
    """Test document retrieval."""
    # Create test data
    user = UserCreate(name="Alice", age=30, email="alice@test.com")
    inserted = await mongo_backend.insert(user)
    
    # Test get by id
    fetched = await mongo_backend.get(str(inserted.id))
    assert fetched.name == "Alice"
    
    # Test get all
    all_users = await mongo_backend.all()
    assert len(all_users) >= 1

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_update(mongo_backend):
    """Test document update."""
    user = UserCreate(name="Alice", age=30, email="alice@test.com")
    inserted = await mongo_backend.insert(user)
    
    # Update using raw model
    raw_model = mongo_backend.get_raw_model()
    await raw_model.find_one(raw_model.id == inserted.id).update({"$set": {"age": 31}})
    
    updated = await mongo_backend.get(str(inserted.id))
    assert updated.age == 31

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_delete(mongo_backend):
    """Test document deletion."""
    user = UserCreate(name="Alice", age=30, email="alice@test.com")
    inserted = await mongo_backend.insert(user)
    
    await mongo_backend.delete(str(inserted.id))
    
    with pytest.raises(DocumentNotFoundError):
        await mongo_backend.get(str(inserted.id)) 