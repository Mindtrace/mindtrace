import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

from mindtrace.core import Config
from mindtrace.registry import LocalRegistryBackend, MinioRegistryBackend, Registry

# Backend configurations
BACKENDS = {
    "local": {
        "class": LocalRegistryBackend,
        "params": {
            "uri": None  # Will be set in fixture
        }
    },
    "minio": {
        "class": MinioRegistryBackend,
        "params": {
            "endpoint": os.getenv("MINDTRACE_MINIO_ENDPOINT", "localhost:9000"),
            "access_key": os.getenv("MINDTRACE_MINIO_ACCESS_KEY", "minioadmin"),
            "secret_key": os.getenv("MINDTRACE_MINIO_SECRET_KEY", "minioadmin"),
            "bucket": None,  # Will be set in fixture
            "secure": False
        }
    }
}

@pytest.fixture(params=BACKENDS.keys())
def backend_type(request):
    """Fixture to provide backend types for testing."""
    return request.param

@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)

@pytest.fixture
def registry(backend_type, temp_dir):
    """Create a Registry instance with the specified backend."""
    backend_config = BACKENDS[backend_type]
    backend_params = backend_config["params"].copy()
    
    if backend_type == "local":
        backend_params["uri"] = temp_dir
    elif backend_type == "minio":
        # Use a unique bucket name for each test run
        backend_params["bucket"] = f"test-registry-{uuid.uuid4().hex[:8]}"
    
    backend = backend_config["class"](**backend_params)
    
    registry = Registry(backend=backend)
    return registry

@pytest.fixture
def test_config():
    """Create a test Config object."""
    return Config(
        MINDTRACE_TEMP_DIR="/custom/temp/dir",
        MINDTRACE_DEFAULT_REGISTRY_DIR="/custom/registry/dir",
        CUSTOM_KEY="custom_value"
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
def test_concurrent_operations(registry, test_config):
    """Test concurrent operations with distributed locking."""
    import threading
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
            MINDTRACE_TEMP_DIR="/custom/temp/dir2",
            MINDTRACE_DEFAULT_REGISTRY_DIR="/custom/registry/dir2",
            CUSTOM_KEY="new_value"
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
        "test.materializer.TestMaterializer",
        "mindtrace.registry.archivers.config_archiver.ConfigArchiver"
    )
    
    # Get registered materializer
    materializer = registry.registered_materializer("test.materializer.TestMaterializer")
    assert materializer == "mindtrace.registry.archivers.config_archiver.ConfigArchiver"
    
    # Get all registered materializers
    materializers = registry.registered_materializers()
    assert "test.materializer.TestMaterializer" in materializers
    assert materializers["test.materializer.TestMaterializer"] == "mindtrace.registry.archivers.config_archiver.ConfigArchiver"

@pytest.mark.slow
def test_concurrent_save_operations(registry, test_config):
    """Test concurrent save operations with distributed locking."""
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    
    def save_with_delay(i):
        time.sleep(0.1)  # Add delay to increase chance of race condition
        new_config = Config(
            MINDTRACE_TEMP_DIR=f"/custom/temp/dir{i}",
            MINDTRACE_DEFAULT_REGISTRY_DIR=f"/custom/registry/dir{i}",
            CUSTOM_KEY=f"value{i}"
        )
        registry.save("test:concurrent-save", new_config, version=f"1.0.{i}")
    
    # Try to save multiple versions concurrently
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(save_with_delay, i) for i in range(5)]
        [future.result() for future in futures]
    
    # Verify all versions were saved correctly
    versions = registry.list_versions("test:concurrent-save")
    assert len(versions) == 5
    for i in range(5):
        config = registry.load("test:concurrent-save", version=f"1.0.{i}")
        assert config["CUSTOM_KEY"] == f"value{i}"

@pytest.mark.slow
def test_concurrent_load_operations(registry, test_config):
    """Test concurrent load operations with shared locks."""
    import threading
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
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    
    # Save initial object
    registry.save("test:race", test_config, version="1.0.0")
    
    def save_new_version():
        time.sleep(0.1)
        new_config = Config(
            MINDTRACE_TEMP_DIR="/custom/temp/dir2",
            MINDTRACE_DEFAULT_REGISTRY_DIR="/custom/registry/dir2",
            CUSTOM_KEY="new_value"
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
    import threading
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
    # Test get() with default
    assert registry.get("nonexistent", "default") == "default"
    
    # Test pop()
    registry["test:pop"] = test_config
    popped_config = registry.pop("test:pop")
    assert popped_config["CUSTOM_KEY"] == "custom_value"
    assert "test:pop" not in registry
    
    # Test pop() with default
    assert registry.pop("nonexistent", "default") == "default"
    
    # Test setdefault()
    registry.setdefault("test:setdefault", test_config)
    assert registry["test:setdefault"]["CUSTOM_KEY"] == "custom_value"
    
    # Test update()
    new_config = Config(CUSTOM_KEY="new_value")
    registry.update({"test:update": new_config})
    assert registry["test:update"]["CUSTOM_KEY"] == "new_value"

def test_dict_like_interface_versioned(registry, test_config):
    """Test dictionary-like interface with versioned keys."""
    # Test versioned keys
    registry["test:versioned@1.0.0"] = test_config
    new_config = Config(CUSTOM_KEY="new_value")
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
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    
    def set_item(i):
        time.sleep(0.1)
        new_config = Config(CUSTOM_KEY=f"value{i}")
        registry[f"test:concurrent-dict-{i}"] = new_config
    
    def get_item(i):
        time.sleep(0.1)
        return registry.get(f"test:concurrent-dict-{i}")
    
    def pop_item(i):
        time.sleep(0.1)
        return registry.pop(f"test:concurrent-dict-{i}", None)
    
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
    
    # Test concurrent pop operations
    with ThreadPoolExecutor(max_workers=5) as executor:
        pop_futures = [executor.submit(pop_item, i) for i in range(5)]
        pop_results = [future.result() for future in pop_futures]
    
    # Verify pop results and that items were removed
    for i, result in enumerate(pop_results):
        assert result["CUSTOM_KEY"] == f"value{i}"
        assert f"test:concurrent_dict_{i}" not in registry

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
