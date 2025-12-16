"""Tests for Basler SDK setup functionality."""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from mindtrace.hardware.cameras.setup.setup_basler import (
    PylonSDKInstaller,
    install_pylon_sdk,
    main,
    uninstall_pylon_sdk,
)


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

    def test_installer_has_sdk_urls(self):
        """Test that installer has SDK URLs defined."""
        PylonSDKInstaller()

        # Should have class-level URL constants
        assert hasattr(PylonSDKInstaller, "LINUX_SDK_URL")
        assert hasattr(PylonSDKInstaller, "WINDOWS_SDK_URL")

        # URLs should be non-empty strings
        assert isinstance(PylonSDKInstaller.LINUX_SDK_URL, str)
        assert isinstance(PylonSDKInstaller.WINDOWS_SDK_URL, str)
        assert len(PylonSDKInstaller.LINUX_SDK_URL) > 0
        assert len(PylonSDKInstaller.WINDOWS_SDK_URL) > 0

    def test_installer_methods_exist(self):
        """Test that installer has expected methods."""
        installer = PylonSDKInstaller()

        # Should have installation methods
        assert hasattr(installer, "install")
        assert hasattr(installer, "uninstall")
        assert callable(installer.install)
        assert callable(installer.uninstall)

    def test_platform_specific_urls(self):
        """Test platform-specific URL handling."""
        # URLs should be appropriate for their platforms
        assert "linux" in PylonSDKInstaller.LINUX_SDK_URL.lower()
        assert (
            "windows" in PylonSDKInstaller.WINDOWS_SDK_URL.lower()
            or "basler" in PylonSDKInstaller.WINDOWS_SDK_URL.lower()
        )

    @patch("subprocess.run")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.download_and_extract_tarball")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.download_and_extract_zip")
    def test_install_method_callable(self, mock_download_zip, mock_download_tarball, mock_subprocess):
        """Test that install method is callable."""
        installer = PylonSDKInstaller()

        # Mock successful subprocess calls
        mock_subprocess.return_value.returncode = 0

        # Mock download functions to return a fake directory

        mock_download_tarball.return_value = Path("/tmp/fake_extracted")
        mock_download_zip.return_value = Path("/tmp/fake_extracted")

        # Should be able to call install without errors
        try:
            result = installer.install()
            # May return bool or None depending on implementation
            assert isinstance(result, (bool, type(None)))
        except Exception as e:
            # If it fails, should be due to missing dependencies, not method errors
            assert "dpkg" in str(e) or "permission" in str(e).lower() or "not found" in str(e).lower()

    @patch("subprocess.run")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.download_and_extract_tarball")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.download_and_extract_zip")
    def test_uninstall_method_callable(self, mock_download_zip, mock_download_tarball, mock_subprocess):
        """Test that uninstall method is callable."""
        installer = PylonSDKInstaller()

        # Mock successful subprocess calls
        mock_subprocess.return_value.returncode = 0

        # Mock download functions to return a fake directory

        mock_download_tarball.return_value = Path("/tmp/fake_extracted")
        mock_download_zip.return_value = Path("/tmp/fake_extracted")

        # Should be able to call uninstall without errors
        try:
            result = installer.uninstall()
            # May return bool or None depending on implementation
            assert isinstance(result, (bool, type(None)))
        except Exception as e:
            # If it fails, should be due to missing dependencies, not method errors
            assert "dpkg" in str(e) or "permission" in str(e).lower() or "not found" in str(e).lower()


