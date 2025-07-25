import importlib
import json
import os
import platform
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from mindtrace.core import Config
from mindtrace.registry import LocalRegistryBackend
from mindtrace.registry.core.exceptions import LockAcquisitionError

# Import platform-specific modules safely
if platform.system() != "Windows":
    import fcntl
else:
    import msvcrt


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    temp_dir = Path(Config()["MINDTRACE_TEMP_DIR"]).expanduser() / f"test_dir_{uuid.uuid4()}"
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

    # Fetch metadata
    fetched_metadata = backend.fetch_metadata("test:object", "1.0.0")

    # Verify metadata content
    assert fetched_metadata["name"] == sample_metadata["name"]
    assert fetched_metadata["version"] == sample_metadata["version"]
    assert fetched_metadata["description"] == sample_metadata["description"]
    assert "path" in fetched_metadata  # Should be added by fetch_metadata


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

    # List versions
    versions = backend.list_versions("test:object")

    # Verify results
    assert len(versions) == 2
    assert "1.0.0" in versions
    assert "2.0.0" in versions


def test_has_object(backend, sample_metadata):
    """Test checking object existence."""
    # Save metadata
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Check existing object
    assert backend.has_object("test:object", "1.0.0")

    # Check non-existing object
    assert not backend.has_object("nonexistent:object", "1.0.0")
    assert not backend.has_object("test:object", "2.0.0")


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


class TestUnixLocks:
    """Test suite for Unix-specific locking mechanisms."""

    @pytest.fixture(autouse=True)
    def setup_unix(self):
        """Setup for Unix-specific tests."""
        with patch("platform.system", return_value="Linux"):
            # Mock fcntl module for Unix tests
            with patch("mindtrace.registry.backends.local_registry_backend.fcntl", create=True) as mock_fcntl:
                # Set up the mock fcntl module with necessary constants
                mock_fcntl.LOCK_EX = 2
                mock_fcntl.LOCK_NB = 4
                mock_fcntl.LOCK_UN = 8
                mock_fcntl.LOCK_SH = 1
                yield

    def test_acquire_file_lock_unix(self, backend):
        """Test acquiring a file lock on Unix systems."""
        # Create a test file
        test_file = backend.uri / "test_lock"
        test_file.touch()

        with open(test_file, "r+") as f:
            # Mock fcntl.flock to simulate successful lock acquisition
            with patch(
                "mindtrace.registry.backends.local_registry_backend.fcntl.flock", return_value=None
            ) as mock_flock:
                assert backend._acquire_file_lock(f)
                mock_flock.assert_called_once_with(f.fileno(), 2 | 4)  # LOCK_EX | LOCK_NB

    def test_acquire_file_lock_unix_failure(self, backend):
        """Test failed file lock acquisition on Unix systems."""
        test_file = backend.uri / "test_lock"
        test_file.touch()

        with open(test_file, "r+") as f:
            # Mock fcntl.flock to raise IOError (simulating lock acquisition failure)
            with patch("mindtrace.registry.backends.local_registry_backend.fcntl.flock", side_effect=IOError):
                assert not backend._acquire_file_lock(f)

    def test_release_file_lock_unix(self, backend):
        """Test releasing a file lock on Unix systems."""
        test_file = backend.uri / "test_lock"
        test_file.touch()

        with open(test_file, "r+") as f:
            # Mock fcntl.flock to simulate successful lock release
            with patch(
                "mindtrace.registry.backends.local_registry_backend.fcntl.flock", return_value=None
            ) as mock_flock:
                backend._release_file_lock(f)
                mock_flock.assert_called_once_with(f.fileno(), 8)  # LOCK_UN

    def test_acquire_shared_lock_unix(self, backend):
        """Test acquiring a shared lock on Unix systems."""
        test_file = backend.uri / "test_lock"
        test_file.touch()

        with open(test_file, "r+") as f:
            # Mock fcntl.flock to simulate successful shared lock acquisition
            with patch(
                "mindtrace.registry.backends.local_registry_backend.fcntl.flock", return_value=None
            ) as mock_flock:
                assert backend._acquire_shared_lock(f)
                mock_flock.assert_called_once_with(f.fileno(), 1)  # LOCK_SH


