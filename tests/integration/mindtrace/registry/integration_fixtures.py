"""Shared integration fixtures for registry, datalake, and other tests (S3/MinIO, GCP).

Loaded from ``tests/conftest.py`` via ``pytest_plugins`` (pytest 8+ disallows
``pytest_plugins`` in nested conftest files).

Contains fixtures for MinIO and GCP backends.
Config resolution order: env vars (only if set in the shell/CI) → config.ini → skip.

Note: ``scripts/docker_up.sh`` intentionally does not set GCP env vars; sourcing it via
``scripts/run_tests.sh`` must not override bucket or project from ``config.ini``.
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
# Shared Config
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def core_config():
    """Session-wide CoreConfig (env vars → config.ini)."""
    return CoreConfig()


# ─────────────────────────────────────────────────────────────────────────────
# S3 / MinIO Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def s3_config(core_config):
    """Resolve S3/MinIO config: env vars → config.ini → skip."""
    minio_cfg = core_config.get("MINDTRACE_MINIO", {})

    endpoint = minio_cfg.get("MINIO_ENDPOINT")
    access_key = minio_cfg.get("MINIO_ACCESS_KEY")
    secret_key = core_config.get_secret("MINDTRACE_MINIO", "MINIO_SECRET_KEY")

    if not all([endpoint, access_key, secret_key]):
        pytest.skip("S3 (MinIO) not configured (set MINDTRACE_MINIO__* env vars or config.ini)")

    return {
        "endpoint": endpoint,
        "access_key": access_key,
        "secret_key": secret_key,
        "secure": os.environ.get("MINIO_SECURE", "0") == "1",
    }


@pytest.fixture(scope="session")
def s3_client(s3_config):
    """Create a MinIO client for S3 testing."""
    try:
        client = Minio(
            endpoint=s3_config["endpoint"],
            access_key=s3_config["access_key"],
            secret_key=s3_config["secret_key"],
            secure=s3_config["secure"],
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
def s3_temp_dir(core_config) -> Generator[Path, None, None]:
    """Create a temporary directory for S3 testing."""
    temp_dir = Path(core_config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]) / f"test_dir_{uuid.uuid4()}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def s3_backend(s3_temp_dir, s3_test_bucket, s3_config) -> Generator[S3RegistryBackend, None, None]:
    """Create an S3RegistryBackend instance with a test bucket."""
    try:
        backend = S3RegistryBackend(
            uri=str(s3_temp_dir),
            endpoint=s3_config["endpoint"],
            access_key=s3_config["access_key"],
            secret_key=s3_config["secret_key"],
            bucket=s3_test_bucket,
            secure=s3_config["secure"],
        )
        yield backend
    except Exception as e:
        pytest.skip(f"S3 backend creation failed: {e}")


@pytest.fixture
def s3_registry(s3_backend):
    """Create a Registry with S3 backend."""
    return Registry(backend=s3_backend)


@pytest.fixture
def minio_registry(s3_registry):
    """Alias for s3_registry (backwards compatibility)."""
    return s3_registry


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
def gcp_project_id(core_config):
    """Get GCP project ID: env vars → config.ini → skip."""
    project_id = core_config.get("MINDTRACE_GCP", {}).get("GCP_PROJECT_ID")
    if not project_id:
        pytest.skip("GCP_PROJECT_ID not configured (set MINDTRACE_GCP__GCP_PROJECT_ID or config.ini)")
    return project_id


@pytest.fixture(scope="session")
def gcp_credentials_path(core_config):
    """Get GCP credentials path: env vars → config.ini → None (ADC fallback).

    If GCP_CREDENTIALS_PATH is configured but the file is missing, skip
    immediately rather than falling back to ADC — otherwise google-auth
    blocks probing the GCE metadata server and bucket operations burn
    several seconds on retries before the skip fires.
    """
    credentials_path = core_config.get("MINDTRACE_GCP", {}).get("GCP_CREDENTIALS_PATH")
    if credentials_path:
        credentials_path = os.path.expanduser(credentials_path)
        if not os.path.exists(credentials_path):
            pytest.skip(f"GCP credentials file not found: {credentials_path}")
    return credentials_path


@pytest.fixture(scope="session")
def gcs_client(gcp_project_id, gcp_credentials_path):
    """Create a GCS client for testing.

    Matches production auth order: service account file first, ADC fallback.
    """
    try:
        from google.cloud import storage

        # 1. Try service account file if available
        if gcp_credentials_path:
            try:
                from google.oauth2 import service_account

                credentials = service_account.Credentials.from_service_account_file(gcp_credentials_path)
                client = storage.Client(project=gcp_project_id, credentials=credentials)
                yield client
                return
            except Exception:
                pass

        # 2. Fall back to ADC (gcloud auth application-default login)
        try:
            client = storage.Client(project=gcp_project_id)
            yield client
            return
        except Exception:
            pass

        pytest.skip("GCS auth failed: no valid service account file and no ADC configured")
    except ImportError:
        pytest.skip("google-cloud-storage not installed")
    except Exception as e:
        pytest.skip(f"GCS client creation failed: {e}")


@pytest.fixture(scope="session")
def gcp_test_bucket_name(core_config):
    """Get registry test bucket: env vars → config.ini → skip.

    Prefer ``MINDTRACE_GCP_REGISTRY.GCP_BUCKET_NAME`` (registry-specific), then fall back
    to ``MINDTRACE_GCP.GCP_BUCKET_NAME`` when the registry section omits a bucket so local
    setups with a single shared bucket still work.
    """
    bucket_name = core_config.get("MINDTRACE_GCP_REGISTRY", {}).get("GCP_BUCKET_NAME") or core_config.get(
        "MINDTRACE_GCP", {}
    ).get("GCP_BUCKET_NAME")
    if not bucket_name:
        pytest.skip(
            "GCP registry test bucket not configured "
            "(set MINDTRACE_GCP_REGISTRY__GCP_BUCKET_NAME, MINDTRACE_GCP__GCP_BUCKET_NAME, or config.ini)"
        )
    return bucket_name


@pytest.fixture
def gcp_test_bucket(gcs_client, gcp_test_bucket_name) -> Generator[str, None, None]:
    """Provide a GCP bucket for registry testing.

    Uses existing bucket - verifies it exists.
    Each test gets a unique prefix for isolation.
    Handles 403 (SA lacks project-level permission to check existence).
    """
    try:
        bucket = gcs_client.bucket(gcp_test_bucket_name)
        if not bucket.exists():
            pytest.skip(f"GCP test bucket '{gcp_test_bucket_name}' does not exist")
    except Exception as e:
        pytest.skip(f"GCP test bucket '{gcp_test_bucket_name}' not accessible: {e}")
    yield gcp_test_bucket_name


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