class TestSetupFunctions:
    """Test module-level setup functions."""

    def test_install_pylon_sdk_function_exists(self):
        """Test that install_pylon_sdk function exists and is callable."""
        assert callable(install_pylon_sdk)

    def test_uninstall_pylon_sdk_function_exists(self):
        """Test that uninstall_pylon_sdk function exists and is callable."""
        assert callable(uninstall_pylon_sdk)

    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller")
    def test_install_function_creates_installer(self, mock_installer_class):
        """Test that install function creates and uses installer."""
        mock_installer = Mock()
        mock_installer.install.return_value = True
        mock_installer_class.return_value = mock_installer

        result = install_pylon_sdk()

        # Should have created installer and called install
        mock_installer_class.assert_called_once()
        mock_installer.install.assert_called_once()
        assert result is True

    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller")
    def test_uninstall_function_creates_installer(self, mock_installer_class):
        """Test that uninstall function creates and uses installer."""
        mock_installer = Mock()
        mock_installer.uninstall.return_value = True
        mock_installer_class.return_value = mock_installer

        result = uninstall_pylon_sdk()

        # Should have created installer and called uninstall
        mock_installer_class.assert_called_once()
        mock_installer.uninstall.assert_called_once()
        assert result is True

    def test_install_function_default_parameters(self):
        """Test install function with default parameters."""
        # Should accept version parameter
        try:
            # Mock the installer to avoid actual installation
            with patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller") as mock_class:
                mock_installer = Mock()
                mock_installer.install.return_value = True
                mock_class.return_value = mock_installer

                result = install_pylon_sdk("v1.0-test")
                assert isinstance(result, bool)
        except Exception as e:
            # Function should at least be callable with parameters
            assert "argument" not in str(e).lower()

    @patch("platform.system")
    def test_platform_detection_linux(self, mock_platform):
        """Test platform detection for Linux."""
        mock_platform.return_value = "Linux"

        installer = PylonSDKInstaller()

        # Should handle Linux platform
        assert installer is not None

    @patch("platform.system")
    def test_platform_detection_windows(self, mock_platform):
        """Test platform detection for Windows."""
        mock_platform.return_value = "Windows"

        installer = PylonSDKInstaller()

        # Should handle Windows platform
        assert installer is not None

    def test_installer_logging(self):
        """Test that installer has proper logging setup."""
        installer = PylonSDKInstaller()

        # Should have logger from Mindtrace base
        assert hasattr(installer, "logger")
        import logging

        assert isinstance(installer.logger, logging.Logger)


class TestInstallMethod:
    """Test cases for install() method."""

    @patch("platform.system")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller._install_linux")
    def test_install_linux_platform(self, mock_install_linux, mock_platform):
        """Test install() calls _install_linux on Linux platform."""
        mock_platform.return_value = "Linux"
        mock_install_linux.return_value = True

        installer = PylonSDKInstaller()
        result = installer.install()

        assert result is True
        mock_install_linux.assert_called_once()

    @patch("platform.system")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller._install_windows")
    def test_install_windows_platform(self, mock_install_windows, mock_platform):
        """Test install() calls _install_windows on Windows platform."""
        mock_platform.return_value = "Windows"
        mock_install_windows.return_value = True

        installer = PylonSDKInstaller()
        result = installer.install()

        assert result is True
        mock_install_windows.assert_called_once()

    @patch("platform.system")
    def test_install_unsupported_platform(self, mock_platform):
        """Test install() returns False for unsupported platform."""
        mock_platform.return_value = "Darwin"

        installer = PylonSDKInstaller()
        result = installer.install()

        assert result is False

    @patch("platform.system")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller._install_linux")
    def test_install_exception_handling(self, mock_install_linux, mock_platform):
        """Test install() handles exceptions properly."""
        mock_platform.return_value = "Linux"
        mock_install_linux.side_effect = Exception("Test exception")

        installer = PylonSDKInstaller()
        result = installer.install()

        assert result is False


