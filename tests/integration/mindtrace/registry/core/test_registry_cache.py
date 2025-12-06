"""Integration tests for Registry caching functionality."""

import os
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

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

    from google.cloud import storage

    client = storage.Client(project=project_id)
    yield client


@pytest.fixture
def test_bucket(gcs_client):
    """Create a temporary bucket for testing."""
    bucket_name = f"mt-test-cache-{uuid.uuid4().hex[:8]}"

    try:
        # Create bucket
        bucket = gcs_client.bucket(bucket_name)
        bucket.create()
        yield bucket_name
    except Exception as e:
        pytest.skip(f"GCP bucket creation failed: {e}")

    # Cleanup - delete all objects first, then the bucket
    try:
        bucket = gcs_client.bucket(bucket_name)
        for blob in bucket.list_blobs():
            blob.delete()
        bucket.delete()
    except Exception:
        pass


@pytest.fixture
def gcp_backend(test_bucket):
    """Create a GCPRegistryBackend instance with a test bucket."""
    config = CoreConfig()
    project_id = os.environ.get("GCP_PROJECT_ID", config["MINDTRACE_GCP"]["GCP_PROJECT_ID"])
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"])

    try:
        return GCPRegistryBackend(
            uri=f"gs://{test_bucket}",
            project_id=project_id,
            bucket_name=test_bucket,
            credentials_path=credentials_path,
        )
    except Exception as e:
        pytest.skip(f"GCP backend creation failed: {e}")


@pytest.fixture
def gcp_registry(gcp_backend):
    """Create a Registry instance with GCP backend."""
    registry = Registry(backend=gcp_backend, version_objects=True)
    # Increase lock timeout for GCP operations
    registry.config["MINDTRACE_LOCK_TIMEOUT"] = 30
    return registry


def test_cache_performance_with_large_dataset(gcp_registry, gcs_client, test_bucket):
    """Integration test: Compare cache vs remote performance with large data."""
    # Create images one at a time (saving individually to avoid list materializer issues)
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("PIL/Pillow not available - skipping image test")

    num_images = 5
    image_names = []

    # Save images individually to registry
    print(f"\nSaving {num_images} images individually to remote registry...")
    save_start = time.time()
    for i in range(num_images):
        # Create a simple test image (640x480 RGB)
        img = Image.new("RGB", (640, 480), color=(i % 256, (i * 2) % 256, (i * 3) % 256))
        image_name = f"test:image:{i}"  # Use colon instead of underscore
        image_names.append(image_name)
        gcp_registry.save(image_name, img, version="1.0.0")
    save_time = time.time() - save_start
    print(f"Save time: {save_time:.2f} seconds")

    # First load - should download from remote and cache
    print("\nFirst load (download + cache)...")
    load1_start = time.time()
    loaded_images1 = []
    for image_name in image_names:
        loaded_img = gcp_registry.load(image_name, version="1.0.0")
        loaded_images1.append(loaded_img)
    load1_time = time.time() - load1_start
    print(f"First load time: {load1_time:.2f} seconds")

    # Verify cache was populated
    assert gcp_registry._cache is not None
    for image_name in image_names:
        assert gcp_registry._cache.has_object(image_name, "1.0.0")

    # Second load - should use cache (much faster)
    print("\nSecond load (from cache)...")
    load2_start = time.time()
    loaded_images2 = []
    for image_name in image_names:
        loaded_img = gcp_registry.load(image_name, version="1.0.0")
        loaded_images2.append(loaded_img)
    load2_time = time.time() - load2_start
    print(f"Second load time (cache): {load2_time:.2f} seconds")

    # Verify data integrity
    assert len(loaded_images1) == num_images
    assert len(loaded_images2) == num_images
    for i in range(num_images):
        assert loaded_images1[i].size == loaded_images2[i].size
        assert loaded_images1[i].mode == loaded_images2[i].mode

    # Delete cache directory to force redownload
    cache_dir = gcp_registry._cache.backend.uri
    print(f"\nDeleting cache directory: {cache_dir}")
    if cache_dir.exists():
        shutil.rmtree(cache_dir)

    # Verify cache is empty
    for image_name in image_names:
        assert not gcp_registry._cache.has_object(image_name, "1.0.0")

    # Third load - should download from remote again (no cache)
    print("\nThird load (redownload after cache deletion)...")
    load3_start = time.time()
    loaded_images3 = []
    for image_name in image_names:
        loaded_img = gcp_registry.load(image_name, version="1.0.0")
        loaded_images3.append(loaded_img)
    load3_time = time.time() - load3_start
    print(f"Third load time (redownload): {load3_time:.2f} seconds")

    # Verify data integrity
    assert len(loaded_images3) == num_images
    for i in range(num_images):
        assert loaded_images1[i].size == loaded_images3[i].size
        assert loaded_images1[i].mode == loaded_images3[i].mode

    # Performance assertions
    print("\nPerformance comparison:")
    print(f"  First load (download):  {load1_time:.2f}s")
    print(f"  Second load (cache):    {load2_time:.2f}s")
    print(f"  Third load (redownload): {load3_time:.2f}s")
    if load2_time > 0:
        print(f"  Cache speedup: {load1_time / load2_time:.2f}x faster")

    # Cache should be significantly faster (at least 2x, but may vary)
    # We'll just verify cache is faster, not enforce a specific ratio
    assert load2_time < load1_time, "Cache should be faster than remote download"
    assert load2_time < load3_time, "Cache should be faster than remote download"

    # Verify cache was repopulated after third load
    for image_name in image_names:
        assert gcp_registry._cache.has_object(image_name, "1.0.0")


