import json
import shutil
import uuid
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest

from mindtrace.core import CoreConfig
from mindtrace.registry import LocalRegistryBackend


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    temp_dir = Path(CoreConfig()["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]).expanduser() / f"test_dir_{uuid.uuid4()}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def backend(temp_dir):
    """Create a LocalRegistryBackend instance with a temporary directory."""
    return LocalRegistryBackend(uri=str(temp_dir))


@pytest.fixture
def sample_object_dir(temp_dir):
    """Create a sample object directory with some files."""
    obj_dir = temp_dir / "sample:object"
    obj_dir.mkdir()
    (obj_dir / "file1.txt").write_text("test content 1")
    (obj_dir / "file2.txt").write_text("test content 2")
    return str(obj_dir)


@pytest.fixture
def sample_metadata():
    """Sample metadata for testing."""
    return {
        "name": "test:object",
        "version": "1.0.0",
        "description": "Test object",
        "created_at": "2024-01-01T00:00:00Z",
    }


def test_init(backend):
    """Test backend initialization."""
    assert backend.uri.exists()
    assert backend.uri.is_dir()


def test_push_and_download(backend, sample_object_dir):
    """Test pushing and downloading objects."""
    # Push the object
    backend.push("test:object", "1.0.0", sample_object_dir)

    # Verify the object was pushed
    object_path = backend.uri / "test:object" / "1.0.0"
    assert object_path.exists()
    assert (object_path / "file1.txt").exists()
    assert (object_path / "file2.txt").exists()

    # Download to a new location
    download_dir = backend.uri / "download"
    download_dir.mkdir()
    backend.pull("test:object", "1.0.0", str(download_dir))

    # Verify the download
    assert (download_dir / "file1.txt").exists()
    assert (download_dir / "file2.txt").exists()
    assert (download_dir / "file1.txt").read_text() == "test content 1"
    assert (download_dir / "file2.txt").read_text() == "test content 2"


def test_save_and_fetch_metadata(backend, sample_metadata):
    """Test saving and fetching metadata."""
    # Save metadata
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Verify metadata file exists
    meta_path = backend.uri / "_meta_test_object@1.0.0.yaml"
    assert meta_path.exists()

    # Fetch metadata - returns OpResults with OpResult for each (name, version)
    result = backend.fetch_metadata("test:object", "1.0.0")
    assert result[("test:object", "1.0.0")].ok
    fetched_metadata = result[("test:object", "1.0.0")].metadata

    # Verify metadata content
    assert fetched_metadata["description"] == sample_metadata["description"]
    assert "path" in fetched_metadata  # Should be added by fetch_metadata


def test_fetch_metadata_empty_file_single(backend):
    """Test that single item fetch_metadata raises for empty metadata files."""
    from mindtrace.registry.core.exceptions import RegistryObjectNotFound

    # Create an empty metadata file (yaml.safe_load will return None for empty files)
    meta_path = backend.uri / "_meta_test_object@1.0.0.yaml"
    meta_path.touch()  # Create empty file

    # Also create the object directory so the path update doesn't fail
    obj_dir = backend.uri / "test:object" / "1.0.0"
    obj_dir.mkdir(parents=True)

    # Single item fetch_metadata raises RegistryObjectNotFound for empty/corrupted files
    with pytest.raises(RegistryObjectNotFound):
        backend.fetch_metadata("test:object", "1.0.0")


def test_fetch_metadata_empty_file_batch(backend, sample_metadata):
    """Test that batch fetch_metadata skips empty metadata files."""
    # Create an empty metadata file (yaml.safe_load will return None for empty files)
    meta_path = backend.uri / "_meta_test_object@1.0.0.yaml"
    meta_path.touch()  # Create empty file

    # Also create the object directory so the path update doesn't fail
    obj_dir = backend.uri / "test:object" / "1.0.0"
    obj_dir.mkdir(parents=True)

    # Create a valid object for batch
    backend.save_metadata("test:valid", "1.0.0", sample_metadata)

    # Batch fetch_metadata skips empty/corrupted entries
    result = backend.fetch_metadata(["test:object", "test:valid"], ["1.0.0", "1.0.0"])
    # Empty file entry should be skipped
    assert ("test:object", "1.0.0") not in result
    # Valid entry should be present
    assert ("test:valid", "1.0.0") in result
    assert result[("test:valid", "1.0.0")].ok


def test_delete_metadata(backend, sample_metadata):
    """Test deleting metadata."""
    # Save metadata first
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Delete metadata
    backend.delete_metadata("test:object", "1.0.0")

    # Verify metadata is deleted
    meta_path = backend.uri / "_meta_test:object@1.0.0.yaml"
    assert not meta_path.exists()


def test_list_objects(backend, sample_metadata):
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


def test_list_versions(backend, sample_metadata):
    """Test listing versions."""
    # Save metadata for multiple versions
    backend.save_metadata("test:object", "1.0.0", sample_metadata)
    backend.save_metadata("test:object", "2.0.0", sample_metadata)

    # List versions - returns Dict[str, List[str]]
    result = backend.list_versions("test:object")
    versions = result["test:object"]

    # Verify results
    assert len(versions) == 2
    assert "1.0.0" in versions
    assert "2.0.0" in versions


def test_has_object(backend, sample_metadata):
    """Test checking object existence."""
    # Save metadata
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Check existing object - returns Dict[Tuple[str, str], bool]
    result = backend.has_object("test:object", "1.0.0")
    assert result[("test:object", "1.0.0")] is True

    # Check non-existing object
    result = backend.has_object("nonexistent:object", "1.0.0")
    assert result[("nonexistent:object", "1.0.0")] is False

    result = backend.has_object("test:object", "2.0.0")
    assert result[("test:object", "2.0.0")] is False


def test_delete_object(backend, sample_object_dir):
    """Test deleting objects."""
    # Push an object
    backend.push("test:object", "1.0.0", sample_object_dir)

    # Save metadata
    backend.save_metadata("test:object", "1.0.0", {"name": "test:object"})

    # Delete the object
    backend.delete("test:object", "1.0.0")

    # Verify object is deleted
    object_path = backend.uri / "test:object" / "1.0.0"
    assert not object_path.exists()

    # Verify metadata is deleted
    meta_path = backend.uri / "_meta_test:object@1.0.0.yaml"
    assert not meta_path.exists()


def test_invalid_object_name(backend):
    """Test handling of invalid object names."""
    with pytest.raises(ValueError):
        backend.push("invalid_name", "1.0.0", "some_path")


def test_register_materializer_metadata_not_exists(backend):
    """Test register_materializer when metadata file doesn't exist."""
    # Ensure metadata file doesn't exist
    if backend.metadata_path.exists():
        backend.metadata_path.unlink()

    # Register a materializer - should create metadata file
    backend.register_materializer("test.Object", "TestMaterializer")

    # Verify metadata file was created and materializer was registered
    assert backend.metadata_path.exists()
    materializer = backend.registered_materializer("test.Object")
    assert materializer == "TestMaterializer"


def test_register_materializer_error(backend):
    """Test error handling when registering a materializer fails."""
    # Create the metadata file first
    with open(backend.metadata_path, "w") as f:
        json.dump({"materializers": {}}, f)

    # Make the metadata file read-only to simulate a file system error
    backend.metadata_path.chmod(0o444)

    # Try to register a materializer - should raise an error
    with pytest.raises(Exception):
        backend.register_materializer("test.Object", "test.Materializer")


def test_registered_materializers_error(backend):
    """Test error handling when fetching registered materializers fails."""
    # Create the metadata file first
    with open(backend.metadata_path, "w") as f:
        json.dump({"materializers": {}}, f)

    # Make the metadata file unreadable to simulate a file system error
    backend.metadata_path.chmod(0o000)

    # Try to get registered materializers - should raise an error
    with pytest.raises(Exception):
        backend.registered_materializers()


def test_registered_materializers_empty(backend):
    """Test that registered_materializers returns an empty dict when metadata path doesn't exist."""
    # Ensure metadata path doesn't exist
    if backend.metadata_path.exists():
        backend.metadata_path.unlink()

    # Get registered materializers
    materializers = backend.registered_materializers()

    # Verify empty dict is returned
    assert materializers == {}
    assert isinstance(materializers, dict)


def test_delete_parent_directory_error(backend, sample_object_dir):
    """Test error handling when deleting parent directory fails."""
    # Save an object first
    backend.push("test:obj", "1.0.0", str(sample_object_dir))

    # Mock rmdir to raise an exception for parent directory cleanup
    original_rmdir = Path.rmdir

    def mock_rmdir(self):
        if "test:obj" in str(self):
            raise OSError("Permission denied")
        return original_rmdir(self)

    with patch.object(Path, "rmdir", mock_rmdir):
        # Delete the object - should succeed but log a warning about parent cleanup
        backend.delete("test:obj", "1.0.0")

        # Verify object was deleted (main operation succeeded)
        object_path = backend.uri / "test:obj" / "1.0.0"
        assert not object_path.exists()


def test_init_with_file_uri(temp_dir):
    """Test LocalRegistryBackend initialization with file:// URI."""
    # Test that file:// prefix is stripped
    file_uri = f"file://{temp_dir}"
    backend = LocalRegistryBackend(uri=file_uri)
    assert backend.uri == temp_dir.resolve()
    assert str(backend.uri).startswith(str(temp_dir))


def test_save_registry_metadata(backend):
    """Test save_registry_metadata method."""
    metadata = {
        "version_objects": True,
        "materializers": {
            "test.Object": "TestMaterializer",
            "another.Object": "AnotherMaterializer",
        },
    }

    # Save registry metadata
    backend.save_registry_metadata(metadata)

    # Verify metadata file was created
    assert backend.metadata_path.exists()

    # Verify metadata content
    with open(backend.metadata_path, "r") as f:
        saved_metadata = json.load(f)
    assert saved_metadata == metadata


def test_save_registry_metadata_error(backend):
    """Test save_registry_metadata error handling."""
    # Make the metadata path directory read-only to cause an error
    backend.metadata_path.parent.chmod(0o444)

    try:
        metadata = {"version_objects": True}
        with pytest.raises(Exception):
            backend.save_registry_metadata(metadata)
    finally:
        # Restore permissions for cleanup
        backend.metadata_path.parent.chmod(0o755)


def test_fetch_registry_metadata_exists(backend):
    """Test fetch_registry_metadata when metadata file exists."""
    metadata = {
        "version_objects": True,
        "materializers": {"test.Object": "TestMaterializer"},
    }

    # Save metadata first
    backend.save_registry_metadata(metadata)

    # Fetch metadata
    fetched_metadata = backend.fetch_registry_metadata()

    # Verify metadata content
    assert fetched_metadata == metadata


def test_fetch_registry_metadata_not_exists(backend):
    """Test fetch_registry_metadata when metadata file doesn't exist."""
    # Ensure metadata file doesn't exist
    if backend.metadata_path.exists():
        backend.metadata_path.unlink()

    # Fetch metadata - should return empty dict
    fetched_metadata = backend.fetch_registry_metadata()
    assert fetched_metadata == {}


def test_fetch_registry_metadata_error(backend):
    """Test fetch_registry_metadata error handling."""
    # Create metadata file with invalid JSON
    backend.metadata_path.write_text("invalid json content")

    # Fetch metadata - should return empty dict on error
    fetched_metadata = backend.fetch_registry_metadata()
    assert fetched_metadata == {}


def test_push_on_conflict_skip_single(backend, sample_object_dir):
    """Test push with on_conflict='skip' for single item raises RegistryVersionConflict."""
    from mindtrace.registry.core.exceptions import RegistryVersionConflict

    # Push the object initially
    result = backend.push("test:object", "1.0.0", sample_object_dir, {"initial": True})
    assert result[("test:object", "1.0.0")].ok

    # Try to push again with on_conflict="skip" - single item raises
    with pytest.raises(RegistryVersionConflict):
        backend.push("test:object", "1.0.0", sample_object_dir, {"updated": True}, on_conflict="skip")


def test_push_on_conflict_skip_batch(backend, sample_object_dir, temp_dir):
    """Test push with on_conflict='skip' for batch items returns error result."""
    # Push the object initially
    result = backend.push("test:object", "1.0.0", sample_object_dir, {"initial": True})
    assert result[("test:object", "1.0.0")].ok

    # Create a second sample object dir
    sample_object_dir2 = temp_dir / "sample_object2"
    sample_object_dir2.mkdir()
    (sample_object_dir2 / "file1.txt").write_text("content1")

    # Batch push with skip - existing item should return error result (not raise)
    result = backend.push(
        ["test:object", "test:object2"],
        ["1.0.0", "1.0.0"],
        [str(sample_object_dir), str(sample_object_dir2)],
        [{"updated": True}, {"name": "test:object2"}],
        on_conflict="skip",
    )
    # First item (existing) should have error
    assert result[("test:object", "1.0.0")].is_error

    # Second item (new) should succeed
    assert result[("test:object2", "1.0.0")].ok


def test_push_on_conflict_overwrite(backend, sample_object_dir, temp_dir):
    """Test push with on_conflict='overwrite' when version already exists."""
    # Push the object initially
    result = backend.push("test:object", "1.0.0", sample_object_dir, {"initial": True})
    assert result[("test:object", "1.0.0")].ok

    # Create a new source directory with different content
    new_obj_dir = temp_dir / "new_sample"
    new_obj_dir.mkdir()
    (new_obj_dir / "new_file.txt").write_text("new content")

    # Push again with on_conflict="overwrite"
    result = backend.push("test:object", "1.0.0", str(new_obj_dir), {"updated": True}, on_conflict="overwrite")
    assert result[("test:object", "1.0.0")].is_overwritten

    # Verify new content exists
    object_path = backend.uri / "test:object" / "1.0.0"
    assert (object_path / "new_file.txt").exists()
    assert (object_path / "new_file.txt").read_text() == "new content"


def test_push_default_raises_when_version_exists(backend, sample_object_dir):
    """Test push default (on_conflict='skip') raises when version exists for single item."""
    from mindtrace.registry.core.exceptions import RegistryVersionConflict

    # Push the object initially with metadata (metadata file is the existence check)
    result = backend.push("test:object", "1.0.0", sample_object_dir, {"initial": True})
    assert result[("test:object", "1.0.0")].ok

    # Try to push again - single item with default on_conflict="skip" raises
    with pytest.raises(RegistryVersionConflict, match="already exists"):
        backend.push("test:object", "1.0.0", sample_object_dir, {"updated": True})


def test_push_auto_increment_version(backend, sample_object_dir):
    """Test push with version=None auto-increments version."""
    # Push first version with metadata (metadata is required for version tracking)
    result = backend.push("test:object", None, sample_object_dir, {"version": 1})
    assert ("test:object", "1") in result
    assert result[("test:object", "1")].ok

    # Push second version with metadata
    result = backend.push("test:object", None, sample_object_dir, {"version": 2})
    assert ("test:object", "2") in result
    assert result[("test:object", "2")].ok

    # Verify both versions exist
    versions = backend.list_versions("test:object")
    assert "1" in versions["test:object"]
    assert "2" in versions["test:object"]


def test_internal_lock_context_manager(backend):
    """Test internal lock context manager."""
    # Test successful lock acquisition
    with backend._internal_lock("test_key"):
        # Verify exclusive lock file exists
        lock_dir = backend._lock_dir("test_key")
        exclusive_path = backend._exclusive_lock_path("test_key")
        assert lock_dir.exists()
        assert exclusive_path.exists()

    # Verify lock is released (directory may still exist but exclusive file should be gone)
    assert not exclusive_path.exists()

    # Test lock contention - trying to acquire same lock should fail
    with backend._internal_lock("test_key2"):
        # Manually try to acquire same exclusive lock
        result = backend._acquire_internal_lock("test_key2", "different_id", 30, shared=False)
        assert result is False


def test_internal_lock_release_on_exception(backend):
    """Test that internal lock is released even if an exception occurs."""
    lock_key = "test_exception_key"

    with pytest.raises(RuntimeError):
        with backend._internal_lock(lock_key):
            raise RuntimeError("Test exception")

    # Verify lock is released
    exclusive_path = backend._exclusive_lock_path(lock_key)
    assert not exclusive_path.exists()


def test_internal_lock_acquire_release(backend):
    """Test direct acquire and release of internal locks."""
    import uuid

    lock_key = "test_direct_lock"
    lock_id = str(uuid.uuid4())

    # Acquire exclusive lock
    result = backend._acquire_internal_lock(lock_key, lock_id, timeout=30, shared=False)
    assert result is True

    # Verify exclusive lock file exists and contains correct data
    exclusive_path = backend._exclusive_lock_path(lock_key)
    assert exclusive_path.exists()

    import json

    with open(exclusive_path, "r") as f:
        lock_data = json.load(f)
    assert lock_data["lock_id"] == lock_id
    assert "expires_at" in lock_data

    # Release lock with correct ID
    result = backend._release_internal_lock(lock_key, lock_id)
    assert result is True
    assert not exclusive_path.exists()


def test_internal_lock_release_wrong_id(backend):
    """Test that releasing a lock with wrong ID doesn't release the actual lock."""
    import uuid

    lock_key = "test_wrong_id_lock"
    lock_id = str(uuid.uuid4())
    wrong_id = str(uuid.uuid4())

    # Acquire exclusive lock
    result = backend._acquire_internal_lock(lock_key, lock_id, timeout=30, shared=False)
    assert result is True

    # Try to release with wrong ID - returns True (no error) but lock should still exist
    result = backend._release_internal_lock(lock_key, wrong_id)
    # Note: returns True because it tries shared lock path which doesn't exist
    # The important check is that the exclusive lock still exists

    # Exclusive lock file should still exist (wrong ID didn't release it)
    exclusive_path = backend._exclusive_lock_path(lock_key)
    assert exclusive_path.exists()

    # Clean up - release with correct ID
    backend._release_internal_lock(lock_key, lock_id)


def test_internal_lock_expired_lock_takeover(backend):
    """Test that expired locks can be taken over."""
    import json
    import time
    import uuid

    lock_key = "test_expired_lock"
    old_lock_id = str(uuid.uuid4())
    new_lock_id = str(uuid.uuid4())

    # Create an expired exclusive lock file manually
    lock_dir = backend._lock_dir(lock_key)
    lock_dir.mkdir(parents=True, exist_ok=True)
    exclusive_path = backend._exclusive_lock_path(lock_key)
    with open(exclusive_path, "w") as f:
        json.dump(
            {
                "lock_id": old_lock_id,
                "expires_at": time.time() - 10,  # Expired 10 seconds ago
            },
            f,
        )

    # New lock acquisition should succeed (taking over expired lock)
    result = backend._acquire_internal_lock(lock_key, new_lock_id, timeout=30, shared=False)
    assert result is True

    # Verify new lock data
    with open(exclusive_path, "r") as f:
        lock_data = json.load(f)
    assert lock_data["lock_id"] == new_lock_id

    # Clean up
    backend._release_internal_lock(lock_key, new_lock_id)


def test_internal_lock_active_lock_blocks(backend):
    """Test that active (non-expired) locks block new acquisitions."""
    import json
    import time
    import uuid

    lock_key = "test_active_lock"
    existing_lock_id = str(uuid.uuid4())
    new_lock_id = str(uuid.uuid4())

    # Create an active exclusive lock file manually
    lock_dir = backend._lock_dir(lock_key)
    lock_dir.mkdir(parents=True, exist_ok=True)
    exclusive_path = backend._exclusive_lock_path(lock_key)
    with open(exclusive_path, "w") as f:
        json.dump(
            {
                "lock_id": existing_lock_id,
                "expires_at": time.time() + 60,  # Expires in 60 seconds
            },
            f,
        )

    # New exclusive lock acquisition should fail
    result = backend._acquire_internal_lock(lock_key, new_lock_id, timeout=30, shared=False)
    assert result is False

    # Clean up
    exclusive_path.unlink()


def test_internal_lock_empty_lock_file(backend):
    """Test that empty lock files are handled gracefully."""
    import uuid

    lock_key = "test_empty_lock"
    lock_id = str(uuid.uuid4())

    # Create an empty exclusive lock file
    lock_dir = backend._lock_dir(lock_key)
    lock_dir.mkdir(parents=True, exist_ok=True)
    exclusive_path = backend._exclusive_lock_path(lock_key)
    exclusive_path.touch()

    # Lock acquisition should succeed (empty file is treated as invalid/corrupted)
    result = backend._acquire_internal_lock(lock_key, lock_id, timeout=30, shared=False)
    assert result is True

    # Clean up
    backend._release_internal_lock(lock_key, lock_id)


def test_internal_lock_corrupted_lock_file(backend):
    """Test that corrupted lock files are handled gracefully."""
    import uuid

    lock_key = "test_corrupted_lock"
    lock_id = str(uuid.uuid4())

    # Create an exclusive lock file with invalid JSON
    lock_dir = backend._lock_dir(lock_key)
    lock_dir.mkdir(parents=True, exist_ok=True)
    exclusive_path = backend._exclusive_lock_path(lock_key)
    with open(exclusive_path, "w") as f:
        f.write("invalid json content")

    # Lock acquisition should succeed (corrupted file is cleaned up and new lock acquired)
    result = backend._acquire_internal_lock(lock_key, lock_id, timeout=30, shared=False)
    assert result is True

    # Clean up
    backend._release_internal_lock(lock_key, lock_id)


def test_internal_lock_release_nonexistent(backend):
    """Test that releasing a non-existent lock returns True."""
    import uuid

    lock_key = "test_nonexistent_lock"
    lock_id = str(uuid.uuid4())

    # Lock directory/file doesn't exist
    lock_dir = backend._lock_dir(lock_key)
    assert not lock_dir.exists()

    # Release should return True (nothing to release)
    result = backend._release_internal_lock(lock_key, lock_id)
    assert result is True


def test_internal_lock_raises_on_acquisition_failure(backend):
    """Test that _internal_lock context manager raises LockAcquisitionError on failure."""
    import json
    import time
    import uuid

    from mindtrace.registry.core.exceptions import LockAcquisitionError

    lock_key = "test_lock_failure"
    existing_lock_id = str(uuid.uuid4())

    # Create an active exclusive lock file manually
    lock_dir = backend._lock_dir(lock_key)
    lock_dir.mkdir(parents=True, exist_ok=True)
    exclusive_path = backend._exclusive_lock_path(lock_key)
    with open(exclusive_path, "w") as f:
        json.dump({"lock_id": existing_lock_id, "expires_at": time.time() + 60}, f)

    # Context manager should raise LockAcquisitionError
    with pytest.raises(LockAcquisitionError, match="Cannot acquire exclusive lock"):
        with backend._internal_lock(lock_key):
            pass  # Should never reach here

    # Clean up
    exclusive_path.unlink()


def test_push_blocked_by_active_lock(backend, sample_object_dir):
    """Test that push is blocked when another operation holds the lock."""
    import json
    import time
    import uuid

    from mindtrace.registry.core.exceptions import LockAcquisitionError

    # Simulate an active exclusive lock on the object@version (push uses "{name}@{version}" lock key)
    lock_key = "test:object@1.0.0"
    lock_id = str(uuid.uuid4())
    lock_dir = backend._lock_dir(lock_key)
    lock_dir.mkdir(parents=True, exist_ok=True)
    exclusive_path = backend._exclusive_lock_path(lock_key)
    with open(exclusive_path, "w") as f:
        json.dump({"lock_id": lock_id, "expires_at": time.time() + 60}, f)

    # Push should fail because lock is held
    with pytest.raises(LockAcquisitionError, match="Cannot acquire exclusive lock"):
        backend.push("test:object", "1.0.0", sample_object_dir, {"test": True})

    # Clean up
    exclusive_path.unlink()


def test_delete_blocked_by_active_lock(backend, sample_object_dir):
    """Test that delete is blocked when another operation holds the lock."""
    import json
    import time
    import uuid

    from mindtrace.registry.core.exceptions import LockAcquisitionError

    # First, push an object so we have something to delete
    backend.push("test:object", "1.0.0", sample_object_dir, {"test": True})

    # Simulate an active exclusive lock on the object@version (as if another delete is in progress)
    lock_key = "test:object@1.0.0"
    lock_id = str(uuid.uuid4())
    lock_dir = backend._lock_dir(lock_key)
    lock_dir.mkdir(parents=True, exist_ok=True)
    exclusive_path = backend._exclusive_lock_path(lock_key)
    with open(exclusive_path, "w") as f:
        json.dump({"lock_id": lock_id, "expires_at": time.time() + 60}, f)

    # Delete should fail because lock is held
    with pytest.raises(LockAcquisitionError, match="Cannot acquire exclusive lock"):
        backend.delete("test:object", "1.0.0")

    # Verify object still exists (delete was blocked)
    result = backend.has_object("test:object", "1.0.0")
    assert result[("test:object", "1.0.0")] is True

    # Clean up
    exclusive_path.unlink()


def test_concurrent_push_same_object_different_versions(backend, sample_object_dir):
    """Test that push operations on same object but different versions use different locks."""
    import json
    import time
    import uuid

    # Simulate an active exclusive lock on test:object@1.0.0
    lock_key_v1 = "test:object@1.0.0"
    lock_id = str(uuid.uuid4())
    lock_dir = backend._lock_dir(lock_key_v1)
    lock_dir.mkdir(parents=True, exist_ok=True)
    exclusive_path = backend._exclusive_lock_path(lock_key_v1)
    with open(exclusive_path, "w") as f:
        json.dump({"lock_id": lock_id, "expires_at": time.time() + 60}, f)

    # Push to a different object should succeed (different lock key)
    result = backend.push("other:object", "1.0.0", sample_object_dir, {"test": True})
    assert result[("other:object", "1.0.0")].ok

    # Clean up
    exclusive_path.unlink()


def test_push_releases_lock_on_failure(backend, sample_object_dir):
    """Test that push releases the lock even if the operation fails."""
    # Try to push with an invalid path that will cause failure
    invalid_path = "/nonexistent/path/that/does/not/exist"

    with pytest.raises(Exception):  # Will fail during copytree
        backend.push("test:object", "1.0.0", invalid_path, {"test": True})

    # Verify lock is released (exclusive lock file should not exist)
    lock_key = "test:object@1.0.0"
    exclusive_path = backend._exclusive_lock_path(lock_key)
    assert not exclusive_path.exists()


def test_delete_releases_lock_on_success(backend, sample_object_dir):
    """Test that delete releases the lock after successful operation."""
    # Push an object first
    backend.push("test:object", "1.0.0", sample_object_dir, {"test": True})

    # Delete it
    backend.delete("test:object", "1.0.0")

    # Verify lock is released (exclusive lock file should not exist)
    lock_key = "test:object@1.0.0"
    exclusive_path = backend._exclusive_lock_path(lock_key)
    assert not exclusive_path.exists()

    # Should be able to push again (lock was released)
    result = backend.push("test:object", "1.0.0", sample_object_dir, {"test": True})
    assert result[("test:object", "1.0.0")].ok


def test_pull_object_not_found(backend):
    """Test pull raises RegistryObjectNotFound for missing objects."""
    from mindtrace.registry.core.exceptions import RegistryObjectNotFound

    with pytest.raises(RegistryObjectNotFound, match="not found"):
        backend.pull("nonexistent:object", "1.0.0", "/tmp/dest")


def test_batch_operations(backend, sample_metadata):
    """Test batch operations with multiple objects."""
    # Test batch save_metadata
    backend.save_metadata(
        ["obj:1", "obj:2", "obj:3"],
        ["1.0", "1.0", "1.0"],
        [sample_metadata, sample_metadata, sample_metadata],
    )

    # Test batch list_versions
    versions = backend.list_versions(["obj:1", "obj:2", "obj:3"])
    assert "obj:1" in versions
    assert "obj:2" in versions
    assert "obj:3" in versions

    # Test batch has_object
    exists = backend.has_object(
        ["obj:1", "obj:2", "nonexistent:obj"],
        ["1.0", "1.0", "1.0"],
    )
    assert exists[("obj:1", "1.0")] is True
    assert exists[("obj:2", "1.0")] is True
    assert exists[("nonexistent:obj", "1.0")] is False

    # Test batch fetch_metadata
    metadata = backend.fetch_metadata(
        ["obj:1", "obj:2"],
        ["1.0", "1.0"],
    )
    assert ("obj:1", "1.0") in metadata
    assert ("obj:2", "1.0") in metadata


def test_fetch_metadata_missing_entry(backend, sample_metadata):
    """Test fetch_metadata returns partial results when some entries are missing."""
    # Save only one object
    backend.save_metadata("exists:obj", "1.0", sample_metadata)

    # Try to fetch both existing and non-existing
    result = backend.fetch_metadata(
        ["exists:obj", "missing:obj"],
        ["1.0", "1.0"],
    )

    # Only existing entry should be in result
    assert ("exists:obj", "1.0") in result
    assert ("missing:obj", "1.0") not in result
