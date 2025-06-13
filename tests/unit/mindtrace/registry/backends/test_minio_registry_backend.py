import json
import tempfile
import time
from pathlib import Path
import pytest
import yaml

from minio import Minio
from minio.error import S3Error

from mindtrace.core import Config
from mindtrace.registry import MinioRegistryBackend


@pytest.fixture
def mock_minio_client(monkeypatch):
    """Create a mock MinIO client."""
    class MockMinio:
        def __init__(self, *args, **kwargs):
            pass
        
        def bucket_exists(self, *args, **kwargs):
            return True
        
        def make_bucket(self, *args, **kwargs):
            pass
        
        def stat_object(self, *args, **kwargs):
            pass
        
        def get_object(self, *args, **kwargs):
            pass
        
        def put_object(self, *args, **kwargs):
            pass
        
        def remove_object(self, *args, **kwargs):
            pass
            
        def list_objects(self, *args, **kwargs):
            return []
    
    monkeypatch.setattr("mindtrace.registry.backends.minio_registry_backend.Minio", MockMinio)
    return MockMinio()


@pytest.fixture
def backend(mock_minio_client):
    """Create a MinioRegistryBackend instance with a mock client."""
    return MinioRegistryBackend(
        uri=str(Path(Config()["MINDTRACE_TEMP_DIR"]).expanduser() / "test_dir"),
        endpoint="localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket="test-bucket",
        secure=False
    )


def test_invalid_object_name(backend):
    """Test handling of invalid object names."""
    with pytest.raises(ValueError):
        backend.push("invalid_name", "1.0.0", "some_path")


def test_register_materializer_error(backend, monkeypatch):
    """Test error handling in register_materializer."""
    # Mock get_object to raise an exception
    def mock_get_object(*args, **kwargs):
        raise Exception("Failed to get metadata file")

    # Mock put_object to raise an exception
    def mock_put_object(*args, **kwargs):
        raise Exception("Failed to save metadata file")

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    monkeypatch.setattr(backend.client, "put_object", mock_put_object)

    # Attempt to register a materializer - should raise the exception from put_object
    with pytest.raises(Exception) as exc_info:
        backend.register_materializer("test:object", "TestMaterializer")

    # Verify the error message
    assert str(exc_info.value) == "Failed to get metadata file"


def test_registered_materializer_error(backend, monkeypatch):
    """Test error handling in registered_materializer."""
    # Mock get_object to raise an exception
    def mock_get_object(*args, **kwargs):
        raise Exception("Failed to get metadata file")

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Attempt to get registered materializer - should raise the exception
    with pytest.raises(Exception) as exc_info:
        backend.registered_materializer("test:object")

    # Verify the error message
    assert str(exc_info.value) == "Failed to get metadata file"


def test_registered_materializers_error(backend, monkeypatch):
    """Test error handling in registered_materializers."""
    # Mock get_object to raise an exception
    def mock_get_object(*args, **kwargs):
        raise Exception("Failed to get metadata file")

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Attempt to get registered materializers - should raise the exception
    with pytest.raises(Exception) as exc_info:
        backend.registered_materializers()

    # Verify the error message
    assert str(exc_info.value) == "Failed to get metadata file"


def test_delete_metadata_no_such_key(backend, monkeypatch):
    """Test that delete_metadata ignores NoSuchKey errors."""
    # Mock the remove_object method to raise NoSuchKey error
    def mock_remove_object(*args, **kwargs):
        raise S3Error(
            code="NoSuchKey",
            message="Object does not exist",
            resource="/test-bucket/metadata.yaml",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,
            bucket_name="test-bucket",
            object_name="metadata.yaml"
        )
    
    monkeypatch.setattr(backend.client, "remove_object", mock_remove_object)
    
    # This should not raise an exception
    backend.delete_metadata("test:object", "1.0.0")


def test_delete_metadata_other_error(backend, monkeypatch):
    """Test that delete_metadata re-raises non-NoSuchKey errors."""
    # Mock the remove_object method to raise a different error
    def mock_remove_object(*args, **kwargs):
        raise S3Error(
            code="InvalidRequest",
            message="Invalid request",
            resource="/test-bucket/metadata.yaml",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,
            bucket_name="test-bucket",
            object_name="metadata.yaml"
        )
    
    monkeypatch.setattr(backend.client, "remove_object", mock_remove_object)
    
    # This should raise the S3Error
    with pytest.raises(S3Error) as exc_info:
        backend.delete_metadata("test:object", "1.0.0")
    
    # Verify it's not a NoSuchKey error
    assert exc_info.value.code != "NoSuchKey"


