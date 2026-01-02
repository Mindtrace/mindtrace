"""Integration tests for Unified ODM multi-model support and Link fields."""

from typing import Optional

import pytest
from pydantic import Field

from mindtrace.database import BackendType, Link, UnifiedMindtraceDocument, UnifiedMindtraceODM
from mindtrace.database.core.exceptions import DocumentNotFoundError


class AddressUnified(UnifiedMindtraceDocument):
    street: str = Field(description="Street address")
    city: str = Field(description="City")
    state: str = Field(description="State")
    zip_code: str = Field(description="Zip code")

    class Meta:
        collection_name = "addresses"
        global_key_prefix = "testapp"
        indexed_fields = ["city", "state"]


class UserUnified(UnifiedMindtraceDocument):
    name: str = Field(description="User name")
    email: str = Field(description="Email address")
    age: int = Field(ge=0, description="Age")
    address: Optional[Link[AddressUnified]] = Field(default=None, description="Linked address")

    class Meta:
        collection_name = "users"
        global_key_prefix = "testapp"
        indexed_fields = ["email", "name"]
        unique_fields = ["email"]


@pytest.mark.asyncio
async def test_unified_multi_model_mongo_crud(mongo_client):
    """Test CRUD operations with unified multi-model mode using MongoDB."""
    db = UnifiedMindtraceODM(
        unified_models={"user": UserUnified, "address": AddressUnified},
        mongo_db_uri="mongodb://localhost:27018",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
        allow_index_dropping=True,
    )

    try:
        # Insert address
        address = AddressUnified(street="123 Main St", city="NYC", state="NY", zip_code="10001")
        inserted_address = await db.address.insert_async(address)
        assert inserted_address.id is not None
        assert inserted_address.street == "123 Main St"

        # Insert user
        user = UserUnified(name="Alice", email="alice@test.com", age=30)
        inserted_user = await db.user.insert_async(user)
        assert inserted_user.id is not None
        assert inserted_user.name == "Alice"

        # Get user
        retrieved_user = await db.user.get_async(str(inserted_user.id))
        assert retrieved_user.name == "Alice"
        assert retrieved_user.email == "alice@test.com"

        # Get address
        retrieved_address = await db.address.get_async(str(inserted_address.id))
        assert retrieved_address.street == "123 Main St"

        # Update user
        retrieved_user.age = 31
        updated_user = await db.user.update_async(retrieved_user)
        assert updated_user.age == 31

        # Find users
        users = await db.user.find_async({"name": "Alice"})
        assert len(users) >= 1
        assert users[0].name == "Alice"

        # All users
        all_users = await db.user.all_async()
        assert len(all_users) >= 1

        # All addresses
        all_addresses = await db.address.all_async()
        assert len(all_addresses) >= 1

        # Delete
        await db.user.delete_async(str(inserted_user.id))
        await db.address.delete_async(str(inserted_address.id))

        with pytest.raises(DocumentNotFoundError):
            await db.user.get_async(str(inserted_user.id))

    finally:
        if db.has_mongo_backend():
            db.get_mongo_backend().client.close()


@pytest.mark.asyncio
async def test_unified_link_field_mongo_fetch_links(mongo_client):
    """Test Link fields with fetch_links in unified ODM using MongoDB."""
    db = UnifiedMindtraceODM(
        unified_models={"user": UserUnified, "address": AddressUnified},
        mongo_db_uri="mongodb://localhost:27018",
        mongo_db_name="test_db",
        preferred_backend=BackendType.MONGO,
        allow_index_dropping=True,
    )

    try:
        # Create address
        address = AddressUnified(street="456 Oak Ave", city="LA", state="CA", zip_code="90001")
        inserted_address = await db.address.insert_async(address)

        # Get MongoDB document for linking (Beanie requires MongoDB Document instances)
        address_mongo = await db.address.get_async(inserted_address.id)

        # Create user with linked address using MongoDB backend directly
        user_data = {
            "name": "Bob",
            "email": "bob@test.com",
            "age": 25,
            "address": address_mongo,  # Beanie Link requires MongoDB Document instance
        }
        inserted_user = await db.user.get_mongo_backend().insert(user_data)

        # Get without fetch_links (default)
        user_without_links = await db.user.get_async(str(inserted_user.id))
        assert user_without_links.address is not None

        # Get with fetch_links=True
        user_with_links = await db.user.get_async(str(inserted_user.id), fetch_links=True)
        assert user_with_links.address is not None
        # Should be the actual Address document
        assert hasattr(user_with_links.address, "street")
        assert user_with_links.address.street == "456 Oak Ave"
        assert user_with_links.address.city == "LA"

        # Find with fetch_links
        users = await db.user.find_async({"name": "Bob"}, fetch_links=True)
        assert len(users) >= 1
        assert users[0].address is not None
        assert users[0].address.street == "456 Oak Ave"

    finally:
        if db.has_mongo_backend():
            db.get_mongo_backend().client.close()


