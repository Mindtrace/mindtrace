"""Integration tests for thread safety with Minio backend."""

import tempfile
import uuid
from pathlib import Path
from typing import Generator

import pytest
from minio import Minio
from minio.error import S3Error

from mindtrace.core import Config
from mindtrace.registry import MinioRegistryBackend, Registry


@pytest.fixture
def minio_client():
    """Create a MinIO client for testing."""
    config = Config()
    client = Minio(
        endpoint=config["MINDTRACE_MINIO_ENDPOINT"],
        access_key=config["MINDTRACE_MINIO_ACCESS_KEY"],
        secret_key=config["MINDTRACE_MINIO_SECRET_KEY"],
        secure=False,
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
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def registry(temp_dir, test_bucket):
    """Create a Registry instance with Minio backend."""
    backend = MinioRegistryBackend(
        uri=str(temp_dir),
        endpoint="localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket=test_bucket,
        secure=False,
    )
    return Registry(backend=backend)


'''
def test_concurrent_save_and_load(registry):
    """Test concurrent save and load operations with Minio backend."""
    def save_operation(i: int) -> None:
        model_data = {
            "weights": [0.1 * i, 0.2 * i],
            "metadata": {"accuracy": 0.8 + 0.01 * i}
        }
        registry.save(f"model:{i}", model_data)
        return i

    def load_operation(i: int) -> Dict[str, Any]:
        return registry.load(f"model:{i}")

    # First save multiple models concurrently
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(save_operation, i) for i in range(5)]
        save_results = [f.result() for f in as_completed(futures)]

    # Then load them concurrently
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(load_operation, i) for i in range(5)]
        load_results = [f.result() for f in as_completed(futures)]

    # Verify results
    assert len(save_results) == 5
    assert len(load_results) == 5
    for i, result in enumerate(load_results):
        assert result["weights"] == [0.1 * i, 0.2 * i]
        assert result["metadata"]["accuracy"] == 0.8 + 0.01 * i


def test_concurrent_versioning(registry):
    """Test concurrent versioning operations with Minio backend."""
    def version_operation(i: int) -> None:
        # Save multiple versions of the same model
        for j in range(3):
            model_data = {
                "weights": [0.1 * i, 0.2 * i],
                "metadata": {"version": j, "accuracy": 0.8 + 0.01 * i}
            }
            registry.save(f"model:{i}", model_data)

    # Create multiple threads to save different versions
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(version_operation, i) for i in range(3)]
        [f.result() for f in as_completed(futures)]

    # Verify all versions were created
    for i in range(3):
        versions = registry.list_versions(f"model:{i}")
        assert len(versions) == 3
        # Verify each version
        for version in versions:
            model_data = registry.load(f"model:{i}", version=version)
            assert "weights" in model_data
            assert "metadata" in model_data
            assert "version" in model_data["metadata"]


def test_concurrent_metadata_updates(registry):
    """Test concurrent metadata updates with Minio backend."""
    # First save some models
    for i in range(3):
        registry.save(f"model:{i}", {"weights": [i], "metadata": {"accuracy": 0.8}})

    def update_metadata(i: int) -> None:
        model_data = registry.load(f"model:{i}")
        model_data["metadata"]["last_updated"] = time.time()
        model_data["metadata"]["update_count"] = model_data["metadata"].get("update_count", 0) + 1
        registry.save(f"model:{i}", model_data)

    # Update metadata concurrently
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(update_metadata, i) for i in range(3)]
        [f.result() for f in as_completed(futures)]

    # Verify all updates were successful
    for i in range(3):
        model_data = registry.load(f"model:{i}")
        assert "last_updated" in model_data["metadata"]
        assert model_data["metadata"]["update_count"] == 1


def test_concurrent_mixed_operations(registry):
    """Test mixed concurrent operations with Minio backend."""
    def mixed_operation(i: int) -> None:
        try:
            if i % 3 == 0:
                # Save new model
                registry.save(f"model:{i}", {"weights": [i], "metadata": {"accuracy": 0.8}})
            elif i % 3 == 1:
                # Load and update existing model
                try:
                    if registry.has_object(f"model:{i-1}"):
                        model_data = registry.load(f"model:{i-1}")
                        model_data["metadata"]["updated"] = True
                        registry.save(f"model:{i-1}", model_data)
                except ValueError:
                    # Model might not exist yet, which is expected in concurrent operations
                    pass
            else:
                # Delete model
                try:
                    if registry.has_object(f"model:{i-2}"):
                        registry.delete(f"model:{i-2}")
                except ValueError:
                    # Model might not exist yet, which is expected in concurrent operations
                    pass
        except Exception as e:
            # Log any unexpected errors
            print(f"Error in operation {i}: {str(e)}")
            raise

    # Perform mixed operations concurrently
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(mixed_operation, i) for i in range(5)]
        [f.result() for f in as_completed(futures)]

    # Verify final state
    # Get all objects in the registry
    objects = registry.list_objects()
    
    # Verify that all existing objects have valid data
    for obj_name in objects:
        assert registry.has_object(obj_name), f"Object {obj_name} should exist"
        model_data = registry.load(obj_name)
        assert "weights" in model_data, f"Object {obj_name} should have weights"
        assert "metadata" in model_data, f"Object {obj_name} should have metadata"
        
        # If the object was updated, verify the update flag
        if "updated" in model_data["metadata"]:
            assert model_data["metadata"]["updated"] is True, f"Object {obj_name} should have updated=True if present"

    # Verify that no objects have invalid states
    for i in range(5):
        if registry.has_object(f"model:{i}"):
            model_data = registry.load(f"model:{i}")
            # Verify data consistency
            assert isinstance(model_data, dict), f"Model {i} should be a dictionary"
            assert "weights" in model_data, f"Model {i} should have weights"
            assert "metadata" in model_data, f"Model {i} should have metadata"
            assert isinstance(model_data["weights"], list), f"Model {i} weights should be a list"
            assert isinstance(model_data["metadata"], dict), f"Model {i} metadata should be a dictionary"


def test_concurrent_dict_interface(registry):
    """Test concurrent dictionary interface operations with Minio backend."""
    def dict_operation(i: int) -> None:
        # Save using dictionary syntax
        registry[f"config:{i}"] = {"param1": i, "param2": i * 2}
        # Load using dictionary syntax
        config = registry[f"config:{i}"]
        assert config["param1"] == i
        assert config["param2"] == i * 2

    # Perform dictionary operations concurrently
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(dict_operation, i) for i in range(3)]
        [f.result() for f in as_completed(futures)]

    # Verify all operations completed successfully
    for i in range(3):
        assert f"config:{i}" in registry
        config = registry[f"config:{i}"]
        assert config["param1"] == i
        assert config["param2"] == i * 2


def test_concurrent_materializer_registration(registry):
    """Test concurrent materializer registration with Minio backend."""
    def register_materializer(i: int) -> None:
        registry.register_materializer(f"test:class:{i}", f"test:materializer:{i}")

    # Register materializers concurrently
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(register_materializer, i) for i in range(3)]
        [f.result() for f in as_completed(futures)]

    # Verify all materializers were registered
    materializers = registry.registered_materializers()
    for i in range(3):
        assert f"test:class:{i}" in materializers
        assert materializers[f"test:class:{i}"] == f"test:materializer:{i}"


def test_concurrent_info_operations(registry):
    """Test concurrent info operations with Minio backend."""
    # First save some models
    for i in range(3):
        registry.save(f"model:{i}", {"weights": [i], "metadata": {"accuracy": 0.8}})

    def info_operation(i: int) -> Dict[str, Any]:
        return registry.info(f"model:{i}")

    # Get info concurrently
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(info_operation, i) for i in range(3)]
        results = [f.result() for f in as_completed(futures)]

    # Verify all info operations completed successfully
    assert len(results) == 3
    for result in results:
        assert isinstance(result, dict)
        latest_version = max(result.keys())
        version_info = result[latest_version]
        assert "class" in version_info
        assert "materializer" in version_info
        assert "metadata" in version_info
'''
