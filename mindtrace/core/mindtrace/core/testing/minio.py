"""Resolve MinIO connection settings for bench suites from explicit ``resources``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

_DEFAULT_BUCKET = "stress-registry"

TEST_STACK_MINIO_ENDPOINT = "localhost:19000"
TEST_STACK_MINIO_RESOURCES: dict[str, str] = {
    "minio_endpoint": TEST_STACK_MINIO_ENDPOINT,
    "minio_access_key": "minioadmin",
    "minio_secret_key": "minioadmin",
}


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


def _require_resource(resources: Mapping[str, Any], key: str) -> str:
    value = _non_empty(resources.get(key))
    if value is None:
        raise ValueError(
            f"minio backend requires resources[{key!r}]; set it on the suite profile or pass a resources overlay"
        )
    return value


@dataclass(frozen=True)
class ResolvedMinioBenchConnection:
    """MinIO settings taken from bench ``resources`` (no CoreConfig fallback)."""

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

    Requires ``minio_endpoint``, ``minio_access_key``, and ``minio_secret_key`` on
    ``resources``. There is no CoreConfig or hardcoded host:port fallback.
    """

    endpoint = _require_resource(resources, "minio_endpoint")
    access_key = _require_resource(resources, "minio_access_key")
    secret_key = _require_resource(resources, "minio_secret_key")
    bucket = _non_empty(resources.get("minio_bucket")) or default_bucket
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

    Connection keys are required at run time for the minio backend (typically from
    suite ``profiles[*].resources``). Omitted keys do not fall back to CoreConfig.
    """

    minio_endpoint: str | None = Field(
        default=None,
        description=(
            "S3-compatible endpoint (host:port) for minio backend. Required when "
            "backend is minio; first-party stress profiles use the test-stack host "
            f"port ({TEST_STACK_MINIO_ENDPOINT})."
        ),
    )
    minio_access_key: str | None = Field(
        default=None,
        description="Access key for minio backend. Required when backend is minio.",
        json_schema_extra={"secret": True},
    )
    minio_secret_key: str | None = Field(
        default=None,
        description="Secret key for minio backend. Required when backend is minio.",
        json_schema_extra={"secret": True},
    )
    minio_bucket: str = Field("stress-registry", description="Bucket for minio backend writes.")
    minio_prefix: str | None = Field(None, description="Optional object prefix for minio backend writes.")
    minio_secure: bool = Field(False, description="Whether the minio endpoint uses TLS.")
