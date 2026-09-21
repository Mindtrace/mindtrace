"""Datalake bench mount builders require explicit MinIO resources."""

from __future__ import annotations

import pytest

from mindtrace.core.testing.bench_framework import BenchSuiteConfig
from mindtrace.core.testing.minio import TEST_STACK_MINIO_RESOURCES
from mindtrace.datalake.testing.mounts import build_payload_mount


def _bench_config(resources: dict | None = None) -> BenchSuiteConfig:
    return BenchSuiteConfig(
        suite_id="datalake.stress.payload_write_ceiling",
        label="test",
        profile="stress",
        duration_seconds=1.0,
        resources=resources or {},
    )


def test_build_payload_mount_minio_uses_profile_resources() -> None:
    mount, _cleanup, meta = build_payload_mount(
        _bench_config(dict(TEST_STACK_MINIO_RESOURCES)),
        "minio",
        "run-prefix",
    )
    assert mount.config.endpoint == TEST_STACK_MINIO_RESOURCES["minio_endpoint"]
    assert mount.config.bucket == "stress-registry"
    assert mount.config.prefix == "run-prefix"
    assert meta == {"backend": "minio", "bucket": "stress-registry", "prefix": "run-prefix"}


def test_build_payload_mount_minio_rejects_empty_resources() -> None:
    with pytest.raises(ValueError, match="minio_endpoint"):
        build_payload_mount(_bench_config(), "minio", "run-prefix")
