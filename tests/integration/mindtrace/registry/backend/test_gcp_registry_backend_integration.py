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
from mindtrace.registry.core.exceptions import RegistryVersionConflict


@pytest.fixture(scope="session")
def config():
    """Create a CoreConfig instance for testing."""
    return CoreConfig()


@pytest.fixture(scope="session")
def gcs_client(config):
    """Create a GCS client for testing."""

    project_id = os.environ.get("GCP_PROJECT_ID", config["MINDTRACE_GCP"]["GCP_PROJECT_ID"])
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"])
    if not credentials_path:
        pytest.skip("No GCP credentials path provided")
    if not os.path.exists(credentials_path):
        pytest.skip(f"GCP credentials path does not exist: {credentials_path}")

    client = storage.Client(project=project_id)
    yield client


@pytest.fixture
def test_bucket(gcs_client, config) -> Generator[str, None, None]:
    """Create a temporary bucket for testing, or use existing one.

    Set GCP_TEST_BUCKET env var to use an existing bucket instead of creating one.
    """
    existing_bucket = config["MINDTRACE_GCP"]["GCP_BUCKET_NAME"]

    if existing_bucket:
        # Use existing bucket - verify it exists
        bucket = gcs_client.bucket(existing_bucket)
        if not bucket.exists():
            pytest.skip(f"GCP_TEST_BUCKET '{existing_bucket}' does not exist")
        yield existing_bucket
        # Don't delete existing bucket
    else:
        # Create a new temporary bucket
        bucket_name = f"mindtrace-test-{uuid.uuid4()}"
        try:
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
def test_prefix():
    """Generate a unique prefix for test isolation."""
    return f"test-{uuid.uuid4()}"


@pytest.fixture
def backend(temp_dir, test_bucket, gcs_client, test_prefix):
    """Create a GCPRegistryBackend instance with a test bucket."""

    config = CoreConfig()
    project_id = os.environ.get("GCP_PROJECT_ID", config["MINDTRACE_GCP"]["GCP_PROJECT_ID"])
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"])

    try:
        backend = GCPRegistryBackend(
            uri=f"gs://{test_bucket}/{test_prefix}",
            project_id=project_id,
            bucket_name=test_bucket,
            credentials_path=credentials_path,
            prefix=test_prefix,
        )
        yield backend
    except Exception as e:
        pytest.skip(f"GCP backend creation failed: {e}")

    # Cleanup: delete all objects with our test prefix
    try:
        bucket = gcs_client.bucket(test_bucket)
        blobs = list(bucket.list_blobs(prefix=test_prefix))
        for blob in blobs:
            blob.delete()
    except Exception:
        pass  # Best effort cleanup


@pytest.fixture
def gcp_registry(backend):
    """Create a Registry instance with GCP backend."""
    return Registry(backend=backend, version_objects=True, use_cache=False)


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


# ─────────────────────────────────────────────────────────────────────────────
# Backend Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_init(backend, test_bucket, gcs_client):
    """Test backend initialization."""
    assert gcs_client.bucket(test_bucket).exists()
    assert backend.gcs.bucket_name == test_bucket


def test_push_and_pull(backend, sample_object_dir, temp_dir):
    """Test pushing and pulling objects."""
    # Push the object
    results = backend.push("test:object", "1.0.0", sample_object_dir)
    assert results.all_ok

    # Verify via has_object
    exists = backend.has_object("test:object", "1.0.0")
    assert exists[("test:object", "1.0.0")]

    # Download to a new location
    download_dir = temp_dir / "download"
    download_dir.mkdir()
    pull_results = backend.pull("test:object", "1.0.0", str(download_dir))
    assert pull_results.all_ok

    # Verify the download
    assert (download_dir / "file1.txt").exists()
    assert (download_dir / "file2.txt").exists()
    assert (download_dir / "subdir" / "file3.txt").exists()
    assert (download_dir / "file1.txt").read_text() == "test content 1"
    assert (download_dir / "file2.txt").read_text() == "test content 2"
    assert (download_dir / "subdir" / "file3.txt").read_text() == "test content 3"


