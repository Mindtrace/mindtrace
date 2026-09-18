"""Tests for bench-suite MinIO CoreConfig resolution."""

from __future__ import annotations

import mindtrace.core.testing.minio as minio_mod
from mindtrace.core.testing.minio import (
    MinioBenchResources,
    ResolvedMinioBenchConnection,
    minio_from_core_config,
    resolve_minio_bench_connection,
)


def test_minio_from_core_config_reads_endpoint_env(monkeypatch) -> None:
    monkeypatch.setenv("MINDTRACE_MINIO__MINIO_ENDPOINT", "localhost:19000")
    monkeypatch.setenv("MINDTRACE_MINIO__MINIO_HOST", "localhost")
    monkeypatch.setenv("MINDTRACE_MINIO__MINIO_PORT", "19000")
    monkeypatch.setenv("MINDTRACE_MINIO__MINIO_ACCESS_KEY", "from-env")
    monkeypatch.setenv("MINDTRACE_MINIO__MINIO_SECRET_KEY", "env-secret")
    cfg = minio_from_core_config()
    assert cfg["endpoint"] == "localhost:19000"
    assert cfg["access_key"] == "from-env"
    assert cfg["secret_key"] == "env-secret"


def test_minio_from_core_config_composes_host_port_when_endpoint_empty(monkeypatch) -> None:
    class _Cfg:
        def get(self, key, default=None):
            if key == "MINDTRACE_MINIO":
                return {
                    "MINIO_ENDPOINT": "",
                    "MINIO_HOST": "127.0.0.1",
                    "MINIO_PORT": 19000,
                    "MINIO_ACCESS_KEY": "ak",
                }
            return default

        def get_secret(self, *_path):
            return "sk"

    monkeypatch.setattr("mindtrace.core.config.CoreConfig", lambda: _Cfg())
    cfg = minio_from_core_config()
    assert cfg["endpoint"] == "127.0.0.1:19000"
    assert cfg["access_key"] == "ak"
    assert cfg["secret_key"] == "sk"


def test_resolve_prefers_explicit_resources(monkeypatch) -> None:
    monkeypatch.setattr(
        minio_mod,
        "minio_from_core_config",
        lambda: {
            "endpoint": "localhost:19000",
            "access_key": "cfg-key",
            "secret_key": "cfg-secret",
            "bucket": "cfg-bucket",
        },
    )
    resolved = resolve_minio_bench_connection(
        {
            "minio_endpoint": "explicit:1",
            "minio_access_key": "explicit-key",
            "minio_secret_key": "explicit-secret",
            "minio_bucket": "explicit-bucket",
            "minio_secure": "true",
        }
    )
    assert resolved == ResolvedMinioBenchConnection(
        endpoint="explicit:1",
        access_key="explicit-key",
        secret_key="explicit-secret",
        bucket="explicit-bucket",
        secure=True,
    )


def test_resolve_falls_back_to_core_config(monkeypatch) -> None:
    monkeypatch.setattr(
        minio_mod,
        "minio_from_core_config",
        lambda: {
            "endpoint": "localhost:19000",
            "access_key": "cfg-key",
            "secret_key": "cfg-secret",
            "bucket": None,
        },
    )
    resolved = resolve_minio_bench_connection({})
    assert resolved.endpoint == "localhost:19000"
    assert resolved.access_key == "cfg-key"
    assert resolved.secret_key == "cfg-secret"
    assert resolved.bucket == "stress-registry"
    assert resolved.secure is False


def test_minio_bench_resources_default_endpoint_is_unset() -> None:
    model = MinioBenchResources.model_validate({})
    assert model.minio_endpoint is None
    schema = MinioBenchResources.model_json_schema()
    assert "minio_endpoint" in schema["properties"]
    assert schema["properties"]["minio_endpoint"].get("default") is None
