"""Tests for bench-suite MinIO resource resolution."""

from __future__ import annotations

import pytest

from mindtrace.core.testing.minio import (
    TEST_STACK_MINIO_ENDPOINT,
    TEST_STACK_MINIO_RESOURCES,
    MinioBenchResources,
    ResolvedMinioBenchConnection,
    resolve_minio_bench_connection,
)


def test_resolve_requires_explicit_endpoint() -> None:
    with pytest.raises(ValueError, match="minio_endpoint"):
        resolve_minio_bench_connection({})


def test_resolve_requires_keys_when_endpoint_set() -> None:
    with pytest.raises(ValueError, match="minio_access_key"):
        resolve_minio_bench_connection({"minio_endpoint": "localhost:19000"})
    with pytest.raises(ValueError, match="minio_secret_key"):
        resolve_minio_bench_connection(
            {"minio_endpoint": "localhost:19000", "minio_access_key": "ak"},
        )


def test_resolve_uses_explicit_resources() -> None:
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


def test_resolve_test_stack_profile_resources() -> None:
    resolved = resolve_minio_bench_connection(TEST_STACK_MINIO_RESOURCES)
    assert resolved.endpoint == TEST_STACK_MINIO_ENDPOINT
    assert resolved.access_key == "minioadmin"
    assert resolved.secret_key == "minioadmin"
    assert resolved.bucket == "stress-registry"
    assert resolved.secure is False


def test_minio_bench_resources_default_endpoint_is_unset() -> None:
    model = MinioBenchResources.model_validate({})
    assert model.minio_endpoint is None
    schema = MinioBenchResources.model_json_schema()
    assert "minio_endpoint" in schema["properties"]
    assert schema["properties"]["minio_endpoint"].get("default") is None
