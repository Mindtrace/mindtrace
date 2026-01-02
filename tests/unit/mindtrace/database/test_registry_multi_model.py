"""Unit tests for Registry multi-model support."""

import pytest
from pydantic import BaseModel

from mindtrace.database import RegistryMindtraceODM


class UserDoc(BaseModel):
    name: str
    email: str


class AddressDoc(BaseModel):
    street: str
    city: str


def test_registry_multi_model_initialization():
    """Test Registry ODM initialization with multiple models."""
    db = RegistryMindtraceODM(
        models={"user": UserDoc, "address": AddressDoc},
    )

    assert db._models == {"user": UserDoc, "address": AddressDoc}
    assert db.model_cls is None
    assert "user" in db._model_odms
    assert "address" in db._model_odms
    assert db._model_odms["user"].model_cls == UserDoc
    assert db._model_odms["address"].model_cls == AddressDoc


def test_registry_multi_model_attribute_access():
    """Test attribute-based access to models in multi-model mode."""
    db = RegistryMindtraceODM(
        models={"user": UserDoc, "address": AddressDoc},
    )

    # Test attribute access
    user_odm = db.user
    address_odm = db.address

    assert user_odm.model_cls == UserDoc
    assert address_odm.model_cls == AddressDoc


def test_registry_multi_model_invalid_attribute():
    """Test that accessing invalid attribute raises AttributeError."""
    db = RegistryMindtraceODM(
        models={"user": UserDoc, "address": AddressDoc},
    )

    with pytest.raises(AttributeError):
        _ = db.invalid_model


def test_registry_multi_model_cannot_use_direct_insert():
    """Test that direct insert() raises ValueError in multi-model mode."""
    db = RegistryMindtraceODM(
        models={"user": UserDoc, "address": AddressDoc},
    )

    with pytest.raises(ValueError, match="Cannot use insert\\(\\) in multi-model mode"):
        db.insert(UserDoc(name="Test", email="test@test.com"))


def test_registry_multi_model_backward_compatibility():
    """Test that single model mode still works (backward compatibility)."""
    db = RegistryMindtraceODM(
        model_cls=UserDoc,
    )

    assert db.model_cls == UserDoc
    assert db._models is None
    assert len(db._model_odms) == 0


def test_registry_multi_model_shared_registry():
    """Test that all model ODMs share the same registry instance."""
    db = RegistryMindtraceODM(
        models={"user": UserDoc, "address": AddressDoc},
    )

    assert db.user.registry == db.registry
    assert db.address.registry == db.registry
    assert db.user.registry == db.address.registry


def test_registry_multi_model_both_model_cls_and_models_error():
    """Test that specifying both model_cls and models raises ValueError."""
    with pytest.raises(ValueError, match="Cannot specify both model_cls and models"):
        RegistryMindtraceODM(
            model_cls=UserDoc,
            models={"user": UserDoc},
        )


def test_registry_multi_model_empty_models_error():
    """Test that empty models dict raises ValueError."""
    with pytest.raises(ValueError, match="models must be a non-empty dictionary"):
        RegistryMindtraceODM(
            models={},
        )


def test_registry_multi_model_cannot_use_direct_get():
    """Test that direct get() raises ValueError in multi-model mode."""
    db = RegistryMindtraceODM(
        models={"user": UserDoc, "address": AddressDoc},
    )

    with pytest.raises(ValueError, match="Cannot use get\\(\\) in multi-model mode"):
        db.get("some_id")


def test_registry_multi_model_cannot_use_direct_update():
    """Test that direct update() raises ValueError in multi-model mode."""
    db = RegistryMindtraceODM(
        models={"user": UserDoc, "address": AddressDoc},
    )

    with pytest.raises(ValueError, match="Cannot use update\\(\\) in multi-model mode"):
        db.update(UserDoc(name="Test", email="test@test.com"))


def test_registry_multi_model_cannot_use_direct_delete():
    """Test that direct delete() raises ValueError in multi-model mode."""
    db = RegistryMindtraceODM(
        models={"user": UserDoc, "address": AddressDoc},
    )

    with pytest.raises(ValueError, match="Cannot use delete\\(\\) in multi-model mode"):
        db.delete("some_id")


def test_registry_multi_model_cannot_use_direct_all():
    """Test that direct all() raises ValueError in multi-model mode."""
    db = RegistryMindtraceODM(
        models={"user": UserDoc, "address": AddressDoc},
    )

    with pytest.raises(ValueError, match="Cannot use all\\(\\) in multi-model mode"):
        db.all()


def test_registry_multi_model_cannot_use_direct_find():
    """Test that direct find() raises ValueError in multi-model mode."""
    db = RegistryMindtraceODM(
        models={"user": UserDoc, "address": AddressDoc},
    )

    with pytest.raises(ValueError, match="Cannot use find\\(\\) in multi-model mode"):
        db.find({"name": "Test"})


def test_registry_multi_model_cannot_use_direct_get_raw_model():
    """Test that direct get_raw_model() raises ValueError in multi-model mode."""
    db = RegistryMindtraceODM(
        models={"user": UserDoc, "address": AddressDoc},
    )

    with pytest.raises(ValueError, match="Cannot use get_raw_model\\(\\) in multi-model mode"):
        db.get_raw_model()
