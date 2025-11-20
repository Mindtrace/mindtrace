"""Pytest configuration for GCP registry backend integration tests."""

import os
import tempfile
import uuid
from pathlib import Path
from typing import Generator

import pytest
from google.cloud import storage
from google.cloud.exceptions import NotFound

from mindtrace.core import CoreConfig
from mindtrace.registry import GCPRegistryBackend


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

    client = storage.Client(project=project_id)
    yield client


@pytest.fixture
def gcp_test_bucket(gcs_client) -> Generator[str, None, None]:
    """Create a temporary GCP bucket for testing."""
    bucket_name = f"mindtrace-test-{uuid.uuid4()}"

    try:
        # Create bucket
        bucket = gcs_client.bucket(bucket_name)
        bucket.create()
        yield bucket_name
    except Exception as e:
        pytest.skip(f"GCP bucket creation failed: {e}")

    # Cleanup - delete all objects first, then the bucket
    try:
        for blob in bucket.list_blobs():
            blob.delete()
        bucket.delete()
    except NotFound:
        pass


@pytest.fixture
def gcp_temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for GCP testing."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    import shutil

    shutil.rmtree(temp_dir)


@pytest.fixture
def gcp_backend(gcp_temp_dir, gcp_test_bucket):
    """Create a GCPRegistryBackend instance with a test bucket."""
    config = CoreConfig()
    project_id = os.environ.get("GCP_PROJECT_ID", config["MINDTRACE_GCP"]["GCP_PROJECT_ID"])
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"])

    try:
        return GCPRegistryBackend(
            uri=f"gs://{gcp_test_bucket}",
            project_id=project_id,
            bucket_name=gcp_test_bucket,
            credentials_path=credentials_path,
        )
    except Exception as e:
        pytest.skip(f"GCP backend creation failed: {e}")