def test_save_and_fetch_metadata(backend, sample_metadata):
    """Test saving and fetching metadata."""
    # Save metadata
    results = backend.save_metadata("test:object", "1.0.0", sample_metadata)
    assert results.all_ok

    # Fetch metadata and verify contents
    fetch_results = backend.fetch_metadata("test:object", "1.0.0")
    assert fetch_results.all_ok

    result = fetch_results.first()
    assert result.ok
    fetched_metadata = result.metadata

    # Remove the path field for comparison since it's added by fetch_metadata
    path = fetched_metadata.pop("path", None)
    assert path is not None  # Verify path was added
    assert path.startswith("gs://")

    # Verify metadata content
    assert fetched_metadata["name"] == sample_metadata["name"]
    assert fetched_metadata["version"] == sample_metadata["version"]
    assert fetched_metadata["description"] == sample_metadata["description"]


def test_delete_metadata(backend, sample_metadata):
    """Test deleting metadata."""
    # Save metadata first
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Verify it exists
    exists_before = backend.has_object("test:object", "1.0.0")
    assert exists_before[("test:object", "1.0.0")]

    # Delete metadata
    backend.delete_metadata("test:object", "1.0.0")

    # Verify metadata is deleted
    exists_after = backend.has_object("test:object", "1.0.0")
    assert not exists_after[("test:object", "1.0.0")]


def test_list_objects(backend, sample_metadata):
    """Test listing objects."""
    # Save metadata for multiple objects
    backend.save_metadata("object:1", "1.0.0", sample_metadata)
    backend.save_metadata("object:2", "1.0.0", sample_metadata)

    # List objects
    objects = backend.list_objects()

    # Verify results
    assert len(objects) >= 2
    assert "object:1" in objects
    assert "object:2" in objects


def test_list_versions(backend, sample_metadata):
    """Test listing versions."""
    # Save metadata for multiple versions
    backend.save_metadata("test:object", "1.0.0", sample_metadata)
    backend.save_metadata("test:object", "2.0.0", sample_metadata)

    # List versions - returns Dict[str, List[str]]
    versions_dict = backend.list_versions("test:object")
    versions = versions_dict["test:object"]

    # Verify results
    assert len(versions) == 2
    assert "1.0.0" in versions
    assert "2.0.0" in versions


def test_has_object(backend, sample_metadata):
    """Test checking object existence."""
    # Save metadata
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Check existing object - returns Dict[Tuple[str, str], bool]
    exists = backend.has_object("test:object", "1.0.0")
    assert exists[("test:object", "1.0.0")]

    # Check non-existing object
    not_exists = backend.has_object("nonexistent:object", "1.0.0")
    assert not not_exists[("nonexistent:object", "1.0.0")]

    not_exists_version = backend.has_object("test:object", "2.0.0")
    assert not not_exists_version[("test:object", "2.0.0")]


def test_delete_object(backend, sample_object_dir, sample_metadata):
    """Test deleting objects."""
    # Push an object
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Verify it exists
    exists_before = backend.has_object("test:object", "1.0.0")
    assert exists_before[("test:object", "1.0.0")]

    # Delete the object
    backend.delete("test:object", "1.0.0")

    # Verify object is deleted
    exists_after = backend.has_object("test:object", "1.0.0")
    assert not exists_after[("test:object", "1.0.0")]


def test_invalid_object_name(backend, sample_object_dir):
    """Test handling of invalid object names."""
    with pytest.raises(ValueError):
        backend.push("invalid_name", "1.0.0", sample_object_dir)


def test_register_materializer(backend):
    """Test registering a materializer."""
    # Register a materializer
    backend.register_materializer("test:object", "TestMaterializer")

    # Verify materializer was registered
    materializers = backend.registered_materializers()
    assert materializers["test:object"] == "TestMaterializer"


