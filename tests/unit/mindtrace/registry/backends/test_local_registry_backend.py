import importlib
import json
import os
from pathlib import Path
import platform
import pytest
import shutil
import sys
from typing import Generator
from unittest.mock import patch, MagicMock
import uuid
import yaml

from mindtrace.core import Config 
from mindtrace.registry import LocalRegistryBackend

# Import platform-specific modules safely
if platform.system() != 'Windows':
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
        "created_at": "2024-01-01T00:00:00Z"
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

class TestUnixLocks:
    """Test suite for Unix-specific locking mechanisms."""

    @pytest.fixture(autouse=True)
    def setup_unix(self):
        """Setup for Unix-specific tests."""
        with patch('platform.system', return_value='Linux'):
            # Mock fcntl module for Unix tests
            with patch('mindtrace.registry.backends.local_registry_backend.fcntl', create=True) as mock_fcntl:
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
        
        with open(test_file, 'r+') as f:
            # Mock fcntl.flock to simulate successful lock acquisition
            with patch('mindtrace.registry.backends.local_registry_backend.fcntl.flock', return_value=None) as mock_flock:
                assert backend._acquire_file_lock(f)
                mock_flock.assert_called_once_with(f.fileno(), 2 | 4)  # LOCK_EX | LOCK_NB

    def test_acquire_file_lock_unix_failure(self, backend):
        """Test failed file lock acquisition on Unix systems."""
        test_file = backend.uri / "test_lock"
        test_file.touch()
        
        with open(test_file, 'r+') as f:
            # Mock fcntl.flock to raise IOError (simulating lock acquisition failure)
            with patch('mindtrace.registry.backends.local_registry_backend.fcntl.flock', side_effect=IOError):
                assert not backend._acquire_file_lock(f)

    def test_release_file_lock_unix(self, backend):
        """Test releasing a file lock on Unix systems."""
        test_file = backend.uri / "test_lock"
        test_file.touch()
        
        with open(test_file, 'r+') as f:
            # Mock fcntl.flock to simulate successful lock release
            with patch('mindtrace.registry.backends.local_registry_backend.fcntl.flock', return_value=None) as mock_flock:
                backend._release_file_lock(f)
                mock_flock.assert_called_once_with(f.fileno(), 8)  # LOCK_UN

    def test_acquire_shared_lock_unix(self, backend):
        """Test acquiring a shared lock on Unix systems."""
        test_file = backend.uri / "test_lock"
        test_file.touch()
        
        with open(test_file, 'r+') as f:
            # Mock fcntl.flock to simulate successful shared lock acquisition
            with patch('mindtrace.registry.backends.local_registry_backend.fcntl.flock', return_value=None) as mock_flock:
                assert backend._acquire_shared_lock(f)
                mock_flock.assert_called_once_with(f.fileno(), 1)  # LOCK_SH


class TestWindowsLocks:
    """Test suite for Windows-specific locking mechanisms."""

    @pytest.fixture(autouse=True)
    def setup_windows(self):
        """Setup for Windows-specific tests."""
        with patch('platform.system', return_value='Windows'):
            # Mock msvcrt module for Windows tests
            with patch('mindtrace.registry.backends.local_registry_backend.msvcrt', create=True) as mock_msvcrt:
                # Set up the mock msvcrt module with necessary constants
                mock_msvcrt.LK_NBLCK = 1
                mock_msvcrt.LK_UNLCK = 2
                yield

    def test_acquire_file_lock_windows(self, backend):
        """Test acquiring a file lock on Windows systems."""
        test_file = backend.uri / "test_lock"
        test_file.touch()
        
        with open(test_file, 'r+') as f:
            # Mock msvcrt.locking to simulate successful lock acquisition
            with patch('mindtrace.registry.backends.local_registry_backend.msvcrt.locking', return_value=None) as mock_locking:
                assert backend._acquire_file_lock(f)
                mock_locking.assert_called_once_with(f.fileno(), 1, 1)  # LK_NBLCK, 1

    def test_acquire_file_lock_windows_failure(self, backend):
        """Test failed file lock acquisition on Windows systems."""
        test_file = backend.uri / "test_lock"
        test_file.touch()
        
        with open(test_file, 'r+') as f:
            # Mock msvcrt.locking to raise IOError (simulating lock acquisition failure)
            with patch('mindtrace.registry.backends.local_registry_backend.msvcrt.locking', side_effect=IOError):
                assert not backend._acquire_file_lock(f)

    def test_release_file_lock_windows(self, backend):
        """Test releasing a file lock on Windows systems."""
        test_file = backend.uri / "test_lock"
        test_file.touch()
        
        with open(test_file, 'r+') as f:
            # Mock msvcrt.locking to simulate successful lock release
            with patch('mindtrace.registry.backends.local_registry_backend.msvcrt.locking', return_value=None) as mock_locking:
                backend._release_file_lock(f)
                mock_locking.assert_called_once_with(f.fileno(), 2, 1)  # LK_UNLCK, 1

    def test_acquire_shared_lock_windows(self, backend):
        """Test acquiring a shared lock on Windows systems."""
        test_file = backend.uri / "test_lock"
        test_file.touch()
        
        with open(test_file, 'r+') as f:
            # Mock msvcrt.locking to simulate successful shared lock acquisition
            with patch('mindtrace.registry.backends.local_registry_backend.msvcrt.locking', return_value=None) as mock_locking:
                assert backend._acquire_shared_lock(f)
                mock_locking.assert_called_once_with(f.fileno(), 1, 1)  # LK_NBLCK, 1