def test_register_materializer_success(backend, monkeypatch):
    """Test register_materializer when metadata file exists and can be updated."""
    # Mock get_object to return existing metadata
    def mock_get_object(*args, **kwargs):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps({
                    "materializers": {
                        "existing:object": "ExistingMaterializer"
                    }
                }).encode()
        return MockResponse()
    
    # Track put_object calls to verify correct metadata was saved
    put_calls = []
    def mock_put_object(bucket, object_name, data, length, **kwargs):
        put_calls.append({
            "bucket": bucket,
            "object_name": object_name,
            "data": data.getvalue().decode(),
            "length": length
        })
    
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    monkeypatch.setattr(backend.client, "put_object", mock_put_object)
    
    # Register a new materializer
    backend.register_materializer("test:object", "TestMaterializer")
    
    # Verify the metadata was updated correctly
    assert len(put_calls) == 1
    saved_metadata = json.loads(put_calls[0]["data"])
    assert saved_metadata["materializers"]["test:object"] == "TestMaterializer"
    assert saved_metadata["materializers"]["existing:object"] == "ExistingMaterializer"


def test_register_materializer_no_such_key(backend, monkeypatch):
    """Test register_materializer when metadata file doesn't exist."""
    # Mock get_object to raise NoSuchKey error
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="NoSuchKey",
            message="Object does not exist",
            resource="/test-bucket/registry_metadata.json",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,
            bucket_name="test-bucket",
            object_name="registry_metadata.json"
        )
    
    # Track put_object calls to verify new metadata was created
    put_calls = []
    def mock_put_object(bucket, object_name, data, length, **kwargs):
        put_calls.append({
            "bucket": bucket,
            "object_name": object_name,
            "data": data.getvalue().decode(),
            "length": length
        })
    
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    monkeypatch.setattr(backend.client, "put_object", mock_put_object)
    
    # Register a materializer - should create new metadata file
    backend.register_materializer("test:object", "TestMaterializer")
    
    # Verify new metadata file was created with correct content
    assert len(put_calls) == 1
    saved_metadata = json.loads(put_calls[0]["data"])
    assert saved_metadata["materializers"]["test:object"] == "TestMaterializer"


def test_register_materializer_other_error(backend, monkeypatch):
    """Test register_materializer when a non-NoSuchKey S3Error occurs."""
    # Mock get_object to raise a different S3Error
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="InvalidRequest",
            message="Invalid request",
            resource="/test-bucket/registry_metadata.json",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,
            bucket_name="test-bucket",
            object_name="registry_metadata.json"
        )
    
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    
    # Attempt to register materializer - should raise the S3Error
    with pytest.raises(S3Error) as exc_info:
        backend.register_materializer("test:object", "TestMaterializer")
    
    # Verify it's not a NoSuchKey error
    assert exc_info.value.code != "NoSuchKey"


def test_registered_materializers_no_such_key(backend, monkeypatch):
    """Test registered_materializers when get_object raises NoSuchKey error."""
    # Mock get_object to raise NoSuchKey error
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="NoSuchKey",
            message="Object does not exist",
            resource="/test-bucket/registry_metadata.json",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,
            bucket_name="test-bucket",
            object_name="registry_metadata.json"
        )
    
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    
    # Call registered_materializers - this should hit lines 324-326
    materializer = backend.registered_materializer("test:object")
    
    # Verify empty dict is returned when metadata file doesn't exist
    assert materializer is None

    # Repeat for registered_materializers
    materializers = backend.registered_materializers()
    assert materializers == {}


def test_registered_materializer_other_error(backend, monkeypatch):
    """Test that registered_materializer re-raises non-NoSuchKey S3Errors."""
    # Mock get_object to raise a different S3Error
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="InvalidRequest",
            message="Invalid request",
            resource="/test-bucket/registry_metadata.json",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,
            bucket_name="test-bucket",
            object_name="registry_metadata.json"
        )
    
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    
    # Attempt to get registered materializer - should raise the S3Error
    with pytest.raises(S3Error) as exc_info:
        backend.registered_materializer("test:object")
    
    # Verify it's not a NoSuchKey error
    assert exc_info.value.code != "NoSuchKey"

    # Repeat for registered_materializers
    with pytest.raises(S3Error) as exc_info:
        backend.registered_materializers()
    
    # Verify it's not a NoSuchKey error
    assert exc_info.value.code != "NoSuchKey"


