import os
import re
import subprocess
from pathlib import Path

import pytest


def _write_command(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


def test_docker_readiness_failure_honors_configured_deadline(tmp_path):
    """A broken service must fail setup promptly instead of hanging the CI job."""
    _write_command(
        tmp_path,
        "docker",
        'case "$*" in\n'
        '  "compose version") exit 0 ;;\n'
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


def test_ci_test_job_has_a_hard_timeout():
    project_root = Path(__file__).resolve().parents[4]
    workflow = (project_root / ".github" / "workflows" / "ci.yml").read_text()
    test_job = re.search(r"(?ms)^  test:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)", workflow)

    assert test_job is not None, "The CI workflow must define its test job."
    assert re.search(
        r"(?m)^    timeout-minutes:\s*[1-9][0-9]*\s*$",
        test_job.group("body"),
    ), "The CI test job needs a hard upper bound even if test setup stalls."