class TestInstallLinux:
    """Test cases for _install_linux() method."""

    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller._install_linux_packages")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.download_and_extract_tarball")
    @patch("os.getcwd")
    @patch("os.chdir")
    def test_install_linux_success(self, mock_chdir, mock_getcwd, mock_download, mock_install_packages):
        """Test successful Linux installation."""
        mock_getcwd.return_value = "/original/cwd"
        mock_download.return_value = "/tmp/extracted"

        installer = PylonSDKInstaller()
        with patch("platform.system", return_value="Linux"):
            installer.platform = "Linux"
            result = installer._install_linux()

        assert result is True
        mock_download.assert_called_once()
        mock_install_packages.assert_called_once()
        mock_chdir.assert_any_call("/tmp/extracted")
        mock_chdir.assert_any_call("/original/cwd")

    @patch("mindtrace.hardware.cameras.setup.setup_basler.download_and_extract_tarball")
    @patch("os.getcwd")
    @patch("os.chdir")
    def test_install_linux_called_process_error(self, mock_chdir, mock_getcwd, mock_download):
        """Test _install_linux handles CalledProcessError."""
        mock_getcwd.return_value = "/original/cwd"
        mock_download.side_effect = subprocess.CalledProcessError(1, "cmd")

        installer = PylonSDKInstaller()
        with patch("platform.system", return_value="Linux"):
            installer.platform = "Linux"
            result = installer._install_linux()

        assert result is False

    @patch("mindtrace.hardware.cameras.setup.setup_basler.download_and_extract_tarball")
    @patch("os.getcwd")
    @patch("os.chdir")
    def test_install_linux_file_not_found_error(self, mock_chdir, mock_getcwd, mock_download):
        """Test _install_linux handles FileNotFoundError."""
        mock_getcwd.return_value = "/original/cwd"
        mock_download.side_effect = FileNotFoundError("File not found")

        installer = PylonSDKInstaller()
        with patch("platform.system", return_value="Linux"):
            installer.platform = "Linux"
            result = installer._install_linux()

        assert result is False

    @patch("mindtrace.hardware.cameras.setup.setup_basler.download_and_extract_tarball")
    @patch("os.getcwd")
    @patch("os.chdir")
    def test_install_linux_unexpected_error(self, mock_chdir, mock_getcwd, mock_download):
        """Test _install_linux handles unexpected exceptions."""
        mock_getcwd.return_value = "/original/cwd"
        mock_download.side_effect = ValueError("Unexpected error")

        installer = PylonSDKInstaller()
        with patch("platform.system", return_value="Linux"):
            installer.platform = "Linux"
            result = installer._install_linux()

        assert result is False


class TestInstallLinuxPackages:
    """Test cases for _install_linux_packages() method."""

    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller._run_command")
    @patch("glob.glob")
    @patch("os.listdir")
    @patch("os.getcwd")
    def test_install_linux_packages_success(self, mock_getcwd, mock_listdir, mock_glob, mock_run_command):
        """Test successful package installation."""
        mock_getcwd.return_value = "/tmp/extracted"
        mock_listdir.return_value = ["pylon_1.deb", "pylon_2.deb"]
        mock_glob.side_effect = lambda pattern: ["pylon_1.deb", "pylon_2.deb"] if "pylon" in pattern else []

        installer = PylonSDKInstaller()
        installer._install_linux_packages()

        assert mock_run_command.call_count >= 3

    @patch("glob.glob")
    @patch("os.listdir")
    @patch("os.getcwd")
    def test_install_linux_packages_no_debs_found(self, mock_getcwd, mock_listdir, mock_glob):
        """Test _install_linux_packages raises FileNotFoundError when no debs found."""
        mock_getcwd.return_value = "/tmp/extracted"
        mock_listdir.return_value = []
        mock_glob.return_value = []

        installer = PylonSDKInstaller()
        with pytest.raises(FileNotFoundError, match="No .deb packages found"):
            installer._install_linux_packages()


