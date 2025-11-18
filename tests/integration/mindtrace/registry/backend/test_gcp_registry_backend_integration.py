"""Integration tests for GCPRegistryBackend."""

import os
import tempfile
import uuid
from pathlib import Path
from typing import Generator

import pytest
from google.cloud import storage
from google.cloud.exceptions import NotFound

from mindtrace.core import CoreConfig
from mindtrace.registry import GCPRegistryBackend, Registry


@pytest.fixture(scope="session")
def gcs_client():
    """Create a GCS client for testing."""

    config = CoreConfig()
    project_id = os.environ.get("GCP_PROJECT_ID", config["MINDTRACE_GCP"]["GCP_PROJECT_ID"])
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"])
    if not credentials_path:
        pytest.skip("No GCP credentials path provided")
    if not os.path.exists(credentials_path):
        pytest.skip(f"GCP credentials path does not exist: {credentials_path}")

    client = storage.Client(project=project_id)
    yield client


@pytest.fixture
def test_bucket(gcs_client) -> Generator[str, None, None]:
    """Create a temporary bucket for testing."""
    bucket_name = f"mindtrace-test-{uuid.uuid4()}"

    try:
        # Create bucket
        bucket = gcs_client.bucket(bucket_name)
        bucket.create()
        yield bucket_name
    except Exception as e:
        pytest.skip(f"GCP bucket creation failed: {e}")

    # Cleanup - delete all objects first, then the bucket
    try:
        for blob in bucket.list_blobs():
            blob.delete()
        bucket.delete()
    except NotFound:
        pass


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    import shutil

    shutil.rmtree(temp_dir)


@pytest.fixture
def backend(temp_dir, test_bucket):
    """Create a GCPRegistryBackend instance with a test bucket."""

    config = CoreConfig()
    project_id = os.environ.get("GCP_PROJECT_ID", config["MINDTRACE_GCP"]["GCP_PROJECT_ID"])
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"])

    try:
        return GCPRegistryBackend(
            uri=f"gs://{test_bucket}",
            project_id=project_id,
            bucket=test_bucket,
            credentials_path=credentials_path,
        )
    except Exception as e:
        pytest.skip(f"GCP backend creation failed: {e}")


@pytest.fixture
def gcp_registry(backend):
    """Create a Registry instance with GCP backend."""
    return Registry(backend=backend)


@pytest.fixture
def sample_object_dir(temp_dir):
    """Create sample object directory for testing."""
    # Create test files
    file1 = temp_dir / "file1.txt"
    file1.write_text("test content 1")

    file2 = temp_dir / "file2.txt"
    file2.write_text("test content 2")

    # Create a subdirectory
    subdir = temp_dir / "subdir"
    subdir.mkdir()
    file3 = subdir / "file3.txt"
    file3.write_text("test content 3")

    return temp_dir


@pytest.fixture
def sample_metadata():
    """Create sample metadata for testing."""
    return {
        "name": "test:object",
        "version": "1.0.0",
        "description": "A test object",
        "created_at": "2023-01-01T00:00:00Z",
        "tags": ["test", "integration"],
    }


def test_init(backend, test_bucket, gcs_client):
    """Test backend initialization."""
    assert backend.uri.name == test_bucket
    assert gcs_client.bucket(test_bucket).exists()


def test_push_and_pull(backend, sample_object_dir, gcs_client, test_bucket, temp_dir):
    """Test pushing and pulling objects."""
    # Push the object
    backend.push("test:object", "1.0.0", sample_object_dir)

    # Verify the object was pushed to GCS
    bucket = gcs_client.bucket(test_bucket)
    objects = list(bucket.list_blobs(prefix="objects/test:object/1.0.0/"))
    assert len(objects) == 3  # file1.txt, file2.txt, subdir/file3.txt

    # Download to a new location
    download_dir = temp_dir / "download"
    download_dir.mkdir()
    backend.pull("test:object", "1.0.0", str(download_dir))

    # Verify the download
    assert (download_dir / "file1.txt").exists()
    assert (download_dir / "file2.txt").exists()
    assert (download_dir / "subdir" / "file3.txt").exists()
    assert (download_dir / "file1.txt").read_text() == "test content 1"
    assert (download_dir / "file2.txt").read_text() == "test content 2"
    assert (download_dir / "subdir" / "file3.txt").read_text() == "test content 3"


