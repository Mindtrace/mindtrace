"""Resolve Mongo URIs for datalake benchmark workloads."""

from __future__ import annotations

from mindtrace.core.testing.bench_framework import BenchSuiteConfig
from mindtrace.datalake.testing.remote_mongo import resolve_stress_atlas_mongo


def require_resource(config: BenchSuiteConfig, key: str) -> str:
    value = config.resources.get(key)
    if not value:
        raise ValueError(f"Suite {config.suite_id} requires resource config key {key!r}")
    return str(value)


def resolve_mongo_triple(config: BenchSuiteConfig) -> tuple[str, str, str]:
    """Return ``(mongo_backend_label, uri, db_name)``."""

    backend = str(config.parameters.get("mongo_backend", "local")).lower()
    default_db_name = f"mindtrace_bench_{config.run_id.replace('-', '_')}"

    if backend == "local":
        return (
            "local",
            require_resource(config, "mongo_uri"),
            str(config.resources.get("mongo_db_name", default_db_name)),
        )

    if backend == "atlas":
        atlas_uri, atlas_db_name = resolve_stress_atlas_mongo(config.resources, default_db_name)
        return ("atlas", atlas_uri, atlas_db_name)

    raise ValueError(f"Unsupported mongo_backend {backend!r}; expected local or atlas")
