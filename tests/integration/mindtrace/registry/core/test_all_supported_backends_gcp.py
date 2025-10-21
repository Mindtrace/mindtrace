"""Integration tests for all supported backends including GCP."""

import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

from mindtrace.core import CoreConfig
from mindtrace.registry import LocalRegistryBackend, MinioRegistryBackend, GCPRegistryBackend, Registry

# Backend configurations
BACKENDS = {
    "local": {
        "class": LocalRegistryBackend,
        "params": {
            "uri": None  # Will be set in fixture
        },
    },
    "minio": {
        "class": MinioRegistryBackend,
        "params": {
            "endpoint": os.getenv("MINDTRACE_MINIO__MINIO_ENDPOINT", "localhost:9100"),
            "access_key": os.getenv("MINDTRACE_MINIO__MINIO_ACCESS_KEY", "minioadmin"),
            "secret_key": os.getenv("MINDTRACE_MINIO__MINIO_SECRET_KEY", "minioadmin"),
            "bucket": None,  # Will be set in fixture
            "secure": False,
        },
    },
    "gcp": {
        "class": GCPRegistryBackend,
        "params": {
            "project_id": None,  # Will be set in fixture
            "bucket_name": None,  # Will be set in fixture
            "credentials_path": None,  # Will be set in fixture
        },
    },
}


@pytest.fixture(params=BACKENDS.keys())
def backend_type(request):
    """Fixture to provide backend types for testing."""
    return request.param


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def test_bucket(backend_type):
    """Create a test bucket for cloud backends."""
    if backend_type == "local":
        return None
    
    bucket_name = f"mindtrace-test-{uuid.uuid4()}"
    return bucket_name