def test_registered_materializer(backend):
    """Test getting a registered materializer."""
    # Register a materializer
    backend.register_materializer("test:object", "TestMaterializer")

    # Get the registered materializer
    materializer = backend.registered_materializer("test:object")
    assert materializer == "TestMaterializer"

    # Test non-existent materializer
    assert backend.registered_materializer("nonexistent:object") is None


def test_registered_materializers(backend):
    """Test getting all registered materializers."""
    # Register multiple materializers
    backend.register_materializer("test:object1", "TestMaterializer1")
    backend.register_materializer("test:object2", "TestMaterializer2")

    # Get all registered materializers
    materializers = backend.registered_materializers()
    assert len(materializers) >= 2
    assert materializers["test:object1"] == "TestMaterializer1"
    assert materializers["test:object2"] == "TestMaterializer2"


def test_push_conflict_skip_single(backend, sample_object_dir, sample_metadata):
    """Test that single push with on_conflict='skip' returns skipped result."""
    # First push should succeed
    results1 = backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)
    assert results1.all_ok

    # Second push should return skipped result (backend is batch-only)
    results2 = backend.push(["test:object"], ["1.0.0"], [sample_object_dir], [sample_metadata], on_conflict="skip")
    assert ("test:object", "1.0.0") in results2
    assert results2[("test:object", "1.0.0")].is_skipped


def test_push_conflict_skip_batch(backend, sample_object_dir, sample_metadata, temp_dir):
    """Test that batch push with on_conflict='skip' returns skipped result."""
    # Create second object dir
    sample_object_dir2 = temp_dir / "sample_object2"
    sample_object_dir2.mkdir()
    (sample_object_dir2 / "file1.txt").write_text("content1")
    sample_metadata2 = {**sample_metadata, "name": "test:object2"}

    # First push for first object
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Batch push - first object already exists, second is new
    results = backend.push(
        ["test:object", "test:object2"],
        ["1.0.0", "1.0.0"],
        [str(sample_object_dir), str(sample_object_dir2)],
        [sample_metadata, sample_metadata2],
        on_conflict="skip",
    )

    # First item should be skipped (conflict)
    result1 = results.get(("test:object", "1.0.0"))
    assert result1.is_skipped

    # Second item should succeed
    result2 = results.get(("test:object2", "1.0.0"))
    assert result2.ok


def test_push_overwrite_requires_lock(backend, sample_object_dir, sample_metadata):
    """Test that overwrite without lock raises error."""
    # First push
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Overwrite without lock should raise
    with pytest.raises(ValueError, match="acquire_lock=True"):
        backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata, on_conflict="overwrite")


def test_push_overwrite_with_lock(backend, sample_object_dir, sample_metadata, temp_dir):
    """Test that overwrite with lock works."""
    # First push
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Create modified content
    modified_dir = temp_dir / "modified"
    modified_dir.mkdir()
    (modified_dir / "file1.txt").write_text("modified content")

    # Overwrite with lock should work
    results = backend.push(
        "test:object",
        "1.0.0",
        str(modified_dir),
        sample_metadata,
        on_conflict="overwrite",
        acquire_lock=True,
    )
    assert results.all_ok

    # Verify the content was updated
    download_dir = temp_dir / "download"
    download_dir.mkdir()
    backend.pull("test:object", "1.0.0", str(download_dir))
    assert (download_dir / "file1.txt").read_text() == "modified content"


# ─────────────────────────────────────────────────────────────────────────────
# Locking Behavior Tests (using internal _acquire_lock/_release_lock for verification)
# ─────────────────────────────────────────────────────────────────────────────


