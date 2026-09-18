"""Registry bench backend builders resolve MinIO via CoreConfig."""

from __future__ import annotations

from mindtrace.core.testing.bench_framework import BenchSuiteConfig
from mindtrace.core.testing.minio import ResolvedMinioBenchConnection
from mindtrace.registry.testing.suites import _backends as registry_backends


def _bench_config(resources: dict | None = None) -> BenchSuiteConfig:
    return BenchSuiteConfig(
        suite_id="registry.stress.write_ceiling",
        label="test",
        profile="stress",
        duration_seconds=1.0,
        resources=resources or {},
    )


def test_build_registry_minio_uses_core_config_fallback(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeBackend:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(registry_backends, "MinioRegistryBackend", _FakeBackend)
    monkeypatch.setattr(registry_backends, "Registry", lambda **_kwargs: object())
    monkeypatch.setattr(
        registry_backends,
        "resolve_minio_bench_connection",
        lambda resources: ResolvedMinioBenchConnection(
            endpoint="localhost:19000",
            access_key="ak",
            secret_key="sk",
            bucket="from-cfg",
            secure=False,
        ),
    )
    _registry, _cleanup, meta = registry_backends.build_registry(_bench_config(), "minio", "run-prefix")
    assert captured["endpoint"] == "localhost:19000"
    assert captured["bucket"] == "from-cfg"
    assert captured["prefix"] == "run-prefix"
    assert meta == {"backend": "minio", "bucket": "from-cfg", "prefix": "run-prefix"}
