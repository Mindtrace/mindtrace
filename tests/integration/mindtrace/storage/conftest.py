"""Pytest configuration for storage integration tests.

GCS fixtures for testing GCSStorageHandler.
"""

import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Generator

import pytest

from mindtrace.core import CoreConfig

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
    """Get GCP credentials path from environment or config.

    Returns None if no credentials file is configured, allowing
    gcs_client to fall back to ADC (gcloud login).
    """
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path:
        try:
            config = CoreConfig()
            credentials_path = config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"]
        except (KeyError, TypeError):
            pass
    if credentials_path:
        credentials_path = os.path.expanduser(credentials_path)
        if not os.path.exists(credentials_path):
            pytest.skip(f"GCP credentials file not found: {credentials_path}")
    return credentials_path


@pytest.fixture(scope="session")
def gcs_client(gcp_project_id, gcp_credentials_path):
    """Create a GCS client for testing.

    Tries ADC (gcloud login) first. If that fails, falls back to
    service account file if gcp_credentials_path is available.
    """
    try:
        from google.cloud import storage

        # 1. Try ADC (gcloud login)
        try:
            client = storage.Client(project=gcp_project_id)
            list(client.list_buckets(max_results=1))  # force API call to verify credentials
            yield client
            return
        except Exception:
            pass

        # 2. Fall back to service account file
        if gcp_credentials_path:
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_file(gcp_credentials_path)
            client = storage.Client(project=gcp_project_id, credentials=credentials)
            yield client
            return

        pytest.skip("GCS auth failed: no valid ADC and no service account file configured")
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