def test_acquire_shared_lock_with_exclusive_lock(backend, monkeypatch):
    """Test that acquire_lock returns False when trying to acquire a shared lock while an exclusive lock exists."""
    # Mock get_object to return an active exclusive lock
    def mock_get_object(*args, **kwargs):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps({
                    "lock_id": "test-lock-id",
                    "expires_at": time.time() + 3600,  # Lock expires in 1 hour
                    "shared": False  # This is an exclusive lock
                }).encode()
        return MockResponse()
    
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    
    # Try to acquire a shared lock while an exclusive lock exists
    assert not backend.acquire_lock("test-key", "new-lock-id", timeout=30, shared=True)


def test_acquire_lock_put_failure(backend, monkeypatch):
    """Test that acquire_lock handles put_object failure after creating lock data."""
    # Mock get_object to raise NoSuchKey to simulate no existing lock
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="NoSuchKey",
            message="Object does not exist",
            resource="/test-bucket/lock",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,
            bucket_name="test-bucket",
            object_name="lock"
        )
    
    # Mock put_object to raise an error
    def mock_put_object(*args, **kwargs):
        raise S3Error(
            code="InternalError",
            message="Failed to put object",
            resource="/test-bucket/lock",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,
            bucket_name="test-bucket",
            object_name="lock"
        )
    
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    monkeypatch.setattr(backend.client, "put_object", mock_put_object)
    
    # Try to acquire a lock - should return False due to put_object failure
    assert not backend.acquire_lock("test-key", "test-lock-id", timeout=30, shared=True)


def test_acquire_exclusive_lock_with_shared_lock(backend, monkeypatch):
    """Test that acquire_lock returns False when trying to acquire an exclusive lock while shared locks exist."""
    # Mock get_object to return an active shared lock
    def mock_get_object(*args, **kwargs):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps({
                    "lock_id": "test-lock-id",
                    "expires_at": time.time() + 3600,  # Lock expires in 1 hour
                    "shared": True  # This is a shared lock
                }).encode()
        return MockResponse()
    
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    
    # Try to acquire an exclusive lock while shared locks exist
    assert not backend.acquire_lock("test-key", "new-lock-id", timeout=30, shared=False)


def test_release_lock_unexpected_error(backend, monkeypatch):
    """Test that release_lock returns False when an unexpected S3Error occurs."""
    # Mock get_object to raise an S3Error with a different error code
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="InternalError",  # Different from "NoSuchKey"
            message="Internal server error",
            resource="/test-bucket/lock",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,
            bucket_name="test-bucket",
            object_name="lock"
        )
    
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    
    # Attempt to release lock - should return False
    result = backend.release_lock("test-key", "test-lock-id")
    assert result is False


def test_check_lock_success(backend, monkeypatch):
    """Test check_lock when lock exists and is not expired."""
    # Mock get_object to return a valid, non-expired lock
    def mock_get_object(*args, **kwargs):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps({
                    "lock_id": "test-lock-id",
                    "expires_at": time.time() + 3600,  # Expires in 1 hour
                    "shared": False
                }).encode()
        return MockResponse()
    
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    
    # Check lock - should return (True, lock_id)
    is_locked, lock_id = backend.check_lock("test-key")
    assert is_locked is True
    assert lock_id == "test-lock-id"


def test_check_lock_expired(backend, monkeypatch):
    """Test check_lock when lock exists but has expired."""
    # Mock get_object to return an expired lock
    def mock_get_object(*args, **kwargs):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps({
                    "lock_id": "test-lock-id",
                    "expires_at": time.time() - 3600,  # Expired 1 hour ago
                    "shared": False
                }).encode()
        return MockResponse()
    
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    
    # Check lock - should return (False, None)
    is_locked, lock_id = backend.check_lock("test-key")
    assert is_locked is False
    assert lock_id is None


def test_check_lock_no_such_key(backend, monkeypatch):
    """Test check_lock when lock file doesn't exist."""
    # Mock get_object to raise NoSuchKey error
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="NoSuchKey",
            message="Object does not exist",
            resource="/test-bucket/lock",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,
            bucket_name="test-bucket",
            object_name="lock"
        )
    
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    
    # Check lock - should return (False, None)
    is_locked, lock_id = backend.check_lock("test-key")
    assert is_locked is False
    assert lock_id is None


def test_check_lock_other_error(backend, monkeypatch):
    """Test check_lock when an unexpected S3Error occurs."""
    # Mock get_object to raise a different S3Error
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="InternalError",
            message="Internal server error",
            resource="/test-bucket/lock",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,
            bucket_name="test-bucket",
            object_name="lock"
        )
    
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    
    # Check lock - should raise the S3Error
    with pytest.raises(S3Error) as exc_info:
        backend.check_lock("test-key")
    
    # Verify it's not a NoSuchKey error
    assert exc_info.value.code == "InternalError"

