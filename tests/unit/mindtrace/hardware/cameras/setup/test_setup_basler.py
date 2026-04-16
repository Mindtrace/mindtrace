"""Tests for Basler SDK setup functionality."""

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from mindtrace.hardware.cameras.setup.setup_basler import (
    PylonSDKInstaller,
    app,
)

runner = CliRunner()


class TestPylonSDKInstaller:
    """Test cases for PylonSDKInstaller class."""

    def test_installer_initialization(self):
        """Test PylonSDKInstaller initialization."""
        installer = PylonSDKInstaller()

        # Should be a Mindtrace instance
        from mindtrace.core import Mindtrace

        assert isinstance(installer, Mindtrace)

        # Should have expected attributes
        assert hasattr(installer, "logger")
        assert installer.logger is not None

    def test_installer_has_platform_info(self):
        """Test that installer has platform information defined."""
        PylonSDKInstaller()

        # Should have class-level platform constants
        assert hasattr(PylonSDKInstaller, "BASLER_DOWNLOAD_PAGE")
        assert hasattr(PylonSDKInstaller, "PLATFORM_INFO")

        # Download page should be a non-empty string
        assert isinstance(PylonSDKInstaller.BASLER_DOWNLOAD_PAGE, str)
        assert len(PylonSDKInstaller.BASLER_DOWNLOAD_PAGE) > 0

        # Platform info should contain Linux and Windows
        assert "Linux" in PylonSDKInstaller.PLATFORM_INFO
        assert "Windows" in PylonSDKInstaller.PLATFORM_INFO

    def test_installer_methods_exist(self):
        """Test that installer has expected methods."""
        installer = PylonSDKInstaller()

        # Should have installation methods
        assert hasattr(installer, "install")
        assert hasattr(installer, "uninstall")
        assert callable(installer.install)
        assert callable(installer.uninstall)

    def test_platform_info_structure(self):
        """Test platform info has expected structure."""
        for platform_name, info in PylonSDKInstaller.PLATFORM_INFO.items():
            assert "search_term" in info
            assert "file_pattern" in info
            assert "file_description" in info
            assert "min_size_mb" in info

    def test_linux_dependencies_defined(self):
        """Test that Linux dependencies are defined."""
        assert hasattr(PylonSDKInstaller, "LINUX_DEPENDENCIES")
        assert isinstance(PylonSDKInstaller.LINUX_DEPENDENCIES, list)
        assert len(PylonSDKInstaller.LINUX_DEPENDENCIES) > 0

    def test_installer_accepts_package_path(self):
        """Test that installer accepts package_path parameter."""
        # Should be able to create installer with package path
        with patch.object(Path, "exists", return_value=True):
            installer = PylonSDKInstaller(package_path="/tmp/fake_package.tar.gz")
            assert installer.package_path == Path("/tmp/fake_package.tar.gz")

    def test_installer_without_package_path(self):
        """Test installer without package path defaults to None."""
        installer = PylonSDKInstaller()
        assert installer.package_path is None

    @patch("platform.system")
    def test_platform_detection_linux(self, mock_platform):
        """Test platform detection for Linux."""
        mock_platform.return_value = "Linux"

        installer = PylonSDKInstaller()

        # Should handle Linux platform
        assert installer is not None
        assert installer.platform == "Linux"

    @patch("platform.system")
    def test_platform_detection_windows(self, mock_platform):
        """Test platform detection for Windows."""
        mock_platform.return_value = "Windows"

        installer = PylonSDKInstaller()

        # Should handle Windows platform
        assert installer is not None
        assert installer.platform == "Windows"

    def test_installer_logging(self):
        """Test that installer has proper logging setup."""
        installer = PylonSDKInstaller()

        # Should have logger from Mindtrace base
        assert hasattr(installer, "logger")
        import logging

        assert isinstance(installer.logger, logging.Logger)


class TestInstallerInternals:
    """More targeted tests for installer internals to improve branch coverage."""

    def test_validate_package_rejects_small_file(self, tmp_path):
        installer = PylonSDKInstaller()
        package = tmp_path / "pylon_small.tar.gz"
        package.write_bytes(b"x" * 1024)

        info = {"min_size_mb": 100, "file_description": "x", "search_term": "x", "file_pattern": "x"}
        assert installer._validate_package(package, info) is False

    def test_validate_package_rejects_non_pylon_name(self, tmp_path):
        installer = PylonSDKInstaller()
        package = tmp_path / "camera_sdk.tar.gz"
        package.write_bytes(b"x" * (120 * 1024 * 1024))

        info = {"min_size_mb": 100, "file_description": "x", "search_term": "x", "file_pattern": "x"}
        assert installer._validate_package(package, info) is False

    def test_install_from_package_unsupported_platform(self, tmp_path):
        installer = PylonSDKInstaller()
        installer.platform = "Darwin"
        package = tmp_path / "pylon.pkg"
        package.write_text("dummy")

        assert installer._install_from_package(package) is False


