"""Tests for GenICam setup utilities and CLI wrappers."""

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from mindtrace.hardware.cameras.setup.setup_genicam import (
    GenICamCTIInstaller,
    app,
    install_genicam_cti,
    uninstall_genicam_cti,
    verify_genicam_cti,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def _block_unmocked_privileged_subprocess_calls(monkeypatch):
    """Fail fast if a test leaks a real privileged subprocess call."""

    original_run = subprocess.run

    def guarded_run(cmd, *args, **kwargs):
        if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "sudo":
            raise AssertionError(f"Unexpected real privileged subprocess call: {cmd!r}")
        return original_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", guarded_run)


def _mock_hw_config():
    cfg = Mock()
    cfg.paths.lib_dir = "/tmp"
    hw = Mock()
    hw.get_config.return_value = cfg
    return hw


@patch("mindtrace.hardware.cameras.setup.setup_genicam.get_hardware_config", return_value=_mock_hw_config())
def test_verify_installation_missing_file(_):
    inst = GenICamCTIInstaller()
    inst.platform = "Linux"
    with patch("os.path.exists", return_value=False):
        assert inst.verify_installation() is False


@patch("mindtrace.hardware.cameras.setup.setup_genicam.get_hardware_config", return_value=_mock_hw_config())
def test_verify_installation_small_file_fails(_):
    inst = GenICamCTIInstaller()
    inst.platform = "Linux"
    with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=512 * 1024):
        assert inst.verify_installation() is False


@patch("mindtrace.hardware.cameras.setup.setup_genicam.get_hardware_config", return_value=_mock_hw_config())
def test_verify_installation_large_file_succeeds(_):
    inst = GenICamCTIInstaller()
    inst.platform = "Linux"
    with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=2 * 1024 * 1024):
        assert inst.verify_installation() is True


@patch("mindtrace.hardware.cameras.setup.setup_genicam.get_hardware_config", return_value=_mock_hw_config())
def test_install_dispatch_unsupported_platform(_):
    inst = GenICamCTIInstaller()
    inst.platform = "Solaris"
    assert inst.install() is False


@patch("mindtrace.hardware.cameras.setup.setup_genicam.get_hardware_config", return_value=_mock_hw_config())
def test_find_install_script(_):
    inst = GenICamCTIInstaller()
    with patch("os.path.exists", side_effect=lambda p: p == "setup.sh"):
        assert inst._find_install_script() == "setup.sh"


@patch("mindtrace.hardware.cameras.setup.setup_genicam.get_hardware_config", return_value=_mock_hw_config())
def test_wrapper_functions_delegate(_):
    with patch.object(GenICamCTIInstaller, "install", return_value=True) as mi:
        assert install_genicam_cti() is True
        mi.assert_called_once()
    with patch.object(GenICamCTIInstaller, "uninstall", return_value=False) as mu:
        assert uninstall_genicam_cti() is False
        mu.assert_called_once()
    with patch.object(GenICamCTIInstaller, "verify_installation", return_value=True) as mv:
        assert verify_genicam_cti() is True
        mv.assert_called_once()


@patch("mindtrace.hardware.cameras.setup.setup_genicam.GenICamCTIInstaller")
def test_cli_verify_success(mock_installer):
    inst = Mock()
    inst.verify_installation.return_value = True
    inst.logger = Mock()
    mock_installer.return_value = inst

    result = runner.invoke(app, ["verify"])
    assert result.exit_code == 0


@patch("mindtrace.hardware.cameras.setup.setup_genicam.GenICamCTIInstaller")
def test_cli_install_failure(mock_installer):
    inst = Mock()
    inst.install.return_value = False
    inst.logger = Mock()
    mock_installer.return_value = inst

    result = runner.invoke(app, ["install"])
    assert result.exit_code == 1


def _installer(tmp_path):
    cfg = Mock()
    cfg.paths.lib_dir = str(tmp_path)
    hw = Mock()
    hw.get_config.return_value = cfg
    with patch("mindtrace.hardware.cameras.setup.setup_genicam.get_hardware_config", return_value=hw):
        return GenICamCTIInstaller()


def test_get_cti_path_unknown_platform_returns_empty(tmp_path):
    inst = _installer(tmp_path)
    inst.platform = "Unknown"
    assert inst.get_cti_path() == ""


def test_install_dispatch_windows_and_macos(tmp_path):
    inst = _installer(tmp_path)

    inst.platform = "Windows"
    with patch.object(inst, "_install_windows", return_value=True) as w:
        assert inst.install() is True
        w.assert_called_once()

    inst.platform = "Darwin"
    with patch.object(inst, "_install_macos", return_value=False) as m:
        assert inst.install() is False
        m.assert_called_once()


