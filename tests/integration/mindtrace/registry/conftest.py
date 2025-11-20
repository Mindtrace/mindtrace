import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Generator

import pytest
from minio import Minio
from minio.error import S3Error

from mindtrace.core import CoreConfig
from mindtrace.registry import MinioRegistryBackend, Registry


@pytest.fixture(scope="session")
def minio_client():
    """Create a MinIO client for testing."""
    endpoint = os.environ.get("MINDTRACE_MINIO__MINIO_ENDPOINT", "localhost:9000")
    access_key = os.environ.get("MINDTRACE_MINIO__MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.environ.get("MINDTRACE_MINIO__MINIO_SECRET_KEY", "minioadmin")
    secure = os.environ.get("MINIO_SECURE", "0") == "1"
    client = Minio(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
    )
    yield client


@pytest.fixture
def minio_test_bucket(minio_client) -> Generator[str, None, None]:
    """Create a temporary MinIO bucket for testing."""
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
def minio_temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for MinIO testing."""
    temp_dir = Path(CoreConfig()["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]) / f"test_dir_{uuid.uuid4()}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def minio_backend(minio_temp_dir, minio_test_bucket):
    """Create a MinioRegistryBackend instance with a test bucket."""
    endpoint = os.environ.get("MINDTRACE_MINIO__MINIO_ENDPOINT", "localhost:9000")
    access_key = os.environ.get("MINDTRACE_MINIO__MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.environ.get("MINDTRACE_MINIO__MINIO_SECRET_KEY", "minioadmin")
    secure = os.environ.get("MINIO_SECURE", "0") == "1"
    return MinioRegistryBackend(
        uri=str(minio_temp_dir),
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        bucket=minio_test_bucket,
        secure=secure,
    )


@pytest.fixture
def minio_registry(minio_backend):
    return Registry(backend=minio_backend)


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
