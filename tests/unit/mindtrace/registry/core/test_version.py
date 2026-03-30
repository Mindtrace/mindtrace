from tempfile import TemporaryDirectory

import pytest

from mindtrace.registry import Registry
from mindtrace.registry.core.types import Version


def test_version_normalization_with_fixed_digits():
    assert Version("1", digits=3) == Version("1.0", digits=3)
    assert Version("1.0", digits=3) == Version("1.0.0", digits=3)
    assert str(Version("1", digits=3)) == "1.0.0"


def test_version_rejects_more_components_than_digits():
    with pytest.raises(ValueError, match="between 1 and 3"):
        Version("1.0.0.0", digits=3)


def test_version_bump_increments_last_component():
    assert str(Version("1", digits=2).bump()) == "1.1"
    assert str(Version("1.0.9", digits=3).bump()) == "1.0.10"


def test_registry_uses_fixed_width_version_canonicalization():
    with TemporaryDirectory() as temp_dir:
        registry = Registry(backend=temp_dir, version_objects=True, version_digits=3)

        registry.save("my:object", 42, version="1")
        assert registry.has_object("my:object", "1")
        assert registry.has_object("my:object", "1.0")
        assert registry.has_object("my:object", "1.0.0")

        with pytest.raises(ValueError, match="between 1 and 3"):
            registry.save("my:object", 43, version="1.0.0.0")


def test_registry_digits_one_rejects_dotted_input():
    with TemporaryDirectory() as temp_dir:
        registry = Registry(backend=temp_dir, version_objects=True, version_digits=1)
        registry.save("my:object", 42, version="1")

        with pytest.raises(ValueError, match="between 1 and 1"):
            registry.save("my:object", 43, version="1.0")

        with pytest.raises(ValueError, match="between 1 and 1"):
            registry.save("my:object", 44, version="1.0.0")


def test_registry_version_digits_is_immutable_once_created():
    with TemporaryDirectory() as temp_dir:
        Registry(backend=temp_dir, version_objects=True, version_digits=1)

        # Matching config is fine
        Registry(backend=temp_dir, version_objects=True, version_digits=1)

        # Mismatched version_digits should fail
        with pytest.raises(ValueError, match="Version digits conflict"):
            Registry(backend=temp_dir, version_objects=True, version_digits=3)
