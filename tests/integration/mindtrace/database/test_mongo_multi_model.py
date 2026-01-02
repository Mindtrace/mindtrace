"""Integration tests for MongoDB multi-model support and fetch_links."""

from typing import Optional

import pytest

from mindtrace.database import Link, MindtraceDocument, MongoMindtraceODM
from mindtrace.database.core.exceptions import DocumentNotFoundError


class AddressDoc(MindtraceDocument):
    street: str
    city: str
    state: str
    zip_code: str

    class Settings:
        name = "addresses"
        use_cache = False


class UserDoc(MindtraceDocument):
    name: str
    email: str
    age: int
    address: Optional[Link[AddressDoc]] = None

    class Settings:
        name = "users"
        use_cache = False


@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_mongo_multi_model_crud_operations(mongo_backend, test_db):
    """Test CRUD operations with multi-model mode."""
    # Create multi-model ODM
    db = MongoMindtraceODM(
        models={"user": UserDoc, "address": AddressDoc},
        db_uri="mongodb://localhost:27018",
        db_name="test_db",
        allow_index_dropping=True,
    )
    await db.initialize()

    try:
        # Insert address
        address = AddressDoc(street="123 Main St", city="NYC", state="NY", zip_code="10001")
        inserted_address = await db.address.insert(address)
        assert inserted_address.id is not None
        assert inserted_address.street == "123 Main St"

        # Insert user
        user = UserDoc(name="Alice", email="alice@test.com", age=30)
        inserted_user = await db.user.insert(user)
        assert inserted_user.id is not None
        assert inserted_user.name == "Alice"

        # Get user
        retrieved_user = await db.user.get(str(inserted_user.id))
        assert retrieved_user.name == "Alice"
        assert retrieved_user.email == "alice@test.com"

        # Get address
        retrieved_address = await db.address.get(str(inserted_address.id))
        assert retrieved_address.street == "123 Main St"

        # Update user
        retrieved_user.age = 31
        updated_user = await db.user.update(retrieved_user)
        assert updated_user.age == 31

        # Find users
        users = await db.user.find({"name": "Alice"})
        assert len(users) >= 1
        assert users[0].name == "Alice"

        # Find addresses
        addresses = await db.address.find({"city": "NYC"})
        assert len(addresses) >= 1
        assert addresses[0].city == "NYC"

        # All users
        all_users = await db.user.all()
        assert len(all_users) >= 1

        # All addresses
        all_addresses = await db.address.all()
        assert len(all_addresses) >= 1

        # Delete
        await db.user.delete(str(inserted_user.id))
        await db.address.delete(str(inserted_address.id))

        with pytest.raises(DocumentNotFoundError):
            await db.user.get(str(inserted_user.id))

    finally:
        db.client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_mongo_fetch_links_get(mongo_backend, test_db):
    """Test fetch_links parameter in get() method."""
    db = MongoMindtraceODM(
        models={"user": UserDoc, "address": AddressDoc},
        db_uri="mongodb://localhost:27018",
        db_name="test_db",
        allow_index_dropping=True,
    )
    await db.initialize()

    try:
        # Create address
        address = AddressDoc(street="456 Oak Ave", city="LA", state="CA", zip_code="90001")
        inserted_address = await db.address.insert(address)

        # Create user with linked address
        user = UserDoc(name="Bob", email="bob@test.com", age=25, address=inserted_address)
        inserted_user = await db.user.insert(user)

        # Get without fetch_links (default)
        user_without_links = await db.user.get(str(inserted_user.id))
        assert user_without_links.address is not None
        # Address should be a Link object, not the actual document
        # Beanie Link objects don't have an 'id' attribute directly
        from beanie import Link as BeanieLink

        assert isinstance(user_without_links.address, BeanieLink)

        # Get with fetch_links=True
        user_with_links = await db.user.get(str(inserted_user.id), fetch_links=True)
        assert user_with_links.address is not None
        assert isinstance(user_with_links.address, AddressDoc)
        assert user_with_links.address.street == "456 Oak Ave"
        assert user_with_links.address.city == "LA"

    finally:
        db.client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_mongo_fetch_links_find(mongo_backend, test_db):
    """Test fetch_links parameter in find() method."""
    db = MongoMindtraceODM(
        models={"user": UserDoc, "address": AddressDoc},
        db_uri="mongodb://localhost:27018",
        db_name="test_db",
        allow_index_dropping=True,
    )
    await db.initialize()

    try:
        # Create address
        address = AddressDoc(street="789 Pine St", city="SF", state="CA", zip_code="94102")
        inserted_address = await db.address.insert(address)

        # Create user with linked address
        user = UserDoc(name="Charlie", email="charlie@test.com", age=35, address=inserted_address)
        await db.user.insert(user)

        # Find without fetch_links (default)
        users_without_links = await db.user.find({"name": "Charlie"})
        assert len(users_without_links) >= 1
        assert users_without_links[0].address is not None
        # Address should be a Link object

        # Find with fetch_links=True
        users_with_links = await db.user.find({"name": "Charlie"}, fetch_links=True)
        assert len(users_with_links) >= 1
        assert users_with_links[0].address is not None
        assert isinstance(users_with_links[0].address, AddressDoc)
        assert users_with_links[0].address.street == "789 Pine St"
        assert users_with_links[0].address.city == "SF"

        # Find with Beanie expression and fetch_links
        users_expr = await db.user.find(UserDoc.name == "Charlie", fetch_links=True)
        assert len(users_expr) >= 1
        assert isinstance(users_expr[0].address, AddressDoc)

    finally:
        db.client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_mongo_fetch_links_optional_address(mongo_backend, test_db):
    """Test fetch_links with optional Link field (None)."""
    db = MongoMindtraceODM(
        models={"user": UserDoc, "address": AddressDoc},
        db_uri="mongodb://localhost:27018",
        db_name="test_db",
        allow_index_dropping=True,
    )
    await db.initialize()

    try:
        # Create user without address
        user = UserDoc(name="Dave", email="dave@test.com", age=28, address=None)
        inserted_user = await db.user.insert(user)

        # Get with fetch_links=True (should handle None gracefully)
        user_with_links = await db.user.get(str(inserted_user.id), fetch_links=True)
        assert user_with_links.address is None

        # Find with fetch_links=True
        users = await db.user.find({"name": "Dave"}, fetch_links=True)
        assert len(users) >= 1
        assert users[0].address is None

    finally:
        db.client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_backend", [UserDoc], indirect=True)
async def test_mongo_multi_model_shared_connection(mongo_backend, test_db):
    """Test that multi-model ODMs share the same database connection."""
    db = MongoMindtraceODM(
        models={"user": UserDoc, "address": AddressDoc},
        db_uri="mongodb://localhost:27018",
        db_name="test_db",
        allow_index_dropping=True,
    )
    await db.initialize()

    try:
        # Verify shared client
        assert db.user.client == db.client
        assert db.address.client == db.client
        assert db.user.db_name == db.db_name
        assert db.address.db_name == db.db_name

        # Verify parent reference
        assert db.user._parent_odm == db
        assert db.address._parent_odm == db

    finally:
        db.client.close()