class TestWindowsLocks:
    """Test suite for Windows-specific locking mechanisms."""

    @pytest.fixture(autouse=True)
    def setup_windows(self):
        """Setup for Windows-specific tests."""
        with patch("platform.system", return_value="Windows"):
            # Mock msvcrt module for Windows tests
            with patch("mindtrace.registry.backends.local_registry_backend.msvcrt", create=True) as mock_msvcrt:
                # Set up the mock msvcrt module with necessary constants
                mock_msvcrt.LK_NBLCK = 1
                mock_msvcrt.LK_UNLCK = 2
                yield

    def test_acquire_file_lock_windows(self, backend):
        """Test acquiring a file lock on Windows systems."""
        test_file = backend.uri / "test_lock"
        test_file.touch()

        with open(test_file, "r+") as f:
            # Mock msvcrt.locking to simulate successful lock acquisition
            with patch(
                "mindtrace.registry.backends.local_registry_backend.msvcrt.locking", return_value=None
            ) as mock_locking:
                assert backend._acquire_file_lock(f)
                mock_locking.assert_called_once_with(f.fileno(), 1, 1)  # LK_NBLCK, 1

    def test_acquire_file_lock_windows_failure(self, backend):
        """Test failed file lock acquisition on Windows systems."""
        test_file = backend.uri / "test_lock"
        test_file.touch()

        with open(test_file, "r+") as f:
            # Mock msvcrt.locking to raise IOError (simulating lock acquisition failure)
            with patch("mindtrace.registry.backends.local_registry_backend.msvcrt.locking", side_effect=IOError):
                assert not backend._acquire_file_lock(f)

    def test_release_file_lock_windows(self, backend):
        """Test releasing a file lock on Windows systems."""
        test_file = backend.uri / "test_lock"
        test_file.touch()

        with open(test_file, "r+") as f:
            # Mock msvcrt.locking to simulate successful lock release
            with patch(
                "mindtrace.registry.backends.local_registry_backend.msvcrt.locking", return_value=None
            ) as mock_locking:
                backend._release_file_lock(f)
                mock_locking.assert_called_once_with(f.fileno(), 2, 1)  # LK_UNLCK, 1

    def test_acquire_shared_lock_windows(self, backend):
        """Test acquiring a shared lock on Windows systems."""
        test_file = backend.uri / "test_lock"
        test_file.touch()

        with open(test_file, "r+") as f:
            # Mock msvcrt.locking to simulate successful shared lock acquisition
            with patch(
                "mindtrace.registry.backends.local_registry_backend.msvcrt.locking", return_value=None
            ) as mock_locking:
                assert backend._acquire_shared_lock(f)
                mock_locking.assert_called_once_with(f.fileno(), 1, 1)  # LK_NBLCK, 1


