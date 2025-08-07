import os
from pathlib import Path
import shutil
import tempfile
from typing import Generator
import uuid

import pytest
from minio import Minio

from mindtrace.core import Config
from mindtrace.registry import Registry, MinioRegistryBackend


@pytest.fixture(scope="session")
def minio_client():
    """Create a MinIO client for testing."""
    endpoint = os.environ.get("MINDTRACE_MINIO_ENDPOINT", "localhost:9000")
    access_key = os.environ.get("MINDTRACE_MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.environ.get("MINDTRACE_MINIO_SECRET_KEY", "minioadmin")
    secure = os.environ.get("MINIO_SECURE", "0") == "1"
    client = Minio(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
    )
    yield client 


@pytest.fixture
def test_bucket(minio_client) -> Generator[str, None, None]:
    """Create a temporary bucket for testing."""
    bucket_name = f"test-bucket-{uuid.uuid4()}"
    minio_client.make_bucket(bucket_name)
    yield bucket_name
    # Cleanup
    try:
        for obj in minio_client.list_objects(bucket_name, recursive=True):
            minio_client.remove_object(bucket_name, obj.object_name)
        minio_client.remove_bucket(bucket_name)
    except S3Error:
        pass


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    temp_dir = Path(Config()["MINDTRACE_TEMP_DIR"]).expanduser() / f"test_dir_{uuid.uuid4()}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def backend(temp_dir, test_bucket):
    """Create a MinioRegistryBackend instance with a test bucket."""
    return MinioRegistryBackend(
        uri=str(temp_dir),
        endpoint="localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket=test_bucket,
        secure=False,
    )

@pytest.fixture
def minio_registry(backend):
    return Registry(backend=backend)


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
