"""Shared fixtures for registry unit tests."""

import tempfile
from pathlib import Path

import pytest

from mindtrace.registry import Registry, S3RegistryBackend
from tests.utils.registry_storage import MockGCSHandler, MockS3Handler


@pytest.fixture
def sample_object_dir():
    """Create a sample object directory with some files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        obj_dir = Path(temp_dir) / "sample:object"
        obj_dir.mkdir()
        (obj_dir / "file1.txt").write_text("test content 1")
        (obj_dir / "file2.txt").write_text("test content 2")
        yield str(obj_dir)


@pytest.fixture
def sample_metadata():
    """Sample metadata for testing."""
    return {
        "name": "test:object",
        "version": "1.0.0",
        "description": "Test object",
        "created_at": "2024-01-01T00:00:00Z",
    }


@pytest.fixture
def cached_mock_registry(mock_s3_handler, tmp_path):
    backend = S3RegistryBackend(
        uri=tmp_path / "remote",
        endpoint="example.invalid",
        access_key="test",
        secret_key="test",
        bucket="registry-contract-tests",
        secure=False,
    )
    return Registry(backend=backend, version_objects=True, mutable=True, use_cache=True)


@pytest.fixture
def mock_s3_handler(monkeypatch):
    """Create a mock S3 storage handler."""
    monkeypatch.setattr("mindtrace.registry.backends.s3_registry_backend.S3StorageHandler", MockS3Handler)
    return MockS3Handler()


@pytest.fixture
def mock_gcs_handler(monkeypatch):
    """Create a mock GCS storage handler."""
    monkeypatch.setattr("mindtrace.registry.backends.gcp_registry_backend.GCSStorageHandler", MockGCSHandler)
    return MockGCSHandler()


@pytest.fixture(params=["parent", "absolute", "embedded_parent"])
def invalid_relative_path(request, tmp_path):
    """Include traversal that stays inside the root: syntax must still be rejected."""
    if request.param == "parent":
        return "../item"
    if request.param == "absolute":
        return str(tmp_path / "absolute-item")
    return "nested/../item"


@pytest.fixture(params=["item", "nested/item", "model..backup", "namespace:object"])
def valid_relative_path(request):
    """Nested names and literal dots are valid; only a '..' component is rejected."""
    return request.param
