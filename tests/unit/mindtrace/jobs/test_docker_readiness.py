import os
import subprocess
from pathlib import Path

import pytest


def _write_command(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


def test_docker_readiness_failure_honors_configured_deadline(tmp_path):
    """A broken service must fail setup promptly instead of hanging the CI job."""
    docker_calls = tmp_path / "docker-calls.txt"
    _write_command(
        tmp_path,
        "docker",
        'printf "%s\\n" "$*" >> "$DOCKER_CALLS_FILE"\n'
        'case "$*" in\n'
        '  "compose version") exit 0 ;;\n'
        '  *"ps -a -q rabbitmq"*) echo rabbitmq-container; exit 0 ;;\n'
        '  *"inspect --format {{.State.Running}}"*) echo true; exit 0 ;;\n'
        '  *"rabbitmq-diagnostics"*) exit 1 ;;\n'
        "  *) exit 0 ;;\n"
        "esac",
    )
    _write_command(tmp_path, "curl", "exit 0")
    _write_command(tmp_path, "nc", "exit 0")

    project_root = Path(__file__).resolve().parents[4]
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    env["SERVICE_READY_TIMEOUT_SECONDS"] = "1"
    env["DOCKER_CALLS_FILE"] = str(docker_calls)

    try:
        result = subprocess.run(
            ["bash", "scripts/docker_up.sh"],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("docker_up.sh did not honor SERVICE_READY_TIMEOUT_SECONDS")

    assert result.returncode != 0
    assert "timed out" in (result.stdout + result.stderr).lower()
    calls = docker_calls.read_text()
    assert "ps -a" in calls
    assert "logs --no-color --tail=200" in calls
    assert "inspect --format {{json .State}} rabbitmq-container" in calls
    assert "exec -T --user rabbitmq rabbitmq rabbitmq-diagnostics -q ping" in calls


def test_docker_readiness_fails_immediately_when_rabbitmq_exits(tmp_path):
    """A crashed broker must not consume the remainder of the readiness deadline."""
    docker_calls = tmp_path / "docker-calls.txt"
    _write_command(
        tmp_path,
        "docker",
        'printf "%s\\n" "$*" >> "$DOCKER_CALLS_FILE"\n'
        'case "$*" in\n'
        '  "compose version") exit 0 ;;\n'
        '  *"ps -a -q rabbitmq"*) echo rabbitmq-container; exit 0 ;;\n'
        '  *"inspect --format {{.State.Running}}"*) echo false; exit 0 ;;\n'
        "  *) exit 0 ;;\n"
        "esac",
    )
    _write_command(tmp_path, "curl", "exit 0")
    _write_command(tmp_path, "nc", "exit 0")

    project_root = Path(__file__).resolve().parents[4]
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    env["SERVICE_READY_TIMEOUT_SECONDS"] = "120"
    env["DOCKER_CALLS_FILE"] = str(docker_calls)

    try:
        result = subprocess.run(
            ["bash", "scripts/docker_up.sh"],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("docker_up.sh waited for the deadline after RabbitMQ had exited")

    assert result.returncode != 0
    assert "rabbitmq container stopped before becoming ready" in (result.stdout + result.stderr).lower()
    calls = docker_calls.read_text()
    assert "logs --no-color --tail=200" in calls
    assert "rabbitmq-diagnostics" not in calls


def test_docker_healthchecks_use_correct_identity_and_port():
    """Healthchecks must not recreate the RabbitMQ cookie race or probe Redis on the wrong port."""
    project_root = Path(__file__).resolve().parents[4]
    compose = (project_root / "tests" / "docker-compose.yml").read_text()

    assert '["CMD", "gosu", "rabbitmq", "rabbitmq-diagnostics", "-q", "ping"]' in compose
    assert '["CMD", "redis-cli", "-p", "6380", "ping"]' in compose


def test_test_runner_aborts_when_docker_setup_fails(tmp_path):
    """A readiness failure must stop the runner before pytest or coverage starts."""
    coverage_calls = tmp_path / "coverage-calls.txt"
    _write_command(
        tmp_path,
        "docker",
        'case "$*" in\n'
        '  "compose version") exit 0 ;;\n'
        '  *"ps -a -q rabbitmq"*) echo rabbitmq-container; exit 0 ;;\n'
        '  *"inspect --format {{.State.Running}}"*) echo true; exit 0 ;;\n'
        '  *"rabbitmq-diagnostics"*) exit 1 ;;\n'
        "  *) exit 0 ;;\n"
        "esac",
    )
    _write_command(tmp_path, "curl", "exit 0")
    _write_command(tmp_path, "nc", "exit 0")
    _write_command(tmp_path, "coverage", 'printf "%s\\n" "$*" >> "$COVERAGE_CALLS_FILE"')

    project_root = Path(__file__).resolve().parents[4]
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    env["SERVICE_READY_TIMEOUT_SECONDS"] = "1"
    env["COVERAGE_CALLS_FILE"] = str(coverage_calls)

    try:
        result = subprocess.run(
            ["bash", "scripts/run_tests.sh", "--integration", "jobs"],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("run_tests.sh did not stop after Docker setup failed")

    assert result.returncode != 0
    assert "aborting before pytest" in (result.stdout + result.stderr).lower()
    assert not coverage_calls.exists()