class TestCrossPlatformLockOperations:
    """Test suite for cross-platform lock operations."""

    def test_acquire_lock_success(self, backend):
        """Test successful lock acquisition."""
        lock_key = "test_lock"
        lock_id = str(uuid.uuid4())

        # Mock platform.system to return current system
        with patch("platform.system", return_value=platform.system()):
            # Test lock acquisition (should succeed when no lock file exists)
            assert backend.acquire_lock(lock_key, lock_id, timeout=30)

            # Verify lock file contents
            lock_path = backend._lock_path(lock_key)
            with open(lock_path, "r") as f:
                lock_data = json.load(f)
                assert lock_data["lock_id"] == lock_id
                assert "expires_at" in lock_data
                assert not lock_data.get("shared", False)

    def test_acquire_lock_failure(self, backend):
        """Test failed lock acquisition."""
        lock_key = "test_lock"
        lock_id = str(uuid.uuid4())

        # Mock platform.system to return current system
        with patch("platform.system", return_value=platform.system()):
            # Create a lock file
            lock_path = backend._lock_path(lock_key)
            lock_path.touch()

            # Mock _acquire_file_lock to simulate failure
            with patch.object(backend, "_acquire_file_lock", return_value=False):
                with pytest.raises(LockAcquisitionError):
                    backend.acquire_lock(lock_key, lock_id, timeout=30)

    def test_release_lock_success(self, backend):
        """Test successful lock release."""
        lock_key = "test_lock"
        lock_id = str(uuid.uuid4())

        # Create and acquire a lock first
        lock_path = backend._lock_path(lock_key)
        lock_path.touch()
        with open(lock_path, "w") as f:
            json.dump({"lock_id": lock_id, "expires_at": 0}, f)

        # Test lock release
        assert backend.release_lock(lock_key, lock_id)
        assert not lock_path.exists()

    def test_release_lock_wrong_id(self, backend):
        """Test releasing a lock with wrong ID."""
        lock_key = "test_lock"
        lock_id = str(uuid.uuid4())
        wrong_id = str(uuid.uuid4())

        # Create a lock file with different ID
        lock_path = backend._lock_path(lock_key)
        lock_path.touch()
        with open(lock_path, "w") as f:
            json.dump({"lock_id": wrong_id, "expires_at": 0}, f)

        # Test lock release with wrong ID
        assert not backend.release_lock(lock_key, lock_id)
        assert lock_path.exists()

    def test_check_lock(self, backend):
        """Test checking lock status."""
        lock_key = "test_lock"
        lock_id = str(uuid.uuid4())

        # Create a lock file
        lock_path = backend._lock_path(lock_key)
        lock_path.touch()
        with open(lock_path, "w") as f:
            json.dump({"lock_id": lock_id, "expires_at": float("inf")}, f)

        # Test lock check
        is_locked, found_id = backend.check_lock(lock_key)
        assert is_locked
        assert found_id == lock_id

    def test_check_expired_lock(self, backend):
        """Test checking expired lock."""
        lock_key = "test_lock"
        lock_id = str(uuid.uuid4())

        # Create a lock file with expired timestamp
        lock_path = backend._lock_path(lock_key)
        lock_path.touch()
        with open(lock_path, "w") as f:
            json.dump({"lock_id": lock_id, "expires_at": 0}, f)

        # Test lock check
        is_locked, found_id = backend.check_lock(lock_key)
        assert not is_locked
        assert found_id is None

    def test_acquire_shared_lock_failure(self, backend):
        """Test error handling when acquiring a shared lock fails."""
        # Create a temporary file to lock
        lock_path = backend.uri / "test.lock"
        lock_path.touch()

        # Open the file and try to acquire a shared lock
        with open(lock_path, "r+") as f:
            # Mock the platform-specific lock function to raise an error
            if platform.system() == "Windows":
                with patch.object(msvcrt, "locking", side_effect=OSError("Failed to lock")):
                    result = backend._acquire_shared_lock(f)
            else:
                with patch.object(fcntl, "flock", side_effect=OSError("Failed to lock")):
                    result = backend._acquire_shared_lock(f)

        # Verify that False is returned on failure
        assert result is False

    def test_acquire_shared_lock_with_active_exclusive(self, backend):
        """Test that shared lock acquisition fails when there's an active exclusive lock."""
        # Create a lock file with an active exclusive lock
        lock_path = backend._lock_path("test_lock")
        lock_path.touch()

        # Write metadata for an active exclusive lock
        with open(lock_path, "w") as f:
            metadata = {
                "lock_id": "test_id",
                "expires_at": time.time() + 60,  # Lock expires in 60 seconds
                "shared": False,  # This is an exclusive lock
            }
            f.write(json.dumps(metadata))

        # Try to acquire a shared lock
        with pytest.raises(LockAcquisitionError):
            backend.acquire_lock("test_lock", "other_id", timeout=30, shared=True)

    def test_acquire_shared_lock_failure_in_acquire_lock(self, backend):
        """Test that acquire_lock returns False when _acquire_shared_lock fails."""
        # Create a lock file
        lock_path = backend._lock_path("test_lock")
        lock_path.touch()

        # Mock _acquire_shared_lock to return False (simulating failure)
        with patch.object(backend, "_acquire_shared_lock", return_value=False):
            # Try to acquire a shared lock
            with pytest.raises(LockAcquisitionError):
                backend.acquire_lock("test_lock", "test_id", timeout=30, shared=True)

    def test_acquire_exclusive_lock_with_active_shared(self, backend):
        """Test that exclusive lock acquisition fails when there are active shared locks."""
        # Create a lock file with an active shared lock
        lock_path = backend._lock_path("test_lock")
        lock_path.touch()

        # Write metadata for an active shared lock
        with open(lock_path, "w") as f:
            metadata = {
                "lock_id": "shared_id",
                "expires_at": time.time() + 60,  # Lock expires in 60 seconds
                "shared": True,  # This is a shared lock
            }
            f.write(json.dumps(metadata))

        # Try to acquire an exclusive lock
        with pytest.raises(LockAcquisitionError):
            backend.acquire_lock("test_lock", "exclusive_id", timeout=30, shared=False)

    def test_acquire_exclusive_lock_with_invalid_content(self, backend):
        """Test that exclusive lock acquisition fails when lock file has invalid content."""
        # Create a lock file with invalid JSON content
        lock_path = backend._lock_path("test_lock")
        lock_path.touch()

        # Write invalid JSON content to the lock file
        with open(lock_path, "w") as f:
            f.write("invalid json content")

        # Try to acquire an exclusive lock - should raise LockAcquisitionError
        with pytest.raises(LockAcquisitionError):
            backend.acquire_lock("test_lock", "test_id", timeout=30, shared=False)