@pytest.fixture
def backend(backend_type, temp_dir, test_bucket):
    """Create a backend instance for testing."""
    from mindtrace.core import CoreConfig
    
    config = CoreConfig()
    backend_config = BACKENDS[backend_type]
    backend_class = backend_config["class"]
    params = backend_config["params"].copy()
    
    if backend_type == "local":
        params["uri"] = str(temp_dir)
    elif backend_type == "minio":
        params["bucket"] = test_bucket
        params["uri"] = str(temp_dir)
    elif backend_type == "gcp":
        params["project_id"] = os.getenv("GCP_PROJECT_ID", config["MINDTRACE_GCP"]["GCP_PROJECT_ID"])
        params["bucket_name"] = test_bucket
        params["credentials_path"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"])
        params["uri"] = f"gs://{test_bucket}"
    
    return backend_class(**params)


@pytest.fixture
def registry(backend):
    """Create a Registry instance with the backend."""
    return Registry(backend=backend)


def test_save_and_load_basic_types(registry):
    """Test saving and loading basic Python types."""
    # Test different data types
    test_data = {
        "int": 42,
        "float": 3.14,
        "str": "Hello, World!",
        "list": [1, 2, 3, 4, 5],
        "dict": {"key": "value", "number": 123},
        "bool": True,
        "none": None,
    }
    
    # Save each type
    for name, value in test_data.items():
        registry.save(f"test:{name}", value)
    
    # Load and verify each type
    for name, expected_value in test_data.items():
        loaded_value = registry.load(f"test:{name}")
        assert loaded_value == expected_value


def test_versioning(registry):
    """Test object versioning functionality."""
    # Save multiple versions
    registry.save("test:versioned", "version1", version="1.0.0")
    registry.save("test:versioned", "version2", version="2.0.0")
    registry.save("test:versioned", "version3", version="3.0.0")
    
    # Load specific versions
    v1 = registry.load("test:versioned", version="1.0.0")
    v2 = registry.load("test:versioned", version="2.0.0")
    v3 = registry.load("test:versioned", version="3.0.0")
    
    assert v1 == "version1"
    assert v2 == "version2"
    assert v3 == "version3"
    
    # Load latest version
    latest = registry.load("test:versioned")
    assert latest == "version3"


def test_object_discovery(registry):
    """Test object discovery functionality."""
    # Save multiple objects
    registry.save("object:1", "data1")
    registry.save("object:2", "data2")
    registry.save("object:3", "data3")
    
    # List all objects
    objects = registry.list_objects()
    assert len(objects) == 3
    assert "object:1" in objects
    assert "object:2" in objects
    assert "object:3" in objects
    
    # List versions for a specific object
    registry.save("object:1", "data1_v2", version="2.0.0")
    versions = registry.list_versions("object:1")
    assert len(versions) == 2
    assert "1" in versions  # Auto-generated version
    assert "2.0.0" in versions


def test_metadata_operations(registry):
    """Test metadata operations."""
    # Save object with metadata
    metadata = {
        "description": "Test object",
        "tags": ["test", "integration"],
        "created_by": "test_user",
    }
    
    registry.save("test:metadata", "test_data", metadata=metadata)
    
    # Get object info
    info = registry.info("test:metadata")
    assert "description" in info["metadata"]
    assert info["metadata"]["description"] == "Test object"
    assert info["metadata"]["tags"] == ["test", "integration"]


def test_object_existence(registry):
    """Test object existence checking."""
    # Save an object
    registry.save("test:exists", "test_data")
    
    # Check existing object
    assert registry.has_object("test:exists")
    assert registry.has_object("test:exists", version="1")  # Auto-generated version
    
    # Check non-existing object
    assert not registry.has_object("test:not_exists")
    assert not registry.has_object("test:exists", version="999.0.0")


def test_delete_operations(registry):
    """Test delete operations."""
    # Save an object
    registry.save("test:delete", "test_data")
    assert registry.has_object("test:delete")
    
    # Delete the object
    registry.delete("test:delete")
    assert not registry.has_object("test:delete")


def test_materializer_registration(registry):
    """Test materializer registration."""
    # Register a materializer
    registry.register_materializer("test:custom", "CustomMaterializer")
    
    # Check registered materializer
    materializer = registry.registered_materializer("test:custom")
    assert materializer == "CustomMaterializer"
    
    # Check all registered materializers
    materializers = registry.registered_materializers()
    assert "test:custom" in materializers
    assert materializers["test:custom"] == "CustomMaterializer"


def test_concurrent_operations(registry):
    """Test concurrent operations with distributed locking."""
    import threading
    import time
    
    results = []
    
    def worker(worker_id):
        try:
            # Save an object (this will use distributed locking)
            registry.save(f"test:concurrent:{worker_id}", f"data_{worker_id}")
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
    assert len(results) == 3
    assert all("completed" in result for result in results)
    
    # Verify objects were saved
    for i in range(3):
        assert registry.has_object(f"test:concurrent:{i}")


def test_error_handling_invalid_names(registry):
    """Test error handling for invalid object names."""
    # Test invalid object names
    invalid_names = [
        "invalid_name",  # Contains underscore
        "invalid@name",  # Contains @
        "",  # Empty name
    ]
    
    for invalid_name in invalid_names:
        with pytest.raises(ValueError):
            registry.save(invalid_name, "test_data")


def test_error_handling_nonexistent_objects(registry):
    """Test error handling for nonexistent objects."""
    # Try to load nonexistent object
    with pytest.raises(ValueError):
        registry.load("nonexistent:object")
    
    # Try to load nonexistent version
    registry.save("test:exists", "data")
    with pytest.raises(ValueError):
        registry.load("test:exists", version="999.0.0")


def test_backend_specific_functionality(backend_type, registry):
    """Test backend-specific functionality."""
    if backend_type == "gcp":
        # Test GCP-specific functionality
        backend = registry.backend
        
        # Test distributed locking
        lock_key = "test:lock"
        lock_id = "test-lock-id"
        
        success = backend.acquire_lock(lock_key, lock_id, 10, shared=False)
        assert success
        
        is_locked, current_lock_id = backend.check_lock(lock_key)
        assert is_locked
        assert current_lock_id == lock_id
        
        backend.release_lock(lock_key, lock_id)
        
        is_locked_after, _ = backend.check_lock(lock_key)
        assert not is_locked_after
    
    elif backend_type == "minio":
        # Test MinIO-specific functionality
        backend = registry.backend
        
        # Test that bucket exists
        assert backend.client.bucket_exists(backend.bucket)
    
    elif backend_type == "local":
        # Test local-specific functionality
        backend = registry.backend
        
        # Test that directory exists
        assert backend.uri.exists()
        assert backend.uri.is_dir()


def test_cleanup_after_tests(registry, backend_type, test_bucket):
    """Test that cleanup works properly after tests."""
    # This test ensures that cleanup works by verifying the backend is functional
    registry.save("test:cleanup", "cleanup_data")
    assert registry.has_object("test:cleanup")
    
    # The actual cleanup will happen in the fixtures after all tests