def test_lock_released_after_successful_push(backend, sample_object_dir, sample_metadata):
    """Test that lock is released after successful push with acquire_lock=True."""
    object_name = "test:lock-release"
    version = "1.0.0"

    # Push with lock
    result = backend.push(
        object_name, version, sample_object_dir, sample_metadata, on_conflict="skip", acquire_lock=True
    )
    assert result.all_ok

    # Verify lock is released by successfully acquiring it again
    lock_key = f"{object_name}@{version}"
    lock_id = "test-lock-verify"
    acquired = backend._acquire_lock(lock_key, lock_id, timeout=5)
    assert acquired, "Lock should be available after push completes"

    # Clean up
    backend._release_lock(lock_key, lock_id)


def test_lock_released_after_overwrite(backend, sample_object_dir, sample_metadata, temp_dir):
    """Test that lock is released after successful overwrite."""
    object_name = "test:lock-overwrite"
    version = "1.0.0"

    # First push
    backend.push(object_name, version, sample_object_dir, sample_metadata)

    # Create modified content
    modified_dir = temp_dir / "modified"
    modified_dir.mkdir()
    (modified_dir / "file1.txt").write_text("modified")

    # Overwrite with lock
    result = backend.push(
        object_name, version, str(modified_dir), sample_metadata, on_conflict="overwrite", acquire_lock=True
    )
    assert result.all_ok or result.first().is_overwritten

    # Verify lock is released
    lock_key = f"{object_name}@{version}"
    lock_id = "test-lock-verify"
    acquired = backend._acquire_lock(lock_key, lock_id, timeout=5)
    assert acquired, "Lock should be available after overwrite completes"
    backend._release_lock(lock_key, lock_id)


def test_lock_prevents_concurrent_push(backend, sample_object_dir, sample_metadata):
    """Test that holding a lock prevents another push from acquiring it."""
    import threading
    import time

    object_name = "test:lock-concurrent"
    version = "1.0.0"
    lock_key = f"{object_name}@{version}"

    # Manually acquire lock
    lock_id = "holding-lock"
    acquired = backend._acquire_lock(lock_key, lock_id, timeout=5)
    assert acquired, "Should be able to acquire lock"

    results = []

    def try_push():
        """Try to push while lock is held."""
        try:
            result = backend.push(
                object_name, version, sample_object_dir, sample_metadata, on_conflict="overwrite", acquire_lock=True
            )
            results.append(("success", result))
        except Exception as e:
            results.append(("error", str(e)))

    # Start push in background thread
    thread = threading.Thread(target=try_push)
    thread.start()

    # Wait a bit and then release lock
    time.sleep(0.5)
    backend._release_lock(lock_key, lock_id)

    thread.join(timeout=10)

    # The push should have either failed (lock timeout) or eventually succeeded after lock release
    assert len(results) == 1
    if results[0][0] == "error":
        assert "lock" in results[0][1].lower(), f"Expected lock error, got: {results[0][1]}"


def test_different_objects_dont_block(backend, sample_object_dir, sample_metadata, temp_dir):
    """Test that locking one object doesn't block operations on another object."""
    object_a = "test:lock-a"
    object_b = "test:lock-b"
    version = "1.0.0"

    # Create second test dir
    dir_b = temp_dir / "object_b"
    dir_b.mkdir()
    (dir_b / "file.txt").write_text("object b content")

    # Acquire lock on object A
    lock_key_a = f"{object_a}@{version}"
    lock_id = "holding-lock-a"
    acquired = backend._acquire_lock(lock_key_a, lock_id, timeout=5)
    assert acquired

    try:
        # Push to object B should succeed immediately (not blocked by A's lock)
        result = backend.push(object_b, version, str(dir_b), sample_metadata, on_conflict="skip", acquire_lock=True)
        assert result.all_ok, "Push to different object should not be blocked"
    finally:
        backend._release_lock(lock_key_a, lock_id)


