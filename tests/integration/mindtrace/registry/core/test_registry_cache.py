"""Integration tests for Registry caching functionality.

GCP fixtures (gcs_client, gcp_test_bucket, gcp_project_id, gcp_credentials_path, gcp_test_prefix)
are inherited from tests/integration/mindtrace/registry/conftest.py
"""

import shutil
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from mindtrace.registry import GCPRegistryBackend, Registry

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def gcp_backend(gcp_test_bucket, gcp_test_prefix, gcp_project_id, gcp_credentials_path):
    """Create a GCPRegistryBackend instance with test isolation via prefix."""
    try:
        return GCPRegistryBackend(
            uri=f"gs://{gcp_test_bucket}/{gcp_test_prefix}",
            project_id=gcp_project_id,
            bucket_name=gcp_test_bucket,
            credentials_path=gcp_credentials_path,
            prefix=gcp_test_prefix,
        )
    except Exception as e:
        pytest.skip(f"GCP backend creation failed: {e}")


@pytest.fixture
def gcp_registry(gcp_backend, gcp_test_bucket, gcp_test_prefix, gcs_client):
    """Create a Registry instance with GCP backend and caching enabled.

    Note: lock_timeout is configured directly on the backend via __init__, not registry config.
    """
    registry = Registry(backend=gcp_backend, version_objects=True, use_cache=True)
    yield registry

    # Cleanup: delete all objects with our test prefix
    try:
        bucket = gcs_client.bucket(gcp_test_bucket)
        blobs = list(bucket.list_blobs(prefix=gcp_test_prefix))
        for blob in blobs:
            blob.delete()
    except Exception:
        pass  # Best effort cleanup


# ─────────────────────────────────────────────────────────────────────────────
# Cache Performance Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_cache_performance_with_large_dataset(gcp_registry):
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


# ─────────────────────────────────────────────────────────────────────────────
# Cache Hash Verification Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_cache_hash_verification_with_remote_backend(gcp_registry):
    """Integration test: Verify cache hash verification works with remote backend."""
    # Save test data
    test_data = {"key": "value", "number": 42}
    gcp_registry.save("test:data", test_data, version="1.0.0")

    # Load and verify hash is stored
    metadata = gcp_registry.info("test:data", version="1.0.0")
    assert "hash" in metadata

    # Load with hash verification (should succeed)
    loaded_data = gcp_registry.load("test:data", version="1.0.0", verify="full")
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


# ─────────────────────────────────────────────────────────────────────────────
# Cache Verification Flag Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_cache_load_with_verify_none(gcp_registry):
    """Integration test: Verify that loading with verify='none' uses cache even if hash doesn't match."""
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
    cached_data = gcp_registry._cache.load("test:cache:modified", version="1.0.0", verify="none")
    assert cached_data == modified_data, "Cache should have modified data"

    # Get the original hash from remote metadata
    remote_metadata = gcp_registry.info("test:cache:modified", version="1.0.0")
    original_hash = remote_metadata.get("hash")
    assert original_hash is not None, "Remote metadata should have a hash"

    # The hashes should be different (cache was modified)
    # Note: The cached hash might not be updated yet, but the data is different

    # Load with verify="none" - should use cache even though hash doesn't match
    loaded_without_verification = gcp_registry.load("test:cache:modified", version="1.0.0", verify="none")

    # Should get the modified cache version, not the original remote version
    assert loaded_without_verification == modified_data, "Should load modified cache version when verify='none'"

    # Load with verify="full" (default) - should download from remote and get original data
    loaded_with_verification = gcp_registry.load("test:cache:modified", version="1.0.0", verify="full")

    # Should get the original remote version (cache should be deleted and redownloaded)
    assert loaded_with_verification == original_data, "Should load original remote version when verify='full'"


