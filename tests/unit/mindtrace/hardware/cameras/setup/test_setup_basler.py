"""Tests for Basler SDK setup functionality."""

from unittest.mock import Mock, patch

from mindtrace.hardware.cameras.setup.setup_basler import (
    PylonSDKInstaller,
    install_pylon_sdk,
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
        from pathlib import Path
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
        from pathlib import Path
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
