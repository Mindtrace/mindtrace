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

    Returns None if no credentials file is configured, allowing
    gcs_client to fall back to ADC (gcloud login).
    """
    credentials_path = core_config.get("MINDTRACE_GCP", {}).get("GCP_CREDENTIALS_PATH")
    if credentials_path:
        credentials_path = os.path.expanduser(credentials_path)
        if not os.path.exists(credentials_path):
            return None
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
    """Get storage test bucket: env vars → config.ini → skip.

    Reads from MINDTRACE_GCP.GCP_BUCKET_NAME (storage-level bucket,
    separate from the registry bucket in MINDTRACE_GCP_REGISTRY).
    """
    bucket_name = core_config.get("MINDTRACE_GCP", {}).get("GCP_BUCKET_NAME")
    if not bucket_name:
        pytest.skip("GCP storage test bucket not configured (set MINDTRACE_GCP.GCP_BUCKET_NAME or config.ini)")
    return bucket_name


@pytest.fixture
def gcp_test_bucket(gcs_client, gcp_test_bucket_name) -> Generator[str, None, None]:
    """Provide a GCP bucket for storage testing.

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