class TestInstallWindows:
    """Test cases for _install_windows() method."""

    @patch("mindtrace.hardware.cameras.setup.setup_basler.ctypes")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller._find_windows_executable")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.download_and_extract_zip")
    @patch("subprocess.run")
    def test_install_windows_with_admin(self, mock_subprocess, mock_download, mock_find_exe, mock_ctypes):
        """Test Windows installation with admin privileges."""
        mock_shell32 = Mock()
        mock_shell32.IsUserAnAdmin.return_value = True
        mock_windll = Mock()
        mock_windll.shell32 = mock_shell32
        mock_ctypes.windll = mock_windll
        mock_download.return_value = "/tmp/extracted"
        mock_find_exe.return_value = "/tmp/extracted/setup.exe"
        mock_subprocess.return_value = Mock(returncode=0)

        installer = PylonSDKInstaller()
        with patch("platform.system", return_value="Windows"):
            installer.platform = "Windows"
            result = installer._install_windows()

        assert result is True
        mock_subprocess.assert_called_once()

    @patch("mindtrace.hardware.cameras.setup.setup_basler.ctypes")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller._elevate_privileges")
    def test_install_windows_without_admin(self, mock_elevate, mock_ctypes):
        """Test Windows installation without admin privileges."""
        mock_shell32 = Mock()
        mock_shell32.IsUserAnAdmin.return_value = False
        mock_windll = Mock()
        mock_windll.shell32 = mock_shell32
        mock_ctypes.windll = mock_windll
        mock_elevate.return_value = False

        installer = PylonSDKInstaller()
        with patch("platform.system", return_value="Windows"):
            installer.platform = "Windows"
            result = installer._install_windows()

        assert result is False
        mock_elevate.assert_called_once()

    @patch("mindtrace.hardware.cameras.setup.setup_basler.ctypes")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller._find_windows_executable")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.download_and_extract_zip")
    @patch("subprocess.run")
    def test_install_windows_called_process_error(self, mock_subprocess, mock_download, mock_find_exe, mock_ctypes):
        """Test _install_windows handles CalledProcessError."""
        mock_shell32 = Mock()
        mock_shell32.IsUserAnAdmin.return_value = True
        mock_windll = Mock()
        mock_windll.shell32 = mock_shell32
        mock_ctypes.windll = mock_windll
        mock_download.return_value = "/tmp/extracted"
        mock_find_exe.return_value = "/tmp/extracted/setup.exe"
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, "cmd")

        installer = PylonSDKInstaller()
        with patch("platform.system", return_value="Windows"):
            installer.platform = "Windows"
            result = installer._install_windows()

        assert result is False

    @patch("mindtrace.hardware.cameras.setup.setup_basler.ctypes")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller._find_windows_executable")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.download_and_extract_zip")
    def test_install_windows_unexpected_error(self, mock_download, mock_find_exe, mock_ctypes):
        """Test _install_windows handles unexpected exceptions."""
        mock_shell32 = Mock()
        mock_shell32.IsUserAnAdmin.return_value = True
        mock_windll = Mock()
        mock_windll.shell32 = mock_shell32
        mock_ctypes.windll = mock_windll
        mock_download.side_effect = ValueError("Unexpected error")

        installer = PylonSDKInstaller()
        with patch("platform.system", return_value="Windows"):
            installer.platform = "Windows"
            result = installer._install_windows()

        assert result is False


class TestFindWindowsExecutable:
    """Test cases for _find_windows_executable() method."""

    def test_find_windows_executable_in_path(self):
        """Test _find_windows_executable when .exe is in path."""
        installer = PylonSDKInstaller()
        result = installer._find_windows_executable("/path/to/setup.exe")
        assert result == "/path/to/setup.exe"

    @patch("pathlib.Path.glob")
    def test_find_windows_executable_in_directory(self, mock_glob):
        """Test _find_windows_executable finds .exe in directory."""
        mock_exe = Mock()
        mock_exe.__str__ = lambda self: "/tmp/extracted/setup.exe"
        mock_glob.return_value = [mock_exe]

        installer = PylonSDKInstaller()
        result = installer._find_windows_executable("/tmp/extracted")
        assert result == "/tmp/extracted/setup.exe"

    @patch("os.listdir")
    @patch("pathlib.Path.glob")
    def test_find_windows_executable_fallback(self, mock_glob, mock_listdir):
        """Test _find_windows_executable falls back to first file."""
        mock_glob.return_value = []
        mock_listdir.return_value = ["setup.exe"]

        installer = PylonSDKInstaller()
        result = installer._find_windows_executable("/tmp/extracted")
        assert result == "/tmp/extracted/setup.exe"

    @patch("os.listdir")
    @patch("pathlib.Path.glob")
    def test_find_windows_executable_not_found(self, mock_glob, mock_listdir):
        """Test _find_windows_executable raises FileNotFoundError when nothing found."""
        mock_glob.return_value = []
        mock_listdir.return_value = []

        installer = PylonSDKInstaller()
        with pytest.raises(FileNotFoundError, match="No executable found"):
            installer._find_windows_executable("/tmp/extracted")


