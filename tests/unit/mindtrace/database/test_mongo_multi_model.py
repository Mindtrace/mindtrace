"""Unit tests for MongoDB multi-model support."""

from typing import Optional
from unittest.mock import patch

import pytest

from mindtrace.database import Link, MindtraceDocument, MongoMindtraceODM


class AddressDoc(MindtraceDocument):
    street: str
    city: str

    class Settings:
        name = "addresses"
        use_cache = False


class UserDoc(MindtraceDocument):
    name: str
    email: str
    address: Optional[Link[AddressDoc]] = None

    class Settings:
        name = "users"
        use_cache = False


@pytest.mark.asyncio
async def test_mongo_multi_model_initialization():
    """Test MongoDB ODM initialization with multiple models."""
    with patch("mindtrace.database.backends.mongo_odm.init_beanie"):
        db = MongoMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            db_uri="mongodb://localhost:27017",
            db_name="test_db",
            auto_init=False,
        )

        assert db._models == {"user": UserDoc, "address": AddressDoc}
        assert db.model_cls is None
        assert "user" in db._model_odms
        assert "address" in db._model_odms
        assert db._model_odms["user"].model_cls == UserDoc
        assert db._model_odms["address"].model_cls == AddressDoc


@pytest.mark.asyncio
async def test_mongo_multi_model_attribute_access():
    """Test attribute-based access to models in multi-model mode."""
    with patch("mindtrace.database.backends.mongo_odm.init_beanie"):
        db = MongoMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            db_uri="mongodb://localhost:27017",
            db_name="test_db",
            auto_init=False,
        )

        # Test attribute access
        user_odm = db.user
        address_odm = db.address

        assert user_odm.model_cls == UserDoc
        assert address_odm.model_cls == AddressDoc
        assert user_odm._parent_odm == db
        assert address_odm._parent_odm == db


@pytest.mark.asyncio
async def test_mongo_multi_model_invalid_attribute():
    """Test that accessing invalid attribute raises AttributeError."""
    with patch("mindtrace.database.backends.mongo_odm.init_beanie"):
        db = MongoMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            db_uri="mongodb://localhost:27017",
            db_name="test_db",
            auto_init=False,
        )

        with pytest.raises(AttributeError):
            _ = db.invalid_model


@pytest.mark.asyncio
async def test_mongo_multi_model_initialization_delegation():
    """Test that child ODMs delegate initialization to parent."""
    with patch("mindtrace.database.backends.mongo_odm.init_beanie") as mock_init:
        db = MongoMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            db_uri="mongodb://localhost:27017",
            db_name="test_db",
            auto_init=False,
        )

        # Initialize via child ODM
        await db.user.initialize()

        # Should have called init_beanie with both models
        assert mock_init.called
        call_args = mock_init.call_args
        document_models = call_args[1]["document_models"]
        assert UserDoc in document_models
        assert AddressDoc in document_models


@pytest.mark.asyncio
async def test_mongo_multi_model_cannot_use_direct_insert():
    """Test that direct insert() raises ValueError in multi-model mode."""
    with patch("mindtrace.database.backends.mongo_odm.init_beanie"):
        db = MongoMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            db_uri="mongodb://localhost:27017",
            db_name="test_db",
            auto_init=False,
        )

        # Use a dict instead of creating a Beanie document (which requires initialization)
        with pytest.raises(ValueError, match="Cannot use insert\\(\\) in multi-model mode"):
            await db.insert({"name": "Test", "email": "test@test.com"})


@pytest.mark.asyncio
async def test_mongo_multi_model_backward_compatibility():
    """Test that single model mode still works (backward compatibility)."""
    with patch("mindtrace.database.backends.mongo_odm.init_beanie"):
        db = MongoMindtraceODM(
            model_cls=UserDoc,
            db_uri="mongodb://localhost:27017",
            db_name="test_db",
            auto_init=False,
        )

        assert db.model_cls == UserDoc
        assert db._models is None
        assert len(db._model_odms) == 0


@pytest.mark.asyncio
async def test_mongo_multi_model_shared_client():
    """Test that all model ODMs share the same client instance."""
    with patch("mindtrace.database.backends.mongo_odm.init_beanie"):
        db = MongoMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            db_uri="mongodb://localhost:27017",
            db_name="test_db",
            auto_init=False,
        )

        assert db.user.client == db.client
        assert db.address.client == db.client
        assert db.user.client == db.address.client


@pytest.mark.asyncio
async def test_mongo_multi_model_both_model_cls_and_models_error():
    """Test that specifying both model_cls and models raises ValueError."""
    with pytest.raises(ValueError, match="Cannot specify both model_cls and models"):
        MongoMindtraceODM(
            model_cls=UserDoc,
            models={"user": UserDoc},
            db_uri="mongodb://localhost:27017",
            db_name="test_db",
            auto_init=False,
        )