class TestTyperCommands:
    """Test Typer CLI commands."""

    def test_install_command_exists(self):
        """Test that install command is registered."""
        # The app should have install command
        result = runner.invoke(app, ["install", "--help"])
        assert result.exit_code == 0
        assert "Install" in result.stdout or "install" in result.stdout

    def test_uninstall_command_exists(self):
        """Test that uninstall command is registered."""
        # The app should have uninstall command
        result = runner.invoke(app, ["uninstall", "--help"])
        assert result.exit_code == 0
        assert "Uninstall" in result.stdout or "uninstall" in result.stdout

    def test_install_has_package_option(self):
        """Test that install command has package option."""
        result = runner.invoke(app, ["install", "--help"])
        assert result.exit_code == 0
        assert "--package" in result.stdout or "-p" in result.stdout

    def test_install_has_verbose_option(self):
        """Test that install command has verbose option."""
        result = runner.invoke(app, ["install", "--help"])
        assert result.exit_code == 0
        assert "--verbose" in result.stdout or "-v" in result.stdout

    def test_uninstall_has_verbose_option(self):
        """Test that uninstall command has verbose option."""
        result = runner.invoke(app, ["uninstall", "--help"])
        assert result.exit_code == 0
        assert "--verbose" in result.stdout or "-v" in result.stdout

    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller")
    def test_install_command_creates_installer(self, mock_installer_class):
        """Test that install command creates and uses installer."""
        mock_installer = Mock()
        mock_installer.install.return_value = True
        mock_installer.logger = Mock()
        mock_installer_class.return_value = mock_installer

        result = runner.invoke(app, ["install"])

        # Should have created installer and called install
        mock_installer_class.assert_called_once_with(package_path=None)
        mock_installer.install.assert_called_once()
        assert result.exit_code == 0

    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller")
    def test_uninstall_command_creates_installer(self, mock_installer_class):
        """Test that uninstall command creates and uses installer."""
        mock_installer = Mock()
        mock_installer.uninstall.return_value = True
        mock_installer.logger = Mock()
        mock_installer_class.return_value = mock_installer

        result = runner.invoke(app, ["uninstall"])

        # Should have created installer and called uninstall
        mock_installer_class.assert_called_once()
        mock_installer.uninstall.assert_called_once()
        assert result.exit_code == 0

    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller")
    def test_install_returns_error_on_failure(self, mock_installer_class):
        """Test that install command returns error code on failure."""
        mock_installer = Mock()
        mock_installer.install.return_value = False
        mock_installer.logger = Mock()
        mock_installer_class.return_value = mock_installer

        result = runner.invoke(app, ["install"])

        assert result.exit_code == 1

    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller")
    def test_uninstall_returns_error_on_failure(self, mock_installer_class):
        """Test that uninstall command returns error code on failure."""
        mock_installer = Mock()
        mock_installer.uninstall.return_value = False
        mock_installer.logger = Mock()
        mock_installer_class.return_value = mock_installer

        result = runner.invoke(app, ["uninstall"])

        assert result.exit_code == 1


@pytest.fixture
def installer(tmp_path):
    cfg = Mock()
    cfg.paths.lib_dir = str(tmp_path)
    hw = Mock()
    hw.get_config.return_value = cfg

    with patch("mindtrace.hardware.cameras.setup.setup_basler.get_hardware_config", return_value=hw):
        inst = PylonSDKInstaller()
    return inst


def test_prompt_for_file_quit(installer):
    with patch("mindtrace.hardware.cameras.setup.setup_basler.typer.prompt", return_value="q"):
        assert installer._prompt_for_file(installer.PLATFORM_INFO["Linux"]) is None


def test_prompt_for_file_accepts_valid_path(installer, tmp_path):
    pkg = tmp_path / "pylon_ok.tar.gz"
    pkg.write_bytes(b"x" * (150 * 1024 * 1024))

    with patch("mindtrace.hardware.cameras.setup.setup_basler.typer.prompt", return_value=str(pkg)):
        got = installer._prompt_for_file(installer.PLATFORM_INFO["Linux"])

    assert got == pkg