def test_install_linux_manual_with_debs(tmp_path):
    inst = _installer(tmp_path)

    deb = tmp_path / "a.deb"
    deb.write_text("x")

    calls = []

    def fake_run(cmd):
        calls.append(cmd)

    with patch("pathlib.Path.glob", return_value=[deb]), patch.object(inst, "_run_command", side_effect=fake_run):
        inst._install_linux_manual()

    assert ["sudo", "dpkg", "-i", str(deb)] in calls
    assert ["sudo", "apt-get", "-f", "install", "-y"] in calls


def test_install_linux_manual_without_debs(tmp_path):
    inst = _installer(tmp_path)

    calls = []

    def fake_run(cmd):
        calls.append(cmd)

    with patch("pathlib.Path.glob", return_value=[]), patch.object(inst, "_run_command", side_effect=fake_run):
        inst._install_linux_manual()

    assert ["sudo", "mkdir", "-p", "/opt/ImpactAcquire"] in calls
    assert ["sudo", "chmod", "-R", "755", "/opt/ImpactAcquire"] in calls


def test_find_install_script_none_when_missing(tmp_path):
    inst = _installer(tmp_path)
    with patch("os.path.exists", return_value=False):
        assert inst._find_install_script() is None


def test_verify_installation_returns_false_when_platform_has_no_cti_path(tmp_path):
    inst = _installer(tmp_path)
    inst.platform = "Unknown"

    assert inst.verify_installation() is False


def test_install_wraps_unexpected_exception(tmp_path):
    inst = _installer(tmp_path)
    inst.platform = "Linux"

    with patch.object(inst, "_install_linux", side_effect=RuntimeError("boom")):
        assert inst.install() is False


def test_install_linux_happy_path(tmp_path):
    inst = _installer(tmp_path)
    installer_path = tmp_path / "impact_acquire" / "ImpactAcquire-installer.sh"
    commands = []

    def fake_run(cmd):
        commands.append(cmd)

    with (
        patch.object(inst, "_run_command", side_effect=fake_run),
        patch.object(inst, "verify_installation", return_value=True),
        patch("urllib.request.urlretrieve") as urlretrieve,
    ):
        assert inst._install_linux() is True

    urlretrieve.assert_called_once_with(inst.LINUX_SDK_URL, installer_path)
    assert ["chmod", "+x", str(installer_path)] in commands
    assert ["sudo", "bash", str(installer_path)] in commands


def test_install_linux_returns_false_when_verification_fails(tmp_path):
    inst = _installer(tmp_path)

    with (
        patch.object(inst, "_run_command"),
        patch.object(inst, "verify_installation", return_value=False),
        patch("urllib.request.urlretrieve"),
    ):
        assert inst._install_linux() is False


def test_install_linux_returns_false_on_file_not_found(tmp_path):
    inst = _installer(tmp_path)

    with (
        patch.object(inst, "_run_command"),
        patch("urllib.request.urlretrieve", side_effect=FileNotFoundError("missing")),
    ):
        assert inst._install_linux() is False


def test_install_windows_non_admin_delegates_to_elevation(tmp_path):
    inst = _installer(tmp_path)
    fake_windll = SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=Mock(return_value=0)))

    with (
        patch("mindtrace.hardware.cameras.setup.setup_genicam.ctypes.windll", fake_windll, create=True),
        patch.object(inst, "_elevate_privileges", return_value=False) as elevate,
    ):
        assert inst._install_windows() is False

    elevate.assert_called_once_with()


def test_install_windows_admin_happy_path(tmp_path):
    inst = _installer(tmp_path)
    installer_file = tmp_path / "impact_acquire" / "ImpactAcquire-installer.exe"
    fake_windll = SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=Mock(return_value=1)))

    with (
        patch("mindtrace.hardware.cameras.setup.setup_genicam.ctypes.windll", fake_windll, create=True),
        patch("urllib.request.urlretrieve") as urlretrieve,
        patch("subprocess.run") as run,
        patch.object(inst, "verify_installation", return_value=True),
    ):
        assert inst._install_windows() is True

    urlretrieve.assert_called_once_with(inst.WINDOWS_SDK_URL, installer_file)
    run.assert_called_once_with([str(installer_file)], check=True)


def test_install_windows_returns_false_on_called_process_error(tmp_path):
    inst = _installer(tmp_path)
    fake_windll = SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=Mock(return_value=1)))

    with (
        patch("mindtrace.hardware.cameras.setup.setup_genicam.ctypes.windll", fake_windll, create=True),
        patch("urllib.request.urlretrieve"),
        patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, ["installer"])),
    ):
        assert inst._install_windows() is False


