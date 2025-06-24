import pytest
from pathlib import Path
import yaml
import tempfile

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
        
        def fput_object(self, *args, **kwargs):
            pass
        
        def fget_object(self, *args, **kwargs):
            pass
        
        def remove_object(self, *args, **kwargs):
            pass
    
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
    # Mock fget_object to raise an exception
    def mock_fget_object(*args, **kwargs):
        raise Exception("Failed to get metadata file")
    
    monkeypatch.setattr(backend.client, "fget_object", mock_fget_object)
    
    # Attempt to register a materializer - should raise the exception
    with pytest.raises(Exception) as exc_info:
        backend.register_materializer("test:object", "TestMaterializer")
    
    # Verify the error message
    assert str(exc_info.value) == "Failed to get metadata file"


def test_registered_materializer_error(backend, monkeypatch):
    """Test error handling in registered_materializer."""
    # Mock fget_object to raise an exception
    def mock_fget_object(*args, **kwargs):
        raise Exception("Failed to get metadata file")
    
    monkeypatch.setattr(backend.client, "fget_object", mock_fget_object)
    
    # Attempt to get registered materializer - should raise the exception
    with pytest.raises(Exception) as exc_info:
        backend.registered_materializer("test:object")
    
    # Verify the error message
    assert str(exc_info.value) == "Failed to get metadata file"


def test_registered_materializers_error(backend, monkeypatch):
    """Test error handling in registered_materializers."""
    # Mock fget_object to raise an exception
    def mock_fget_object(*args, **kwargs):
        raise Exception("Failed to get metadata file")
    
    monkeypatch.setattr(backend.client, "fget_object", mock_fget_object)
    
    # Attempt to get all registered materializers - should raise the exception
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