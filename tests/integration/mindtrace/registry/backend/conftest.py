"""Pytest configuration for registry backend integration tests.

GCP fixtures (gcs_client, gcp_test_bucket, gcp_project_id, gcp_credentials_path, gcp_test_prefix)
are inherited from tests/integration/mindtrace/registry/conftest.py
"""

import shutil
import tempfile
from pathlib import Path
from typing import Generator

import pytest

from mindtrace.registry import GCPRegistryBackend

# ─────────────────────────────────────────────────────────────────────────────
# GCP Backend Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def gcp_backend(
    gcp_test_bucket, gcp_test_prefix, gcp_project_id, gcp_credentials_path, gcs_client
) -> Generator[GCPRegistryBackend, None, None]:
    """Create a GCPRegistryBackend instance with test isolation via prefix."""
    try:
        backend = GCPRegistryBackend(
            uri=f"gs://{gcp_test_bucket}/{gcp_test_prefix}",
            project_id=gcp_project_id,
            bucket_name=gcp_test_bucket,
            credentials_path=gcp_credentials_path,
            prefix=gcp_test_prefix,
        )
        yield backend
    except Exception as e:
        pytest.skip(f"GCP backend creation failed: {e}")

    # Cleanup: delete all objects with our test prefix
    try:
        bucket = gcs_client.bucket(gcp_test_bucket)
        blobs = list(bucket.list_blobs(prefix=gcp_test_prefix))
        for blob in blobs:
            blob.delete()
    except Exception:
        pass  # Best effort cleanup


@pytest.fixture
def gcp_temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for GCP testing."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)
