import tempfile
from pathlib import Path
from typing import Dict

import pytest

from mindtrace.registry import RegistryBackend


@pytest.fixture
def concrete_backend():
    class ConcreteBackend(RegistryBackend):
        def __init__(self, uri: str | Path):
            super().__init__(uri=uri)
            self._materializers: Dict[str, str] = {}

        @property
        def uri(self) -> Path:
            return self._uri

        def push(self, name: str, version: str | None = None, local_path: str | None = None):
            pass

        def pull(self, name: str, version: str, local_path: str):
            pass

        def delete(self, name: str, version: str = "all"):
            pass

        def save_metadata(self, name: str, version: str, metadata: dict):
            pass

        def fetch_metadata(self, name: str, version: str) -> dict:
            return {}

        def delete_metadata(self, name: str, version: str) -> dict:
            return {}

        def list_objects(self) -> list[str]:
            return []

        def list_versions(self, name: str) -> list[str]:
            return []

        def has_object(self, name: str, version: str) -> bool:
            return False

        def register_materializer(self, object_class: str, materializer_class: str):
            self._materializers[object_class] = materializer_class

        def registered_materializer(self, object_class: str) -> str | None:
            return self._materializers.get(object_class)

        def registered_materializers(self) -> Dict[str, str]:
            return self._materializers.copy()

        def acquire_lock(self, key: str, lock_id: str, timeout: int) -> bool:
            """Test implementation of acquire_lock."""
            return True

        def release_lock(self, key: str, lock_id: str) -> bool:
            """Test implementation of release_lock."""
            return True

        def check_lock(self, key: str) -> tuple[bool, str | None]:
            """Test implementation of check_lock."""
            return False, None

        def overwrite(self, source_name: str, source_version: str, target_name: str, target_version: str):
            pass

    with tempfile.TemporaryDirectory() as temp_dir:
        yield ConcreteBackend(temp_dir)


def test_validate_object_name_valid(concrete_backend):
    # Test valid object names
    valid_names = ["object", "namespace:object", "deep:namespace:object", "object-with-hyphens", "object123"]

    for name in valid_names:
        concrete_backend.validate_object_name(name)  # Should not raise any exception


def test_validate_object_name_invalid(concrete_backend):
    # Test invalid object names (with underscores)
    invalid_names = ["object_name", "namespace:object_name", "object_with_multiple_underscores"]

    for name in invalid_names:
        with pytest.raises(ValueError, match="Object names cannot contain underscores"):
            concrete_backend.validate_object_name(name)