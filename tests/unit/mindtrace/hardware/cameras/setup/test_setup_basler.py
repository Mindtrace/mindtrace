"""Tests for Basler SDK setup functionality."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from mindtrace.hardware.cameras.setup.setup_basler import (
    PylonSDKInstaller,
    app,
    install,
    uninstall,
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