def test_install_macos_pkg_branch(tmp_path):
    inst = _installer(tmp_path)
    dmg_file = tmp_path / "impact_acquire" / "ImpactAcquire.dmg"
    mount_path = "/Volumes/ImpactAcquire"
    pkg = Path("/Volumes/ImpactAcquire/ImpactAcquire.pkg")
    mount_result = Mock(stdout=f"/dev/disk4\tApple_HFS\t{mount_path}\n")

    with (
        patch("urllib.request.urlretrieve") as urlretrieve,
        patch("subprocess.run", side_effect=[mount_result, Mock(), Mock()]) as run,
        patch("pathlib.Path.glob", side_effect=[[pkg], []]),
        patch.object(inst, "verify_installation", return_value=True),
    ):
        assert inst._install_macos() is True

    urlretrieve.assert_called_once_with(inst.MACOS_SDK_URL, dmg_file)
    assert run.call_args_list[1].args[0][:3] == ["sudo", "installer", "-pkg"]
    assert run.call_args_list[2].args[0] == ["hdiutil", "detach", mount_path]


def test_install_macos_app_branch_replaces_existing_app(tmp_path):
    inst = _installer(tmp_path)
    mount_path = "/Volumes/ImpactAcquire"
    app_file = Path("/Volumes/ImpactAcquire/mvIMPACT_Acquire.app")
    mount_result = Mock(stdout=f"/dev/disk4\tApple_HFS\t{mount_path}\n")

    with (
        patch("urllib.request.urlretrieve"),
        patch("subprocess.run", side_effect=[mount_result, Mock()]),
        patch("pathlib.Path.glob", side_effect=[[], [app_file]]),
        patch("mindtrace.hardware.cameras.setup.setup_genicam.Path.exists", return_value=True),
        patch("shutil.rmtree") as rmtree,
        patch("shutil.copytree") as copytree,
        patch.object(inst, "verify_installation", return_value=True),
    ):
        assert inst._install_macos() is True

    rmtree.assert_called_once()
    copytree.assert_called_once()


def test_install_macos_returns_false_when_mount_point_missing(tmp_path):
    inst = _installer(tmp_path)
    mount_result = Mock(stdout="no volumes here")

    with (
        patch("urllib.request.urlretrieve"),
        patch("subprocess.run", return_value=mount_result),
    ):
        assert inst._install_macos() is False


def test_elevate_privileges_handles_shell_execute_error(tmp_path):
    inst = _installer(tmp_path)
    fake_windll = SimpleNamespace(shell32=SimpleNamespace(ShellExecuteW=Mock(side_effect=RuntimeError("boom"))))

    with patch("mindtrace.hardware.cameras.setup.setup_genicam.ctypes.windll", fake_windll, create=True):
        assert inst._elevate_privileges() is False


def test_uninstall_wraps_unexpected_exception(tmp_path):
    inst = _installer(tmp_path)
    inst.platform = "Linux"

    with patch.object(inst, "_uninstall_linux", side_effect=RuntimeError("boom")):
        assert inst.uninstall() is False


def test_uninstall_linux_removes_install_dir_when_present(tmp_path):
    inst = _installer(tmp_path)
    calls = []

    def fake_subprocess_run(cmd, check=False):
        calls.append((cmd, check))
        return Mock()

    with (
        patch("subprocess.run", side_effect=fake_subprocess_run),
        patch("os.path.exists", side_effect=lambda path: path == "/opt/ImpactAcquire"),
        patch.object(inst, "_run_command") as run_command,
    ):
        assert inst._uninstall_linux() is True

    assert any(call[0][:4] == ["sudo", "apt-get", "remove", "-y"] for call in calls)
    run_command.assert_any_call(["sudo", "rm", "-rf", "/opt/ImpactAcquire"])
    run_command.assert_any_call(["sudo", "apt-get", "autoremove", "-y"])


def test_uninstall_macos_removes_app_and_extra_dirs(tmp_path):
    inst = _installer(tmp_path)
    removed = []

    def fake_exists(path):
        return path in {
            "/Applications/mvIMPACT_Acquire.app",
            "/usr/local/lib/mvIMPACT_Acquire",
        }

    with (
        patch("os.path.exists", side_effect=fake_exists),
        patch("shutil.rmtree") as rmtree,
        patch("subprocess.run", side_effect=lambda cmd, check=False: removed.append(cmd) or Mock()),
    ):
        assert inst._uninstall_macos() is True

    rmtree.assert_called_once_with("/Applications/mvIMPACT_Acquire.app")
    assert ["sudo", "rm", "-rf", "/usr/local/lib/mvIMPACT_Acquire"] in removed


def test_cli_uninstall_failure_and_verify_verbose(tmp_path):
    installer = Mock()
    installer.uninstall.return_value = False
    installer.verify_installation.return_value = True
    installer.logger = Mock()

    with patch("mindtrace.hardware.cameras.setup.setup_genicam.GenICamCTIInstaller", return_value=installer):
        uninstall_result = runner.invoke(app, ["uninstall"])
        verify_result = runner.invoke(app, ["verify", "--verbose"])

    assert uninstall_result.exit_code == 1
    assert verify_result.exit_code == 0
    installer.logger.setLevel.assert_called_once()
