"""Registry bench backend builders require explicit MinIO resources."""

from __future__ import annotations

import pytest

from mindtrace.core.testing.bench_framework import BenchSuiteConfig
from mindtrace.core.testing.minio import TEST_STACK_MINIO_RESOURCES
from mindtrace.registry.testing.suites import _backends as registry_backends


def _bench_config(resources: dict | None = None) -> BenchSuiteConfig:
    return BenchSuiteConfig(
        suite_id="registry.stress.write_ceiling",
        label="test",
        profile="stress",
        duration_seconds=1.0,
        resources=resources or {},
    )


def test_build_registry_minio_uses_profile_resources(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeBackend:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(registry_backends, "MinioRegistryBackend", _FakeBackend)
    monkeypatch.setattr(registry_backends, "Registry", lambda **_kwargs: object())
    _registry, _cleanup, meta = registry_backends.build_registry(
        _bench_config(dict(TEST_STACK_MINIO_RESOURCES)),
        "minio",
        "run-prefix",
    )
    assert captured["endpoint"] == TEST_STACK_MINIO_RESOURCES["minio_endpoint"]
    assert captured["bucket"] == "stress-registry"
    assert captured["prefix"] == "run-prefix"
    assert meta == {"backend": "minio", "bucket": "stress-registry", "prefix": "run-prefix"}


def test_build_registry_minio_rejects_empty_resources() -> None:
    with pytest.raises(ValueError, match="minio_endpoint"):
        registry_backends.build_registry(_bench_config(), "minio", "run-prefix")
