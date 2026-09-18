"""Datalake bench mount builders resolve MinIO via CoreConfig."""

from __future__ import annotations

from mindtrace.core.testing.bench_framework import BenchSuiteConfig
from mindtrace.core.testing.minio import ResolvedMinioBenchConnection
from mindtrace.datalake.testing.mounts import build_payload_mount


def _bench_config(resources: dict | None = None) -> BenchSuiteConfig:
    return BenchSuiteConfig(
        suite_id="datalake.stress.payload_write_ceiling",
        label="test",
        profile="stress",
        duration_seconds=1.0,
        resources=resources or {},
    )


def test_build_payload_mount_minio_uses_core_config_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "mindtrace.datalake.testing.mounts.resolve_minio_bench_connection",
        lambda resources: ResolvedMinioBenchConnection(
            endpoint="localhost:19000",
            access_key="ak",
            secret_key="sk",
            bucket="from-cfg",
            secure=False,
        ),
    )
    mount, _cleanup, meta = build_payload_mount(_bench_config(), "minio", "run-prefix")
    assert mount.config.endpoint == "localhost:19000"
    assert mount.config.bucket == "from-cfg"
    assert mount.config.prefix == "run-prefix"
    assert meta == {"backend": "minio", "bucket": "from-cfg", "prefix": "run-prefix"}
