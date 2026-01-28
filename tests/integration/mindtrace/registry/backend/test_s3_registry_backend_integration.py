"""Integration tests for S3RegistryBackend.

Uses MinIO as the S3-compatible backend for testing.
"""

import uuid
from pathlib import Path

import pytest

from mindtrace.core import CoreConfig
from mindtrace.registry import S3RegistryBackend


def test_init(s3_backend, s3_test_bucket, s3_client):
    """Test backend initialization."""
    assert s3_client.bucket_exists(s3_test_bucket)


def test_push_and_pull(s3_backend, sample_object_dir, s3_client, s3_test_bucket):
    """Test pushing and pulling objects with MVCC (UUID-based isolation)."""
    # Push the object with metadata containing _files manifest
    metadata = {"_files": ["file1.txt", "file2.txt"]}
    result = s3_backend.push("test:object", "1.0.0", sample_object_dir, metadata=metadata)
    assert result.first().ok

    # Verify the object was pushed to S3 (UUID folder contains 2 files)
    # With MVCC, path is: objects/test:object/1.0.0/{uuid}/file1.txt
    objects = list(s3_client.list_objects(s3_test_bucket, prefix="objects/test:object/1.0.0/", recursive=True))
    # Should have 2 files in the UUID folder
    files = [obj for obj in objects if not obj.is_dir]
    assert len(files) == 2

    # Download to a new location - use fetch_metadata to get _storage.uuid
    download_dir = s3_backend.uri / "download"
    download_dir.mkdir(parents=True, exist_ok=True)
    fetched = s3_backend.fetch_metadata("test:object", "1.0.0")
    assert fetched.first().ok
    result = s3_backend.pull("test:object", "1.0.0", str(download_dir), metadata=[fetched.first().metadata])
    assert result.first().ok

    # Verify the download
    assert (download_dir / "file1.txt").exists()
    assert (download_dir / "file2.txt").exists()
    assert (download_dir / "file1.txt").read_text() == "test content 1"
    assert (download_dir / "file2.txt").read_text() == "test content 2"


def test_save_and_fetch_metadata(s3_backend, sample_metadata, s3_client, s3_test_bucket):
    """Test saving and fetching metadata."""
    # Save metadata
    result = s3_backend.save_metadata("test:object", "1.0.0", sample_metadata)
    assert result.first().ok

    # Verify metadata exists in S3
    objects = list(s3_client.list_objects(s3_test_bucket, prefix="_meta_test_object@1.0.0.json"))
    assert len(objects) == 1

    # Fetch metadata and verify contents
    fetch_result = s3_backend.fetch_metadata("test:object", "1.0.0")
    assert fetch_result.first().ok
    fetched_metadata = fetch_result.first().metadata

    # With MVCC, path is only set during push() - save_metadata is low-level
    # Just verify the metadata we saved is returned correctly
    assert fetched_metadata == sample_metadata

    # Delete metadata
    result = s3_backend.delete_metadata("test:object", "1.0.0")
    assert result.first().ok

    # Verify metadata is deleted
    objects = list(s3_client.list_objects(s3_test_bucket, prefix="_meta_test_object@1.0.0.json"))
    assert len(objects) == 0


def test_delete_metadata(s3_backend, sample_metadata, s3_client, s3_test_bucket):
    """Test deleting metadata."""
    # Save metadata first
    s3_backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Delete metadata
    result = s3_backend.delete_metadata("test:object", "1.0.0")
    assert result.first().ok

    # Verify metadata is deleted from S3
    objects = list(s3_client.list_objects(s3_test_bucket, prefix="_meta_test_object@1.0.0.json"))
    assert len(objects) == 0


def test_list_objects(s3_backend, sample_metadata, s3_client, s3_test_bucket):
    """Test listing objects."""
    # Save metadata for multiple objects
    s3_backend.save_metadata("object:1", "1.0.0", sample_metadata)
    s3_backend.save_metadata("object:2", "1.0.0", sample_metadata)

    # List objects
    objects = s3_backend.list_objects()

    # Verify results
    assert len(objects) == 2
    assert "object:1" in objects
    assert "object:2" in objects


def test_list_versions(s3_backend, sample_metadata, s3_client, s3_test_bucket):
    """Test listing versions."""
    # Save metadata for multiple versions
    s3_backend.save_metadata("test:object", "1.0.0", sample_metadata)
    s3_backend.save_metadata("test:object", "2.0.0", sample_metadata)

    # List versions - returns Dict[str, List[str]]
    versions_dict = s3_backend.list_versions("test:object")
    versions = versions_dict.get("test:object", [])

    # Verify results
    assert len(versions) == 2
    assert "1.0.0" in versions
    assert "2.0.0" in versions


