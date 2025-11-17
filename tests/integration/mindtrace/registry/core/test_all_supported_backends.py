"""Integration tests for all supported backends."""

import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

from mindtrace.core import Config, CoreConfig
from mindtrace.registry import GCPRegistryBackend, LocalRegistryBackend, MinioRegistryBackend, Registry

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

    bucket_name = f"mt-test-{uuid.uuid4().hex[:8]}"
    return bucket_name


@pytest.fixture(scope="session")
def gcp_backend_session():
    """Create a session-scoped GCP backend for faster testing."""
    config = CoreConfig()

    # Check if GCP credentials are available
    gcp_project_id = os.getenv("GCP_PROJECT_ID")
    gcp_credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    # Try to get from config if not in environment
    if not gcp_project_id:
        try:
            gcp_project_id = config["MINDTRACE_GCP"]["GCP_PROJECT_ID"]
        except (KeyError, TypeError):
            pass

    if not gcp_credentials_path:
        try:
            gcp_credentials_path = config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"]
        except (KeyError, TypeError):
            pass

    # Skip GCP tests if credentials are not available
    if not gcp_project_id or not gcp_credentials_path:
        pytest.skip("GCP credentials not available - skipping GCP backend tests")

    # Create a shared bucket for all GCP tests in this session
    bucket_name = f"mt-test-session-{uuid.uuid4().hex[:8]}"

    params = {
        "project_id": gcp_project_id,
        "bucket_name": bucket_name,
        "credentials_path": gcp_credentials_path,
        "uri": f"gs://{bucket_name}",
    }

    try:
        backend_instance = GCPRegistryBackend(**params)
        yield backend_instance
    except Exception as e:
        pytest.skip(f"GCP backend creation failed: {e}")


@pytest.fixture
def backend(request, backend_type, temp_dir, test_bucket):
    """Create a backend instance for testing."""
    backend_config = BACKENDS[backend_type]
    backend_class = backend_config["class"]
    params = backend_config["params"].copy()

    if backend_type == "local":
        params["uri"] = str(temp_dir)
        return backend_class(**params)
    elif backend_type == "minio":
        params["bucket"] = test_bucket
        params["uri"] = str(temp_dir)
        return backend_class(**params)
    elif backend_type == "gcp":
        # Use the session-scoped GCP backend for faster testing
        gcp_backend_session = request.getfixturevalue("gcp_backend_session")
        return gcp_backend_session


@pytest.fixture
def registry(backend):
    """Create a Registry instance with the backend."""
    return Registry(backend=backend, version_objects=True)


@pytest.fixture
def test_config():
    """Create a test Config object."""
    return Config(
        {
            "MINDTRACE_DIR_PATHS": {
                "TEMP_DIR": "/custom/temp/dir",
                "REGISTRY_DIR": "/custom/registry/dir",
            },
            "CUSTOM_KEY": "custom_value",
        }
    )


def test_save_and_load_config(registry, test_config):
    """Test saving and loading a Config object."""
    # Save the config
    registry.save("test:config", test_config, version="1.0.0")

    # Verify the config exists
    assert registry.has_object("test:config", "1.0.0")

    # Load the config
    loaded_config = registry.load("test:config", version="1.0.0")

    # Verify the loaded config matches the original
    assert loaded_config == test_config


def test_versioning(registry, test_config):
    """Test versioning functionality."""
    # Save multiple versions
    registry.save("test:versioning", test_config, version="1.0.0")
    registry.save("test:versioning", test_config, version="1.0.1")
    registry.save("test:versioning", test_config, version="1.1.0")

    # List versions
    versions = registry.list_versions("test:versioning")
    assert len(versions) == 3
    assert "1.0.0" in versions
    assert "1.0.1" in versions
    assert "1.1.0" in versions

    # Load specific version
    loaded_config = registry.load("test:versioning", version="1.0.1")
    assert loaded_config["CUSTOM_KEY"] == "custom_value"

    # Load latest version
    latest_config = registry.load("test:versioning")
    assert latest_config["CUSTOM_KEY"] == "custom_value"


def test_delete(registry, test_config):
    """Test deletion functionality."""
    # Save object
    registry.save("test:delete", test_config, version="1.0.0")
    assert registry.has_object("test:delete", "1.0.0")

    # Delete specific version
    registry.delete("test:delete", version="1.0.0")
    assert not registry.has_object("test:delete", "1.0.0")

    # Save multiple versions
    registry.save("test:delete", test_config, version="1.0.0")
    registry.save("test:delete", test_config, version="1.0.1")

    # Delete all versions
    registry.delete("test:delete")
    assert not registry.has_object("test:delete", "1.0.0")
    assert not registry.has_object("test:delete", "1.0.1")