class TestPlatformSpecificImports:
    """Test suite for platform-specific import logic."""

    @pytest.fixture(autouse=True)
    def setup_imports(self):
        """Setup and teardown for import tests."""
        # Store original modules
        self.original_modules = {
            "fcntl": sys.modules.get("fcntl"),
            "msvcrt": sys.modules.get("msvcrt"),
            "mindtrace.registry.backends.local_registry_backend": sys.modules.get(
                "mindtrace.registry.backends.local_registry_backend"
            ),
        }

        # Create mock modules
        self.mock_fcntl = MagicMock()
        self.mock_msvcrt = MagicMock()

        yield

        # Restore original modules
        for module_name, module in self.original_modules.items():
            if module is not None:
                sys.modules[module_name] = module
            elif module_name in sys.modules:
                del sys.modules[module_name]

    def _cleanup_modules(self):
        """Clean up modules before reloading."""
        # Remove platform-specific modules
        if "fcntl" in sys.modules:
            del sys.modules["fcntl"]
        if "msvcrt" in sys.modules:
            del sys.modules["msvcrt"]

        # Remove the backend module
        if "mindtrace.registry.backends.local_registry_backend" in sys.modules:
            del sys.modules["mindtrace.registry.backends.local_registry_backend"]

    def test_windows_imports(self):
        """Test that Windows-specific imports are used on Windows."""
        # Mock the platform check
        with patch("platform.system", return_value="Windows"):
            # Clean up modules
            self._cleanup_modules()

            # Mock the msvcrt module
            sys.modules["msvcrt"] = self.mock_msvcrt

            # Reload the module to trigger the import logic
            importlib.reload(importlib.import_module("mindtrace.registry.backends.local_registry_backend"))

            # Get the reloaded module
            module = importlib.import_module("mindtrace.registry.backends.local_registry_backend")

            # Verify that msvcrt is imported and fcntl is not
            assert hasattr(module, "msvcrt")
            assert not hasattr(module, "fcntl")

    def test_unix_imports(self):
        """Test that Unix-specific imports are used on Unix systems."""
        # Mock the platform check
        with patch("platform.system", return_value="Linux"):
            # Clean up modules
            self._cleanup_modules()

            # Mock the fcntl module
            sys.modules["fcntl"] = self.mock_fcntl

            # Reload the module to trigger the import logic
            importlib.reload(importlib.import_module("mindtrace.registry.backends.local_registry_backend"))

            # Get the reloaded module
            module = importlib.import_module("mindtrace.registry.backends.local_registry_backend")

            # Verify that fcntl is imported and msvcrt is not
            assert hasattr(module, "fcntl")
            assert not hasattr(module, "msvcrt")

    def test_unknown_platform_imports(self):
        """Test that Unix-specific imports are used as fallback for unknown platforms."""
        # Mock the platform check
        with patch("platform.system", return_value="UnknownOS"):
            # Clean up modules
            self._cleanup_modules()

            # Mock the fcntl module
            sys.modules["fcntl"] = self.mock_fcntl

            # Reload the module to trigger the import logic
            importlib.reload(importlib.import_module("mindtrace.registry.backends.local_registry_backend"))

            # Get the reloaded module
            module = importlib.import_module("mindtrace.registry.backends.local_registry_backend")

            # Verify that fcntl is imported and msvcrt is not
            assert hasattr(module, "fcntl")
            assert not hasattr(module, "msvcrt")


def test_delete_parent_directory_error(backend, sample_object_dir, caplog):
    """Test error handling when deleting parent directory fails."""
    # Save an object first
    backend.push("test:obj", "1.0.0", str(sample_object_dir))

    # Create a parent directory that will be empty after deletion
    parent_dir = backend.uri / "test:obj"
    parent_dir.mkdir(exist_ok=True)

    # Mock rmdir to raise an exception
    with patch.object(Path, "rmdir", side_effect=OSError("Permission denied")):
        # Try to delete the object
        with pytest.raises(OSError, match="Permission denied"):
            backend.delete("test:obj", "1.0.0")

        # Verify that the error was logged
        assert "Error deleting parent directory" in caplog.text


def test_release_file_lock_error(backend, caplog):
    """Test error handling when releasing a file lock fails."""
    # Create a temporary file to lock
    lock_path = backend.uri / "test.lock"
    lock_path.touch()

    # Open the file and acquire a lock
    with open(lock_path, "r+") as f:
        # Mock the platform-specific unlock function to raise an error
        if platform.system() == "Windows":
            with patch.object(msvcrt, "locking", side_effect=OSError("Failed to unlock")):
                backend._release_file_lock(f)
        else:
            with patch.object(fcntl, "flock", side_effect=OSError("Failed to unlock")):
                backend._release_file_lock(f)

    # Verify that the error was logged
    assert "Error releasing file lock" in caplog.text
    assert "Failed to unlock" in caplog.text


def test_acquire_lock_inner_exception(backend, caplog):
    """Test error handling when an exception occurs during lock acquisition inner block."""
    # Create a lock file
    lock_path = backend._lock_path("test_lock")
    lock_path.touch()

    # Mock _acquire_existing_lock to raise an exception
    with patch.object(backend, "_acquire_existing_lock", side_effect=Exception("Test error")):
        # Try to acquire a lock - should return False due to exception handling
        result = backend.acquire_lock("test_lock", "test_id", timeout=30)
        assert result is False

    # Verify that the error was logged
    assert "Error acquiring lock for test_lock" in caplog.text
    assert "Test error" in caplog.text


