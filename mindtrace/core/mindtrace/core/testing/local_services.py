"""Python view of the test-stack MinIO ports.

Port numbers live only in ``minio.env`` (this directory). Compose interpolates
that file via ``--env-file``; ``scripts/docker_up.sh`` sources it. This module
parses the same file so tests and samples stay aligned without generating
dotenv at runtime.
"""

from __future__ import annotations

from pathlib import Path

LOCAL_MINIO_ENV_PATH = Path(__file__).with_name("minio.env")

# Compose interpolation names (must match ``tests/docker-compose.yml`` and ``minio.env``).
COMPOSE_MINIO_API_PORT_VAR = "MINIO_API_PORT"
COMPOSE_MINIO_CONSOLE_PORT_VAR = "MINIO_CONSOLE_PORT"
COMPOSE_MINIO_CONTAINER_API_PORT_VAR = "MINIO_CONTAINER_API_PORT"
COMPOSE_MINIO_CONTAINER_CONSOLE_PORT_VAR = "MINIO_CONTAINER_CONSOLE_PORT"
COMPOSE_MINIO_HOST_VAR = "MINIO_HOST"


def parse_dotenv(path: Path) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines, ignoring blanks and ``#`` comments."""
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ValueError(f"invalid dotenv line in {path}: {raw!r}")
        env[key.strip()] = value.strip()
    return env


def load_local_minio_env(path: Path | None = None) -> dict[str, str]:
    """Load primitive MinIO bind settings from ``minio.env``."""
    env_path = Path(path) if path is not None else LOCAL_MINIO_ENV_PATH
    env = parse_dotenv(env_path)
    required = (
        COMPOSE_MINIO_HOST_VAR,
        COMPOSE_MINIO_API_PORT_VAR,
        COMPOSE_MINIO_CONSOLE_PORT_VAR,
        COMPOSE_MINIO_CONTAINER_API_PORT_VAR,
        COMPOSE_MINIO_CONTAINER_CONSOLE_PORT_VAR,
    )
    missing = [key for key in required if key not in env]
    if missing:
        raise ValueError(f"missing keys in {env_path}: {missing}")
    return env


_minio_env = load_local_minio_env()

LOCAL_MINIO_HOST = _minio_env[COMPOSE_MINIO_HOST_VAR]
LOCAL_MINIO_API_PORT = int(_minio_env[COMPOSE_MINIO_API_PORT_VAR])
LOCAL_MINIO_CONSOLE_PORT = int(_minio_env[COMPOSE_MINIO_CONSOLE_PORT_VAR])
LOCAL_MINIO_CONTAINER_API_PORT = int(_minio_env[COMPOSE_MINIO_CONTAINER_API_PORT_VAR])
LOCAL_MINIO_CONTAINER_CONSOLE_PORT = int(_minio_env[COMPOSE_MINIO_CONTAINER_CONSOLE_PORT_VAR])

LOCAL_MINIO_ENDPOINT = f"{LOCAL_MINIO_HOST}:{LOCAL_MINIO_API_PORT}"
LOCAL_MINIO_HEALTH_URL = f"http://{LOCAL_MINIO_ENDPOINT}/minio/health/live"
LOCAL_MINIO_HTTP_ORIGIN = f"http://{LOCAL_MINIO_ENDPOINT}"