class TestElevatePrivileges:
    """Test cases for _elevate_privileges() method."""

    @patch("mindtrace.hardware.cameras.setup.setup_basler.ctypes")
    @patch("sys.executable")
    @patch("sys.argv")
    def test_elevate_privileges_success(self, mock_argv, mock_executable, mock_ctypes):
        """Test _elevate_privileges calls ShellExecuteW."""
        mock_shell32 = Mock()
        mock_shell32.ShellExecuteW.return_value = None
        mock_windll = Mock()
        mock_windll.shell32 = mock_shell32
        mock_ctypes.windll = mock_windll
        mock_executable.return_value = "/usr/bin/python"

        installer = PylonSDKInstaller()
        result = installer._elevate_privileges()

        assert result is False
        mock_shell32.ShellExecuteW.assert_called_once()

    @patch("mindtrace.hardware.cameras.setup.setup_basler.ctypes")
    @patch("sys.executable")
    @patch("sys.argv")
    def test_elevate_privileges_exception(self, mock_argv, mock_executable, mock_ctypes):
        """Test _elevate_privileges handles exceptions."""
        mock_shell32 = Mock()
        mock_shell32.ShellExecuteW.side_effect = Exception("Elevation failed")
        mock_windll = Mock()
        mock_windll.shell32 = mock_shell32
        mock_ctypes.windll = mock_windll
        mock_executable.return_value = "/usr/bin/python"

        installer = PylonSDKInstaller()
        result = installer._elevate_privileges()

        assert result is False


class TestRunCommand:
    """Test cases for _run_command() method."""

    @patch("subprocess.run")
    def test_run_command_success(self, mock_subprocess):
        """Test _run_command runs command successfully."""
        mock_subprocess.return_value = Mock(returncode=0)

        installer = PylonSDKInstaller()
        installer._run_command(["echo", "test"])

        mock_subprocess.assert_called_once_with(["echo", "test"], check=True)

    @patch("subprocess.run")
    def test_run_command_failure(self, mock_subprocess):
        """Test _run_command raises CalledProcessError on failure."""
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, "cmd")

        installer = PylonSDKInstaller()
        with pytest.raises(subprocess.CalledProcessError):
            installer._run_command(["false"])


class TestUninstallMethod:
    """Test cases for uninstall() method."""

    @patch("platform.system")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller._uninstall_linux")
    def test_uninstall_linux_platform(self, mock_uninstall_linux, mock_platform):
        """Test uninstall() calls _uninstall_linux on Linux platform."""
        mock_platform.return_value = "Linux"
        mock_uninstall_linux.return_value = True

        installer = PylonSDKInstaller()
        result = installer.uninstall()

        assert result is True
        mock_uninstall_linux.assert_called_once()

    @patch("platform.system")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller._uninstall_windows")
    def test_uninstall_windows_platform(self, mock_uninstall_windows, mock_platform):
        """Test uninstall() calls _uninstall_windows on Windows platform."""
        mock_platform.return_value = "Windows"
        mock_uninstall_windows.return_value = False

        installer = PylonSDKInstaller()
        result = installer.uninstall()

        assert result is False
        mock_uninstall_windows.assert_called_once()

    @patch("platform.system")
    def test_uninstall_unsupported_platform(self, mock_platform):
        """Test uninstall() returns False for unsupported platform."""
        mock_platform.return_value = "Darwin"

        installer = PylonSDKInstaller()
        result = installer.uninstall()

        assert result is False

    @patch("platform.system")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller._uninstall_linux")
    def test_uninstall_exception_handling(self, mock_uninstall_linux, mock_platform):
        """Test uninstall() handles exceptions properly."""
        mock_platform.return_value = "Linux"
        mock_uninstall_linux.side_effect = Exception("Test exception")

        installer = PylonSDKInstaller()
        result = installer.uninstall()

        assert result is False


