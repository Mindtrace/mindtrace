"""Fixtures for ultralytics archiver integration tests.

These tests require a running S3-compatible store and network access to download
ultralytics model weights. They are skipped when the store is not available.

S3 connection settings follow the same resolution as the rest of the integration
suite (``CoreConfig``: env vars such as ``MINDTRACE_MINIO__MINIO_ENDPOINT`` →
``config.ini``). The test Docker stack maps the S3 API to ``localhost:19000``; that is
set by ``scripts/docker_up.sh`` when running ``ds test`` / ``run_tests.sh``.
"""

import os
import socket

import pytest

from mindtrace.registry import Registry, S3RegistryBackend


def _s3_endpoint_reachable(endpoint: str, timeout: float = 2.0) -> bool:
    """TCP check against the configured host:port (same idea as legacy fixture, but not hard-coded)."""
    if ":" not in endpoint:
        return False
    host, port_str = endpoint.rsplit(":", 1)
    try:
        port = int(port_str)
    except ValueError:
        return False
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except OSError:
        return False


@pytest.fixture()
def s3_registry(core_config):
    """Registry on S3, using integration-harness S3 settings."""
    minio_cfg = core_config.get("MINDTRACE_MINIO", {})
    endpoint = minio_cfg.get("MINIO_ENDPOINT")
    access_key = minio_cfg.get("MINIO_ACCESS_KEY")
    secret_key = core_config.get_secret("MINDTRACE_MINIO", "MINIO_SECRET_KEY")

    if not all([endpoint, access_key, secret_key]):
        pytest.skip("S3 not configured (set MINDTRACE_MINIO__* env vars or config.ini)")

    if not _s3_endpoint_reachable(endpoint):
        pytest.skip("S3 not available")

    bucket = os.environ.get("MINIO_BUCKET") or minio_cfg.get("MINIO_BUCKET", "minio-registry")
    secure = os.environ.get("MINIO_SECURE", "0") == "1"

    backend = S3RegistryBackend(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        bucket=bucket,
        secure=secure,
    )
    return Registry(backend=backend)
