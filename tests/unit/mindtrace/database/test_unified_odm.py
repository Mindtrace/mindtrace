"""Comprehensive unit tests for Unified ODM backend."""

from typing import Optional, Union
from unittest.mock import MagicMock, patch

import pytest
from pydantic import Field

from mindtrace.database import (
    BackendType,
    Link,
    UnifiedMindtraceDocument,
    UnifiedMindtraceODM,
)


class AddressUnified(UnifiedMindtraceDocument):
    street: str = Field(description="Street address")
    city: str = Field(description="City")

    class Meta:
        collection_name = "addresses"
        global_key_prefix = "testapp"
        indexed_fields = ["city"]


class UserUnified(UnifiedMindtraceDocument):
    name: str = Field(description="User name")
    email: str = Field(description="Email address")
    address: Optional[Link[AddressUnified]] = Field(default=None, description="Linked address")

    class Meta:
        collection_name = "users"
        global_key_prefix = "testapp"
        indexed_fields = ["email", "name"]
        unique_fields = ["email"]


@pytest.mark.asyncio
async def test_unified_multi_model_mongo_models_path():
    """Test unified ODM with mongo_models parameter."""
    with (
        patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_mongo,
        patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_redis,
    ):
        mock_mongo_instance = MagicMock()
        mock_mongo.return_value = mock_mongo_instance
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        # Create mock MongoDB models
        class MongoUser(MagicMock):
            pass

        class MongoAddress(MagicMock):
            pass

        db = UnifiedMindtraceODM(
            mongo_models={"user": MongoUser, "address": MongoAddress},
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        assert db.mongo_backend is not None
        mock_mongo.assert_called_once()


@pytest.mark.asyncio
async def test_unified_multi_model_redis_models_path():
    """Test unified ODM with redis_models parameter."""
    with (
        patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_mongo,
        patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_redis,
    ):
        mock_mongo_instance = MagicMock()
        mock_mongo.return_value = mock_mongo_instance
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        # Create mock Redis models
        class RedisUser(MagicMock):
            pass

        class RedisAddress(MagicMock):
            pass

        db = UnifiedMindtraceODM(
            redis_models={"user": RedisUser, "address": RedisAddress},
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.REDIS,
            auto_init=False,
        )

        assert db.redis_backend is not None
        mock_redis.assert_called_once()


@pytest.mark.asyncio
async def test_unified_convert_objectids_to_strings():
    """Test _convert_objectids_to_strings method."""
    from beanie import PydanticObjectId

    with (
        patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_mongo,
        patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_redis,
    ):
        mock_mongo_instance = MagicMock()
        mock_mongo.return_value = mock_mongo_instance
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        db = UnifiedMindtraceODM(
            unified_model_cls=UserUnified,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        # Test with PydanticObjectId
        oid = PydanticObjectId()
        data = {"id": oid, "name": "Test"}
        result = db._convert_objectids_to_strings(data)
        assert result["id"] == str(oid)
        assert result["name"] == "Test"

        # Test with nested dict
        data = {"user": {"id": oid, "name": "Test"}}
        result = db._convert_objectids_to_strings(data)
        assert result["user"]["id"] == str(oid)

        # Test with list
        data = {"ids": [oid, oid]}
        result = db._convert_objectids_to_strings(data)
        assert all(isinstance(item, str) for item in result["ids"])

        # Test with list of dicts
        data = {"users": [{"id": oid}, {"id": oid}]}
        result = db._convert_objectids_to_strings(data)
        assert all(isinstance(u["id"], str) for u in result["users"])

        # Test with non-dict (should return as-is)
        result = db._convert_objectids_to_strings("not a dict")
        assert result == "not a dict"


@pytest.mark.asyncio
async def test_unified_multi_model_cannot_use_direct_get():
    """Test that direct get() raises ValueError in multi-model mode."""
    with (
        patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_mongo,
        patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_redis,
    ):
        mock_mongo_instance = MagicMock()
        mock_mongo.return_value = mock_mongo_instance
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        db = UnifiedMindtraceODM(
            unified_models={"user": UserUnified, "address": AddressUnified},
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        with pytest.raises(ValueError, match="Cannot use get\\(\\) in multi-model mode"):
            db.get("some_id")


@pytest.mark.asyncio
async def test_unified_multi_model_cannot_use_direct_update():
    """Test that direct update() raises ValueError in multi-model mode."""
    with (
        patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_mongo,
        patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_redis,
    ):
        mock_mongo_instance = MagicMock()
        mock_mongo.return_value = mock_mongo_instance
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        db = UnifiedMindtraceODM(
            unified_models={"user": UserUnified, "address": AddressUnified},
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        user = UserUnified(name="Test", email="test@test.com")
        with pytest.raises(ValueError, match="Cannot use update\\(\\) in multi-model mode"):
            db.update(user)


@pytest.mark.asyncio
async def test_unified_multi_model_cannot_use_direct_delete():
    """Test that direct delete() raises ValueError in multi-model mode."""
    with (
        patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_mongo,
        patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_redis,
    ):
        mock_mongo_instance = MagicMock()
        mock_mongo.return_value = mock_mongo_instance
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        db = UnifiedMindtraceODM(
            unified_models={"user": UserUnified, "address": AddressUnified},
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        with pytest.raises(ValueError, match="Cannot use delete\\(\\) in multi-model mode"):
            db.delete("some_id")


@pytest.mark.asyncio
async def test_unified_multi_model_cannot_use_direct_all():
    """Test that direct all() raises ValueError in multi-model mode."""
    with (
        patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_mongo,
        patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_redis,
    ):
        mock_mongo_instance = MagicMock()
        mock_mongo.return_value = mock_mongo_instance
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        db = UnifiedMindtraceODM(
            unified_models={"user": UserUnified, "address": AddressUnified},
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        with pytest.raises(ValueError, match="Cannot use all\\(\\) in multi-model mode"):
            db.all()


@pytest.mark.asyncio
async def test_unified_multi_model_cannot_use_direct_find():
    """Test that direct find() raises ValueError in multi-model mode."""
    with (
        patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_mongo,
        patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_redis,
    ):
        mock_mongo_instance = MagicMock()
        mock_mongo.return_value = mock_mongo_instance
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        db = UnifiedMindtraceODM(
            unified_models={"user": UserUnified, "address": AddressUnified},
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        with pytest.raises(ValueError, match="Cannot use find\\(\\) in multi-model mode"):
            db.find({"name": "Test"})


@pytest.mark.asyncio
async def test_unified_multi_model_cannot_use_direct_insert_async():
    """Test that direct insert_async() raises ValueError in multi-model mode."""
    with (
        patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_mongo,
        patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_redis,
    ):
        mock_mongo_instance = MagicMock()
        mock_mongo.return_value = mock_mongo_instance
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        db = UnifiedMindtraceODM(
            unified_models={"user": UserUnified, "address": AddressUnified},
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        user = UserUnified(name="Test", email="test@test.com")
        with pytest.raises(ValueError, match="Cannot use insert_async\\(\\) in multi-model mode"):
            await db.insert_async(user)


@pytest.mark.asyncio
async def test_unified_multi_model_cannot_use_direct_get_async():
    """Test that direct get_async() raises ValueError in multi-model mode."""
    with (
        patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_mongo,
        patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_redis,
    ):
        mock_mongo_instance = MagicMock()
        mock_mongo.return_value = mock_mongo_instance
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        db = UnifiedMindtraceODM(
            unified_models={"user": UserUnified, "address": AddressUnified},
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        with pytest.raises(ValueError, match="Cannot use get_async\\(\\) in multi-model mode"):
            await db.get_async("some_id")


@pytest.mark.asyncio
async def test_unified_multi_model_cannot_use_direct_update_async():
    """Test that direct update_async() raises ValueError in multi-model mode."""
    with (
        patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_mongo,
        patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_redis,
    ):
        mock_mongo_instance = MagicMock()
        mock_mongo.return_value = mock_mongo_instance
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        db = UnifiedMindtraceODM(
            unified_models={"user": UserUnified, "address": AddressUnified},
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        user = UserUnified(name="Test", email="test@test.com")
        with pytest.raises(ValueError, match="Cannot use update_async\\(\\) in multi-model mode"):
            await db.update_async(user)


@pytest.mark.asyncio
async def test_unified_multi_model_cannot_use_direct_all_async():
    """Test that direct all_async() raises ValueError in multi-model mode."""
    with (
        patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_mongo,
        patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_redis,
    ):
        mock_mongo_instance = MagicMock()
        mock_mongo.return_value = mock_mongo_instance
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        db = UnifiedMindtraceODM(
            unified_models={"user": UserUnified, "address": AddressUnified},
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        with pytest.raises(ValueError, match="Cannot use all_async\\(\\) in multi-model mode"):
            await db.all_async()


@pytest.mark.asyncio
async def test_unified_multi_model_cannot_use_direct_find_async():
    """Test that direct find_async() raises ValueError in multi-model mode."""
    with (
        patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_mongo,
        patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_redis,
    ):
        mock_mongo_instance = MagicMock()
        mock_mongo.return_value = mock_mongo_instance
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        db = UnifiedMindtraceODM(
            unified_models={"user": UserUnified, "address": AddressUnified},
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        with pytest.raises(ValueError, match="Cannot use find_async\\(\\) in multi-model mode"):
            await db.find_async({"name": "Test"})


@pytest.mark.asyncio
async def test_unified_convert_unified_to_backend_data_dict():
    """Test _convert_unified_to_backend_data with dict input."""
    with (
        patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_mongo,
        patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_redis,
    ):
        mock_mongo_instance = MagicMock()
        mock_mongo.return_value = mock_mongo_instance
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        db = UnifiedMindtraceODM(
            unified_model_cls=UserUnified,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        # Test with dict
        data = {"name": "Test", "email": "test@test.com"}
        result = db._convert_unified_to_backend_data(data)
        assert isinstance(result, dict)
        assert result["name"] == "Test"


@pytest.mark.asyncio
async def test_unified_link_field_direct_link_conversion():
    """Test Link field conversion when it's a direct Link type (not Optional) - covers lines 149-159."""
    from typing import get_args, get_origin

    from beanie import Link as BeanieLink

    class DirectLinkUser(UnifiedMindtraceDocument):
        name: str = Field(description="User name")
        address: Link[AddressUnified] = Field(description="Linked address")

        class Meta:
            collection_name = "direct_link_users"
            global_key_prefix = "testapp"

    # Generate MongoDB model - this should trigger the direct Link conversion path
    mongo_model = DirectLinkUser._auto_generate_mongo_model()

    # Check that the model was generated
    assert mongo_model is not None

    # Check that Link field exists and was converted
    annotations = mongo_model.__annotations__
    assert "address" in annotations
    address_type = annotations["address"]

    # Should be a Link type (may be wrapped)
    origin = get_origin(address_type)
    if origin is BeanieLink or (hasattr(BeanieLink, "__origin__") and origin == BeanieLink.__origin__):
        link_args = get_args(address_type)
        assert len(link_args) > 0


@pytest.mark.asyncio
async def test_unified_convert_objectids_to_strings_with_list_of_dicts():
    """Test _convert_objectids_to_strings with list of dicts containing ObjectIds."""
    from beanie import PydanticObjectId

    with (
        patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_mongo,
        patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_redis,
    ):
        mock_mongo_instance = MagicMock()
        mock_mongo.return_value = mock_mongo_instance
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        db = UnifiedMindtraceODM(
            unified_model_cls=UserUnified,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        # Test with list of dicts containing ObjectIds
        oid1 = PydanticObjectId()
        oid2 = PydanticObjectId()
        data = {"users": [{"id": oid1, "name": "User1"}, {"id": oid2, "name": "User2"}]}
        result = db._convert_objectids_to_strings(data)
        assert all(isinstance(u["id"], str) for u in result["users"])
        assert result["users"][0]["id"] == str(oid1)
        assert result["users"][1]["id"] == str(oid2)


@pytest.mark.asyncio
async def test_unified_convert_objectids_to_strings_with_list_of_objectids():
    """Test _convert_objectids_to_strings with list of ObjectIds."""
    from beanie import PydanticObjectId

    with (
        patch("mindtrace.database.backends.unified_odm.MongoMindtraceODM") as mock_mongo,
        patch("mindtrace.database.backends.unified_odm.RedisMindtraceODM") as mock_redis,
    ):
        mock_mongo_instance = MagicMock()
        mock_mongo.return_value = mock_mongo_instance
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        db = UnifiedMindtraceODM(
            unified_model_cls=UserUnified,
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        # Test with list of ObjectIds
        oid1 = PydanticObjectId()
        oid2 = PydanticObjectId()
        data = {"ids": [oid1, oid2]}
        result = db._convert_objectids_to_strings(data)
        assert all(isinstance(item, str) for item in result["ids"])
        assert result["ids"][0] == str(oid1)
        assert result["ids"][1] == str(oid2)


def test_unified_auto_generate_mongo_model_union_type_direct():
    """Test _auto_generate_mongo_model with direct Union type to hit lines 136-139.

    Lines 136-139 execute when:
    - field_default is ... (no default set)
    - origin is not None
    - origin is Union (direct check at line 135, not just string check)
    - type(None) in args (making it Optional)
    """

    class TestUnified(UnifiedMindtraceDocument):
        name: str
        # Use Union[str, None] directly (not Optional) to test origin is Union check
        description: Union[str, None]  # No default, should trigger Optional detection at lines 136-139

        class Meta:
            collection_name = "test"

    mongo_model = TestUnified._auto_generate_mongo_model()
    assert mongo_model is not None
    # Verify the Union field was handled correctly
    annotations = getattr(mongo_model, "__annotations__", {})
    assert "description" in annotations, "description field should be in annotations"