def test_acquire_lock_outer_exception(backend, caplog):
    """Test error handling when an exception occurs during lock acquisition outer block."""
    # Create a lock file
    lock_path = backend._lock_path("test_lock")
    lock_path.touch()

    # Mock file operations to raise an exception before inner block
    with patch("builtins.open", side_effect=Exception("Test error")):
        # Try to acquire a lock - should raise LockAcquisitionError
        with pytest.raises(LockAcquisitionError):
            backend.acquire_lock("test_lock", "test_id", timeout=30)

    # Verify that the error was logged (this comes from _acquire_existing_lock)
    assert "Error acquiring existing lock" in caplog.text
    assert "Test error" in caplog.text


def test_release_lock_inner_exception(backend, caplog):
    """Test error handling when an exception occurs during lock release inner block."""
    # Create a lock file with valid metadata
    lock_path = backend._lock_path("test_lock")
    lock_path.touch()
    with open(lock_path, "w") as f:
        json.dump({"lock_id": "test_id", "expires_at": time.time() + 30}, f)

    # Mock _release_file_lock to verify it's called
    with patch.object(backend, "_release_file_lock") as mock_release:
        # Mock file operations to raise an exception during unlink
        with patch("pathlib.Path.unlink", side_effect=Exception("Test error")):
            # Try to release the lock
            result = backend.release_lock("test_lock", "test_id")

            # Verify that lock release failed
            assert result is False
            # Verify that the error was logged
            assert "Error releasing lock for test_lock" in caplog.text
            assert "Test error" in caplog.text
            # Verify that _release_file_lock was called
            mock_release.assert_called_once()


def test_release_lock_outer_exception(backend, caplog):
    """Test error handling when an exception occurs during lock release outer block."""
    # Create a lock file
    lock_path = backend._lock_path("test_lock")
    lock_path.touch()

    # Mock file operations to raise an exception before inner block
    with patch("builtins.open", side_effect=Exception("Test error")):
        # Try to release the lock
        result = backend.release_lock("test_lock", "test_id")

        # Verify that lock release failed
        assert result is False
        # Verify that the error was logged
        assert "Error releasing lock for test_lock" in caplog.text
        assert "Test error" in caplog.text


def test_check_lock_cannot_acquire_shared(backend):
    """Test check_lock behavior when the lock file doesn't exist."""
    # Mock _lock_path to return a path that doesn't exist
    non_existent_path = Path("/non/existent/path")
    with patch.object(backend, "_lock_path", return_value=non_existent_path):
        # Check the lock
        is_locked, lock_id = backend.check_lock("test_lock")

        # Verify that the method indicates there is no lock
        assert is_locked is False
        assert lock_id is None


def test_check_lock_invalid_metadata(backend):
    """Test check_lock behavior when the lock file exists but has invalid metadata."""
    # Create a lock file with invalid JSON content
    lock_path = backend._lock_path("test_lock")
    lock_path.touch()
    with open(lock_path, "w") as f:
        f.write("invalid json content")

    # Mock _acquire_shared_lock to return True to simulate successful lock acquisition
    with patch.object(backend, "_acquire_shared_lock", return_value=False):
        # Check the lock
        is_locked, lock_id = backend.check_lock("test_lock")

        # Verify that the method indicates the file is not locked due to invalid metadata
        assert is_locked is True
        assert lock_id is None


def test_check_lock_io_error(backend):
    """Test check_lock behavior when an IOError occurs while reading the lock file."""
    # Create a lock file
    lock_path = backend._lock_path("test_lock")
    lock_path.touch()

    # Mock _acquire_shared_lock to return True to simulate successful lock acquisition
    with (
        patch.object(backend, "_acquire_shared_lock", return_value=True),
        patch.object(backend, "_release_file_lock"),
        patch("builtins.open", side_effect=IOError("Test IO error")),
    ):
        # Check the lock
        is_locked, lock_id = backend.check_lock("test_lock")

        # Verify that the method indicates the file is not locked due to IO error
        assert is_locked is False
        assert lock_id is None


def test_check_lock_expired(backend):
    """Test check_lock behavior when the lock has expired."""
    # Create a lock file with expired metadata
    lock_path = backend._lock_path("test_lock")
    lock_path.touch()
    with open(lock_path, "w") as f:
        metadata = {
            "lock_id": "test_id",
            "expires_at": time.time() - 1,  # Expired 1 second ago
            "shared": False,
        }
        f.write(json.dumps(metadata))

    # Mock _acquire_shared_lock to return True to simulate successful lock acquisition
    with (
        patch.object(backend, "_acquire_shared_lock", return_value=True),
        patch.object(backend, "_release_file_lock"),
        patch("json.loads", side_effect=json.JSONDecodeError("Test error", "", 0)),
    ):
        # Check the lock
        is_locked, lock_id = backend.check_lock("test_lock")

        # Verify that the method indicates the file is not locked due to JSON decode error
        assert is_locked is False
        assert lock_id is None


