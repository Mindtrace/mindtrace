"""Fixtures for ultralytics archiver integration tests.

These tests require a running MinIO instance and network access to download
ultralytics model weights. They are skipped when MinIO is not available.
"""

import os
import socket

import pytest

from mindtrace.registry import MinioRegistryBackend, Registry

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "minio-registry")


def _minio_available() -> bool:
    host, port_str = MINIO_ENDPOINT.split(":")
    try:
        sock = socket.create_connection((host, int(port_str)), timeout=2)
        sock.close()
        return True
    except (OSError, ValueError):
        return False


@pytest.fixture()
def minio_registry():
    if not _minio_available():
        pytest.skip("MinIO not available")
    backend = MinioRegistryBackend(
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        bucket=MINIO_BUCKET,
        secure=False,
    )
    return Registry(backend=backend)
