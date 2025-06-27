import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Generator

import pytest
import yaml
from minio import Minio
from minio.error import S3Error

from mindtrace.core import Config
from mindtrace.registry import MinioRegistryBackend


@pytest.fixture
def minio_client():
    """Create a MinIO client for testing."""
    config = Config()
    client = Minio(
        endpoint=config["MINDTRACE_MINIO_ENDPOINT"],
        access_key=config["MINDTRACE_MINIO_ACCESS_KEY"],
        secret_key=config["MINDTRACE_MINIO_SECRET_KEY"],
        secure=False
    )
    return client


@pytest.fixture
def test_bucket(minio_client) -> Generator[str, None, None]:
    """Create a temporary bucket for testing."""
    bucket_name = f"test-bucket-{uuid.uuid4()}"
    minio_client.make_bucket(bucket_name)
    yield bucket_name
    # Cleanup
    try:
        for obj in minio_client.list_objects(bucket_name, recursive=True):
            minio_client.remove_object(bucket_name, obj.object_name)
        minio_client.remove_bucket(bucket_name)
    except S3Error:
        pass


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    temp_dir = Path(Config()["MINDTRACE_TEMP_DIR"]).expanduser() / f"test_dir_{uuid.uuid4()}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def backend(temp_dir, test_bucket, minio_client):
    """Create a MinioRegistryBackend instance with a test bucket."""
    return MinioRegistryBackend(
        uri=str(temp_dir),
        endpoint="localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket=test_bucket,
        secure=False
    )


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
        "created_at": "2024-01-01T00:00:00Z"
    }


def test_init(backend, test_bucket, minio_client):
    """Test backend initialization."""
    assert backend.uri.exists()
    assert backend.uri.is_dir()
    assert minio_client.bucket_exists(test_bucket)


def test_push_and_pull(backend, sample_object_dir, minio_client, test_bucket):
    """Test pushing and pulling objects."""
    # Push the object
    backend.push("test:object", "1.0.0", sample_object_dir)
    
    # Verify the object was pushed to MinIO
    objects = list(minio_client.list_objects(test_bucket, prefix="objects/test:object/1.0.0/"))
    assert len(objects) == 2
    
    # Download to a new location
    download_dir = backend.uri / "download"
    download_dir.mkdir()
    backend.pull("test:object", "1.0.0", str(download_dir))
    
    # Verify the download
    assert (download_dir / "file1.txt").exists()
    assert (download_dir / "file2.txt").exists()
    assert (download_dir / "file1.txt").read_text() == "test content 1"
    assert (download_dir / "file2.txt").read_text() == "test content 2"


def test_save_and_fetch_metadata(backend, sample_metadata, minio_client, test_bucket):
    """Test saving and fetching metadata."""
    # Save metadata
    backend.save_metadata("test:object", "1.0.0", sample_metadata)
    
    # Verify metadata exists in MinIO
    objects = list(minio_client.list_objects(test_bucket, prefix="_meta_test_object@1.0.0.json"))
    assert len(objects) == 1
    
    # Fetch metadata and verify contents
    fetched_metadata = backend.fetch_metadata("test:object", "1.0.0")
    
    # Remove the path field for comparison since it's added by fetch_metadata
    path = fetched_metadata.pop("path", None)
    assert path is not None  # Verify path was added
    assert fetched_metadata == sample_metadata
    
    # Verify metadata content
    assert fetched_metadata["name"] == sample_metadata["name"]
    assert fetched_metadata["version"] == sample_metadata["version"]
    assert fetched_metadata["description"] == sample_metadata["description"]
    
    # Delete metadata
    backend.delete_metadata("test:object", "1.0.0")
    
    # Verify metadata is deleted
    objects = list(minio_client.list_objects(test_bucket, prefix="_meta_test_object@1.0.0.json"))
    assert len(objects) == 0


def test_delete_metadata(backend, sample_metadata, minio_client, test_bucket):
    """Test deleting metadata."""
    # Save metadata first
    backend.save_metadata("test:object", "1.0.0", sample_metadata)
    
    # Delete metadata
    backend.delete_metadata("test:object", "1.0.0")
    
    # Verify metadata is deleted from MinIO
    objects = list(minio_client.list_objects(test_bucket, prefix="_meta_test_object@1.0.0.json"))
    assert len(objects) == 0


def test_list_objects(backend, sample_metadata, minio_client, test_bucket):
    """Test listing objects."""
    # Save metadata for multiple objects
    backend.save_metadata("object:1", "1.0.0", sample_metadata)
    backend.save_metadata("object:2", "1.0.0", sample_metadata)
    
    # List objects
    objects = backend.list_objects()
    
    # Verify results
    assert len(objects) == 2
    assert "object:1" in objects
    assert "object:2" in objects


def test_list_versions(backend, sample_metadata, minio_client, test_bucket):
    """Test listing versions."""
    # Save metadata for multiple versions
    backend.save_metadata("test:object", "1.0.0", sample_metadata)
    backend.save_metadata("test:object", "2.0.0", sample_metadata)
    
    # List versions
    versions = backend.list_versions("test:object")
    
    # Verify results
    assert len(versions) == 2
    assert "1.0.0" in versions
    assert "2.0.0" in versions


def test_has_object(backend, sample_metadata, minio_client, test_bucket):
    """Test checking object existence."""
    # Save metadata
    backend.save_metadata("test:object", "1.0.0", sample_metadata)
    
    # Check existing object
    assert backend.has_object("test:object", "1.0.0")
    
    # Check non-existing object
    assert not backend.has_object("nonexistent:object", "1.0.0")
    assert not backend.has_object("test:object", "2.0.0")


