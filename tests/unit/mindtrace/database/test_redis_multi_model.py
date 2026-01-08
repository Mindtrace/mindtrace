"""Unit tests for Redis multi-model support."""

from unittest.mock import MagicMock, patch

import pytest
from redis_om import Field

from mindtrace.database import MindtraceRedisDocument, RedisMindtraceODM


class AddressDoc(MindtraceRedisDocument):
    street: str = Field(index=True)
    city: str = Field(index=True)

    class Meta:
        global_key_prefix = "testapp"


class UserDoc(MindtraceRedisDocument):
    name: str = Field(index=True)
    email: str = Field(index=True)
    address_id: str | None = None

    class Meta:
        global_key_prefix = "testapp"


def test_redis_multi_model_initialization():
    """Test Redis ODM initialization with multiple models."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_redis:
        mock_redis.return_value = MagicMock()

        db = RedisMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            redis_url="redis://localhost:6379",
            auto_init=False,
        )

        assert db._models == {"user": UserDoc, "address": AddressDoc}
        assert db.model_cls is None
        assert "user" in db._model_odms
        assert "address" in db._model_odms
        assert db._model_odms["user"].model_cls == UserDoc
        assert db._model_odms["address"].model_cls == AddressDoc


def test_redis_multi_model_attribute_access():
    """Test attribute-based access to models in multi-model mode."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_redis:
        mock_redis.return_value = MagicMock()

        db = RedisMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            redis_url="redis://localhost:6379",
            auto_init=False,
        )

        # Test attribute access
        user_odm = db.user
        address_odm = db.address

        assert user_odm.model_cls == UserDoc
        assert address_odm.model_cls == AddressDoc
        assert user_odm._parent_odm == db
        assert address_odm._parent_odm == db


def test_redis_multi_model_invalid_attribute():
    """Test that accessing invalid attribute raises AttributeError."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_redis:
        mock_redis.return_value = MagicMock()

        db = RedisMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            redis_url="redis://localhost:6379",
            auto_init=False,
        )

        with pytest.raises(AttributeError):
            _ = db.invalid_model


def test_redis_multi_model_cannot_use_direct_insert():
    """Test that direct insert() raises ValueError in multi-model mode."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_redis:
        mock_redis.return_value = MagicMock()

        db = RedisMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            redis_url="redis://localhost:6379",
            auto_init=False,
        )

        with pytest.raises(ValueError, match="Cannot use insert\\(\\) in multi-model mode"):
            db.insert(UserDoc(name="Test", email="test@test.com"))


def test_redis_multi_model_backward_compatibility():
    """Test that single model mode still works (backward compatibility)."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_redis:
        mock_redis.return_value = MagicMock()

        db = RedisMindtraceODM(
            model_cls=UserDoc,
            redis_url="redis://localhost:6379",
            auto_init=False,
        )

        assert db.model_cls == UserDoc
        assert db._models is None
        assert len(db._model_odms) == 0


def test_redis_multi_model_shared_connection():
    """Test that all model ODMs share the same Redis connection."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_redis:
        mock_conn = MagicMock()
        mock_redis.return_value = mock_conn

        db = RedisMindtraceODM(
            models={"user": UserDoc, "address": AddressDoc},
            redis_url="redis://localhost:6379",
            auto_init=False,
        )

        assert db.user.redis == db.redis
        assert db.address.redis == db.redis
        assert db.user.redis == db.address.redis


def test_redis_multi_model_both_model_cls_and_models_error():
    """Test that specifying both model_cls and models raises ValueError."""
    with pytest.raises(ValueError, match="Cannot specify both model_cls and models"):
        RedisMindtraceODM(
            model_cls=UserDoc,
            models={"user": UserDoc},
            redis_url="redis://localhost:6379",
            auto_init=False,
        )


def test_redis_multi_model_empty_models_error():
    """Test that empty models dict raises ValueError."""
    with pytest.raises(ValueError, match="models must be a non-empty dictionary"):
        RedisMindtraceODM(
            models={},
            redis_url="redis://localhost:6379",
            auto_init=False,
        )


def test_redis_multi_model_no_models_error():
    """Test that not specifying any model raises ValueError."""
    with pytest.raises(ValueError, match="Must specify either model_cls or models"):
        RedisMindtraceODM(
            redis_url="redis://localhost:6379",
            auto_init=False,
        )


def test_redis_multi_model_backward_compat_positional_args():
    """Test backward compatibility with old positional argument style."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_redis:
        mock_redis.return_value = MagicMock()

        # Old API: RedisMindtraceODM(model_cls, redis_url)
        # This should still work
        db = RedisMindtraceODM(
            UserDoc,  # model_cls as positional
            "redis://localhost:6379",  # redis_url as positional (passed as models)
            auto_init=False,
        )

        # Should have parsed correctly
        assert db.model_cls == UserDoc
        assert db.redis_url == "redis://localhost:6379"