def test_open_download_page_handles_browser_error(installer):
    with patch("mindtrace.hardware.cameras.setup.setup_basler.webbrowser.open", side_effect=RuntimeError("boom")):
        installer._open_download_page()


def test_install_from_package_dispatches_linux(installer, tmp_path):
    installer.platform = "Linux"
    pkg = tmp_path / "pylon.tar.gz"
    pkg.write_text("x")

    with patch.object(installer, "_install_linux", return_value=True) as m:
        assert installer._install_from_package(pkg) is True
        m.assert_called_once_with(pkg)


def test_install_from_package_dispatches_windows(installer, tmp_path):
    installer.platform = "Windows"
    pkg = tmp_path / "pylon.exe"
    pkg.write_text("x")

    with patch.object(installer, "_install_windows", return_value=True) as m:
        assert installer._install_from_package(pkg) is True
        m.assert_called_once_with(pkg)


def test_install_uses_package_path_without_wizard(installer, tmp_path):
    installer.platform = "Linux"
    installer.package_path = tmp_path / "pylon.tar.gz"

    with (
        patch.object(installer, "_install_from_package", return_value=True) as install_pkg,
        patch.object(installer, "_run_wizard") as wizard,
    ):
        assert installer.install() is True

    install_pkg.assert_called_once_with(installer.package_path)
    wizard.assert_not_called()


def test_install_runs_wizard_when_no_package(installer):
    installer.platform = "Linux"
    installer.package_path = None

    with patch.object(installer, "_run_wizard", return_value=True) as wizard:
        assert installer.install() is True

    wizard.assert_called_once_with()


def test_run_wizard_returns_false_when_user_declines(installer):
    installer.platform = "Linux"

    with (
        patch.object(installer, "_display_intro"),
        patch("mindtrace.hardware.cameras.setup.setup_basler.typer.confirm", return_value=False),
        patch.object(installer, "_open_download_page") as open_page,
    ):
        assert installer._run_wizard() is False

    open_page.assert_not_called()


def test_run_wizard_happy_path(installer, tmp_path):
    installer.platform = "Linux"
    pkg = tmp_path / "pylon.tar.gz"
    pkg.write_text("x")

    with (
        patch.object(installer, "_display_intro"),
        patch("mindtrace.hardware.cameras.setup.setup_basler.typer.confirm", return_value=True),
        patch.object(installer, "_open_download_page") as open_page,
        patch.object(installer, "_show_download_instructions") as instructions,
        patch("builtins.input", return_value=""),
        patch.object(installer, "_prompt_for_file", return_value=pkg) as prompt_file,
        patch.object(installer, "_install_from_package", return_value=True) as install_pkg,
    ):
        assert installer._run_wizard() is True

    open_page.assert_called_once_with()
    instructions.assert_called_once_with(installer.PLATFORM_INFO["Linux"])
    prompt_file.assert_called_once_with(installer.PLATFORM_INFO["Linux"])
    install_pkg.assert_called_once_with(pkg)


def test_prompt_for_file_reprompts_after_missing_file_and_accepts_anyway(installer, tmp_path):
    missing = tmp_path / "missing.tar.gz"
    pkg = tmp_path / "camera_sdk.tar.gz"
    pkg.write_bytes(b"x" * (150 * 1024 * 1024))

    with (
        patch(
            "mindtrace.hardware.cameras.setup.setup_basler.typer.prompt",
            side_effect=[str(missing), str(pkg)],
        ),
        patch("mindtrace.hardware.cameras.setup.setup_basler.typer.confirm", return_value=True),
    ):
        got = installer._prompt_for_file(installer.PLATFORM_INFO["Linux"])

    assert got == pkg


def test_install_linux_installs_debs(installer, tmp_path):
    installer.platform = "Linux"
    installer.pylon_dir = tmp_path / "pylon"
    pkg = tmp_path / "pylon_debs.tar.gz"
    pkg.write_bytes(b"x")

    deb1 = installer.pylon_dir / "a.deb"
    deb2 = installer.pylon_dir / "sub" / "b.deb"
    deb2.parent.mkdir(parents=True, exist_ok=True)
    deb1.write_text("a")
    deb2.write_text("b")

    class DummyTar:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extractall(self, path):
            return None

    calls = []

    def fake_run(cmd):
        calls.append(cmd)

    with patch("tarfile.open", return_value=DummyTar()), patch.object(installer, "_run_command", side_effect=fake_run):
        ok = installer._install_linux(pkg)

    assert ok is True
    assert any(cmd[:3] == ["sudo", "apt-get", "update"] for cmd in calls)
    assert any(cmd[:3] == ["sudo", "dpkg", "-i"] for cmd in calls)