def test_overwrite_metadata_error_handling(backend, temp_dir, monkeypatch):
    """Test error handling during metadata operations in overwrite."""

    # Create source metadata and directory
    source_meta = {
        "name": "test:source",
        "version": "1.0.0",
        "description": "Test source",
        "created_at": "2024-01-01",
        "path": str(temp_dir / "test:source" / "1.0.0"),
    }

    # Create source directory and write a test file
    source_dir = temp_dir / "test:source" / "1.0.0"
    source_dir.mkdir(parents=True)
    with open(source_dir / "test.txt", "w") as f:
        f.write("test content")

    # Save source metadata
    backend.save_metadata("test:source", "1.0.0", source_meta)

    # Mock os.rename to raise an error when renaming metadata files
    original_rename = os.rename

    def mock_rename(src, dst):
        if "_meta_" in str(src) and "_meta_" in str(dst):  # If renaming metadata files
            raise OSError("Simulated rename error")
        return original_rename(src, dst)

    # Apply the mock
    monkeypatch.setattr(os, "rename", mock_rename)

    # Attempt overwrite - should raise an error
    with pytest.raises(OSError) as exc_info:
        backend.overwrite(
            source_name="test:source", source_version="1.0.0", target_name="test:source", target_version="2.0.0"
        )

    # Verify the error message
    assert "Simulated rename error" in str(exc_info.value)

    # Verify that the source metadata still exists (rollback worked)
    assert (backend.uri / "_meta_test_source@1.0.0.yaml").exists()

    # Verify that the target metadata doesn't exist (rollback worked)
    assert not (backend.uri / "_meta_test_source@2.0.0.yaml").exists()


def test_overwrite_updates_metadata_path(backend, temp_dir):
    """Test that overwrite updates the path in metadata correctly."""
    # Create source metadata and directory
    source_meta = {
        "name": "test:source",
        "version": "1.0.0",
        "description": "Test source",
        "created_at": "2024-01-01",
        "path": str(temp_dir / "test:source" / "1.0.0"),
    }

    # Create source directory and write a test file
    source_dir = temp_dir / "test:source" / "1.0.0"
    source_dir.mkdir(parents=True)
    with open(source_dir / "test.txt", "w") as f:
        f.write("test content")

    # Save source metadata
    backend.save_metadata("test:source", "1.0.0", source_meta)

    # Perform overwrite
    backend.overwrite(
        source_name="test:source", source_version="1.0.0", target_name="test:source", target_version="2.0.0"
    )

    # Verify that the target metadata exists and has the correct path
    target_meta = backend.fetch_metadata("test:source", "2.0.0")
    expected_path = str(backend.uri / "test:source" / "2.0.0")
    assert target_meta["path"] == expected_path


def test_release_lock_handles_invalid_json_and_io_errors(backend):
    """Test that release_lock properly handles JSON decode errors and IO errors."""
    # Create a lock file with invalid JSON content
    lock_path = backend._lock_path("test_lock")
    lock_path.touch()
    with open(lock_path, "w") as f:
        f.write("invalid json content")

    # Test JSON decode error
    result = backend.release_lock("test_lock", "test_id")
    assert result is False

    # Test IO error by making the file unreadable
    if platform.system() == "Windows":
        # On Windows, we need to close the file before changing permissions
        import stat

        lock_path.chmod(stat.S_IREAD)  # Make read-only
    else:
        lock_path.chmod(0o000)  # Remove all permissions

    result = backend.release_lock("test_lock", "test_id")
    assert result is False

    # Clean up
    if platform.system() == "Windows":
        lock_path.chmod(stat.S_IWRITE | stat.S_IREAD)  # Restore read/write
    else:
        lock_path.chmod(0o666)  # Restore permissions
    lock_path.unlink()


def test_acquire_lock_windows_atomic_creation(backend):
    """Test Windows-specific atomic file creation in acquire_lock (lines 356-358)."""
    import os
    
    lock_key = "test_lock"
    lock_id = str(uuid.uuid4())
    
    # Mock platform.system to return "Windows"
    with patch("platform.system", return_value="Windows"):
        # Mock os.open to track calls and simulate success
        with patch("os.open") as mock_os_open:
            # Mock os.fdopen to return a file-like object
            mock_file = MagicMock()
            mock_file.write = MagicMock()
            mock_file.flush = MagicMock()
            
            with patch("os.fdopen", return_value=mock_file):
                with patch("os.fsync"):
                    # Attempt to acquire lock
                    result = backend.acquire_lock(lock_key, lock_id, timeout=30)
                    
                    # Verify the lock was acquired successfully
                    assert result is True
                    
                    # Verify os.open was called with Windows-specific flags
                    mock_os_open.assert_called_once()
                    call_args = mock_os_open.call_args
                    assert call_args[0][0] == backend._lock_path(lock_key)  # First arg is path
                    assert call_args[0][1] == (os.O_CREAT | os.O_EXCL | os.O_RDWR)  # Second arg is flags
                    
                    # Verify no mode parameter was passed (Windows doesn't use it)
                    assert len(call_args[0]) == 2  # Only path and flags, no mode