def test_save_and_fetch_metadata(backend, sample_metadata, gcs_client, test_bucket):
    """Test saving and fetching metadata."""
    # Save metadata
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Verify metadata exists in GCS
    bucket = gcs_client.bucket(test_bucket)
    objects = list(bucket.list_blobs(prefix="_meta_test_object@1.0.0.json"))
    assert len(objects) == 1

    # Fetch metadata and verify contents
    fetched_metadata = backend.fetch_metadata("test:object", "1.0.0")

    # Remove the path field for comparison since it's added by fetch_metadata
    path = fetched_metadata.pop("path", None)
    assert path is not None  # Verify path was added
    assert path.startswith(f"gs://{test_bucket}/objects/test:object/1.0.0")
    assert fetched_metadata == sample_metadata

    # Verify metadata content
    assert fetched_metadata["name"] == sample_metadata["name"]
    assert fetched_metadata["version"] == sample_metadata["version"]
    assert fetched_metadata["description"] == sample_metadata["description"]


def test_delete_metadata(backend, sample_metadata, gcs_client, test_bucket):
    """Test deleting metadata."""
    # Save metadata first
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Delete metadata
    backend.delete_metadata("test:object", "1.0.0")

    # Verify metadata is deleted from GCS
    bucket = gcs_client.bucket(test_bucket)
    objects = list(bucket.list_blobs(prefix="_meta_test_object@1.0.0.json"))
    assert len(objects) == 0


def test_list_objects(backend, sample_metadata, gcs_client, test_bucket):
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


def test_list_versions(backend, sample_metadata, gcs_client, test_bucket):
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


def test_has_object(backend, sample_metadata, gcs_client, test_bucket):
    """Test checking object existence."""
    # Save metadata
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Check existing object
    assert backend.has_object("test:object", "1.0.0")

    # Check non-existing object
    assert not backend.has_object("nonexistent:object", "1.0.0")
    assert not backend.has_object("test:object", "2.0.0")


def test_delete_object(backend, sample_object_dir, gcs_client, test_bucket):
    """Test deleting objects."""
    # Push an object
    backend.push("test:object", "1.0.0", sample_object_dir)

    # Save metadata
    backend.save_metadata("test:object", "1.0.0", {"name": "test:object"})

    # Delete the object
    backend.delete("test:object", "1.0.0")

    # Verify object is deleted from GCS
    bucket = gcs_client.bucket(test_bucket)
    objects = list(bucket.list_blobs(prefix="objects/test:object/1.0.0/"))
    assert len(objects) == 0


def test_invalid_object_name(backend):
    """Test handling of invalid object names."""
    with pytest.raises(ValueError):
        backend.push("invalid_name", "1.0.0", "some_path")


def test_register_materializer(backend, gcs_client, test_bucket):
    """Test registering a materializer."""
    # Register a materializer
    backend.register_materializer("test:object", "TestMaterializer")

    # Verify materializer was registered
    materializers = backend.registered_materializers()
    assert materializers["test:object"] == "TestMaterializer"


def test_registered_materializer(backend, gcs_client, test_bucket):
    """Test getting a registered materializer."""
    # Register a materializer
    backend.register_materializer("test:object", "TestMaterializer")

    # Get the registered materializer
    materializer = backend.registered_materializer("test:object")
    assert materializer == "TestMaterializer"

    # Test non-existent materializer
    assert backend.registered_materializer("nonexistent:object") is None


