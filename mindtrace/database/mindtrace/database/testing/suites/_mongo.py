"""Mongo resource helpers for database benchmark suites."""

from __future__ import annotations

from typing import Literal

from mindtrace.core import BenchSuiteConfig


def resolve_mongo_resources(config: BenchSuiteConfig) -> tuple[str, str, str]:
    """Return ``(backend_label, uri, db_name)`` from suite parameters/resources."""

    backend = str(config.parameters.get("mongo_backend", "local")).lower()
    if backend == "atlas":
        uri = str(config.resources.get("REMOTE_MONGO_DB_URI") or config.resources.get("mongo_atlas_uri") or "")
        db_name = str(
            config.resources.get("REMOTE_MONGO_DB_NAME")
            or config.resources.get("mongo_atlas_db_name")
            or config.resources.get("mongo_db_name")
            or ""
        )
        if not uri:
            raise ValueError(f"Suite {config.suite_id} requires REMOTE_MONGO_DB_URI or mongo_atlas_uri")
        if not db_name:
            raise ValueError(f"Suite {config.suite_id} requires REMOTE_MONGO_DB_NAME or mongo_atlas_db_name")
        return "atlas", uri, db_name

    uri = str(config.resources.get("mongo_uri", "mongodb://127.0.0.1:27017"))
    db_name = str(config.resources.get("mongo_db_name") or f"mindtrace_bench_{config.run_id.replace('-', '_')}")
    return "local", uri, db_name
