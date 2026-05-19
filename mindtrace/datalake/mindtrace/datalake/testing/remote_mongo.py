"""Remote MongoDB (Atlas) helpers for datalake benchmark suites."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _non_empty(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def remote_mongo_from_core_config() -> tuple[str | None, str | None]:
    """Return ``(REMOTE_MONGO_DB_URI, REMOTE_MONGO_DB_NAME)`` from CoreConfig when set."""

    try:
        from mindtrace.core import CoreConfig

        core_config = CoreConfig()
        datalake_cfg = core_config.get("MINDTRACE_DATALAKE", {})
        uri = core_config.get_secret("MINDTRACE_DATALAKE", "REMOTE_MONGO_DB_URI")
        name = datalake_cfg.get("REMOTE_MONGO_DB_NAME")
        return _non_empty(uri), _non_empty(name)
    except Exception:
        return None, None


def resolve_stress_atlas_mongo(resources: Mapping[str, Any], default_db_name: str) -> tuple[str, str]:
    """Resolve Atlas URI/database for ``mongo_backend: atlas`` workloads."""

    cfg_uri, cfg_db = remote_mongo_from_core_config()

    uri = _non_empty(resources.get("REMOTE_MONGO_DB_URI")) or _non_empty(resources.get("mongo_atlas_uri")) or cfg_uri
    if uri is None:
        raise ValueError(
            "Atlas Mongo requires REMOTE_MONGO_DB_URI / mongo_atlas_uri in resources, or "
            "MINDTRACE_DATALAKE__REMOTE_MONGO_DB_URI in environment / CoreSettings.",
        )

    db_name = (
        _non_empty(resources.get("REMOTE_MONGO_DB_NAME"))
        or _non_empty(resources.get("mongo_atlas_db_name"))
        or _non_empty(resources.get("mongo_db_name"))
        or cfg_db
        or default_db_name
    )

    return uri, db_name
