"""Guard test-stack MinIO port mapping and docker_up exports."""

from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "tests" / "docker-compose.yml").is_file() and (parent / "pyproject.toml").is_file():
            return parent
    raise AssertionError("could not locate repository root from test file path")


def test_compose_publishes_test_stack_minio_on_host_19000() -> None:
    compose = (_repo_root() / "tests" / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"19000:9000"' in compose
    assert '--address ":9000"' in compose
    assert "http://localhost:9000/minio/health/live" in compose


def test_docker_up_exports_minio_endpoint_before_compose_up() -> None:
    docker_up = (_repo_root() / "scripts" / "docker_up.sh").read_text(encoding="utf-8")
    export_at = docker_up.index("export MINDTRACE_MINIO__MINIO_ENDPOINT=localhost:19000")
    up_at = docker_up.index("mindtrace_test_compose up")
    assert export_at < up_at
    assert "minio.env" not in docker_up
    helper = (_repo_root() / "scripts" / "test_stack_compose.sh").read_text(encoding="utf-8")
    assert "--env-file" not in helper


def test_run_tests_sources_docker_up_for_stress() -> None:
    """ds test --stress must export test-stack MinIO before pytest, not product :9000."""
    run_tests = (_repo_root() / "scripts" / "run_tests.sh").read_text(encoding="utf-8")
    stress_at = run_tests.index("--stress)")
    needs_docker_at = run_tests.index("NEEDS_DOCKER=true", stress_at)
    next_case_at = run_tests.index("--utils)", stress_at)
    assert needs_docker_at < next_case_at
    assert "tests/stress/*" in run_tests
    assert '[ "$RUN_STRESS" = true ]' in run_tests