@pytest.mark.asyncio
async def test_mongo_multi_model_empty_models_error():
    """Test that empty models dict raises ValueError."""
    with pytest.raises(ValueError, match="models must be a non-empty dictionary"):
        MongoMindtraceODM(
            models={},
            db_uri="mongodb://localhost:27017",
            db_name="test_db",
            auto_init=False,
        )


@pytest.mark.asyncio
async def test_mongo_multi_model_no_models_error():
    """Test that not specifying any model raises ValueError."""
    with pytest.raises(ValueError, match="Must specify either model_cls or models"):
        MongoMindtraceODM(
            db_uri="mongodb://localhost:27017",
            db_name="test_db",
            auto_init=False,
        )


@pytest.mark.asyncio
async def test_mongo_multi_model_backward_compat_positional_args():
    """Test backward compatibility with old positional argument style."""
    with patch("mindtrace.database.backends.mongo_odm.init_beanie"):
        # Old API: MongoMindtraceODM(model_cls, db_uri, db_name)
        # This should still work
        db = MongoMindtraceODM(
            UserDoc,  # model_cls as positional
            "mongodb://localhost:27017",  # db_uri as positional (passed as models)
            "test_db",  # db_name as positional (passed as db_uri)
            auto_init=False,
        )

        # Should have parsed correctly
        assert db.model_cls == UserDoc
        assert db.db_name == "test_db"


@pytest.mark.asyncio
async def test_mongo_multi_model_missing_db_uri_error():
    """Test that missing db_uri raises ValueError."""
    with pytest.raises(ValueError, match="db_uri and db_name are required"):
        MongoMindtraceODM(
            models={"user": UserDoc},
            db_uri="",
            db_name="test_db",
            auto_init=False,
        )


@pytest.mark.asyncio
async def test_mongo_multi_model_cannot_use_direct_get():
    """Test that direct get() raises ValueError in multi-model mode."""
    with patch("mindtrace.database.backends.mongo_odm.init_beanie"):
        db = MongoMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            db_uri="mongodb://localhost:27017",
            db_name="test_db",
            auto_init=False,
        )

        with pytest.raises(ValueError, match="Cannot use get\\(\\) in multi-model mode"):
            await db.get("some_id")


@pytest.mark.asyncio
async def test_mongo_multi_model_cannot_use_direct_update():
    """Test that direct update() raises ValueError in multi-model mode."""
    with patch("mindtrace.database.backends.mongo_odm.init_beanie"):
        db = MongoMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            db_uri="mongodb://localhost:27017",
            db_name="test_db",
            auto_init=False,
        )

        with pytest.raises(ValueError, match="Cannot use update\\(\\) in multi-model mode"):
            await db.update({"name": "Test", "email": "test@test.com"})


@pytest.mark.asyncio
async def test_mongo_multi_model_cannot_use_direct_delete():
    """Test that direct delete() raises ValueError in multi-model mode."""
    with patch("mindtrace.database.backends.mongo_odm.init_beanie"):
        db = MongoMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            db_uri="mongodb://localhost:27017",
            db_name="test_db",
            auto_init=False,
        )

        with pytest.raises(ValueError, match="Cannot use delete\\(\\) in multi-model mode"):
            await db.delete("some_id")


@pytest.mark.asyncio
async def test_mongo_multi_model_cannot_use_direct_all():
    """Test that direct all() raises ValueError in multi-model mode."""
    with patch("mindtrace.database.backends.mongo_odm.init_beanie"):
        db = MongoMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            db_uri="mongodb://localhost:27017",
            db_name="test_db",
            auto_init=False,
        )

        with pytest.raises(ValueError, match="Cannot use all\\(\\) in multi-model mode"):
            await db.all()


@pytest.mark.asyncio
async def test_mongo_multi_model_cannot_use_direct_find():
    """Test that direct find() raises ValueError in multi-model mode."""
    with patch("mindtrace.database.backends.mongo_odm.init_beanie"):
        db = MongoMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            db_uri="mongodb://localhost:27017",
            db_name="test_db",
            auto_init=False,
        )

        with pytest.raises(ValueError, match="Cannot use find\\(\\) in multi-model mode"):
            await db.find({"name": "Test"})


@pytest.mark.asyncio
async def test_mongo_multi_model_cannot_use_direct_get_raw_model():
    """Test that direct get_raw_model() raises ValueError in multi-model mode."""
    with patch("mindtrace.database.backends.mongo_odm.init_beanie"):
        db = MongoMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            db_uri="mongodb://localhost:27017",
            db_name="test_db",
            auto_init=False,
        )

        with pytest.raises(ValueError, match="Cannot use get_raw_model\\(\\) in multi-model mode"):
            db.get_raw_model()
