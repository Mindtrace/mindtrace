"""Pytest configuration for GCP integration tests."""

import os
import tempfile
import uuid
from pathlib import Path
from typing import Generator

import pytest
from google.cloud import storage
from google.cloud.exceptions import NotFound

from mindtrace.core import CoreConfig
from mindtrace.registry import GCPRegistryBackend, Registry


@pytest.fixture(scope="session")
def gcs_client():
    """Create a GCS client for testing."""
    from mindtrace.core import CoreConfig
    
    config = CoreConfig()
    project_id = os.environ.get("GCP_PROJECT_ID", config["MINDTRACE_GCP"]["GCP_PROJECT_ID"])
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"])
    
    client = storage.Client(project=project_id)
    yield client


@pytest.fixture
def test_bucket(gcs_client) -> Generator[str, None, None]:
    """Create a temporary bucket for testing."""
    bucket_name = f"mindtrace-test-{uuid.uuid4()}"
    
    # Create bucket
    bucket = gcs_client.bucket(bucket_name)
    bucket.create()
    
    yield bucket_name
    
    # Cleanup - delete all objects first, then the bucket
    try:
        for blob in bucket.list_blobs():
            blob.delete()
        bucket.delete()
    except NotFound:
        pass


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    import shutil
    shutil.rmtree(temp_dir)


@pytest.fixture
def backend(temp_dir, test_bucket):
    """Create a GCPRegistryBackend instance with a test bucket."""
    from mindtrace.core import CoreConfig
    
    config = CoreConfig()
    project_id = os.environ.get("GCP_PROJECT_ID", config["MINDTRACE_GCP"]["GCP_PROJECT_ID"])
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"])
    
    return GCPRegistryBackend(
        uri=f"gs://{test_bucket}",
        project_id=project_id,
        bucket_name=test_bucket,
        credentials_path=credentials_path,
    )


@pytest.fixture
def gcp_registry(backend):
    """Create a Registry instance with GCP backend."""
    return Registry(backend=backend)


@pytest.fixture
def sample_object_dir(temp_dir):
    """Create sample object directory for testing."""
    # Create test files
    file1 = temp_dir / "file1.txt"
    file1.write_text("test content 1")
    
    file2 = temp_dir / "file2.txt"
    file2.write_text("test content 2")
    
    # Create a subdirectory
    subdir = temp_dir / "subdir"
    subdir.mkdir()
    file3 = subdir / "file3.txt"
    file3.write_text("test content 3")
    
    return temp_dir


@pytest.fixture
def sample_metadata():
    """Create sample metadata for testing."""
    return {
        "name": "test:object",
        "version": "1.0.0",
        "description": "A test object",
        "created_at": "2023-01-01T00:00:00Z",
        "tags": ["test", "integration"],
    }