def test_registered_materializers(backend, gcs_client, test_bucket):
    """Test getting all registered materializers."""
    # Register multiple materializers
    backend.register_materializer("test:object1", "TestMaterializer1")
    backend.register_materializer("test:object2", "TestMaterializer2")

    # Get all registered materializers
    materializers = backend.registered_materializers()
    assert len(materializers) == 2
    assert materializers["test:object1"] == "TestMaterializer1"
    assert materializers["test:object2"] == "TestMaterializer2"


def test_acquire_and_release_lock(backend):
    """Test distributed locking functionality."""
    lock_key = "test:lock"
    lock_id = "test-lock-id"
    timeout = 10

    # Acquire lock
    success = backend.acquire_lock(lock_key, lock_id, timeout, shared=False)
    assert success

    # Check lock status
    is_locked, current_lock_id = backend.check_lock(lock_key)
    assert is_locked
    assert current_lock_id == lock_id

    # Release lock
    release_success = backend.release_lock(lock_key, lock_id)
    assert release_success

    # Verify lock is released
    is_locked_after, _ = backend.check_lock(lock_key)
    assert not is_locked_after


def test_shared_locks(backend):
    """Test shared locking functionality."""
    lock_key = "test:shared"
    lock_id1 = "test-shared-lock-1"
    lock_id2 = "test-shared-lock-2"
    timeout = 10

    # Acquire first shared lock
    success1 = backend.acquire_lock(lock_key, lock_id1, timeout, shared=True)
    assert success1

    # Acquire second shared lock (should work for shared locks)
    success2 = backend.acquire_lock(lock_key, lock_id2, timeout, shared=True)
    assert success2

    # Release both locks
    backend.release_lock(lock_key, lock_id1)
    backend.release_lock(lock_key, lock_id2)

    # Verify locks are released
    is_locked, _ = backend.check_lock(lock_key)
    assert not is_locked


def test_exclusive_lock_conflict(backend):
    """Test that exclusive locks conflict with shared locks."""
    from mindtrace.registry.core.exceptions import LockAcquisitionError

    lock_key = "test:conflict"
    shared_lock_id = "shared-lock"
    exclusive_lock_id = "exclusive-lock"
    timeout = 10

    # Acquire shared lock first
    shared_success = backend.acquire_lock(lock_key, shared_lock_id, timeout, shared=True)
    assert shared_success

    # Try to acquire exclusive lock (should raise LockAcquisitionError)
    with pytest.raises(LockAcquisitionError) as exc_info:
        backend.acquire_lock(lock_key, exclusive_lock_id, timeout, shared=False)
    assert "currently held as shared" in str(exc_info.value)

    # Release shared lock
    backend.release_lock(lock_key, shared_lock_id)


def test_overwrite_operation(backend, sample_object_dir, gcs_client, test_bucket):
    """Test overwrite operation."""
    # Push source object
    backend.push("source:object", "1.0.0", sample_object_dir)
    backend.save_metadata("source:object", "1.0.0", {"name": "source:object"})

    # Overwrite to target object
    backend.overwrite("source:object", "1.0.0", "target:object", "2.0.0")

    # Verify source is deleted
    bucket = gcs_client.bucket(test_bucket)
    source_objects = list(bucket.list_blobs(prefix="objects/source:object/1.0.0/"))
    assert len(source_objects) == 0

    # Verify target exists
    target_objects = list(bucket.list_blobs(prefix="objects/target:object/2.0.0/"))
    assert len(target_objects) == 3  # file1.txt, file2.txt, subdir/file3.txt

    # Verify target metadata exists
    target_metadata = list(bucket.list_blobs(prefix="_meta_target_object@2.0.0.json"))
    assert len(target_metadata) == 1


