"""Host ports for services started by ``tests/docker-compose.yml``.

MinIO uses non-default **host** ports so local dev does not collide with
Prometheus ``node_exporter`` (API **9100**). Inside the container MinIO still
listens on its defaults (**9000** / **9001**); compose publishes::

    ${MINIO_API_PORT}:9000
    ${MINIO_CONSOLE_PORT}:9001

Those host values are defined only here. ``scripts/docker_up.sh`` writes them to
``tests/.env.minio`` and passes ``--env-file`` to Compose. Do not hardcode
19000/19001 in YAML.
"""

from __future__ import annotations

from pathlib import Path

LOCAL_MINIO_HOST = "localhost"
LOCAL_MINIO_API_PORT = 19000
LOCAL_MINIO_CONSOLE_PORT = 19001
LOCAL_MINIO_CONTAINER_API_PORT = 9000
LOCAL_MINIO_CONTAINER_CONSOLE_PORT = 9001

LOCAL_MINIO_ENDPOINT = f"{LOCAL_MINIO_HOST}:{LOCAL_MINIO_API_PORT}"
LOCAL_MINIO_HEALTH_URL = f"http://{LOCAL_MINIO_ENDPOINT}/minio/health/live"
LOCAL_MINIO_HTTP_ORIGIN = f"http://{LOCAL_MINIO_ENDPOINT}"

# Compose interpolation names (must match ``tests/docker-compose.yml``).
COMPOSE_MINIO_API_PORT_VAR = "MINIO_API_PORT"
COMPOSE_MINIO_CONSOLE_PORT_VAR = "MINIO_CONSOLE_PORT"
COMPOSE_MINIO_CONTAINER_API_PORT_VAR = "MINIO_CONTAINER_API_PORT"
COMPOSE_MINIO_CONTAINER_CONSOLE_PORT_VAR = "MINIO_CONTAINER_CONSOLE_PORT"
COMPOSE_MINIO_ENV_FILENAME = ".env.minio"


def local_minio_compose_env() -> dict[str, str]:
    """Environment mapping consumed by ``tests/docker-compose.yml`` and ``docker_up.sh``."""
    return {
        COMPOSE_MINIO_API_PORT_VAR: str(LOCAL_MINIO_API_PORT),
        COMPOSE_MINIO_CONSOLE_PORT_VAR: str(LOCAL_MINIO_CONSOLE_PORT),
        COMPOSE_MINIO_CONTAINER_API_PORT_VAR: str(LOCAL_MINIO_CONTAINER_API_PORT),
        COMPOSE_MINIO_CONTAINER_CONSOLE_PORT_VAR: str(LOCAL_MINIO_CONTAINER_CONSOLE_PORT),
        "MINIO_HOST": LOCAL_MINIO_HOST,
        "LOCAL_MINIO_ENDPOINT": LOCAL_MINIO_ENDPOINT,
        "LOCAL_MINIO_HEALTH_URL": LOCAL_MINIO_HEALTH_URL,
    }


def write_local_minio_compose_env(path: Path) -> Path:
    """Write dotenv lines for Compose ``--env-file`` / ``source`` in ``docker_up.sh``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{key}={value}\n" for key, value in local_minio_compose_env().items())
    path.write_text(body, encoding="utf-8")
    return path
