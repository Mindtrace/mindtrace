"""Unit tests for ``ProcessManager`` (filesystem and subprocess behavior mocked)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import psutil
import pytest

from mindtrace.hardware.cli.core.process_manager import ProcessManager


@pytest.fixture
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_init_creates_mindtrace_dir_and_empty_processes(isolated_home: Path) -> None:
    pm = ProcessManager()
    assert (isolated_home / ".mindtrace").is_dir()
    assert pm.processes == {}
    assert not pm.pid_file.exists()


def test_load_pids_missing_file(isolated_home: Path) -> None:
    pm = ProcessManager()
    assert pm.processes == {}


def test_load_pids_corrupt_json(isolated_home: Path) -> None:
    d = isolated_home / ".mindtrace"
    d.mkdir(parents=True)
    (d / "hw_services.json").write_text("{not json")
    pm = ProcessManager()
    assert pm.processes == {}


def test_load_pids_removes_dead_processes(isolated_home: Path) -> None:
    d = isolated_home / ".mindtrace"
    d.mkdir(parents=True)
    payload = {"old_svc": {"pid": 999001, "host": "localhost", "port": 1}}
    (d / "hw_services.json").write_text(json.dumps(payload))

    with patch("mindtrace.hardware.cli.core.process_manager.psutil.Process") as mock_proc:
        mock_proc.side_effect = psutil.NoSuchProcess(999001)
        pm = ProcessManager()

    assert pm.processes == {}
    assert pm.pid_file.exists()
    saved = json.loads(pm.pid_file.read_text())
    assert saved == {}


def test_save_pids_roundtrip(isolated_home: Path) -> None:
    pm = ProcessManager()
    pm.processes = {"svc": {"pid": 42, "host": "h", "port": 3}}
    pm.save_pids()
    raw = json.loads(pm.pid_file.read_text())
    assert raw["svc"]["pid"] == 42


_ENV_FOR_START_METHOD: dict[str, list[str]] = {
    "start_plc_api": ["PLC_API_HOST", "PLC_API_PORT", "PLC_API_URL"],
    "start_stereo_camera_api": [
        "STEREO_CAMERA_API_HOST",
        "STEREO_CAMERA_API_PORT",
        "STEREO_CAMERA_API_URL",
    ],
    "start_scanner_3d_api": ["SCANNER_3D_API_HOST", "SCANNER_3D_API_PORT", "SCANNER_3D_API_URL"],
}


@patch("mindtrace.hardware.cli.core.process_manager.time.sleep")
def test_start_camera_api_success(mock_sleep: MagicMock, isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("CAMERA_API_HOST", "CAMERA_API_PORT", "CAMERA_API_URL"):
        monkeypatch.delenv(key, raising=False)
    mock_proc = MagicMock()
    mock_proc.pid = 4242
    mock_proc.poll.return_value = None
    with patch("mindtrace.hardware.cli.core.process_manager.subprocess.Popen", return_value=mock_proc) as popen:
        pm = ProcessManager()
        out = pm.start_camera_api(host="127.0.0.1", port=9000, include_mocks=True)

    assert out is mock_proc
    popen.assert_called_once()
    cmd = popen.call_args[0][0]
    assert cmd[:5] == [sys.executable, "-m", "mindtrace.hardware.services.cameras.launcher", "--host", "127.0.0.1"]
    assert cmd[5] == "--port"
    assert cmd[6] == "9000"
    assert "--include-mocks" in cmd
    assert pm.processes["camera_api"]["pid"] == 4242
    assert pm.processes["camera_api"]["host"] == "127.0.0.1"
    assert pm.processes["camera_api"]["port"] == 9000
    assert mock_sleep.call_count >= 1
    assert os.environ["CAMERA_API_URL"] == "http://127.0.0.1:9000"


@patch("mindtrace.hardware.cli.core.process_manager.time.sleep")
def test_start_camera_api_poll_non_none_raises(mock_sleep: MagicMock, isolated_home: Path) -> None:
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 1
    with patch("mindtrace.hardware.cli.core.process_manager.subprocess.Popen", return_value=mock_proc):
        pm = ProcessManager()
        with pytest.raises(RuntimeError, match="Failed to start camera API"):
            pm.start_camera_api(host="h", port=1)
    assert "camera_api" not in pm.processes


@patch("mindtrace.hardware.cli.core.process_manager.time.sleep")
@pytest.mark.parametrize(
    "method, key, launcher_mod",
    [
        ("start_plc_api", "plc_api", "mindtrace.hardware.services.plcs.launcher"),
        ("start_stereo_camera_api", "stereo_camera_api", "mindtrace.hardware.services.stereo_cameras.launcher"),
        ("start_scanner_3d_api", "scanner_3d_api", "mindtrace.hardware.services.scanners_3d.launcher"),
    ],
)
def test_start_other_apis_set_env_and_store_pid(
    mock_sleep: MagicMock,
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    key: str,
    launcher_mod: str,
) -> None:
    for env_key in _ENV_FOR_START_METHOD[method]:
        monkeypatch.delenv(env_key, raising=False)
    mock_proc = MagicMock()
    mock_proc.pid = 777
    mock_proc.poll.return_value = None
    with patch("mindtrace.hardware.cli.core.process_manager.subprocess.Popen", return_value=mock_proc):
        pm = ProcessManager()
        getattr(pm, method)(host="10.0.0.1", port=6000)

    assert pm.processes[key]["pid"] == 777
    cmd = " ".join([sys.executable, "-m", launcher_mod, "--host", "10.0.0.1", "--port", "6000"])
    assert pm.processes[key]["command"] == cmd


def test_stop_service_unknown_returns_false(isolated_home: Path) -> None:
    pm = ProcessManager()
    assert pm.stop_service("missing") is False


def test_stop_service_removes_and_saves(isolated_home: Path) -> None:
    pm = ProcessManager()
    pm.processes = {"plc_api": {"pid": 333, "host": "x", "port": 1}}
    pm.save_pids()

    with (
        patch("mindtrace.hardware.cli.core.process_manager.os.kill") as mock_kill,
        patch.object(ProcessManager, "_is_process_running", return_value=False),
    ):
        assert pm.stop_service("plc_api") is True

    mock_kill.assert_called()
    assert "plc_api" not in pm.processes
    disk = pm.pid_file.read_text()
    assert "plc_api" not in json.loads(disk)


def test_get_status_includes_uptime_when_running(isolated_home: Path) -> None:
    pm = ProcessManager()
    pm.processes = {
        "camera_api": {
            "pid": 1,
            "host": "localhost",
            "port": 8002,
            "start_time": "t",
        }
    }
    mock_ps_instance = MagicMock()
    mock_ps_instance.is_running.return_value = True
    mock_ps_instance.create_time.return_value = time.time() - 125
    mock_ps_instance.memory_info.return_value = MagicMock(rss=4 * 1024 * 1024)

    with patch("mindtrace.hardware.cli.core.process_manager.psutil.Process", return_value=mock_ps_instance):
        status = pm.get_status()

    assert status["camera_api"]["running"] is True
    assert status["camera_api"]["uptime"] == "2m 5s"
    assert status["camera_api"]["memory_mb"] == 4.0


def test_is_service_running_false_when_unknown(isolated_home: Path) -> None:
    pm = ProcessManager()
    assert pm.is_service_running("nope") is False


def test_stop_all_calls_stop_for_each_tracked_service(isolated_home: Path) -> None:
    pm = ProcessManager()
    pm.processes = {"a": {"pid": 1}, "b": {"pid": 2}}
    with patch.object(pm, "stop_service") as mock_stop:
        pm.stop_all()
    assert mock_stop.call_count == 2
    names = {call.args[0] for call in mock_stop.call_args_list}
    assert names == {"a", "b"}
