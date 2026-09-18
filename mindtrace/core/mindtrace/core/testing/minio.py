"""Resolve MinIO connection settings for bench suites from CoreConfig."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

_PRODUCT_ENDPOINT = "localhost:9000"
_PRODUCT_ACCESS_KEY = "minioadmin"
_PRODUCT_SECRET_KEY = "minioadmin"
_DEFAULT_BUCKET = "stress-registry"


def _non_empty(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    text = str(value).strip()
    return text if text else None


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _host_port_endpoint(minio_cfg: Mapping[str, Any]) -> str | None:
    host = _non_empty(minio_cfg.get("MINIO_HOST"))
    port = _non_empty(minio_cfg.get("MINIO_PORT"))
    if host is None or port is None:
        return None
    return f"{host}:{port}"


def _resolve_minio_endpoint(minio_cfg: Mapping[str, Any]) -> str | None:
    """Return the MinIO endpoint, or raise if host/port and endpoint disagree.

    When ``MINIO_ENDPOINT``, ``MINIO_HOST``, and ``MINIO_PORT`` are all set,
    ``MINIO_ENDPOINT`` must equal ``{MINIO_HOST}:{MINIO_PORT}``. Prefer
    ``MINIO_ENDPOINT`` when host/port are incomplete; compose host/port when
    endpoint is unset (host defaults to ``localhost``).
    """

    endpoint = _non_empty(minio_cfg.get("MINIO_ENDPOINT"))
    composed = _host_port_endpoint(minio_cfg)
    if endpoint is not None and composed is not None and endpoint != composed:
        raise ValueError(
            f"MINDTRACE_MINIO.MINIO_ENDPOINT does not match MINIO_HOST:MINIO_PORT ({endpoint!r} != {composed!r})"
        )
    if endpoint is not None:
        return endpoint
    host = _non_empty(minio_cfg.get("MINIO_HOST")) or "localhost"
    port = _non_empty(minio_cfg.get("MINIO_PORT"))
    if port is None:
        return None
    return f"{host}:{port}"


def minio_from_core_config() -> dict[str, str | None]:
    """Return MinIO endpoint/keys from CoreConfig, or empty values if unavailable.

    Endpoint prefers ``MINDTRACE_MINIO.MINIO_ENDPOINT``. If that is unset, it is
    composed from ``MINIO_HOST`` and ``MINIO_PORT``. If all three are set and
    ``MINIO_ENDPOINT`` is not ``{MINIO_HOST}:{MINIO_PORT}``, raises ``ValueError``.
    """

    try:
        from mindtrace.core.config import CoreConfig

        core_config = CoreConfig()
        minio_cfg = core_config.get("MINDTRACE_MINIO", {}) or {}
        endpoint = _resolve_minio_endpoint(minio_cfg)
        access_key = _non_empty(minio_cfg.get("MINIO_ACCESS_KEY"))
        secret_key = _non_empty(core_config.get_secret("MINDTRACE_MINIO", "MINIO_SECRET_KEY"))
        bucket = _non_empty(minio_cfg.get("MINIO_BUCKET"))
        return {
            "endpoint": endpoint,
            "access_key": access_key,
            "secret_key": secret_key,
            "bucket": bucket,
        }
    except ValueError:
        raise
    except Exception:
        return {"endpoint": None, "access_key": None, "secret_key": None, "bucket": None}


@dataclass(frozen=True)
class ResolvedMinioBenchConnection:
    """MinIO settings after applying bench ``resources`` over CoreConfig."""

    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    secure: bool


def resolve_minio_bench_connection(
    resources: Mapping[str, Any],
    *,
    default_bucket: str = _DEFAULT_BUCKET,
) -> ResolvedMinioBenchConnection:
    """Resolve MinIO connection for a bench run.

    Explicit ``resources`` keys win, then CoreConfig (env / ``config.ini``), then
    product defaults (``localhost:9000`` / ``minioadmin``).
    """

    cfg = minio_from_core_config()
    endpoint = _non_empty(resources.get("minio_endpoint")) or cfg.get("endpoint") or _PRODUCT_ENDPOINT
    access_key = _non_empty(resources.get("minio_access_key")) or cfg.get("access_key") or _PRODUCT_ACCESS_KEY
    secret_key = _non_empty(resources.get("minio_secret_key")) or cfg.get("secret_key") or _PRODUCT_SECRET_KEY
    bucket = _non_empty(resources.get("minio_bucket")) or cfg.get("bucket") or default_bucket
    secure = _as_bool(resources.get("minio_secure", False))
    return ResolvedMinioBenchConnection(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        bucket=bucket,
        secure=secure,
    )


class MinioBenchResources(BaseModel):
    """MinIO resource fields for bench suites.

    Omitted connection keys fall back to CoreConfig at run time via
    :func:`resolve_minio_bench_connection`.
    """

    minio_endpoint: str | None = Field(
        default=None,
        description=(
            "S3-compatible endpoint for minio backend. When omitted, uses CoreConfig "
            "``MINDTRACE_MINIO.MINIO_ENDPOINT`` (environment, then config.ini), or "
            "``MINIO_HOST``:``MINIO_PORT`` if endpoint is unset. Raises if those "
            "values are all set and disagree."
        ),
    )
    minio_access_key: str | None = Field(
        default=None,
        description=(
            "Access key for minio backend. When omitted, uses CoreConfig ``MINDTRACE_MINIO.MINIO_ACCESS_KEY``."
        ),
        json_schema_extra={"secret": True},
    )
    minio_secret_key: str | None = Field(
        default=None,
        description=(
            "Secret key for minio backend. When omitted, uses CoreConfig ``MINDTRACE_MINIO.MINIO_SECRET_KEY``."
        ),
        json_schema_extra={"secret": True},
    )
    minio_bucket: str = Field("stress-registry", description="Bucket for minio backend writes.")
    minio_prefix: str | None = Field(None, description="Optional object prefix for minio backend writes.")
    minio_secure: bool = Field(False, description="Whether the minio endpoint uses TLS.")
