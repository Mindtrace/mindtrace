"""Guard test-stack MinIO host port interpolation against CoreConfig env names."""

from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "tests" / "docker-compose.yml").is_file() and (parent / "pyproject.toml").is_file():
            return parent
    raise AssertionError("could not locate repository root from test file path")


def test_compose_interpolates_mindtrace_minio_host_port() -> None:
    compose = (_repo_root() / "tests" / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"${MINDTRACE_MINIO__MINIO_PORT:-19000}:9000"' in compose
    assert '"19000:9000"' not in compose
    assert '--address ":9000"' in compose
    assert "http://localhost:9000/minio/health/live" in compose


def test_docker_up_exports_minio_port_before_compose_up() -> None:
    docker_up = (_repo_root() / "scripts" / "docker_up.sh").read_text(encoding="utf-8")
    export_at = docker_up.index("export MINDTRACE_MINIO__MINIO_PORT=19000")
    up_at = docker_up.index("mindtrace_test_compose up")
    assert export_at < up_at
    assert "minio.env" not in docker_up
    helper = (_repo_root() / "scripts" / "test_stack_compose.sh").read_text(encoding="utf-8")
    assert "--env-file" not in helper