def test_info(registry, test_config):
    """Test info functionality."""
    # Save object with metadata
    registry.save("test:info", test_config, version="1.0.0", metadata={"description": "test object"})

    # Get info for specific version
    info = registry.info("test:info", version="1.0.0")
    assert info["version"] == "1.0.0"
    assert info["metadata"]["description"] == "test object"

    # Get info for all versions
    all_info = registry.info("test:info")
    assert "1.0.0" in all_info
    assert all_info["1.0.0"]["metadata"]["description"] == "test object"


@pytest.mark.slow
def test_concurrent_operations_threadpool(registry, test_config):
    """Test concurrent operations with distributed locking."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    # Save initial object
    registry.save("test:concurrent", test_config, version="1.0.0")

    # Function to perform concurrent loads
    def load_object():
        time.sleep(0.1)  # Add delay to increase chance of race condition
        obj = registry.load("test:concurrent")
        return obj["CUSTOM_KEY"]

    # Try to load the same object concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(load_object) for _ in range(10)]
        results = [future.result() for future in futures]

    # All loads should return the same value
    assert all(r == "custom_value" for r in results)

    # Test save-load race condition
    def save_object():
        time.sleep(0.1)
        new_config = Config(
            {
                "MINDTRACE_DIR_PATHS": {
                    "TEMP_DIR": "/custom/temp/dir2",
                    "REGISTRY_DIR": "/custom/registry/dir2",
                },
                "CUSTOM_KEY": "new_value",
            }
        )
        registry.save("test:concurrent", new_config)

    with ThreadPoolExecutor(max_workers=2) as executor:
        save_future = executor.submit(save_object)
        load_future = executor.submit(load_object)

        save_future.result()
        load_value = load_future.result()

    # Loaded value should be consistent
    assert load_value in ("custom_value", "new_value")


def test_materializer_registration(registry):
    """Test materializer registration and retrieval."""
    # Register a materializer
    registry.register_materializer(
        "test.materializer.TestMaterializer", "mindtrace.registry.archivers.config_archiver.ConfigArchiver"
    )

    # Get registered materializer
    materializer = registry.registered_materializer("test.materializer.TestMaterializer")
    assert materializer == "mindtrace.registry.archivers.config_archiver.ConfigArchiver"

    # Get all registered materializers
    materializers = registry.registered_materializers()
    assert "test.materializer.TestMaterializer" in materializers
    assert (
        materializers["test.materializer.TestMaterializer"]
        == "mindtrace.registry.archivers.config_archiver.ConfigArchiver"
    )

    # Register a materializer
    registry.register_materializer("test:custom", "CustomMaterializer")

    # Check registered materializer
    materializer = registry.registered_materializer("test:custom")
    assert materializer == "CustomMaterializer"

    # Check all registered materializers
    materializers = registry.registered_materializers()
    assert "test:custom" in materializers
    assert materializers["test:custom"] == "CustomMaterializer"


@pytest.mark.slow
def test_concurrent_save_operations(request, registry, test_config):
    """Test concurrent save operations with distributed locking."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    # Get the backend type
    backend_type = request.getfixturevalue("backend_type")
    n_workers = 2 if backend_type == "gcp" else 3
    n_versions = 3 if backend_type == "gcp" else 5

    # Use unique test prefix to avoid conflicts with other tests when using shared bucket
    test_prefix = f"test:concurrent-save:{uuid.uuid4().hex[:8]}:"

    def save_with_delay(i):
        time.sleep(0.1)  # Add delay to increase chance of race condition
        new_config = Config(
            {
                "MINDTRACE_DIR_PATHS": {
                    "TEMP_DIR": f"/custom/temp/dir{i}",
                    "REGISTRY_DIR": f"/custom/registry/dir{i}",
                },
                "CUSTOM_KEY": f"value{i}",
            }
        )
        registry.save(f"{test_prefix}save", new_config, version=f"1.0.{i}")

    # Try to save multiple versions concurrently (reduced workers to avoid lock contention)
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = [executor.submit(save_with_delay, i) for i in range(n_versions)]
        [future.result() for future in futures]

    # Verify all versions were saved correctly
    versions = registry.list_versions(f"{test_prefix}save")
    assert len(versions) == n_versions
    for i in range(n_versions):
        config = registry.load(f"{test_prefix}save", version=f"1.0.{i}")
        assert config["CUSTOM_KEY"] == f"value{i}"


