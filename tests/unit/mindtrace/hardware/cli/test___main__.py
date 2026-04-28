"""Unit tests for the hardware CLI Typer app (``__main__``)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from mindtrace.hardware.cli.__main__ import app


@pytest.fixture(autouse=True)
def _cli_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_version_prints_and_exits_zero(runner: CliRunner) -> None:
    from mindtrace.hardware.cli import __version__

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
    assert "mindtrace-hw version" in result.stdout


def test_root_help_lists_service_commands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "camera" in result.stdout
    assert "status" in result.stdout


def test_invoke_without_subcommand_shows_banner(runner: CliRunner) -> None:
    with patch("mindtrace.hardware.cli.__main__.show_banner") as banner:
        result = runner.invoke(app, [])
    assert result.exit_code == 0
    banner.assert_called_once()
    assert "mindtrace-hw --help" in result.stdout or "--help" in result.stdout


def test_status_delegates_to_status_command(runner: CliRunner) -> None:
    with patch("mindtrace.hardware.cli.__main__.status_command") as sc:
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    sc.assert_called_once()


def test_stop_no_running_services(runner: CliRunner) -> None:
    with patch("mindtrace.hardware.cli.__main__.ProcessManager") as PM:
        PM.return_value.get_status.return_value = {
            "camera_api": {"running": False, "pid": 0},
        }
        with patch("mindtrace.hardware.cli.__main__.RichLogger") as RL:
            result = runner.invoke(app, ["stop"])
    assert result.exit_code == 0
    PM.return_value.stop_all.assert_not_called()
    RL.return_value.info.assert_called()


def test_stop_invokes_stop_all_when_services_running(runner: CliRunner) -> None:
    with patch("mindtrace.hardware.cli.__main__.ProcessManager") as PM:
        PM.return_value.get_status.return_value = {
            "camera_api": {"running": True, "pid": 1},
            "plc_api": {"running": True, "pid": 2},
        }
        with patch("mindtrace.hardware.cli.__main__.RichLogger"):
            result = runner.invoke(app, ["stop"])
    assert result.exit_code == 0
    PM.return_value.stop_all.assert_called_once()


def test_logs_rejects_unknown_service(runner: CliRunner) -> None:
    result = runner.invoke(app, ["logs", "not-a-service"])
    assert result.exit_code == 1
    out = (result.stdout or "") + (result.stderr or "")
    assert "Invalid service" in out


def test_logs_camera_prints_locations(runner: CliRunner) -> None:
    result = runner.invoke(app, ["logs", "camera"])
    assert result.exit_code == 0
    assert "camera" in result.stdout.lower() or "log" in result.stdout.lower()