class TestCrossPlatformLockOperations:
    """Test suite for cross-platform lock operations."""

    def test_acquire_lock_success(self, backend):
        """Test successful lock acquisition."""
        lock_key = "test_lock"
        lock_id = str(uuid.uuid4())
        
        # Mock platform.system to return current system
        with patch('platform.system', return_value=platform.system()):
            # Create a lock file
            lock_path = backend._lock_path(lock_key)
            lock_path.touch()
            
            # Test lock acquisition
            assert backend.acquire_lock(lock_key, lock_id, timeout=30)
            
            # Verify lock file contents
            with open(lock_path, 'r') as f:
                lock_data = json.load(f)
                assert lock_data["lock_id"] == lock_id
                assert "expires_at" in lock_data
                assert not lock_data.get("shared", False)

    def test_acquire_lock_failure(self, backend):
        """Test failed lock acquisition."""
        lock_key = "test_lock"
        lock_id = str(uuid.uuid4())
        
        # Mock platform.system to return current system
        with patch('platform.system', return_value=platform.system()):
            # Create a lock file
            lock_path = backend._lock_path(lock_key)
            lock_path.touch()
            
            # Mock _acquire_file_lock to simulate failure
            with patch.object(backend, '_acquire_file_lock', return_value=False):
                assert not backend.acquire_lock(lock_key, lock_id, timeout=30)

    def test_release_lock_success(self, backend):
        """Test successful lock release."""
        lock_key = "test_lock"
        lock_id = str(uuid.uuid4())
        
        # Create and acquire a lock first
        lock_path = backend._lock_path(lock_key)
        lock_path.touch()
        with open(lock_path, 'w') as f:
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
        with open(lock_path, 'w') as f:
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
        with open(lock_path, 'w') as f:
            json.dump({"lock_id": lock_id, "expires_at": float('inf')}, f)
        
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
        with open(lock_path, 'w') as f:
            json.dump({"lock_id": lock_id, "expires_at": 0}, f)
        
        # Test lock check
        is_locked, found_id = backend.check_lock(lock_key)
        assert not is_locked
        assert found_id is None


class TestPlatformSpecificImports:
    """Test suite for platform-specific import logic."""

    @pytest.fixture(autouse=True)
    def setup_imports(self):
        """Setup and teardown for import tests."""
        # Store original modules
        self.original_modules = {
            'fcntl': sys.modules.get('fcntl'),
            'msvcrt': sys.modules.get('msvcrt'),
            'mindtrace.registry.backends.local_registry_backend': sys.modules.get('mindtrace.registry.backends.local_registry_backend')
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
        if 'fcntl' in sys.modules:
            del sys.modules['fcntl']
        if 'msvcrt' in sys.modules:
            del sys.modules['msvcrt']
        
        # Remove the backend module
        if 'mindtrace.registry.backends.local_registry_backend' in sys.modules:
            del sys.modules['mindtrace.registry.backends.local_registry_backend']

    def test_windows_imports(self):
        """Test that Windows-specific imports are used on Windows."""
        # Mock the platform check
        with patch('platform.system', return_value='Windows'):
            # Clean up modules
            self._cleanup_modules()
            
            # Mock the msvcrt module
            sys.modules['msvcrt'] = self.mock_msvcrt
            
            # Reload the module to trigger the import logic
            importlib.reload(importlib.import_module('mindtrace.registry.backends.local_registry_backend'))
            
            # Get the reloaded module
            module = importlib.import_module('mindtrace.registry.backends.local_registry_backend')
            
            # Verify that msvcrt is imported and fcntl is not
            assert hasattr(module, 'msvcrt')
            assert not hasattr(module, 'fcntl')

    def test_unix_imports(self):
        """Test that Unix-specific imports are used on Unix systems."""
        # Mock the platform check
        with patch('platform.system', return_value='Linux'):
            # Clean up modules
            self._cleanup_modules()
            
            # Mock the fcntl module
            sys.modules['fcntl'] = self.mock_fcntl
            
            # Reload the module to trigger the import logic
            importlib.reload(importlib.import_module('mindtrace.registry.backends.local_registry_backend'))
            
            # Get the reloaded module
            module = importlib.import_module('mindtrace.registry.backends.local_registry_backend')
            
            # Verify that fcntl is imported and msvcrt is not
            assert hasattr(module, 'fcntl')
            assert not hasattr(module, 'msvcrt')

    def test_unknown_platform_imports(self):
        """Test that Unix-specific imports are used as fallback for unknown platforms."""
        # Mock the platform check
        with patch('platform.system', return_value='UnknownOS'):
            # Clean up modules
            self._cleanup_modules()
            
            # Mock the fcntl module
            sys.modules['fcntl'] = self.mock_fcntl
            
            # Reload the module to trigger the import logic
            importlib.reload(importlib.import_module('mindtrace.registry.backends.local_registry_backend'))
            
            # Get the reloaded module
            module = importlib.import_module('mindtrace.registry.backends.local_registry_backend')
            
            # Verify that fcntl is imported and msvcrt is not
            assert hasattr(module, 'fcntl')
            assert not hasattr(module, 'msvcrt') 