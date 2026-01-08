"""Unit tests for Unified ODM multi-model support and Link fields."""

from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from pydantic import Field

from mindtrace.database import BackendType, Link, UnifiedMindtraceDocument, UnifiedMindtraceODM


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
async def test_unified_multi_model_initialization():
    """Test Unified ODM initialization with multiple models."""
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
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        assert db._unified_models == {"user": UserUnified, "address": AddressUnified}
        assert db.unified_model_cls is None
        assert "user" in db._model_odms
        assert "address" in db._model_odms
        assert db._model_odms["user"].unified_model_cls == UserUnified
        assert db._model_odms["address"].unified_model_cls == AddressUnified


@pytest.mark.asyncio
async def test_unified_multi_model_attribute_access():
    """Test attribute-based access to models in multi-model mode."""
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
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        # Test attribute access
        user_odm = db.user
        address_odm = db.address

        assert user_odm.unified_model_cls == UserUnified
        assert address_odm.unified_model_cls == AddressUnified


@pytest.mark.asyncio
async def test_unified_multi_model_invalid_attribute():
    """Test that accessing invalid attribute raises AttributeError."""
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
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        with pytest.raises(AttributeError):
            _ = db.invalid_model


@pytest.mark.asyncio
async def test_unified_multi_model_both_unified_model_cls_and_models_error():
    """Test that specifying both unified_model_cls and unified_models raises ValueError."""
    with pytest.raises(ValueError, match="Cannot specify both unified_model_cls and unified_models"):
        UnifiedMindtraceODM(
            unified_model_cls=UserUnified,
            unified_models={"user": UserUnified},
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )


@pytest.mark.asyncio
async def test_unified_multi_model_empty_models_error():
    """Test that empty unified_models dict raises ValueError."""
    with pytest.raises(ValueError, match="unified_models must be a non-empty dictionary"):
        UnifiedMindtraceODM(
            unified_models={},
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="test_db",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )


@pytest.mark.asyncio
async def test_unified_link_field_generation():
    """Test that Link fields in unified models are correctly converted to MongoDB models."""
    # Generate MongoDB model from unified model with Link field
    mongo_model = UserUnified._auto_generate_mongo_model()

    # Check that the model was generated
    assert mongo_model is not None

    # Check that Link field exists (it should be converted to Link[MongoModel])
    from beanie import Link as BeanieLink

    annotations = mongo_model.__annotations__

    # The address field should be Optional[Link[MongoAddressModel]]
    assert "address" in annotations
    address_type = annotations["address"]

    # Check that it's a Link type (may be wrapped in Optional/Union)
    from typing import get_args, get_origin

    origin = get_origin(address_type)

    # Should be Union (Optional) containing Link
    assert origin is not None
    args = get_args(address_type)

    # One of the args should be a Link type
    has_link = False
    for arg in args:
        if arg is not type(None):
            arg_origin = get_origin(arg)
            if arg_origin is BeanieLink or (hasattr(BeanieLink, "__origin__") and arg_origin == BeanieLink.__origin__):
                has_link = True
                # Check that the Link points to the MongoDB Address model
                link_args = get_args(arg)
                if link_args:
                    target_model = link_args[0]
                    # Should be the MongoDB version of Address
                    assert target_model.__name__ == "DynamicMongoModel" or "Address" in target_model.__name__
                break

    assert has_link, "Link type not found in address field"


@pytest.mark.asyncio
async def test_unified_link_field_direct_link_type():
    """Test Link field conversion when it's a direct Link type (not Optional)."""
    from pydantic import Field

    from mindtrace.database import Link, UnifiedMindtraceDocument

    class DirectLinkUser(UnifiedMindtraceDocument):
        name: str = Field(description="User name")
        address: Link[AddressUnified] = Field(description="Linked address")

        class Meta:
            collection_name = "direct_link_users"
            global_key_prefix = "testapp"

    # Generate MongoDB model
    mongo_model = DirectLinkUser._auto_generate_mongo_model()

    # Check that the model was generated
    assert mongo_model is not None

    # Check that Link field exists
    annotations = mongo_model.__annotations__
    assert "address" in annotations
    address_type = annotations["address"]

    # Should be a direct Link type (not Optional)
    from typing import get_args, get_origin

    from beanie import Link as BeanieLink

    origin = get_origin(address_type)

    # Should be Link directly or wrapped
    if origin is BeanieLink or (hasattr(BeanieLink, "__origin__") and origin == BeanieLink.__origin__):
        link_args = get_args(address_type)
        assert len(link_args) > 0


@pytest.mark.asyncio
async def test_unified_link_field_caching():
    """Test that generated MongoDB models with Link fields are cached correctly."""
    # Generate model twice
    mongo_model1 = UserUnified._auto_generate_mongo_model()
    mongo_model2 = UserUnified._auto_generate_mongo_model()

    # Should return the same cached model instance
    assert mongo_model1 is mongo_model2


@pytest.mark.asyncio
async def test_unified_multi_model_backward_compatibility():
    """Test that single model mode still works (backward compatibility)."""
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
            redis_url="redis://localhost:6379",
            preferred_backend=BackendType.MONGO,
            auto_init=False,
        )

        assert db.unified_model_cls == UserUnified
        assert db._unified_models is None
        assert len(db._model_odms) == 0
