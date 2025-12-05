"""Integration tests for GCP Registry Backend caching functionality."""

import os
import uuid
from pathlib import Path
from typing import Generator

import pytest
from google.cloud import storage
from google.cloud.exceptions import NotFound

from mindtrace.core import CoreConfig
from mindtrace.registry import GCPRegistryBackend, LocalRegistryBackend, Registry


@pytest.fixture(scope="session")
def gcs_client():
    """Create a GCS client for testing."""
    config = CoreConfig()
    project_id = os.environ.get("GCP_PROJECT_ID", config["MINDTRACE_GCP"]["GCP_PROJECT_ID"])
    credentials_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS", config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"]
    )
    if not credentials_path:
        pytest.skip("No GCP credentials path provided")
    if not os.path.exists(credentials_path):
        pytest.skip(f"GCP credentials path does not exist: {credentials_path}")

    client = storage.Client(project=project_id)
    yield client


@pytest.fixture
def test_bucket(gcs_client) -> Generator[str, None, None]:
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
    except NotFound:
        pass


@pytest.fixture
def backend(test_bucket):
    """Create a GCPRegistryBackend instance with a test bucket."""
    config = CoreConfig()
    project_id = os.environ.get("GCP_PROJECT_ID", config["MINDTRACE_GCP"]["GCP_PROJECT_ID"])
    credentials_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS", config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"]
    )

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
def gcp_registry(backend):
    """Create a Registry instance with GCP backend."""
    return Registry(backend=backend, version_objects=True)


def test_gcp_backend_cache_initialization(gcp_registry, backend):
    """Test that Registry with GCP backend initializes cache correctly."""
    # Verify cache is initialized for GCP backend
    assert gcp_registry._cache is not None
    assert isinstance(gcp_registry._cache.backend, LocalRegistryBackend)

    # Verify cache directory is deterministic
    cache_dir1 = gcp_registry._cache.backend.uri
    assert cache_dir1.exists() or cache_dir1.parent.exists()

    # Create another registry with same backend URI - should use same cache
    registry2 = Registry(backend=backend, version_objects=True)
    cache_dir2 = registry2._cache.backend.uri
    assert cache_dir1 == cache_dir2, "Same backend URI should produce same cache directory"


def test_gcp_backend_cache_persistence(gcp_registry, backend):
    """Test that GCP backend cache persists across Registry instances."""
    # First registry instance - save data
    test_data = {"key": "persistence_test", "value": 456}
    gcp_registry.save("test:persist", test_data, version="1.0.0")

    # Load to populate cache
    loaded1 = gcp_registry.load("test:persist", version="1.0.0")
    assert loaded1 == test_data

    # Verify cache was populated
    assert gcp_registry._cache.has_object("test:persist", "1.0.0")
    cache_dir = gcp_registry._cache.backend.uri

    # Create second registry instance with same backend
    registry2 = Registry(backend=backend, version_objects=True)

    # Should use same cache directory
    assert registry2._cache.backend.uri == cache_dir

    # Load from second registry - should use cache if available
    loaded2 = registry2.load("test:persist", version="1.0.0")
    assert loaded2 == test_data

    # Verify cache is being used
    assert registry2._cache.has_object("test:persist", "1.0.0")


def test_gcp_backend_cache_hash_verification(gcp_registry):
    """Test that GCP backend cache properly verifies hashes."""
    import json

    # Save initial data
    test_data1 = {"key": "hash_test", "value": 789}
    gcp_registry.save("test:hash", test_data1, version="1.0.0")

    # Get hash from metadata
    metadata1 = gcp_registry.info("test:hash", version="1.0.0")
    hash1 = metadata1["hash"]
    assert hash1 is not None

    # Load to populate cache
    loaded1 = gcp_registry.load("test:hash", version="1.0.0", verify_hash=True)
    assert loaded1 == test_data1

    # Verify cache has correct hash
    cached_metadata = gcp_registry._cache.info("test:hash", version="1.0.0")
    assert cached_metadata["hash"] == hash1

    # Corrupt the cache by modifying the data directly
    # This simulates cache corruption or external modification
    cache_dir = gcp_registry._cache.backend._full_path(
        gcp_registry._cache.backend._object_key("test:hash", "1.0.0")
    )
    data_json_path = cache_dir / "data.json"
    assert data_json_path.exists(), "data.json should exist in cache"

    # Modify the cached data to have different content
    corrupted_data = {"key": "hash_test", "value": 999}
    with open(data_json_path, "w") as f:
        json.dump(corrupted_data, f)

    # Verify cache now has corrupted data
    cached_corrupted = gcp_registry._cache.load("test:hash", version="1.0.0", verify_hash=False)
    assert cached_corrupted == corrupted_data

    # Load with verify_hash=True should detect the hash mismatch
    # and download the correct version from remote, updating the cache
    loaded2 = gcp_registry.load("test:hash", version="1.0.0", verify_hash=True)
    assert loaded2 == test_data1, "Should load original data from remote after detecting hash mismatch"

    # Verify cache was updated with correct hash
    cached_metadata2 = gcp_registry._cache.info("test:hash", version="1.0.0")
    assert cached_metadata2["hash"] == hash1, "Cache should have correct hash after verification"
    
    # Verify cache now has correct data
    cached_correct = gcp_registry._cache.load("test:hash", version="1.0.0", verify_hash=False)
    assert cached_correct == test_data1, "Cache should have correct data after verification"