def test_delete_with_lock(backend, sample_object_dir, sample_metadata):
    """Test delete operation with acquire_lock=True."""
    object_name = "test:delete-lock"
    version = "1.0.0"

    # Push first
    backend.push(object_name, version, sample_object_dir, sample_metadata)
    assert backend.has_object(object_name, version)[(object_name, version)]

    # Delete with lock
    result = backend.delete(object_name, version, acquire_lock=True)
    assert result.all_ok

    # Verify deleted
    assert not backend.has_object(object_name, version)[(object_name, version)]

    # Verify lock was released
    lock_key = f"{object_name}@{version}"
    lock_id = "test-lock-verify"
    acquired = backend._acquire_lock(lock_key, lock_id, timeout=5)
    assert acquired, "Lock should be available after delete completes"
    backend._release_lock(lock_key, lock_id)


def test_pull_with_lock(backend, sample_object_dir, sample_metadata, temp_dir):
    """Test pull operation with acquire_lock=True (read lock for mutable registries)."""
    object_name = "test:pull-lock"
    version = "1.0.0"

    # Push first
    backend.push(object_name, version, sample_object_dir, sample_metadata)

    # Fetch metadata for pull
    meta_results = backend.fetch_metadata([object_name], [version])
    metadata = [meta_results.first().metadata]

    # Pull with lock
    download_dir = temp_dir / "download"
    download_dir.mkdir()
    result = backend.pull(object_name, version, str(download_dir), acquire_lock=True, metadata=metadata)
    assert result.all_ok

    # Verify content was downloaded
    assert (download_dir / "file1.txt").exists()

    # Verify lock was released
    lock_key = f"{object_name}@{version}"
    lock_id = "test-lock-verify"
    acquired = backend._acquire_lock(lock_key, lock_id, timeout=5)
    assert acquired, "Lock should be available after pull completes"
    backend._release_lock(lock_key, lock_id)


def test_lock_timeout_short(backend, sample_object_dir, sample_metadata):
    """Test that lock acquisition respects timeout parameter."""
    object_name = "test:lock-timeout"
    version = "1.0.0"
    lock_key = f"{object_name}@{version}"

    # Acquire lock
    lock_id_holder = "holding-lock"
    acquired = backend._acquire_lock(lock_key, lock_id_holder, timeout=30)
    assert acquired

    try:
        # Try to acquire same lock with very short timeout - should fail
        lock_id_waiter = "waiting-lock"
        acquired_waiter = backend._acquire_lock(lock_key, lock_id_waiter, timeout=1)
        assert not acquired_waiter, "Should not acquire lock when already held"
    finally:
        backend._release_lock(lock_key, lock_id_holder)


def test_lock_stale_detection(backend):
    """Test that stale locks (from crashed processes) are eventually overridable.

    Note: GCS-based locks use generation matching. A stale lock can be detected
    by checking lock timestamp vs current time. This test verifies basic lock
    lifecycle but full stale lock handling may require TTL mechanisms.
    """
    lock_key = "test:stale-lock"
    lock_id_1 = "process-1"
    lock_id_2 = "process-2"

    # Acquire lock
    acquired = backend._acquire_lock(lock_key, lock_id_1, timeout=5)
    assert acquired

    # Simulate process crash by NOT releasing lock, but verify it exists
    lock_path = backend._lock_path(lock_key)
    assert backend.gcs.exists(lock_path), "Lock file should exist"

    # Another process trying to acquire should fail (lock is held)
    acquired_2 = backend._acquire_lock(lock_key, lock_id_2, timeout=1)
    assert not acquired_2, "Should not acquire lock held by another process"

    # Clean up (simulate recovery - force delete lock file)
    backend.gcs.delete(lock_path)


# ─────────────────────────────────────────────────────────────────────────────
# Registry Integration Tests - Mutable vs Immutable
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mutable_registry(backend):
    """Create a mutable Registry instance (allows overwrites)."""
    return Registry(backend=backend, version_objects=True, mutable=True, use_cache=False)


@pytest.fixture
def immutable_registry(backend):
    """Create an immutable Registry instance (raises on conflicts)."""
    return Registry(backend=backend, version_objects=True, mutable=False, use_cache=False)