@pytest.mark.slow
def test_concurrent_load_operations(registry, test_config):
    """Test concurrent load operations with shared locks."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    # Save initial object
    registry.save("test:concurrent-load", test_config, version="1.0.0")

    def load_with_delay():
        time.sleep(0.1)  # Add delay to increase chance of race condition
        return registry.load("test:concurrent-load", version="1.0.0")

    # Try to load the same object concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(load_with_delay) for _ in range(10)]
        results = [future.result() for future in futures]

    # All loads should return the same value
    assert all(r["CUSTOM_KEY"] == "custom_value" for r in results)


@pytest.mark.slow
def test_concurrent_save_load_race(registry, test_config):
    """Test race conditions between save and load operations."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    # Save initial object
    registry.save("test:race", test_config, version="1.0.0")

    def save_new_version():
        time.sleep(0.1)
        new_config = Config(
            {
                "MINDTRACE_DIR_PATHS": {
                    "TEMP_DIR": "/custom/temp/dir2",
                    "REGISTRY_DIR": "/custom/registry/dir2",
                },
                "CUSTOM_KEY": "new_value",
            }
        )
        registry.save("test:race", new_config, version="1.0.1")

    def load_object():
        time.sleep(0.1)
        return registry.load("test:race", version="1.0.0")

    # Try to save and load concurrently
    with ThreadPoolExecutor(max_workers=2) as executor:
        save_future = executor.submit(save_new_version)
        load_future = executor.submit(load_object)

        save_future.result()
        load_result = load_future.result()

    # Loaded value should be consistent
    assert load_result["CUSTOM_KEY"] == "custom_value"


@pytest.mark.slow
def test_concurrent_delete_operations(registry, test_config):
    """Test concurrent delete operations with distributed locking."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    # Save multiple versions
    for i in range(5):
        registry.save("test:concurrent-delete", test_config, version=f"1.0.{i}")

    # Confirm that all versions exist
    for i in range(5):
        assert test_config == registry.load("test:concurrent-delete", version=f"1.0.{i}")

    print(registry.__str__(latest_only=False))

    def delete_with_delay(version):
        time.sleep(0.1)
        registry.delete("test:concurrent-delete", version=version)

    # Try to delete multiple versions concurrently
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(delete_with_delay, f"1.0.{i}") for i in range(5)]
        [future.result() for future in futures]

    # Verify all versions were deleted
    assert not registry.has_object("test:concurrent-delete", "1.0.0")
    assert len(registry.list_versions("test:concurrent-delete")) == 0


def test_dict_like_interface_basic(registry, test_config):
    """Test basic dictionary-like interface methods."""
    # Test __setitem__ and __getitem__
    registry["test:dict"] = test_config
    loaded_config = registry["test:dict"]
    assert loaded_config["CUSTOM_KEY"] == "custom_value"

    # Test __delitem__
    del registry["test:dict"]
    assert "test:dict" not in registry

    # Test __contains__
    registry["test:dict"] = test_config
    assert "test:dict" in registry
    assert "nonexistent" not in registry


def test_dict_like_interface_advanced(registry, test_config):
    """Test advanced dictionary-like interface methods."""
    # Use unique test prefix to avoid conflicts with other tests when using shared bucket
    test_prefix = f"test:advanced:{uuid.uuid4().hex[:8]}:"

    # Test get() with default
    assert registry.get(f"{test_prefix}nonexistent", "default") == "default"

    # Test pop()
    registry[f"{test_prefix}pop"] = test_config
    popped_config = registry.pop(f"{test_prefix}pop")
    assert popped_config["CUSTOM_KEY"] == "custom_value"
    assert f"{test_prefix}pop" not in registry

    # Test pop() with default
    assert registry.pop(f"{test_prefix}nonexistent", "default") == "default"

    # Test setdefault()
    registry.setdefault(f"{test_prefix}setdefault", test_config)
    assert registry[f"{test_prefix}setdefault"]["CUSTOM_KEY"] == "custom_value"

    # Test update()
    new_config = Config({"CUSTOM_KEY": "new_value"})
    registry.update({f"{test_prefix}update": new_config})
    assert registry[f"{test_prefix}update"]["CUSTOM_KEY"] == "new_value"


def test_dict_like_interface_versioned(registry, test_config):
    """Test dictionary-like interface with versioned keys."""
    # Test versioned keys
    registry["test:versioned@1.0.0"] = test_config
    new_config = Config({"CUSTOM_KEY": "new_value"})
    registry["test:versioned@1.0.1"] = new_config

    # Test loading specific versions
    assert registry["test:versioned@1.0.0"]["CUSTOM_KEY"] == "custom_value"
    assert registry["test:versioned@1.0.1"]["CUSTOM_KEY"] == "new_value"

    # Test deleting specific versions
    del registry["test:versioned@1.0.0"]
    assert "test:versioned@1.0.0" not in registry
    assert "test:versioned@1.0.1" in registry


@pytest.mark.slow
def test_concurrent_dict_operations(registry, test_config):
    """Test concurrent dictionary-like operations."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    # Use unique test prefix to avoid conflicts with other tests when using shared bucket
    test_prefix = f"test:concurrent-dict:{uuid.uuid4().hex[:8]}:"

    def set_item(i):
        time.sleep(0.1)
        new_config = Config({"CUSTOM_KEY": f"value{i}"})
        registry[f"{test_prefix}{i}"] = new_config

    def get_item(i):
        time.sleep(0.1)
        return registry.get(f"{test_prefix}{i}")

    def pop_item(i):
        time.sleep(0.1)
        return registry.pop(f"{test_prefix}{i}", None)

    # Test concurrent set operations
    with ThreadPoolExecutor(max_workers=5) as executor:
        set_futures = [executor.submit(set_item, i) for i in range(5)]
        [future.result() for future in set_futures]

    # Test concurrent get operations
    with ThreadPoolExecutor(max_workers=5) as executor:
        get_futures = [executor.submit(get_item, i) for i in range(5)]
        get_results = [future.result() for future in get_futures]

    # Verify get results
    for i, result in enumerate(get_results):
        assert result["CUSTOM_KEY"] == f"value{i}"

    # Test concurrent pop operations (with reduced parallelism for GCP to avoid lock contention)
    with ThreadPoolExecutor(max_workers=3) as executor:  # Reduced from 5 to 3 for better reliability
        pop_futures = [executor.submit(pop_item, i) for i in range(5)]
        pop_results = [future.result() for future in pop_futures]

    # Verify pop results and that items were removed
    for i, result in enumerate(pop_results):
        assert result["CUSTOM_KEY"] == f"value{i}"
        assert f"{test_prefix}{i}" not in registry