def test_cache_load_verify_integrity(gcp_backend):
    """Integration test: Verify that verify='integrity' checks hash but NOT staleness.

    verify='integrity' behavior:
    - Checks that cached data matches the cache's own metadata hash
    - Does NOT compare cache hash with remote hash (no staleness check)
    - Faster than 'full' because it avoids remote metadata fetch for staleness
    """
    # Create a mutable registry for this test (allows overwriting)
    mutable_registry = Registry(backend=gcp_backend, version_objects=True, mutable=True, use_cache=True)

    # Save original data to registry
    original_data = {"key": "original_value", "number": 42}
    mutable_registry.save("test:cache:integrity", original_data, version="1.0.0")

    # Load to populate cache
    loaded_data = mutable_registry.load("test:cache:integrity", version="1.0.0")
    assert loaded_data == original_data

    # Verify cache was populated
    assert mutable_registry._cache.has_object("test:cache:integrity", "1.0.0")

    # Now update the remote data (simulating another client updating it)
    updated_data = {"key": "updated_value", "number": 999}
    mutable_registry._remote.save("test:cache:integrity", updated_data, version="1.0.0", on_conflict="overwrite")

    # verify="integrity" should NOT detect the remote update (no staleness check)
    # It only checks that cached data matches the cache's own hash
    loaded_with_integrity = mutable_registry.load("test:cache:integrity", version="1.0.0", verify="integrity")
    assert loaded_with_integrity == original_data, "verify='integrity' should use cache (no staleness check)"

    # verify="full" SHOULD detect the remote update and fetch new data
    loaded_with_full = mutable_registry.load("test:cache:integrity", version="1.0.0", verify="full")
    assert loaded_with_full == updated_data, "verify='full' should detect staleness and fetch updated data"


def test_cache_verify_levels_comparison(gcp_registry):
    """Integration test: Compare all three verification levels side-by-side.

    VerifyLevel semantics:
    - 'none': Trust cache completely, no verification
    - 'integrity': Verify cache data matches cache's hash (no remote check)
    - 'full': Verify integrity + check if cache is stale vs remote
    """
    import json

    # Save data to registry
    original_data = {"key": "test", "value": 1}
    gcp_registry.save("test:verify:levels", original_data, version="1.0.0")

    # Load to populate cache
    gcp_registry.load("test:verify:levels", version="1.0.0")
    assert gcp_registry._cache.has_object("test:verify:levels", "1.0.0")

    # Get cache directory path
    cache_dir = gcp_registry._cache.backend._full_path(
        gcp_registry._cache.backend._object_key("test:verify:levels", "1.0.0")
    )
    data_json_path = cache_dir / "data.json"

    # Corrupt the cache by modifying data (but not updating cache metadata hash)
    corrupted_data = {"key": "corrupted", "value": -1}
    with open(data_json_path, "w") as f:
        json.dump(corrupted_data, f)

    # verify="none": Returns corrupted data (no verification at all)
    result_none = gcp_registry.load("test:verify:levels", version="1.0.0", verify="none")
    assert result_none == corrupted_data, "verify='none' should return corrupted cache data"

    # verify="integrity": Should detect hash mismatch and re-fetch from remote
    # (cache data doesn't match cache's declared hash)
    result_integrity = gcp_registry.load("test:verify:levels", version="1.0.0", verify="integrity")
    assert result_integrity == original_data, "verify='integrity' should detect corruption and re-fetch"

    # verify="full": Also detects corruption (integrity check is included in full)
    result_full = gcp_registry.load("test:verify:levels", version="1.0.0", verify="full")
    assert result_full == original_data, "verify='full' should detect corruption and re-fetch"


def test_cache_load_verify_none_cache_first(gcp_registry):
    """Integration test: Verify that loading with verify='none' returns cache immediately if available, otherwise loads from remote."""
    # Save data to registry
    test_data = {"key": "test_value", "number": 123}
    gcp_registry.save("test:verify:cache", test_data, version="1.0.0")

    # Load to populate cache
    loaded_data = gcp_registry.load("test:verify:cache", version="1.0.0")
    assert loaded_data == test_data

    # Verify cache was populated
    assert gcp_registry._cache.has_object("test:verify:cache", "1.0.0")

    # Load with verify="none" - should return cache immediately without staleness check
    # This is a completely local operation when cache exists
    loaded_from_cache = gcp_registry.load("test:verify:cache", version="1.0.0", verify="none")
    assert loaded_from_cache == test_data, "Should load from cache when verify='none' and cache exists"

    # Test that verify="none" falls through to remote loading when cache doesn't exist
    # Delete from cache but keep in remote
    gcp_registry._cache.delete("test:verify:cache", "1.0.0")
    assert not gcp_registry._cache.has_object("test:verify:cache", "1.0.0")

    # Should fall through to remote loading when cache doesn't exist and verify="none"
    loaded_from_remote = gcp_registry.load("test:verify:cache", version="1.0.0", verify="none")
    assert loaded_from_remote == test_data, "Should load from remote when verify='none' and cache doesn't exist"

    # Verify cache was repopulated after loading from remote
    assert gcp_registry._cache.has_object("test:verify:cache", "1.0.0")

    # Test with verify="full" (default) - should work normally
    loaded_with_verify = gcp_registry.load("test:verify:cache", version="1.0.0", verify="full")
    assert loaded_with_verify == test_data, "Should load normally when verify='full'"
