"""Guard test-stack MinIO ports against drift from ``minio.env``."""

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
    LOCAL_MINIO_ENV_PATH,
    LOCAL_MINIO_HOST,
    load_local_minio_env,
)


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "tests" / "docker-compose.yml").is_file() and (parent / "pyproject.toml").is_file():
            return parent
    raise AssertionError("could not locate repository root from test file path")


def test_minio_env_is_the_single_source_of_port_numbers() -> None:
    env = load_local_minio_env()
    assert LOCAL_MINIO_ENV_PATH.name == "minio.env"
    assert env[COMPOSE_MINIO_API_PORT_VAR] == str(LOCAL_MINIO_API_PORT)
    assert env[COMPOSE_MINIO_CONSOLE_PORT_VAR] == str(LOCAL_MINIO_CONSOLE_PORT)
    assert env[COMPOSE_MINIO_CONTAINER_API_PORT_VAR] == str(LOCAL_MINIO_CONTAINER_API_PORT)
    assert env[COMPOSE_MINIO_CONTAINER_CONSOLE_PORT_VAR] == str(LOCAL_MINIO_CONTAINER_CONSOLE_PORT)
    assert env["MINIO_HOST"] == LOCAL_MINIO_HOST
    assert LOCAL_MINIO_CONTAINER_API_PORT == 9000
    assert LOCAL_MINIO_CONTAINER_CONSOLE_PORT == 9001


def test_compose_yaml_interpolates_minio_env_keys() -> None:
    compose = (_repo_root() / "tests" / "docker-compose.yml").read_text(encoding="utf-8")
    assert str(LOCAL_MINIO_API_PORT) not in compose
    assert str(LOCAL_MINIO_CONSOLE_PORT) not in compose
    assert f"${{{COMPOSE_MINIO_API_PORT_VAR}}}:${{{COMPOSE_MINIO_CONTAINER_API_PORT_VAR}}}" in compose
    assert f"${{{COMPOSE_MINIO_CONSOLE_PORT_VAR}}}:${{{COMPOSE_MINIO_CONTAINER_CONSOLE_PORT_VAR}}}" in compose
    assert f'--address ":${{{COMPOSE_MINIO_CONTAINER_API_PORT_VAR}}}"' in compose
    assert f"http://localhost:${{{COMPOSE_MINIO_CONTAINER_API_PORT_VAR}}}/minio/health/live" in compose


def test_shell_scripts_pass_minio_env_to_compose() -> None:
    repo = _repo_root()
    env_rel = "mindtrace/core/mindtrace/core/testing/minio.env"
    helper = (repo / "scripts" / "test_stack_compose.sh").read_text(encoding="utf-8")
    docker_up = (repo / "scripts" / "docker_up.sh").read_text(encoding="utf-8")
    run_tests = (repo / "scripts" / "run_tests.sh").read_text(encoding="utf-8")

    assert env_rel in helper
    assert "--env-file" in helper
    assert "uv run" not in docker_up
    assert "test_stack_compose.sh" in docker_up
    assert "MINDTRACE_MINIO_ENV" in docker_up
    assert "test_stack_compose.sh" in run_tests
    assert "mindtrace_test_compose down" in run_tests
    assert "uv run" not in helper
