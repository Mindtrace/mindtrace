"""Guard test-stack MinIO ports against drift from ``local_services``."""

from __future__ import annotations

from pathlib import Path

from mindtrace.core.testing.local_services import (
    COMPOSE_MINIO_API_PORT_VAR,
    COMPOSE_MINIO_CONSOLE_PORT_VAR,
    COMPOSE_MINIO_CONTAINER_API_PORT_VAR,
    COMPOSE_MINIO_CONTAINER_CONSOLE_PORT_VAR,
    LOCAL_MINIO_API_PORT,
    LOCAL_MINIO_CONSOLE_PORT,
    LOCAL_MINIO_CONTAINER_API_PORT,
    LOCAL_MINIO_CONTAINER_CONSOLE_PORT,
    local_minio_compose_env,
    write_local_minio_compose_env,
)


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "tests" / "docker-compose.yml").is_file() and (parent / "pyproject.toml").is_file():
            return parent
    raise AssertionError("could not locate repository root from test file path")


def test_compose_yaml_has_no_hardcoded_minio_host_ports() -> None:
    compose = (_repo_root() / "tests" / "docker-compose.yml").read_text(encoding="utf-8")
    assert str(LOCAL_MINIO_API_PORT) not in compose
    assert str(LOCAL_MINIO_CONSOLE_PORT) not in compose
    assert f"${{{COMPOSE_MINIO_API_PORT_VAR}}}:${{{COMPOSE_MINIO_CONTAINER_API_PORT_VAR}}}" in compose
    assert f"${{{COMPOSE_MINIO_CONSOLE_PORT_VAR}}}:${{{COMPOSE_MINIO_CONTAINER_CONSOLE_PORT_VAR}}}" in compose
    assert f'--address ":${{{COMPOSE_MINIO_CONTAINER_API_PORT_VAR}}}"' in compose
    assert f"http://localhost:${{{COMPOSE_MINIO_CONTAINER_API_PORT_VAR}}}/minio/health/live" in compose


def test_compose_env_exports_host_to_container_mapping(tmp_path: Path) -> None:
    env = local_minio_compose_env()
    assert env[COMPOSE_MINIO_API_PORT_VAR] == str(LOCAL_MINIO_API_PORT)
    assert env[COMPOSE_MINIO_CONSOLE_PORT_VAR] == str(LOCAL_MINIO_CONSOLE_PORT)
    assert env[COMPOSE_MINIO_CONTAINER_API_PORT_VAR] == str(LOCAL_MINIO_CONTAINER_API_PORT)
    assert env[COMPOSE_MINIO_CONTAINER_CONSOLE_PORT_VAR] == str(LOCAL_MINIO_CONTAINER_CONSOLE_PORT)
    assert LOCAL_MINIO_CONTAINER_API_PORT == 9000
    assert LOCAL_MINIO_CONTAINER_CONSOLE_PORT == 9001

    path = write_local_minio_compose_env(tmp_path / ".env.minio")
    text = path.read_text(encoding="utf-8")
    assert f"{COMPOSE_MINIO_API_PORT_VAR}={LOCAL_MINIO_API_PORT}" in text
    assert f"{COMPOSE_MINIO_CONTAINER_API_PORT_VAR}={LOCAL_MINIO_CONTAINER_API_PORT}" in text