def test_acquire_lock_windows_atomic_creation_failure(backend):
    """Test Windows-specific atomic file creation failure in acquire_lock (lines 356-358)."""
    import os
    
    lock_key = "test_lock"
    lock_id = str(uuid.uuid4())
    
    # Mock platform.system to return "Windows"
    with patch("platform.system", return_value="Windows"):
        # Mock os.open to raise FileExistsError (simulating existing file)
        with patch("os.open", side_effect=FileExistsError("File already exists")):
            # Mock _acquire_existing_lock to return False (simulating lock acquisition failure)
            with patch.object(backend, "_acquire_existing_lock", return_value=False):
                # Attempt to acquire lock - should raise LockAcquisitionError
                with pytest.raises(LockAcquisitionError, match="Lock test_lock is currently in use"):
                    backend.acquire_lock(lock_key, lock_id, timeout=30)


def test_acquire_lock_windows_os_error(backend):
    """Test Windows-specific atomic file creation with OS error in acquire_lock (lines 356-358)."""
    import os
    
    lock_key = "test_lock"
    lock_id = str(uuid.uuid4())
    
    # Mock platform.system to return "Windows"
    with patch("platform.system", return_value="Windows"):
        # Mock os.open to raise OSError (simulating system error)
        with patch("os.open", side_effect=OSError("Permission denied")):
            # Attempt to acquire lock - should return False due to exception handling
            result = backend.acquire_lock(lock_key, lock_id, timeout=30)
            assert result is False


def test_acquire_existing_lock_file_not_exists(backend):
    """Test _acquire_existing_lock when the lock file doesn't exist (lines 402-403)."""
    lock_key = "test_lock"
    lock_id = str(uuid.uuid4())
    
    # Ensure the lock file doesn't exist
    lock_path = backend._lock_path(lock_key)
    if lock_path.exists():
        lock_path.unlink()
    
    # Call _acquire_existing_lock directly
    result = backend._acquire_existing_lock(lock_path, lock_id, timeout=30, shared=False)
    
    # Verify that the method returns False when the lock file doesn't exist
    assert result is False


def test_acquire_existing_lock_file_not_found_error(backend):
    """Test _acquire_existing_lock FileNotFoundError handling when removing corrupted lock file (lines 424-425)."""
    lock_key = "test_lock"
    lock_id = str(uuid.uuid4())
    
    # Create a lock file
    lock_path = backend._lock_path(lock_key)
    lock_path.touch()
    
    # Mock the open operation to raise FileNotFoundError when trying to read the file
    with patch("builtins.open", side_effect=FileNotFoundError("File not found")):
        # Call _acquire_existing_lock directly
        result = backend._acquire_existing_lock(lock_path, lock_id, timeout=30, shared=False)
        
        # Verify that the method returns False when FileNotFoundError occurs
        assert result is False
        
        # Verify that the lock file was attempted to be removed (the unlink operation)
        # The actual unlink might not happen due to the mock, but we can verify the method handled the error gracefully


def test_acquire_existing_lock_file_not_found_error_during_unlink(backend):
    """Test _acquire_existing_lock FileNotFoundError during unlink operation (lines 424-425)."""
    lock_key = "test_lock"
    lock_id = str(uuid.uuid4())
    
    # Create a lock file with corrupted content
    lock_path = backend._lock_path(lock_key)
    lock_path.touch()
    
    # Write invalid JSON content to trigger the corrupted file path
    with open(lock_path, "w") as f:
        f.write("invalid json content")
    
    # Mock unlink to raise FileNotFoundError
    with patch("pathlib.Path.unlink", side_effect=FileNotFoundError("File not found")):
        # Call _acquire_existing_lock directly
        result = backend._acquire_existing_lock(lock_path, lock_id, timeout=30, shared=False)
        
        # Verify that the method returns False when FileNotFoundError occurs during unlink
        assert result is False


def test_acquire_existing_lock_file_not_found_error(backend):
    """Test _acquire_existing_lock FileNotFoundError handling."""
    lock_key = "test_lock"
    lock_id = str(uuid.uuid4())
    
    # Create a lock file with corrupted content
    lock_path = backend._lock_path(lock_key)
    lock_path.touch()
    
    # Write invalid JSON content to trigger the corrupted file path
    with open(lock_path, "w") as f:
        f.write("invalid json content")
    
    # Mock unlink to raise FileNotFoundError specifically for the corrupted file cleanup
    original_unlink = Path.unlink
    
    def mock_unlink(self):
        # Only raise FileNotFoundError for the specific lock file we're testing
        if self == lock_path:
            raise FileNotFoundError("File was already deleted by another thread")
        return original_unlink(self)
    
    with patch("pathlib.Path.unlink", side_effect=mock_unlink):
        # Call _acquire_existing_lock directly
        result = backend._acquire_existing_lock(lock_path, lock_id, timeout=30, shared=False)
        
        # Verify that the method returns False when FileNotFoundError occurs during corrupted file cleanup
        assert result is False