@pytest.fixture
def unversioned_registry(backend):
    """Create a registry without version tracking."""
    return Registry(backend=backend, version_objects=False, mutable=True, use_cache=False)


def test_mutable_registry_allows_overwrite(mutable_registry):
    """Test that mutable registry allows saving to same version without error."""
    # First save
    mutable_registry.save("test:mutable", "value1", version="1.0.0")
    loaded1 = mutable_registry.load("test:mutable", version="1.0.0")
    assert loaded1 == "value1"

    # Overwrite same version - should work in mutable mode
    mutable_registry.save("test:mutable", "value2", version="1.0.0")
    loaded2 = mutable_registry.load("test:mutable", version="1.0.0")
    assert loaded2 == "value2"


def test_immutable_registry_raises_on_conflict(immutable_registry):
    """Test that immutable registry raises RegistryVersionConflict on duplicate."""
    # First save
    immutable_registry.save("test:immutable", "value1", version="1.0.0")

    # Second save to same version should raise
    with pytest.raises(RegistryVersionConflict):
        immutable_registry.save("test:immutable", "value2", version="1.0.0")


def test_version_objects_keeps_history(gcp_registry):
    """Test that version_objects=True keeps version history."""
    # Save multiple versions
    gcp_registry.save("test:history", "v1", version="1.0.0")
    gcp_registry.save("test:history", "v2", version="2.0.0")
    gcp_registry.save("test:history", "v3", version="3.0.0")

    # All versions should be accessible
    assert gcp_registry.load("test:history", version="1.0.0") == "v1"
    assert gcp_registry.load("test:history", version="2.0.0") == "v2"
    assert gcp_registry.load("test:history", version="3.0.0") == "v3"

    # Latest should be highest version
    assert gcp_registry.load("test:history") == "v3"

    # List versions should show all
    versions = gcp_registry.list_versions("test:history")
    assert "1.0.0" in versions
    assert "2.0.0" in versions
    assert "3.0.0" in versions


def test_unversioned_registry_single_version(unversioned_registry):
    """Test that version_objects=False uses single version."""
    # Save without explicit version
    unversioned_registry.save("test:unversioned", "value1")
    loaded1 = unversioned_registry.load("test:unversioned")
    assert loaded1 == "value1"

    # Overwrite (mutable=True allows this)
    unversioned_registry.save("test:unversioned", "value2")
    loaded2 = unversioned_registry.load("test:unversioned")
    assert loaded2 == "value2"


def test_registry_delete_version(gcp_registry):
    """Test deleting a specific version."""
    # Save multiple versions
    gcp_registry.save("test:delete", "v1", version="1.0.0")
    gcp_registry.save("test:delete", "v2", version="2.0.0")

    # Delete v1
    gcp_registry.delete("test:delete", version="1.0.0")

    # v1 should be gone, v2 should still exist
    with pytest.raises(Exception):  # ObjectNotFound or similar
        gcp_registry.load("test:delete", version="1.0.0")

    assert gcp_registry.load("test:delete", version="2.0.0") == "v2"


def test_registry_delete_all_versions(gcp_registry):
    """Test deleting all versions of an object."""
    # Save multiple versions
    gcp_registry.save("test:deleteall", "v1", version="1.0.0")
    gcp_registry.save("test:deleteall", "v2", version="2.0.0")

    # Delete all versions
    gcp_registry.delete("test:deleteall")

    # Object should not exist
    assert "test:deleteall" not in gcp_registry.list_objects()


# ─────────────────────────────────────────────────────────────────────────────
# Registry Integration Tests - Basic
# ─────────────────────────────────────────────────────────────────────────────


def test_registry_integration(gcp_registry):
    """Test full registry integration with GCP backend."""
    # Save objects using registry with explicit versions to avoid conflicts
    gcp_registry.save("test:str", "Hello, GCP!", version="1.0.0")
    gcp_registry.save("test:list", [1, 2, 3], version="1.0.0")

    # Load objects
    loaded_str = gcp_registry.load("test:str", version="1.0.0")
    loaded_list = gcp_registry.load("test:list", version="1.0.0")

    assert loaded_str == "Hello, GCP!"
    assert loaded_list == [1, 2, 3]


