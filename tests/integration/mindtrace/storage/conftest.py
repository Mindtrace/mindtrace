"""Pytest configuration for storage integration tests.

GCS fixtures for testing GCSStorageHandler.
Config resolution order: env vars → config.ini → skip.
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
# Shared Config
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def core_config():
    """Session-wide CoreConfig (env vars → config.ini)."""
    return CoreConfig()


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
    blocks probing the GCE metadata server and bucket.create() burns
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


@pytest.fixture
def gcp_test_bucket(gcs_client) -> Generator[str, None, None]:
    """Create a temporary GCP bucket for testing, tear it down after."""
    from google.cloud.exceptions import NotFound

    bucket_name = f"mindtrace-test-{uuid.uuid4().hex[:8]}"
    bucket = gcs_client.bucket(bucket_name)
    try:
        bucket.create()
    except Exception as e:
        pytest.skip(f"GCP bucket creation failed: {e}")

    yield bucket_name

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