def test_list_versions_uses_metadata_prefix(s3_backend, sample_metadata, s3_client, s3_test_bucket):
    """Test that list_versions correctly uses _object_metadata_prefix."""
    # Save metadata for an object with colons in the name
    s3_backend.save_metadata("test:object:with:colons", "1.0.0", sample_metadata)
    s3_backend.save_metadata("test:object:with:colons", "2.0.0", sample_metadata)

    # Verify the metadata prefix is correctly generated (colons should be replaced with underscores)
    expected_prefix = "_meta_test_object_with_colons@"
    assert s3_backend._object_metadata_prefix("test:object:with:colons") == expected_prefix

    # List versions - returns Dict[str, List[str]]
    versions_dict = s3_backend.list_versions("test:object:with:colons")
    versions = versions_dict.get("test:object:with:colons", [])

    # Verify results
    assert len(versions) == 2
    assert "1.0.0" in versions
    assert "2.0.0" in versions

    # Verify the metadata files were created with the correct prefix format
    objects = list(s3_client.list_objects(s3_test_bucket, prefix=expected_prefix))
    assert len(objects) == 2
    assert any(obj.object_name == f"{expected_prefix}1.0.0.json" for obj in objects)
    assert any(obj.object_name == f"{expected_prefix}2.0.0.json" for obj in objects)


def test_has_object(s3_backend, sample_metadata, s3_client, s3_test_bucket):
    """Test checking object existence."""
    # Save metadata
    s3_backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Check existing object - returns Dict[Tuple[str, str], bool]
    result = s3_backend.has_object("test:object", "1.0.0")
    assert result[("test:object", "1.0.0")]

    # Check non-existing object
    result = s3_backend.has_object("nonexistent:object", "1.0.0")
    assert not result[("nonexistent:object", "1.0.0")]
    result = s3_backend.has_object("test:object", "2.0.0")
    assert not result[("test:object", "2.0.0")]


def test_delete_object(s3_backend, sample_object_dir, s3_client, s3_test_bucket):
    """Test deleting objects."""
    # Push an object (push() handles metadata automatically)
    metadata = {"name": "test:object", "_files": ["file1.txt", "file2.txt"]}
    s3_backend.push("test:object", "1.0.0", sample_object_dir, metadata=metadata)

    # Delete the object
    result = s3_backend.delete("test:object", "1.0.0")
    assert result.first().ok

    # Verify object is deleted from S3
    objects = list(s3_client.list_objects(s3_test_bucket, prefix="objects/test:object/1.0.0/"))
    assert len(objects) == 0


def test_invalid_object_name(s3_backend):
    """Test handling of invalid object names."""
    with pytest.raises(ValueError):
        s3_backend.push("invalid_name", "1.0.0", "some_path")


def test_register_materializer(s3_backend, s3_client, s3_test_bucket):
    """Test registering a materializer."""
    # Register a materializer
    s3_backend.register_materializer("test:object", "TestMaterializer")

    # Verify materializer was registered
    materializers = s3_backend.registered_materializers()
    assert materializers["test:object"] == "TestMaterializer"


def test_registered_materializer(s3_backend, s3_client, s3_test_bucket):
    """Test getting a registered materializer."""
    # Register a materializer
    s3_backend.register_materializer("test:object", "TestMaterializer")

    # Get the registered materializer
    materializer = s3_backend.registered_materializer("test:object")
    assert materializer == "TestMaterializer"

    # Test non-existent materializer
    assert s3_backend.registered_materializer("nonexistent:object") is None


def test_registered_materializers(s3_backend, s3_client, s3_test_bucket):
    """Test getting all registered materializers."""
    # Register multiple materializers
    s3_backend.register_materializer("test:object1", "TestMaterializer1")
    s3_backend.register_materializer("test:object2", "TestMaterializer2")

    # Get all registered materializers
    materializers = s3_backend.registered_materializers()
    assert len(materializers) == 2
    assert materializers["test:object1"] == "TestMaterializer1"
    assert materializers["test:object2"] == "TestMaterializer2"


def test_init_with_default_uri(s3_client, s3_test_bucket):
    """Test backend initialization with default URI (S3 path)."""
    from tests.integration.mindtrace.registry.conftest import get_s3_config

    config = get_s3_config()
    # Create backend without specifying URI - uses bucket as default
    backend = S3RegistryBackend(
        endpoint=config["endpoint"],
        access_key=config["access_key"],
        secret_key=config["secret_key"],
        bucket=s3_test_bucket,
        secure=config["secure"],
    )

    # Verify the URI is set to the S3 bucket path
    expected_uri = Path(f"s3:/{s3_test_bucket}")
    assert backend.uri == expected_uri
    assert s3_client.bucket_exists(s3_test_bucket)


