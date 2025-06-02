import pytest

# Import shared test models
from .test_crud import UserDoc, UserCreate, UserProjection

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_find_operations(mongo_backend):
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
async def test_aggregation(mongo_backend):
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
    assert result[0]["avg_age"] == 30

@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_advanced_queries(mongo_backend):
    """Test advanced query operations using Beanie's native query builders."""
    # Insert test data
    users = [
        UserCreate(name="Alice", age=30, email="alice@test.com"),
        UserCreate(name="Bob", age=25, email="bob@test.com"),
        UserCreate(name="Charlie", age=35, email="charlie@test.com"),
    ]
    for user in users:
        await mongo_backend.insert(user)

    raw_model = mongo_backend.get_raw_model()
    
    # Test find_one
    bob = await raw_model.find_one(raw_model.name == "Bob")
    assert bob.age == 25
    
    # Test find_many with sorting
    sorted_users = await raw_model.find(
        raw_model.age >= 25
    ).sort(+raw_model.age).to_list()
    assert len(sorted_users) == 3
    assert sorted_users[0].name == "Bob"
    assert sorted_users[-1].name == "Charlie"
    
    # Test projection
    names_only = await raw_model.find().project(UserProjection).to_list()
    assert all(hasattr(user, 'name') for user in names_only)
    assert all(not hasattr(user, 'age') for user in names_only)
    
    # Test pagination
    paged_users = await raw_model.find().skip(1).limit(1).to_list()
    assert len(paged_users) == 1 