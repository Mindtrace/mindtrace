"""Pytest configuration for registry integration tests.

Contains fixtures for MinIO and GCP backends.
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


# ─────────────────────────────────────────────────────────────────────────────
# GCP / GCS Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def gcp_project_id():
    """Get GCP project ID from environment or config."""
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        try:
            config = CoreConfig()
            project_id = config["MINDTRACE_GCP"]["GCP_PROJECT_ID"]
        except (KeyError, TypeError):
            pass
    if not project_id:
        pytest.skip("GCP_PROJECT_ID not set")
    return project_id


@pytest.fixture(scope="session")
def gcp_credentials_path():
    """Get GCP credentials path from environment or config."""
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path:
        try:
            config = CoreConfig()
            credentials_path = config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"]
        except (KeyError, TypeError):
            pass
    if credentials_path:
        credentials_path = os.path.expanduser(credentials_path)
    if not credentials_path:
        pytest.skip("GOOGLE_APPLICATION_CREDENTIALS not set")
    if not os.path.exists(credentials_path):
        pytest.skip(f"GCP credentials file not found: {credentials_path}")
    return credentials_path


@pytest.fixture(scope="session")
def gcs_client(gcp_project_id, gcp_credentials_path):
    """Create a GCS client for testing."""
    try:
        from google.cloud import storage

        client = storage.Client(project=gcp_project_id)
        yield client
    except ImportError:
        pytest.skip("google-cloud-storage not installed")
    except Exception as e:
        pytest.skip(f"GCS client creation failed: {e}")


@pytest.fixture(scope="session")
def gcp_test_bucket_name():
    """Get test bucket name from environment or config.

    Set GCP_TEST_BUCKET to use an existing bucket (recommended).
    If not set, tests will attempt to create a temporary bucket.
    """
    bucket_name = os.environ.get("GCP_TEST_BUCKET")
    if not bucket_name:
        try:
            config = CoreConfig()
            bucket_name = config.get("MINDTRACE_GCP", {}).get("GCP_TEST_BUCKET")
        except (KeyError, TypeError):
            pass
    return bucket_name


@pytest.fixture
def gcp_test_bucket(gcs_client, gcp_test_bucket_name) -> Generator[str, None, None]:
    """Provide a GCP bucket for testing.

    Uses GCP_TEST_BUCKET env var if set, otherwise creates a temporary bucket.
    When using an existing bucket, each test gets a unique prefix for isolation.
    """
    from google.cloud.exceptions import NotFound

    if gcp_test_bucket_name:
        # Use existing bucket - verify it exists
        bucket = gcs_client.bucket(gcp_test_bucket_name)
        if not bucket.exists():
            pytest.skip(f"GCP_TEST_BUCKET '{gcp_test_bucket_name}' does not exist")
        yield gcp_test_bucket_name
        # Don't delete existing bucket - cleanup handled by test prefix
    else:
        # Create a temporary bucket
        bucket_name = f"mindtrace-test-{uuid.uuid4().hex[:8]}"
        try:
            bucket = gcs_client.bucket(bucket_name)
            bucket.create()
            yield bucket_name
        except Exception as e:
            pytest.skip(f"GCP bucket creation failed: {e}")

        # Cleanup - delete all objects then bucket
        try:
            for blob in bucket.list_blobs():
                blob.delete()
            bucket.delete()
        except NotFound:
            pass


@pytest.fixture
def gcp_test_prefix():
    """Generate unique prefix for test isolation within a shared bucket."""
    return f"test-{uuid.uuid4().hex[:8]}"


# ─────────────────────────────────────────────────────────────────────────────
# Common Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)