def test_delete_object(backend, sample_object_dir, minio_client, test_bucket):
    """Test deleting objects."""
    # Push an object
    backend.push("test:object", "1.0.0", sample_object_dir)
    
    # Save metadata
    backend.save_metadata("test:object", "1.0.0", {"name": "test:object"})
    
    # Delete the object
    backend.delete("test:object", "1.0.0")
    
    # Verify object is deleted from MinIO
    objects = list(minio_client.list_objects(test_bucket, prefix="objects/test:object/1.0.0/"))
    assert len(objects) == 0

def test_invalid_object_name(backend):
    """Test handling of invalid object names."""
    with pytest.raises(ValueError):
        backend.push("invalid_name", "1.0.0", "some_path")


def test_register_materializer(backend, minio_client, test_bucket):
    """Test registering a materializer."""
    # Register a materializer
    backend.register_materializer("test:object", "TestMaterializer")
    
    # Verify materializer was registered
    materializers = backend.registered_materializers()
    assert materializers["test:object"] == "TestMaterializer"


def test_registered_materializer(backend, minio_client, test_bucket):
    """Test getting a registered materializer."""
    # Register a materializer
    backend.register_materializer("test:object", "TestMaterializer")
    
    # Get the registered materializer
    materializer = backend.registered_materializer("test:object")
    assert materializer == "TestMaterializer"
    
    # Test non-existent materializer
    assert backend.registered_materializer("nonexistent:object") is None


def test_registered_materializers(backend, minio_client, test_bucket):
    """Test getting all registered materializers."""
    # Register multiple materializers
    backend.register_materializer("test:object1", "TestMaterializer1")
    backend.register_materializer("test:object2", "TestMaterializer2")
    
    # Get all registered materializers
    materializers = backend.registered_materializers()
    assert len(materializers) == 2
    assert materializers["test:object1"] == "TestMaterializer1"
    assert materializers["test:object2"] == "TestMaterializer2"


def test_init_with_default_uri(minio_client, test_bucket):
    """Test backend initialization with default URI from config."""
    # Create backend without specifying URI
    backend = MinioRegistryBackend(
        endpoint="localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket=test_bucket,
        secure=False
    )
    
    # Verify the URI is set to the default from config
    expected_uri = Path(Config()["MINDTRACE_MINIO_REGISTRY_URI"]).expanduser().resolve()
    assert backend.uri == expected_uri
    assert backend.uri.exists()
    assert backend.uri.is_dir()
    assert minio_client.bucket_exists(test_bucket)


def test_init_creates_bucket(minio_client):
    """Test backend initialization creates a new bucket if it doesn't exist."""
    # Create a unique bucket name that doesn't exist
    bucket_name = f"test-bucket-{uuid.uuid4()}"
    
    # Verify bucket doesn't exist
    assert not minio_client.bucket_exists(bucket_name)
    
    # Create backend with the new bucket name
    backend = MinioRegistryBackend(
        uri=str(Path(Config()["MINDTRACE_TEMP_DIR"]).expanduser() / f"test_dir_{uuid.uuid4()}"),
        endpoint="localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket=bucket_name,
        secure=False
    )
    
    # Verify the bucket was created
    assert minio_client.bucket_exists(bucket_name)
    
    # Cleanup - remove all objects first, then the bucket
    for obj in minio_client.list_objects(bucket_name, recursive=True):
        minio_client.remove_object(bucket_name, obj.object_name)
    minio_client.remove_bucket(bucket_name)


def test_init_handles_metadata_error(minio_client, test_bucket, monkeypatch):
    """Test backend initialization handles errors when checking metadata file."""
    # Create a backend with valid credentials
    backend = MinioRegistryBackend(
        uri=str(Path(Config()["MINDTRACE_TEMP_DIR"]).expanduser() / f"test_dir_{uuid.uuid4()}"),
        endpoint="localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket=test_bucket,
        secure=False
    )
    
    # Create a mock Minio class that raises a non-NoSuchKey error
    class MockMinio:
        def __init__(self, *args, **kwargs):
            pass
        
        def bucket_exists(self, *args, **kwargs):
            return True
        
        def make_bucket(self, *args, **kwargs):
            pass
        
        def stat_object(self, *args, **kwargs):
            raise S3Error(
                code="InvalidRequest",
                message="Invalid request",
                resource="/test-bucket/registry_metadata.yaml",
                request_id="test-request-id",
                host_id="test-host-id",
                response=None,
                bucket_name="test-bucket",
                object_name="registry_metadata.yaml"
            )
    
    # Replace the Minio class with our mock
    monkeypatch.setattr("mindtrace.registry.backends.minio_registry_backend.Minio", MockMinio)
    
    # Try to create another backend - should fail with a non-NoSuchKey error
    with pytest.raises(S3Error) as exc_info:
        MinioRegistryBackend(
            uri=str(Path(Config()["MINDTRACE_TEMP_DIR"]).expanduser() / f"test_dir_{uuid.uuid4()}"),
            endpoint="localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket=test_bucket,
            secure=False
        )
    
    # Verify the error is not a NoSuchKey error
    assert exc_info.value.code != "NoSuchKey"


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
    
    # Attempt to get all registered materializers - should raise the exception
    with pytest.raises(Exception) as exc_info:
        backend.registered_materializers()
    
    # Verify the error message
    assert str(exc_info.value) == "Failed to get metadata file"