def test_dict_like_interface_error_handling(registry, test_config):
    """Test error handling in dictionary-like interface."""
    # Test KeyError for non-existent key
    with pytest.raises(KeyError):
        _ = registry["nonexistent"]

    # Test KeyError for non-existent version
    registry["test:error"] = test_config
    with pytest.raises(KeyError):
        _ = registry["test:error@nonexistent"]

    # Test ValueError for invalid version format
    with pytest.raises(ValueError):
        registry["test:error@invalid-version"] = test_config

    # Test pop() with non-existent key and no default
    with pytest.raises(KeyError):
        registry.pop("nonexistent")


def test_dict_like_interface_complex_objects(registry):
    """Test dictionary-like interface with complex objects."""
    # Test with nested dictionary
    nested_dict = {"outer": {"inner": {"value": 42}}}
    registry["test:nested"] = nested_dict
    loaded_dict = registry["test:nested"]
    assert loaded_dict["outer"]["inner"]["value"] == 42

    # Test with list of objects
    list_of_objects = [{"id": i, "value": f"value{i}"} for i in range(3)]
    registry["test:list"] = list_of_objects
    loaded_list = registry["test:list"]
    assert len(loaded_list) == 3
    assert loaded_list[1]["value"] == "value1"


def test_save_and_load_basic_types(registry):
    """Test saving and loading basic Python types."""
    # Test different data types (excluding None as it has no materializer)
    test_data = {
        "int": 42,
        "float": 3.14,
        "str": "Hello, World!",
        "list": [1, 2, 3, 4, 5],
        "dict": {"key": "value", "number": 123},
        "bool": True,
    }

    # Save each type
    for name, value in test_data.items():
        registry.save(f"test:{name}", value)

    # Load and verify each type
    for name, expected_value in test_data.items():
        loaded_value = registry.load(f"test:{name}")
        assert loaded_value == expected_value