def test_registry_integration(gcp_registry, sample_object_dir):
    """Test full registry integration with GCP backend."""
    # Save objects using registry
    gcp_registry.save("test:int", 42)
    gcp_registry.save("test:str", "Hello, GCP!")
    gcp_registry.save("test:list", [1, 2, 3])

    # Load objects
    loaded_int = gcp_registry.load("test:int")
    loaded_str = gcp_registry.load("test:str")
    loaded_list = gcp_registry.load("test:list")

    assert loaded_int == 42
    assert loaded_str == "Hello, GCP!"
    assert loaded_list == [1, 2, 3]

    # Test versioning
    orig_version_objects = gcp_registry.version_objects
    gcp_registry.version_objects = True
    gcp_registry.save("test:versioned", "version1", version="1.0.0")
    gcp_registry.save("test:versioned", "version2", version="2.0.0")
    v1 = gcp_registry.load("test:versioned", version="1.0.0")
    v2 = gcp_registry.load("test:versioned", version="2.0.0")
    latest = gcp_registry.load("test:versioned")

    assert v1 == "version1"
    assert v2 == "version2"
    assert latest == "version2"

    # Test object discovery
    objects = gcp_registry.list_objects()
    assert "test:int" in objects
    assert "test:str" in objects
    assert "test:list" in objects
    assert "test:versioned" in objects

    # Test version listing
    versions = gcp_registry.list_versions("test:versioned")
    assert "1.0.0" in versions
    assert "2.0.0" in versions
    gcp_registry.version_objects = orig_version_objects


def test_concurrent_operations(gcp_registry):
    """Test concurrent operations with distributed locking."""
    import threading
    import time

    results = []

    def worker(worker_id):
        try:
            # Use unique object name per worker to avoid lock contention
            obj_name = f"test:concurrent:{worker_id}"
            with gcp_registry.get_lock(obj_name):
                results.append(f"Worker {worker_id} acquired lock")
                # Save an object to use the lock
                gcp_registry.save(obj_name, f"data_{worker_id}")
                time.sleep(0.1)  # Simulate work
                results.append(f"Worker {worker_id} completed")
        except Exception as e:
            results.append(f"Worker {worker_id} failed: {e}")

    # Start multiple workers
    threads = []
    for i in range(3):
        thread = threading.Thread(target=worker, args=(i,))
        threads.append(thread)
        thread.start()

    # Wait for all threads
    for thread in threads:
        thread.join()

    # Verify all operations completed
    assert len(results) == 6  # 3 acquired + 3 completed
    assert all("acquired lock" in result or "completed" in result for result in results)


def test_error_handling_invalid_credentials():
    """Test error handling for invalid credentials."""
    with pytest.raises(Exception):  # Should raise authentication error
        GCPRegistryBackend(
            uri="gs://test-bucket",
            project_id="invalid-project",
            bucket="test-bucket",
            credentials_path="/nonexistent/credentials.json",
        )


def test_error_handling_nonexistent_bucket():
    """Test error handling for nonexistent bucket."""
    with pytest.raises(Exception):  # Should raise bucket not found error
        GCPRegistryBackend(
            uri="gs://nonexistent-bucket",
            project_id=os.environ.get("GCP_PROJECT_ID", "mindtrace-test"),
            bucket="nonexistent-bucket",
            ensure_bucket=True,
            create_if_missing=False,
        )


def test_metadata_file_initialization(backend, gcs_client, test_bucket):
    """Test that metadata file is initialized correctly."""
    # Ensure metadata file is created by performing an operation that requires it
    backend._ensure_metadata_file()

    # Check that metadata file exists
    bucket = gcs_client.bucket(test_bucket)
    metadata_objects = list(bucket.list_blobs(prefix="registry_metadata.json"))
    assert len(metadata_objects) == 1

    # Verify metadata file content
    blob = bucket.blob("registry_metadata.json")
    content = blob.download_as_text()
    import json

    metadata = json.loads(content)
    assert "materializers" in metadata
    assert isinstance(metadata["materializers"], dict)


def test_cleanup_after_test(backend, gcs_client, test_bucket):
    """Test that cleanup works properly after tests."""
    # This test ensures that the bucket cleanup in the fixture works
    # by verifying the bucket exists during the test
    bucket = gcs_client.bucket(test_bucket)
    assert bucket.exists()

    # The cleanup will happen in the fixture after this test
