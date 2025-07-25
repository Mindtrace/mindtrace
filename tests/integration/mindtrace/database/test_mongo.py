from typing import Annotated, Optional

import pytest
from beanie import Indexed, PydanticObjectId
from pydantic import BaseModel
from pymongo.errors import OperationFailure

from mindtrace.database import DocumentNotFoundError, DuplicateInsertError, MindtraceDocument


class UserDoc(MindtraceDocument):
    name: str
    age: int
    email: Annotated[str, Indexed(unique=True)]

    class Settings:
        name = "users"
        use_cache = False

class UserProjection(BaseModel):
    name: str
    id: Optional[PydanticObjectId] = None

class UserCreate(BaseModel):
    name: str
    age: int
    email: str

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_mongo_backend_crud(mongo_backend):
    """Test basic CRUD operations."""
    user = UserCreate(name="Alice", age=30, email="alice@test.com")
    inserted = await mongo_backend.insert(user)
    fetched = await mongo_backend.get(str(inserted.id))

    assert fetched.name == "Alice"
    assert fetched.age == 30
    assert fetched.email == "alice@test.com"

    all_users = await mongo_backend.all()
    assert len(all_users) >= 1

    await mongo_backend.delete(str(inserted.id))

    with pytest.raises(DocumentNotFoundError):
        await mongo_backend.get(str(inserted.id))

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_mongo_backend_find(mongo_backend):
    """Test find operations with filters."""
    # Insert test data
    users = [
        UserCreate(name="Alice", age=30, email="alice@test.com"),
        UserCreate(name="Bob", age=25, email="bob@test.com"),
        UserCreate(name="Charlie", age=35, email="charlie@test.com"),
    ]
    for user in users:
        await mongo_backend.insert(user)

    # Test find with filter
    young_users = await mongo_backend.find({"age": {"$lt": 30}})
    assert len(young_users) == 1
    assert young_users[0].name == "Bob"

    # Test find with multiple conditions
    adult_users = await mongo_backend.find({"age": {"$gte": 30}})
    assert len(adult_users) == 2
    names = {user.name for user in adult_users}
    assert names == {"Alice", "Charlie"}

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_mongo_backend_aggregate(mongo_backend):
    """Test aggregation operations."""
    # Insert test data
    users = [
        UserCreate(name="Alice", age=30, email="alice@test.com"),
        UserCreate(name="Bob", age=25, email="bob@test.com"),
        UserCreate(name="Charlie", age=35, email="charlie@test.com"),
    ]
    for user in users:
        await mongo_backend.insert(user)

    # Test average age aggregation
    pipeline = [
        {"$group": {"_id": None, "avg_age": {"$avg": "$age"}}}
    ]
    result = await mongo_backend.aggregate(pipeline)
    assert len(result) == 1
    assert result[0]["avg_age"] == 30  # (30 + 25 + 35) / 3 

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_mongo_backend_duplicate_insert(mongo_backend):
    """Test duplicate insert handling."""
    # Insert first user
    user1 = UserCreate(name="Alice", age=30, email="aliceTest@test.com")
    await mongo_backend.insert(user1)

    # Try to insert another user with the same email
    user2 = UserCreate(name="Alice2", age=31, email="aliceTest@test.com")
    with pytest.raises(DuplicateInsertError):
        await mongo_backend.insert(user2)

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_is_async(mongo_backend):
    """Test is_async method."""
    assert mongo_backend.is_async() is True

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_get_raw_model(mongo_backend):
    """Test get_raw_model method and verify Beanie-specific functionality."""
    model_cls = mongo_backend.get_raw_model()
    assert model_cls == UserDoc
    
    # Insert some test data
    users = [
        UserCreate(name="Alice", age=30, email="alice@test.com"),
        UserCreate(name="Bob", age=25, email="bob@test.com"),
        UserCreate(name="Charlie", age=35, email="charlie@test.com"),
    ]
    for user in users:
        await mongo_backend.insert(user)

    # Test Beanie's native query builders
    raw_model = mongo_backend.get_raw_model()
    
    # Test find_one
    bob = await raw_model.find_one(raw_model.name == "Bob")
    assert bob.age == 25
    
    # Test find_many with sorting
    sorted_users = await raw_model.find(
        raw_model.age >= 25
    ).sort(+raw_model.age).to_list()
    assert len(sorted_users) == 3
    assert sorted_users[0].name == "Bob"  # age 25
    assert sorted_users[-1].name == "Charlie"  # age 35
    
    # Test projection using Beanie's projection model
    names_only = await raw_model.find().project(UserProjection).to_list()
    assert all(hasattr(user, 'name') for user in names_only)
    assert all(not hasattr(user, 'age') for user in names_only)
    
    # Test skip and limit
    paged_users = await raw_model.find().skip(1).limit(1).to_list()
    assert len(paged_users) == 1
    
    # Test count
    total_count = await raw_model.find().count()
    assert total_count == 3
    
    # Test exists
    exists = await raw_model.find_one(raw_model.name == "Alice").exists()
    assert exists is True
    
    # Test update_all
    await raw_model.find(raw_model.age < 30).update({"$set": {"age": 26}})
    updated_bob = await raw_model.find_one(raw_model.name == "Bob")
    assert updated_bob.age == 26

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_document_update(mongo_backend):
    """Test document update operations."""
    user = UserCreate(name="Alice", age=30, email="alice@test.com")
    inserted = await mongo_backend.insert(user)
    
    # Update using raw model
    raw_model = mongo_backend.get_raw_model()
    await raw_model.find_one(raw_model.id == inserted.id).update({"$set": {"age": 31}})
    
    updated = await mongo_backend.get(str(inserted.id))
    assert updated.age == 31

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_document_not_found(mongo_backend):
    """Test handling of non-existent document retrieval."""
    with pytest.raises(DocumentNotFoundError):
        await mongo_backend.get("507f1f77bcf86cd799439011")  # Random ObjectId

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_find_invalid_query(mongo_backend):
    """Test find operation with invalid query."""
    # Insert test data
    user = UserCreate(name="Alice", age=30, email="alice@test.com")
    await mongo_backend.insert(user)

    # Test with non-existent field (should return empty list)
    result = await mongo_backend.find({"non_existent_field": "value"})
    assert len(result) == 0

    # Test with invalid operator (should handle gracefully)
    try:
        result = await mongo_backend.find({"age": {"$invalid_operator": 30}})
        assert False, "Should have raised an OperationFailure"
    except OperationFailure:
        # Expected behavior
        pass

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_aggregate_invalid_pipeline(mongo_backend):
    """Test aggregate operation with invalid pipeline."""
    # Insert test data
    user = UserCreate(name="Alice", age=30, email="alice@test.com")
    await mongo_backend.insert(user)

    # Test with empty pipeline (should match all documents)
    result = await mongo_backend.aggregate([{"$match": {}}])
    assert len(result) == 1

    # Test with invalid stage
    try:
        result = await mongo_backend.aggregate([{"$invalid_stage": {"field": "value"}}])
        assert False, "Should have raised an OperationFailure"
    except OperationFailure:
        # Expected behavior
        pass

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_initialize_multiple_calls(mongo_backend):
    """Test multiple initialize calls."""
    # First initialization happens automatically in the fixture
    
    # Call initialize explicitly multiple times
    await mongo_backend.initialize()
    await mongo_backend.initialize()
    
    # Verify we can still perform operations
    user = UserCreate(name="Alice", age=30, email="alice@test.com")
    inserted = await mongo_backend.insert(user)
    assert inserted.name == "Alice" 