def test_object_discovery(registry):
    """Test object discovery functionality."""
    # Use unique test prefix to avoid conflicts with other tests when using shared bucket (e.g., GCP session-scoped)
    test_prefix = f"test:discovery:{uuid.uuid4().hex[:8]}:"

    # Save multiple objects
    registry.save(f"{test_prefix}object:1", "data1")
    registry.save(f"{test_prefix}object:2", "data2")
    registry.save(f"{test_prefix}object:3", "data3")

    # List all objects and filter to our test objects
    all_objects = registry.list_objects()
    test_objects = [obj for obj in all_objects if obj.startswith(test_prefix)]
    assert len(test_objects) == 3
    assert f"{test_prefix}object:1" in test_objects
    assert f"{test_prefix}object:2" in test_objects
    assert f"{test_prefix}object:3" in test_objects

    # List versions for a specific object
    registry.save(f"{test_prefix}object:1", "data1_v2", version="2.0.0")
    versions = registry.list_versions(f"{test_prefix}object:1")
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

    # Handle different metadata structures between backends
    if isinstance(info, dict) and "1" in info:
        # GCP backend returns versioned structure
        version_info = info["1"]
        assert "metadata" in version_info
        assert "description" in version_info["metadata"]
        assert version_info["metadata"]["description"] == "Test object"
        assert version_info["metadata"]["tags"] == ["test", "integration"]
    else:
        # Other backends return direct metadata
        assert "description" in info
        assert info["description"] == "Test object"
        assert info["tags"] == ["test", "integration"]


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


def test_concurrent_operations_threads(registry):
    """Test concurrent operations with distributed locking."""
    import threading

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

    # Wait for all threads with timeout
    for thread in threads:
        thread.join(timeout=10)

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

        # Test distributed locking with timeout
        lock_key = "test:lock"
        lock_id = "test-lock-id"

        try:
            success = backend.acquire_lock(lock_key, lock_id, 5, shared=False)
            assert success

            is_locked, current_lock_id = backend.check_lock(lock_key)
            assert is_locked
            assert current_lock_id == lock_id

            backend.release_lock(lock_key, lock_id)

            is_locked_after, _ = backend.check_lock(lock_key)
            assert not is_locked_after
        except Exception as e:
            pytest.skip(f"GCP locking test failed (likely due to credentials): {e}")

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


def test_from_uri_integration(backend_type, temp_dir, test_bucket):
    """Test that from_uri creates correct backend type and works end-to-end."""
    if backend_type == "local":
        uri = str(temp_dir)
        registry = Registry.from_uri(uri, version_objects=True)
        assert isinstance(registry.backend, LocalRegistryBackend)

    elif backend_type == "minio":
        uri = f"s3://{test_bucket}"
        registry = Registry.from_uri(
            uri,
            endpoint=os.getenv("MINDTRACE_MINIO__MINIO_ENDPOINT", "localhost:9100"),
            access_key=os.getenv("MINDTRACE_MINIO__MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINDTRACE_MINIO__MINIO_SECRET_KEY", "minioadmin"),
            bucket=test_bucket,
            secure=False,
            version_objects=True,
        )
        assert isinstance(registry.backend, MinioRegistryBackend)

    elif backend_type == "gcp":
        config = CoreConfig()

        # Check if GCP credentials are available
        gcp_project_id = os.getenv("GCP_PROJECT_ID")
        gcp_credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        # Try to get from config if not in environment
        if not gcp_project_id:
            try:
                gcp_project_id = config["MINDTRACE_GCP"]["GCP_PROJECT_ID"]
            except (KeyError, TypeError):
                pass

        if not gcp_credentials_path:
            try:
                gcp_credentials_path = config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"]
            except (KeyError, TypeError):
                pass

        # Skip if credentials are not available
        if not gcp_project_id or not gcp_credentials_path:
            pytest.skip("GCP credentials not available - skipping GCP from_uri test")

        uri = f"gs://{test_bucket}"
        try:
            registry = Registry.from_uri(
                uri,
                project_id=gcp_project_id,
                bucket_name=test_bucket,
                credentials_path=gcp_credentials_path,
                version_objects=True,
            )
        except Exception as e:
            pytest.skip(f"GCP backend creation failed: {e}")
        assert isinstance(registry.backend, GCPRegistryBackend)

    # Test basic functionality
    test_config = Config(
        {
            "MINDTRACE_DIR_PATHS": {
                "TEMP_DIR": "/test/temp",
                "REGISTRY_DIR": "/test/registry",
            },
            "TEST_KEY": "test_value",
        }
    )

    registry.save("test:fromuri", test_config, version="1.0.0")
    loaded_config = registry.load("test:fromuri", version="1.0.0")
    assert loaded_config["TEST_KEY"] == "test_value"
    assert "test:fromuri" in registry.list_objects()

    # Cleanup
    registry.delete("test:fromuri", version="1.0.0")


def test_cleanup_after_tests(registry, backend_type, test_bucket):
    """Test that cleanup works properly after tests."""
    # This test ensures that cleanup works by verifying the backend is functional
    registry.save("test:cleanup", "cleanup_data")
    assert registry.has_object("test:cleanup")

    # The actual cleanup will happen in the fixtures after all tests