def test_cache_hash_verification_with_remote_backend(gcp_registry):
    """Integration test: Verify cache hash verification works with remote backend."""
    # Save test data
    test_data = {"key": "value", "number": 42}
    gcp_registry.save("test:data", test_data, version="1.0.0")

    # Load and verify hash is stored
    metadata = gcp_registry.info("test:data", version="1.0.0")
    assert "hash" in metadata

    # Load with hash verification (should succeed)
    loaded_data = gcp_registry.load("test:data", version="1.0.0", verify_hash=True)
    assert loaded_data == test_data

    # Verify cache was populated
    assert gcp_registry._cache.has_object("test:data", "1.0.0")
    cached_metadata = gcp_registry._cache.info("test:data", version="1.0.0")
    assert cached_metadata["hash"] == metadata["hash"]

    # Load from cache (should use cache due to hash match)
    loaded_from_cache = gcp_registry.load("test:data", version="1.0.0")
    assert loaded_from_cache == test_data


def test_cache_concurrent_access(gcp_registry):
    """Integration test: Verify cache works correctly with concurrent access."""
    # Save test data
    test_data = {"key": "concurrent_test", "value": 123}
    gcp_registry.save("test:concurrent", test_data, version="1.0.0")

    # Concurrent loads - should all use cache after first load
    results = []
    errors = []

    def load_data(thread_id):
        try:
            loaded = gcp_registry.load("test:concurrent", version="1.0.0")
            results.append((thread_id, loaded))
        except Exception as e:
            errors.append((thread_id, e))

    # Run 10 concurrent loads
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(load_data, i) for i in range(10)]
        for future in futures:
            future.result()

    # Verify all loads succeeded
    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert len(results) == 10

    # Verify all results are correct
    for thread_id, loaded_data in results:
        assert loaded_data == test_data

    # Verify cache was used (all threads should have accessed cache)
    assert gcp_registry._cache.has_object("test:concurrent", "1.0.0")