@pytest.mark.asyncio
async def test_unified_multi_model_redis_crud(redis_client):
    """Test CRUD operations with unified multi-model mode using Redis."""
    db = UnifiedMindtraceODM(
        unified_models={"user": UserUnified, "address": AddressUnified},
        redis_url="redis://localhost:6380",
        preferred_backend=BackendType.REDIS,
    )

    try:
        # Insert address (sync - native for Redis)
        address = AddressUnified(street="789 Pine St", city="SF", state="CA", zip_code="94102")
        inserted_address = db.address.insert(address)
        assert inserted_address.id is not None
        assert inserted_address.street == "789 Pine St"

        # Insert user (async wrapper)
        user = UserUnified(name="Charlie", email="charlie@test.com", age=35)
        inserted_user = await db.user.insert_async(user)
        assert inserted_user.id is not None
        assert inserted_user.name == "Charlie"

        # Get user (sync)
        retrieved_user = db.user.get(inserted_user.id)
        assert retrieved_user.name == "Charlie"

        # Get address (async)
        retrieved_address = await db.address.get_async(inserted_address.id)
        assert retrieved_address.street == "789 Pine St"

        # Update user
        retrieved_user.age = 36
        updated_user = await db.user.update_async(retrieved_user)
        assert updated_user.age == 36

        # Find users
        users = db.user.find({"name": "Charlie"})
        assert len(users) >= 1
        assert users[0].name == "Charlie"

        # All users
        all_users = db.user.all()
        assert len(all_users) >= 1

        # All addresses
        all_addresses = await db.address.all_async()
        assert len(all_addresses) >= 1

        # Delete
        db.user.delete(inserted_user.id)
        db.address.delete(inserted_address.id)

        with pytest.raises(DocumentNotFoundError):
            db.user.get(inserted_user.id)

    finally:
        if db.has_redis_backend():
            db.get_redis_backend().redis.close()


@pytest.mark.asyncio
async def test_unified_multi_model_backend_switching(mongo_client, redis_client):
    """Test switching backends with multi-model mode."""
    db = UnifiedMindtraceODM(
        unified_models={"user": UserUnified, "address": AddressUnified},
        mongo_db_uri="mongodb://localhost:27018",
        mongo_db_name="test_db",
        redis_url="redis://localhost:6380",
        preferred_backend=BackendType.MONGO,
        allow_index_dropping=True,
    )

    try:
        # Insert in MongoDB
        user_mongo = UserUnified(name="MongoUser", email="mongo@test.com", age=30)
        inserted_mongo = await db.user.insert_async(user_mongo)
        assert inserted_mongo.id is not None

        # Switch to Redis
        db.switch_backend(BackendType.REDIS)
        assert db.get_current_backend_type() == BackendType.REDIS

        # Insert in Redis
        user_redis = UserUnified(name="RedisUser", email="redis@test.com", age=25)
        inserted_redis = await db.user.insert_async(user_redis)
        assert inserted_redis.id is not None

        # Data should be isolated
        redis_users = await db.user.all_async()
        assert len(redis_users) >= 1
        assert any(u.name == "RedisUser" for u in redis_users)

        # Switch back to MongoDB
        db.switch_backend(BackendType.MONGO)
        mongo_users = await db.user.all_async()
        assert len(mongo_users) >= 1
        assert any(u.name == "MongoUser" for u in mongo_users)

    finally:
        if db.has_mongo_backend():
            db.get_mongo_backend().client.close()
        if db.has_redis_backend():
            db.get_redis_backend().redis.close()