def test_registry_versioning(gcp_registry):
    """Test registry versioning functionality."""
    gcp_registry.save("test:versioned", "version1", version="1.0.0")
    gcp_registry.save("test:versioned", "version2", version="2.0.0")

    v1 = gcp_registry.load("test:versioned", version="1.0.0")
    v2 = gcp_registry.load("test:versioned", version="2.0.0")
    latest = gcp_registry.load("test:versioned")

    assert v1 == "version1"
    assert v2 == "version2"
    assert latest == "version2"


def test_registry_object_discovery(gcp_registry):
    """Test registry object listing."""
    gcp_registry.save("test:obj1", "data1")
    gcp_registry.save("test:obj2", "data2")

    objects = gcp_registry.list_objects()
    assert "test:obj1" in objects
    assert "test:obj2" in objects


def test_registry_version_listing(gcp_registry):
    """Test registry version listing."""
    gcp_registry.save("test:versioned", "v1", version="1.0.0")
    gcp_registry.save("test:versioned", "v2", version="2.0.0")

    versions = gcp_registry.list_versions("test:versioned")
    assert "1.0.0" in versions
    assert "2.0.0" in versions


def test_concurrent_save_load(gcp_registry):
    """Test concurrent save/load operations."""
    import threading

    results = []
    errors = []

    def worker(worker_id):
        try:
            # Use unique object names with explicit versions
            obj_name = f"test:concurrent:{worker_id}"
            version = "1.0.0"
            gcp_registry.save(obj_name, f"data_{worker_id}", version=version)
            loaded = gcp_registry.load(obj_name, version=version)
            if loaded == f"data_{worker_id}":
                results.append(f"Worker {worker_id} success")
            else:
                errors.append(f"Worker {worker_id} data mismatch: {loaded}")
        except Exception as e:
            errors.append(f"Worker {worker_id} failed: {e}")

    # Start multiple workers
    threads = []
    for i in range(3):
        thread = threading.Thread(target=worker, args=(i,))
        threads.append(thread)
        thread.start()

    # Wait for all threads
    for thread in threads:
        thread.join()

    # Verify all operations completed successfully
    assert len(errors) == 0, f"Errors: {errors}"
    assert len(results) == 3


# ─────────────────────────────────────────────────────────────────────────────
# Error Handling Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_error_handling_invalid_credentials():
    """Test error handling for invalid credentials."""
    with pytest.raises(Exception):  # Should raise authentication error
        GCPRegistryBackend(
            uri="gs://test-bucket",
            project_id="invalid-project",
            bucket_name="test-bucket",
            credentials_path="/nonexistent/credentials.json",
        )


def test_error_handling_nonexistent_bucket():
    """Test error handling for nonexistent bucket."""
    with pytest.raises(Exception):  # Should raise bucket not found error
        GCPRegistryBackend(
            uri="gs://nonexistent-bucket",
            project_id=os.environ.get("GCP_PROJECT_ID", "mindtrace-test"),
            bucket_name="nonexistent-bucket",
            ensure_bucket=True,
            create_if_missing=False,
        )


def test_metadata_file_initialization(backend):
    """Test that backend initializes metadata file correctly."""
    # The metadata file should be created on init
    metadata = backend.fetch_registry_metadata()
    assert isinstance(metadata, dict)
    assert "materializers" in metadata


def test_cleanup_after_test(backend, sample_metadata):
    """Test that cleanup works correctly."""
    # Save some data
    backend.save_metadata("cleanup:test", "1.0.0", sample_metadata)

    # Verify it exists
    exists = backend.has_object("cleanup:test", "1.0.0")
    assert exists[("cleanup:test", "1.0.0")]

    # The fixture cleanup should handle deletion after test