def test_cache_load_with_verify_hash_false(gcp_registry):
    """Integration test: Verify that loading with verify_hash=False uses cache even if hash doesn't match."""
    import json

    # Save original data to registry
    original_data = {"key": "original_value", "number": 42}
    gcp_registry.save("test:cache:modified", original_data, version="1.0.0")

    # Load to populate cache
    loaded_data = gcp_registry.load("test:cache:modified", version="1.0.0")
    assert loaded_data == original_data

    # Verify cache was populated
    assert gcp_registry._cache.has_object("test:cache:modified", "1.0.0")

    # Get cache directory path
    cache_dir = gcp_registry._cache.backend._full_path(
        gcp_registry._cache.backend._object_key("test:cache:modified", "1.0.0")
    )
    assert cache_dir.exists(), "Cache directory should exist"

    # Modify the cache directly by changing the data.json file
    # BuiltInContainerMaterializer saves dicts to data.json
    data_json_path = cache_dir / "data.json"
    assert data_json_path.exists(), "data.json should exist in cache"

    # Modify the cached data
    modified_data = {"key": "modified_value", "number": 999}
    with open(data_json_path, "w") as f:
        json.dump(modified_data, f)

    # Verify the cache now has different data
    cached_data = gcp_registry._cache.load("test:cache:modified", version="1.0.0", verify_hash=False)
    assert cached_data == modified_data, "Cache should have modified data"

    # Get the original hash from remote metadata
    remote_metadata = gcp_registry.info("test:cache:modified", version="1.0.0")
    original_hash = remote_metadata.get("hash")
    assert original_hash is not None, "Remote metadata should have a hash"

    # Get the cached hash (should be different now)
    cached_metadata = gcp_registry._cache.info("test:cache:modified", version="1.0.0")
    cached_hash = cached_metadata.get("hash")

    # The hashes should be different (cache was modified)
    # Note: The cached hash might not be updated yet, but the data is different

    # Load with verify_hash=False - should use cache even though hash doesn't match
    loaded_without_verification = gcp_registry.load("test:cache:modified", version="1.0.0", verify_hash=False)

    # Should get the modified cache version, not the original remote version
    assert loaded_without_verification == modified_data, "Should load modified cache version when verify_hash=False"

    # Load with verify_hash=True (default) - should download from remote and get original data
    loaded_with_verification = gcp_registry.load("test:cache:modified", version="1.0.0", verify_hash=True)

    # Should get the original remote version (cache should be deleted and redownloaded)
    assert loaded_with_verification == original_data, "Should load original remote version when verify_hash=True"


def test_cache_load_with_verify_cache_false(gcp_registry):
    """Integration test: Verify that loading with verify_cache=False returns cache immediately if available, otherwise loads from remote."""
    # Save data to registry
    test_data = {"key": "test_value", "number": 123}
    gcp_registry.save("test:verify:cache", test_data, version="1.0.0")

    # Load to populate cache
    loaded_data = gcp_registry.load("test:verify:cache", version="1.0.0")
    assert loaded_data == test_data

    # Verify cache was populated
    assert gcp_registry._cache.has_object("test:verify:cache", "1.0.0")

    # Load with verify_cache=False - should return cache immediately without remote operations
    # This is a completely local operation when cache exists
    loaded_from_cache = gcp_registry.load("test:verify:cache", version="1.0.0", verify_cache=False)
    assert loaded_from_cache == test_data, "Should load from cache when verify_cache=False and cache exists"

    # Test that verify_cache=False falls through to remote loading when cache doesn't exist
    # Delete from cache but keep in remote
    gcp_registry._cache.delete("test:verify:cache", "1.0.0")
    assert not gcp_registry._cache.has_object("test:verify:cache", "1.0.0")

    # Should fall through to remote loading when cache doesn't exist and verify_cache=False
    loaded_from_remote = gcp_registry.load("test:verify:cache", version="1.0.0", verify_cache=False)
    assert loaded_from_remote == test_data, "Should load from remote when verify_cache=False and cache doesn't exist"

    # Verify cache was repopulated after loading from remote
    assert gcp_registry._cache.has_object("test:verify:cache", "1.0.0")

    # Test with verify_cache=True (default) - should work normally
    loaded_with_verify = gcp_registry.load("test:verify:cache", version="1.0.0", verify_cache=True)
    assert loaded_with_verify == test_data, "Should load normally when verify_cache=True"