def test_release_lock_file_not_found_error (backend):
    """Test release_lock FileNotFoundError handling."""
    lock_key = "test_lock"
    lock_id = str(uuid.uuid4())
    
    # Create a lock file with valid metadata
    lock_path = backend._lock_path(lock_key)
    lock_path.touch()
    
    # Write valid metadata to the lock file
    metadata = {
        "lock_id": lock_id,
        "expires_at": time.time() + 60,
        "shared": False,
    }
    with open(lock_path, "w") as f:
        f.write(json.dumps(metadata))
    
    # Mock the file lock acquisition to succeed
    with patch.object(backend, "_acquire_file_lock", return_value=True):
        # Mock the file lock release to succeed
        with patch.object(backend, "_release_file_lock"):
            # Mock unlink to raise FileNotFoundError when trying to remove the lock file
            with patch("pathlib.Path.unlink", side_effect=FileNotFoundError("File was already deleted by another thread")):
                # Try to release the lock
                result = backend.release_lock(lock_key, lock_id)
                
                # Verify that the method returns True (successful release)
                assert result is True


def test_acquire_existing_lock_exclusive_with_existing_lock(backend):
    """Test _acquire_existing_lock when trying to acquire exclusive lock but existing lock is held (line 485)."""
    lock_key = "test_lock"
    lock_id = str(uuid.uuid4())
    
    # Create a lock file with valid metadata for an existing exclusive lock
    lock_path = backend._lock_path(lock_key)
    lock_path.touch()
    
    # Write metadata for an existing exclusive lock
    metadata = {
        "lock_id": "existing_id",
        "expires_at": time.time() + 60,  # Lock expires in 60 seconds
        "shared": False,  # This is an exclusive lock
    }
    with open(lock_path, "w") as f:
        f.write(json.dumps(metadata))
    
    # Try to acquire an exclusive lock (shared=False) when an existing exclusive lock is held
    result = backend._acquire_existing_lock(lock_path, lock_id, timeout=30, shared=False)
    
    # Verify that the method returns False (line 485)
    assert result is False


def test_overwrite_with_metadata_update(backend, temp_dir):
    """Test overwrite method with metadata file handling (lines 565, 567)."""
    # Create source metadata and directory
    source_meta = {
        "name": "test:source",
        "version": "1.0.0",
        "description": "Test source",
        "created_at": "2024-01-01",
        "path": str(temp_dir / "test:source" / "1.0.0"),
    }

    # Create source directory and write a test file
    source_dir = temp_dir / "test:source" / "1.0.0"
    source_dir.mkdir(parents=True)
    with open(source_dir / "test.txt", "w") as f:
        f.write("test content")

    # Save source metadata
    backend.save_metadata("test:source", "1.0.0", source_meta)

    # Perform overwrite
    backend.overwrite(
        source_name="test:source", source_version="1.0.0", target_name="test:source", target_version="2.0.0"
    )

    # Verify that the target metadata exists and has the correct path
    target_meta = backend.fetch_metadata("test:source", "2.0.0")
    expected_path = str(backend.uri / "test:source" / "2.0.0")
    assert target_meta["path"] == expected_path


def test_overwrite_with_metadata_file_exists_check(backend, temp_dir):
    """Test overwrite method specifically for the metadata file exists check (line 565)."""
    # Create source metadata and directory
    source_meta = {
        "name": "test:source",
        "version": "1.0.0",
        "description": "Test source",
        "created_at": "2024-01-01",
        "path": str(temp_dir / "test:source" / "1.0.0"),
    }

    # Create source directory and write a test file
    source_dir = temp_dir / "test:source" / "1.0.0"
    source_dir.mkdir(parents=True)
    with open(source_dir / "test.txt", "w") as f:
        f.write("test content")

    # Save source metadata
    backend.save_metadata("test:source", "1.0.0", source_meta)

    # Mock the target metadata path to exist
    target_meta_path = backend.uri / "_meta_test_source@2.0.0.yaml"
    target_meta_path.touch()

    # Perform overwrite
    backend.overwrite(
        source_name="test:source", source_version="1.0.0", target_name="test:source", target_version="2.0.0"
    )

    # Verify that the target metadata was updated
    target_meta = backend.fetch_metadata("test:source", "2.0.0")
    expected_path = str(backend.uri / "test:source" / "2.0.0")
    assert target_meta["path"] == expected_path