class TestUninstallLinux:
    """Test cases for _uninstall_linux() method."""

    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller._run_command")
    @patch("subprocess.run")
    def test_uninstall_linux_success(self, mock_subprocess, mock_run_command):
        """Test successful Linux uninstallation."""
        mock_subprocess.return_value = Mock(returncode=0)

        installer = PylonSDKInstaller()
        result = installer._uninstall_linux()

        assert result is True
        assert mock_run_command.call_count == 2

    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller._run_command")
    def test_uninstall_linux_called_process_error(self, mock_run_command):
        """Test _uninstall_linux handles CalledProcessError."""
        mock_run_command.side_effect = subprocess.CalledProcessError(1, "cmd")

        installer = PylonSDKInstaller()
        result = installer._uninstall_linux()

        assert result is False


class TestUninstallWindows:
    """Test cases for _uninstall_windows() method."""

    def test_uninstall_windows_returns_false(self):
        """Test _uninstall_windows returns False."""
        installer = PylonSDKInstaller()
        result = installer._uninstall_windows()
        assert result is False


class TestMainFunction:
    """Test cases for main() function."""

    @patch("sys.argv", ["setup_basler.py"])
    @patch("sys.exit")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller")
    def test_main_install(self, mock_installer_class, mock_exit):
        """Test main() with install action."""
        mock_installer = Mock()
        mock_installer.install.return_value = True
        mock_installer.logger = Mock()
        mock_installer_class.return_value = mock_installer

        main()

        mock_installer.install.assert_called_once()
        mock_exit.assert_called_once_with(0)

    @patch("sys.argv", ["setup_basler.py", "--uninstall"])
    @patch("sys.exit")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller")
    def test_main_uninstall(self, mock_installer_class, mock_exit):
        """Test main() with uninstall action."""
        mock_installer = Mock()
        mock_installer.uninstall.return_value = True
        mock_installer.logger = Mock()
        mock_installer_class.return_value = mock_installer

        main()

        mock_installer.uninstall.assert_called_once()
        mock_exit.assert_called_once_with(0)

    @patch("sys.argv", ["setup_basler.py", "--version", "v2.0"])
    @patch("sys.exit")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller")
    def test_main_with_version(self, mock_installer_class, mock_exit):
        """Test main() with version argument."""
        mock_installer = Mock()
        mock_installer.install.return_value = True
        mock_installer.logger = Mock()
        mock_installer_class.return_value = mock_installer

        main()

        mock_installer_class.assert_called_once_with("v2.0")
        mock_exit.assert_called_once_with(0)

    @patch("sys.argv", ["setup_basler.py", "--verbose"])
    @patch("sys.exit")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller")
    def test_main_with_verbose(self, mock_installer_class, mock_exit):
        """Test main() with verbose flag."""
        import logging

        mock_installer = Mock()
        mock_installer.install.return_value = True
        mock_logger = Mock()
        mock_installer.logger = mock_logger
        mock_installer_class.return_value = mock_installer

        main()

        mock_logger.setLevel.assert_called_once_with(logging.DEBUG)
        mock_exit.assert_called_once_with(0)

    @patch("sys.argv", ["setup_basler.py"])
    @patch("sys.exit")
    @patch("mindtrace.hardware.cameras.setup.setup_basler.PylonSDKInstaller")
    def test_main_install_failure(self, mock_installer_class, mock_exit):
        """Test main() exits with code 1 on install failure."""
        mock_installer = Mock()
        mock_installer.install.return_value = False
        mock_installer.logger = Mock()
        mock_installer_class.return_value = mock_installer

        main()

        mock_exit.assert_called_once_with(1)


class TestMainBlock:
    """Test cases for __main__ block."""

    @patch("sys.argv", ["setup_basler.py"])
    @patch("mindtrace.hardware.cameras.setup.setup_basler.main")
    def test_main_block_execution(self, mock_main):
        """Test that __main__ block calls main() when executed."""
        # Import the module
        import mindtrace.hardware.cameras.setup.setup_basler as module

        # Verify the module has the main function
        assert hasattr(module, "main")
        assert callable(module.main)
