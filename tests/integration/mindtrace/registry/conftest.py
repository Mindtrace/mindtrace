"""Fixtures for S3 registry backend integration tests.

Uses MinIO as the S3-compatible backend for testing.
"""

import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Generator
from urllib.error import URLError

import pytest
from minio import Minio
from minio.error import S3Error

from mindtrace.core import CoreConfig
from mindtrace.registry import Registry, S3RegistryBackend

# ─────────────────────────────────────────────────────────────────────────────
# S3 Configuration (uses MinIO as backend)
# ─────────────────────────────────────────────────────────────────────────────


def get_s3_config():
    """Get S3 configuration from environment or config."""
    # Try environment variables first, then fall back to CoreConfig
    endpoint = os.environ.get("MINDTRACE_MINIO__MINIO_ENDPOINT")
    access_key = os.environ.get("MINDTRACE_MINIO__MINIO_ACCESS_KEY")
    secret_key = os.environ.get("MINDTRACE_MINIO__MINIO_SECRET_KEY")

    if not endpoint or not access_key or not secret_key:
        try:
            config = CoreConfig()
            minio_config = config.get("MINDTRACE_MINIO", {})
            endpoint = endpoint or minio_config.get("MINIO_ENDPOINT", "localhost:9100")
            access_key = access_key or minio_config.get("MINIO_ACCESS_KEY", "minioadmin")
            # Use get_secret() for secret key to get unmasked value
            secret_key = secret_key or config.get_secret("MINDTRACE_MINIO", "MINIO_SECRET_KEY") or "minioadmin"
        except Exception:
            # Fall back to defaults if CoreConfig fails
            endpoint = endpoint or "localhost:9100"
            access_key = access_key or "minioadmin"
            secret_key = secret_key or "minioadmin"

    return {
        "endpoint": endpoint,
        "access_key": access_key,
        "secret_key": secret_key,
        "secure": os.environ.get("MINIO_SECURE", "0") == "1",
    }


# ─────────────────────────────────────────────────────────────────────────────
# S3 Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def s3_client():
    """Create a MinIO client for S3 testing."""
    config = get_s3_config()
    try:
        client = Minio(
            endpoint=config["endpoint"],
            access_key=config["access_key"],
            secret_key=config["secret_key"],
            secure=config["secure"],
        )
        # Test connection by listing buckets
        client.list_buckets()
        yield client
    except (URLError, S3Error, Exception) as e:
        pytest.skip(f"S3 (MinIO) not available: {e}")


@pytest.fixture
def s3_test_bucket(s3_client) -> Generator[str, None, None]:
    """Create a temporary S3 bucket for testing."""
    bucket_name = f"test-bucket-{uuid.uuid4().hex[:8]}"
    try:
        s3_client.make_bucket(bucket_name)
    except S3Error as e:
        pytest.skip(f"Failed to create S3 bucket: {e}")
    yield bucket_name
    # Cleanup
    try:
        for obj in s3_client.list_objects(bucket_name, recursive=True):
            s3_client.remove_object(bucket_name, obj.object_name)
        s3_client.remove_bucket(bucket_name)
    except S3Error:
        pass


@pytest.fixture
def s3_test_prefix():
    """Generate unique prefix for test isolation within a shared bucket."""
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def s3_temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for S3 testing."""
    temp_dir = Path(CoreConfig()["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]) / f"test_dir_{uuid.uuid4()}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def s3_backend(s3_temp_dir, s3_test_bucket) -> Generator[S3RegistryBackend, None, None]:
    """Create an S3RegistryBackend instance with a test bucket."""
    config = get_s3_config()
    try:
        backend = S3RegistryBackend(
            uri=str(s3_temp_dir),
            endpoint=config["endpoint"],
            access_key=config["access_key"],
            secret_key=config["secret_key"],
            bucket=s3_test_bucket,
            secure=config["secure"],
        )
        yield backend
    except Exception as e:
        pytest.skip(f"S3 backend creation failed: {e}")


@pytest.fixture
def s3_registry(s3_backend):
    """Create a Registry with S3 backend."""
    return Registry(backend=s3_backend)


@pytest.fixture
def sample_object_dir():
    """Create a sample object directory with some files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        obj_dir = Path(temp_dir) / "sample:object"
        obj_dir.mkdir()
        (obj_dir / "file1.txt").write_text("test content 1")
        (obj_dir / "file2.txt").write_text("test content 2")
        yield str(obj_dir)


@pytest.fixture
def sample_metadata():
    """Sample metadata for testing."""
    return {
        "name": "test:object",
        "version": "1.0.0",
        "description": "Test object",
        "created_at": "2024-01-01T00:00:00Z",
    }