def test_init_creates_bucket(s3_client):
    """Test backend initialization creates a new bucket if it doesn't exist."""
    from tests.integration.mindtrace.registry.conftest import get_s3_config

    config = get_s3_config()
    # Create a unique bucket name that doesn't exist
    bucket_name = f"test-bucket-{uuid.uuid4()}"

    # Verify bucket doesn't exist
    assert not s3_client.bucket_exists(bucket_name)

    # Create backend with the new bucket name
    _ = S3RegistryBackend(
        uri=str(Path(CoreConfig()["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]).expanduser() / f"test_dir_{uuid.uuid4()}"),
        endpoint=config["endpoint"],
        access_key=config["access_key"],
        secret_key=config["secret_key"],
        bucket=bucket_name,
        secure=config["secure"],
    )

    # Verify the bucket was created
    assert s3_client.bucket_exists(bucket_name)

    # Cleanup - remove all objects first, then the bucket
    for obj in s3_client.list_objects(bucket_name, recursive=True):
        s3_client.remove_object(bucket_name, obj.object_name)
    s3_client.remove_bucket(bucket_name)


# ─────────────────────────────────────────────────────────────────────────────
# Locking Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_push_conflict_skip_returns_skipped(s3_backend, sample_object_dir, sample_metadata):
    """Test that pushing with on_conflict='skip' returns skipped result (batch-only behavior)."""
    object_name = f"test:conflict-skip-{uuid.uuid4().hex[:8]}"
    version = "1.0.0"

    # First push should succeed
    result1 = s3_backend.push(object_name, version, sample_object_dir, metadata=sample_metadata)
    assert result1.first().ok

    # Second push with skip should return skipped result (not raise)
    results = s3_backend.push(object_name, version, sample_object_dir, metadata=sample_metadata, on_conflict="skip")
    result = results.get((object_name, version))
    assert result.is_skipped


def test_push_overwrite_without_lock(s3_backend, sample_object_dir, sample_metadata, s3_temp_dir):
    """Test that overwrite works without lock using MVCC."""
    object_name = f"test:overwrite-mvcc-{uuid.uuid4().hex[:8]}"
    version = "1.0.0"

    # First push
    result1 = s3_backend.push(object_name, version, sample_object_dir, metadata=sample_metadata)
    assert result1.first().ok

    # Create modified data
    modified_dir = s3_temp_dir / "modified"
    modified_dir.mkdir()
    (modified_dir / "file1.txt").write_text("modified content")
    (modified_dir / "file2.txt").write_text("modified content 2")

    # Overwrite without lock should succeed using MVCC
    result2 = s3_backend.push(
        object_name, version, str(modified_dir), metadata=sample_metadata, on_conflict="overwrite"
    )
    assert result2.first().ok or result2.first().overwritten

    # Verify pull gets the modified content
    download_dir = s3_backend.uri / "download_verify"
    download_dir.mkdir(parents=True, exist_ok=True)
    fetched = s3_backend.fetch_metadata(object_name, version)
    result = s3_backend.pull(object_name, version, str(download_dir), metadata=[fetched.first().metadata])
    assert result.first().ok
    assert (download_dir / "file1.txt").read_text() == "modified content"


def test_push_overwrite_with_lock(s3_backend, sample_object_dir, sample_metadata, s3_temp_dir):
    """Test that overwrite with lock succeeds."""
    object_name = f"test:overwrite-lock-{uuid.uuid4().hex[:8]}"
    version = "1.0.0"

    # First push
    s3_backend.push(object_name, version, sample_object_dir, metadata=sample_metadata)

    # Create modified data
    modified_dir = s3_temp_dir / "modified"
    modified_dir.mkdir()
    (modified_dir / "file1.txt").write_text("modified content")
    (modified_dir / "file2.txt").write_text("modified content 2")

    # Overwrite with lock should succeed
    result = s3_backend.push(
        object_name,
        version,
        str(modified_dir),
        metadata=sample_metadata,
        on_conflict="overwrite",
        acquire_lock=True,
    )
    assert result.first().ok or result.first().is_overwritten


def test_lock_released_after_successful_push(s3_backend, sample_object_dir, sample_metadata):
    """Test that lock is released after successful push with acquire_lock=True."""
    object_name = f"test:lock-release-{uuid.uuid4().hex[:8]}"
    version = "1.0.0"

    # Push with lock
    result = s3_backend.push(
        object_name, version, sample_object_dir, metadata=sample_metadata, on_conflict="skip", acquire_lock=True
    )
    assert result.first().ok

    # Lock should be released - try to acquire it
    lock_key = f"{object_name}@{version}"
    lock_id = f"test-{uuid.uuid4().hex[:8]}"
    acquired = s3_backend._acquire_lock(lock_key, lock_id, timeout=5)
    assert acquired, "Lock should be available after push completes"
    s3_backend._release_lock(lock_key, lock_id)


def test_mvcc_concurrent_push_first_wins(s3_backend, sample_object_dir, sample_metadata):
    """Test that with MVCC, concurrent pushes with on_conflict='skip' result in first-write-wins."""
    object_name = f"test:mvcc-concurrent-{uuid.uuid4().hex[:8]}"
    version = "1.0.0"

    # First push should succeed
    result1 = s3_backend.push(object_name, version, sample_object_dir, metadata=sample_metadata, on_conflict="skip")
    assert result1.first().ok

    # Second push with skip should return skipped (first write wins)
    result2 = s3_backend.push(object_name, version, sample_object_dir, metadata=sample_metadata, on_conflict="skip")
    assert result2.first().is_skipped


def test_mvcc_batch_push_mixed_results(s3_backend, sample_object_dir, sample_metadata):
    """Test batch push with mixed results (some exist, some new)."""
    object_name1 = f"test:mvcc-batch1-{uuid.uuid4().hex[:8]}"
    object_name2 = f"test:mvcc-batch2-{uuid.uuid4().hex[:8]}"
    version = "1.0.0"

    # Pre-push first object to make it exist
    pre_result = s3_backend.push(object_name1, version, sample_object_dir, metadata=sample_metadata)
    assert pre_result.first().ok

    # Batch push both with skip - first should skip, second should succeed
    result = s3_backend.push(
        [object_name1, object_name2],
        [version, version],
        [sample_object_dir, sample_object_dir],
        metadata=[sample_metadata, sample_metadata],
        on_conflict="skip",
    )

    assert len(result) == 2
    result1 = result.get((object_name1, version))
    result2 = result.get((object_name2, version))

    assert result1 is not None and result1.is_skipped, "First object should be skipped (exists)"
    assert result2 is not None and result2.ok, "Second object should succeed"


def test_delete_with_lock(s3_backend, sample_object_dir, sample_metadata):
    """Test delete operation with acquire_lock=True."""
    object_name = f"test:delete-lock-{uuid.uuid4().hex[:8]}"
    version = "1.0.0"

    # Push with metadata (push() handles metadata automatically)
    metadata = {**sample_metadata, "_files": ["file1.txt", "file2.txt"]}
    s3_backend.push(object_name, version, sample_object_dir, metadata=metadata)

    # Delete with lock
    result = s3_backend.delete(object_name, version, acquire_lock=True)
    assert result.first().ok

    # Verify deleted
    assert not s3_backend.has_object(object_name, version)[(object_name, version)]

    # Verify lock was released
    lock_key = f"{object_name}@{version}"
    lock_id = f"test-{uuid.uuid4().hex[:8]}"
    acquired = s3_backend._acquire_lock(lock_key, lock_id, timeout=5)
    assert acquired
    s3_backend._release_lock(lock_key, lock_id)


def test_pull_with_metadata(s3_backend, sample_object_dir, sample_metadata, s3_temp_dir):
    """Test pull operation with pre-fetched metadata."""
    object_name = f"test:pull-meta-{uuid.uuid4().hex[:8]}"
    version = "1.0.0"

    # Push with metadata
    metadata = {**sample_metadata, "_files": ["file1.txt", "file2.txt"]}
    s3_backend.push(object_name, version, sample_object_dir, metadata=metadata)

    # Fetch metadata (includes _storage.uuid from MVCC)
    fetched = s3_backend.fetch_metadata(object_name, version)
    assert fetched.first().ok

    # Pull with pre-fetched metadata
    download_dir = s3_temp_dir / "pull_test"
    download_dir.mkdir()
    result = s3_backend.pull(object_name, version, str(download_dir), metadata=[fetched.first().metadata])
    assert result.first().ok

    # Verify files downloaded
    assert (download_dir / "file1.txt").exists()

    # Verify lock was released
    lock_key = f"{object_name}@{version}"
    lock_id = f"test-{uuid.uuid4().hex[:8]}"
    acquired = s3_backend._acquire_lock(lock_key, lock_id, timeout=5)
    assert acquired
    s3_backend._release_lock(lock_key, lock_id)
