from __future__ import annotations

import os

import uvicorn

from mindtrace.datalake import DatalakeService
from mindtrace.registry import Mount, MountBackendKind, S3AccessKeyAuth, S3MountConfig


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def build_service() -> DatalakeService:
    service_host = _env("MINDTRACE_DATALAKE__SERVICE_HOST", "0.0.0.0")
    service_port = int(_env("MINDTRACE_DATALAKE__SERVICE_PORT", "8080"))

    mount_name = _env("MINDTRACE_DATALAKE__MOUNT_NAME", "minio")
    bucket = _env("MINDTRACE_DATALAKE__S3_BUCKET", "datalake")
    prefix = os.getenv("MINDTRACE_DATALAKE__S3_PREFIX") or None
    endpoint = _env("MINDTRACE_DATALAKE__S3_ENDPOINT", "minio:9000")
    access_key = _env("MINDTRACE_DATALAKE__S3_ACCESS_KEY", "minioadmin")
    secret_key = _env("MINDTRACE_DATALAKE__S3_SECRET_KEY", "minioadmin")
    secure = _env_bool("MINDTRACE_DATALAKE__S3_SECURE", False)

    mount = Mount(
        name=mount_name,
        backend=MountBackendKind.S3,
        config=S3MountConfig(
            bucket=bucket,
            prefix=prefix,
            endpoint=endpoint,
            secure=secure,
        ),
        auth=S3AccessKeyAuth(access_key=access_key, secret_key=secret_key),
        is_default=True,
        registry_options={"mutable": True},
    )

    service = DatalakeService(
        url=f"http://{service_host}:{service_port}",
        mongo_db_uri=_env("MINDTRACE_DATALAKE__MONGO_DB_URI", "mongodb://mongodb:27017"),
        mongo_db_name=_env("MINDTRACE_DATALAKE__MONGO_DB_NAME", "mindtrace_datalake"),
        mounts=[mount],
        default_mount=mount_name,
        initialize_on_startup=True,
        live_service=True,
    )
    return service


if __name__ == "__main__":
    host = _env("MINDTRACE_DATALAKE__SERVICE_HOST", "0.0.0.0")
    port = int(_env("MINDTRACE_DATALAKE__SERVICE_PORT", "8080"))
    service = build_service()
    uvicorn.run(service.app, host=host, port=port)