def test_install_from_package_wraps_exceptions(installer, tmp_path):
    installer.platform = "Linux"
    pkg = tmp_path / "pylon.tar.gz"
    pkg.write_text("x")

    with patch.object(installer, "_install_linux", side_effect=RuntimeError("boom")):
        assert installer._install_from_package(pkg) is False


def test_install_linux_returns_false_for_unsupported_archive(installer, tmp_path):
    installer.platform = "Linux"
    installer.pylon_dir = tmp_path / "pylon"
    pkg = tmp_path / "pylon.zip"
    pkg.write_text("x")

    assert installer._install_linux(pkg) is False


def test_install_linux_returns_false_on_called_process_error(installer, tmp_path):
    installer.platform = "Linux"
    installer.pylon_dir = tmp_path / "pylon"
    pkg = tmp_path / "pylon.tar.gz"
    pkg.write_bytes(b"x")
    deb = installer.pylon_dir / "a.deb"
    deb.parent.mkdir(parents=True, exist_ok=True)
    deb.write_text("x")

    class DummyTar:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extractall(self, path):
            return None

    with (
        patch("tarfile.open", return_value=DummyTar()),
        patch.object(
            installer,
            "_run_command",
            side_effect=subprocess.CalledProcessError(1, ["sudo", "apt-get", "update"]),
        ),
    ):
        assert installer._install_linux(pkg) is False


def test_install_windows_runs_exe(installer, tmp_path):
    installer.platform = "Windows"
    pkg = tmp_path / "Basler_pylon.exe"
    pkg.write_text("x")
    fake_windll = SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=Mock(return_value=1)))

    with (
        patch("mindtrace.hardware.cameras.setup.setup_basler.ctypes.windll", fake_windll, create=True),
        patch("subprocess.run") as run,
        patch.object(installer, "_show_success_message") as success,
    ):
        assert installer._install_windows(pkg) is True

    run.assert_called_once_with([str(pkg)], check=True)
    success.assert_called_once_with()


def test_install_windows_returns_false_when_zip_has_no_exe(installer, tmp_path):
    installer.platform = "Windows"
    installer.pylon_dir = tmp_path / "pylon"
    pkg = tmp_path / "Basler_pylon.zip"
    pkg.write_text("x")
    fake_windll = SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=Mock(return_value=1)))

    class DummyZip:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extractall(self, path):
            return None

    with (
        patch("mindtrace.hardware.cameras.setup.setup_basler.ctypes.windll", fake_windll, create=True),
        patch("zipfile.ZipFile", return_value=DummyZip()),
        patch("pathlib.Path.rglob", return_value=[]),
    ):
        assert installer._install_windows(pkg) is False


def test_install_windows_returns_false_on_called_process_error(installer, tmp_path):
    installer.platform = "Windows"
    pkg = tmp_path / "Basler_pylon.exe"
    pkg.write_text("x")
    fake_windll = SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=Mock(return_value=1)))

    with (
        patch("mindtrace.hardware.cameras.setup.setup_basler.ctypes.windll", fake_windll, create=True),
        patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, [str(pkg)])),
    ):
        assert installer._install_windows(pkg) is False


def test_uninstall_linux_runs_cleanup(installer):
    installer.platform = "Linux"

    calls = []

    def fake_subprocess_run(cmd, check=False):
        calls.append((cmd, check))
        return Mock()

    with patch("subprocess.run", side_effect=fake_subprocess_run), patch.object(installer, "_run_command") as rc:
        assert installer._uninstall_linux() is True
        rc.assert_called_once_with(["sudo", "apt-get", "autoremove", "-y"])

    assert any(c[0][:4] == ["sudo", "apt-get", "remove", "-y"] for c in calls)


def test_uninstall_windows_returns_false(installer):
    installer.platform = "Windows"
    assert installer._uninstall_windows() is False


def test_uninstall_wraps_exceptions(installer):
    installer.platform = "Linux"

    with patch.object(installer, "_uninstall_linux", side_effect=RuntimeError("boom")):
        assert installer.uninstall() is False


def test_install_cli_verbose_and_package(tmp_path):
    pkg = tmp_path / "Basler_pylon.exe"
    pkg.write_text("x")
    installer = Mock()
    installer.install.return_value = True
    installer.logger = Mock()

    with patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller", return_value=installer) as cls:
        result = runner.invoke(app, ["install", "--verbose", "--package", str(pkg)])

    assert result.exit_code == 0
    cls.assert_called_once_with(package_path=str(pkg))
    installer.logger.setLevel.assert_called_once()
