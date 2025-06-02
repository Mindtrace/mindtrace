import pytest
from pymongo.errors import OperationFailure
from mindtrace.database import DocumentNotFoundError, DuplicateInsertError

# Import shared test models
from .test_crud import UserDoc, UserCreate

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_duplicate_insert_handling(mongo_backend):
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
async def test_document_not_found(mongo_backend):
    """Test handling of non-existent document retrieval."""
    with pytest.raises(DocumentNotFoundError):
        await mongo_backend.get("507f1f77bcf86cd799439011")  # Random ObjectId

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_invalid_query_handling(mongo_backend):
    """Test handling of invalid queries."""
    # Insert test data
    user = UserCreate(name="Alice", age=30, email="alice@test.com")
    await mongo_backend.insert(user)

    # Test with non-existent field (should return empty list)
    result = await mongo_backend.find({"non_existent_field": "value"})
    assert len(result) == 0

    # Test with invalid operator
    with pytest.raises(OperationFailure):
        await mongo_backend.find({"age": {"$invalid_operator": 30}})

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_invalid_aggregation_handling(mongo_backend):
    """Test handling of invalid aggregation pipelines."""
    # Test with invalid stage
    with pytest.raises(OperationFailure):
        await mongo_backend.aggregate([{"$invalid_stage": {"field": "value"}}]) 