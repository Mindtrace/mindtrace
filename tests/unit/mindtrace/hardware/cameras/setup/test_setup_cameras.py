"""Tests for Camera Setup and Configuration Script."""

import subprocess
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from mindtrace.hardware.cameras.setup.setup_cameras import (
    CameraSystemSetup,
    app,
)

runner = CliRunner()


class TestCameraSystemSetup:
    """Test cases for CameraSystemSetup class."""

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config")
    def test_setup_initialization(self, mock_config):
        """Test CameraSystemSetup initialization."""
        # Mock hardware config
        mock_hw_config = Mock()
        mock_config_obj = Mock()
        mock_config_obj.network.camera_ip_range = "192.168.50.0/24"
        mock_config_obj.network.firewall_rule_name = "Allow Camera Network"
        mock_config_obj.network.timeout_seconds = 30
        mock_hw_config.get_config.return_value = mock_config_obj
        mock_config.return_value = mock_hw_config

        setup = CameraSystemSetup()

        # Should be a Mindtrace instance
        from mindtrace.core import Mindtrace

        assert isinstance(setup, Mindtrace)

        # Should have expected attributes
        assert hasattr(setup, "logger")
        assert hasattr(setup, "hardware_config")
        assert hasattr(setup, "platform")
        assert setup.logger is not None

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config")
    def test_setup_has_required_methods(self, mock_config):
        """Test that setup has expected methods."""
        # Mock hardware config
        mock_hw_config = Mock()
        mock_config_obj = Mock()
        mock_config_obj.network.camera_ip_range = "192.168.50.0/24"
        mock_config_obj.network.firewall_rule_name = "Allow Camera Network"
        mock_config_obj.network.timeout_seconds = 30
        mock_hw_config.get_config.return_value = mock_config_obj
        mock_config.return_value = mock_hw_config

        setup = CameraSystemSetup()

        # Should have main methods
        assert hasattr(setup, "install_all_sdks")
        assert hasattr(setup, "uninstall_all_sdks")
        assert hasattr(setup, "configure_firewall")
        assert callable(setup.install_all_sdks)
        assert callable(setup.uninstall_all_sdks)
        assert callable(setup.configure_firewall)

    @pytest.mark.skip(reason="Test triggers sudo prompt despite mocks - skip to avoid blocking")
    @patch("mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config")
    @patch("mindtrace.hardware.cameras.setup.setup_cameras.PylonSDKInstaller")
    def test_install_all_sdks_success(self, mock_pylon_class, mock_config):
        """Test successful installation of all SDKs."""
        # Mock hardware config
        mock_hw_config = Mock()
        mock_config_obj = Mock()
        mock_config_obj.network.camera_ip_range = "192.168.50.0/24"
        mock_config_obj.network.firewall_rule_name = "Allow Camera Network"
        mock_config_obj.network.timeout_seconds = 30
        mock_hw_config.get_config.return_value = mock_config_obj
        mock_config.return_value = mock_hw_config

        # Mock successful Pylon SDK installation
        mock_installer = Mock()
        mock_installer.install.return_value = True
        mock_pylon_class.return_value = mock_installer

        setup = CameraSystemSetup()
        result = setup.install_all_sdks()

        # Should create PylonSDKInstaller and call install
        mock_pylon_class.assert_called_once()
        mock_installer.install.assert_called_once()
        assert result is False  # Currently 1/2 SDKs succeed (only Basler implemented)

    @pytest.mark.skip(reason="Test triggers sudo prompt despite mocks - skip to avoid blocking")
    @patch("mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config")
    @patch("mindtrace.hardware.cameras.setup.setup_cameras.PylonSDKInstaller")
    def test_install_all_sdks_failure(self, mock_pylon_class, mock_config):
        """Test failed installation of all SDKs."""
        # Mock hardware config
        mock_hw_config = Mock()
        mock_config_obj = Mock()
        mock_config_obj.network.camera_ip_range = "192.168.50.0/24"
        mock_config_obj.network.firewall_rule_name = "Allow Camera Network"
        mock_config_obj.network.timeout_seconds = 30
        mock_hw_config.get_config.return_value = mock_config_obj
        mock_config.return_value = mock_hw_config

        # Mock failed Pylon SDK installation
        mock_installer = Mock()
        mock_installer.install.return_value = False
        mock_pylon_class.return_value = mock_installer

        setup = CameraSystemSetup()
        result = setup.install_all_sdks()

        # Should create PylonSDKInstaller and call install
        mock_pylon_class.assert_called_once()
        mock_installer.install.assert_called_once()
        assert result is False

    @pytest.mark.skip(reason="Requires sudo privileges - triggers interactive password prompt")
    @patch("mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config")
    @patch("mindtrace.hardware.cameras.setup.setup_cameras.PylonSDKInstaller")
    def test_uninstall_all_sdks_success(self, mock_pylon_class, mock_config):
        """Test successful uninstallation of all SDKs."""
        # Mock hardware config
        mock_hw_config = Mock()
        mock_config_obj = Mock()
        mock_config_obj.network.camera_ip_range = "192.168.50.0/24"
        mock_config_obj.network.firewall_rule_name = "Allow Camera Network"
        mock_config_obj.network.timeout_seconds = 30
        mock_hw_config.get_config.return_value = mock_config_obj
        mock_config.return_value = mock_hw_config

        # Mock successful Pylon SDK uninstallation
        mock_installer = Mock()
        mock_installer.uninstall.return_value = True
        mock_pylon_class.return_value = mock_installer

        setup = CameraSystemSetup()
        result = setup.uninstall_all_sdks()

        # Should create PylonSDKInstaller and call uninstall
        mock_pylon_class.assert_called_once()
        mock_installer.uninstall.assert_called_once()
        assert result is False  # Currently 1/2 SDKs succeed (only Basler implemented)

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config")
    @patch("mindtrace.hardware.cameras.setup.setup_cameras.PylonSDKInstaller")
    @patch("mindtrace.hardware.cameras.setup.setup_cameras.uninstall_genicam_cti")
    def test_uninstall_all_sdks_failure(self, mock_uninstall_genicam, mock_pylon_class, mock_config):
        """Test failed uninstallation of all SDKs."""
        # Mock hardware config
        mock_hw_config = Mock()
        mock_config_obj = Mock()
        mock_config_obj.network.camera_ip_range = "192.168.50.0/24"
        mock_config_obj.network.firewall_rule_name = "Allow Camera Network"
        mock_config_obj.network.timeout_seconds = 30
        mock_hw_config.get_config.return_value = mock_config_obj
        mock_config.return_value = mock_hw_config

        # Mock failed Pylon SDK uninstallation
        mock_installer = Mock()
        mock_installer.uninstall.return_value = False
        mock_pylon_class.return_value = mock_installer

        # Mock failed GenICam CTI uninstallation
        mock_uninstall_genicam.return_value = False

        setup = CameraSystemSetup()
        result = setup.uninstall_all_sdks()

        # Should create PylonSDKInstaller and call uninstall
        mock_pylon_class.assert_called_once()
        mock_installer.uninstall.assert_called_once()
        mock_uninstall_genicam.assert_called_once()
        assert result is False

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config")
    @patch("platform.system")
    def test_configure_firewall_windows(self, mock_platform, mock_config):
        """Test firewall configuration on Windows."""
        # Mock hardware config
        mock_hw_config = Mock()
        mock_config_obj = Mock()
        mock_config_obj.network.camera_ip_range = "192.168.50.0/24"
        mock_config_obj.network.firewall_rule_name = "Allow Camera Network"
        mock_config_obj.network.firewall_timeout = 30
        mock_hw_config.get_config.return_value = mock_config_obj
        mock_config.return_value = mock_hw_config

        # Mock Windows platform
        mock_platform.return_value = "Windows"

        setup = CameraSystemSetup()
        with patch.object(setup, "_configure_windows_firewall") as mock_windows_fw:
            mock_windows_fw.return_value = True

            result = setup.configure_firewall()

            # Should call Windows firewall configuration
            mock_windows_fw.assert_called_once_with("192.168.50.0/24")
            assert result is True

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config")
    @patch("platform.system")
    def test_configure_firewall_linux(self, mock_platform, mock_config):
        """Test firewall configuration on Linux."""
        # Mock hardware config
        mock_hw_config = Mock()
        mock_config_obj = Mock()
        mock_config_obj.network.camera_ip_range = "192.168.50.0/24"
        mock_config_obj.network.firewall_rule_name = "Allow Camera Network"
        mock_config_obj.network.firewall_timeout = 30
        mock_hw_config.get_config.return_value = mock_config_obj
        mock_config.return_value = mock_hw_config

        # Mock Linux platform
        mock_platform.return_value = "Linux"

        setup = CameraSystemSetup()
        with patch.object(setup, "_configure_linux_firewall") as mock_linux_fw:
            mock_linux_fw.return_value = True

            result = setup.configure_firewall()

            # Should call Linux firewall configuration
            mock_linux_fw.assert_called_once_with("192.168.50.0/24")
            assert result is True

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config")
    @patch("platform.system")
    def test_configure_firewall_custom_ip_range(self, mock_platform, mock_config):
        """Test firewall configuration with custom IP range."""
        # Mock hardware config
        mock_hw_config = Mock()
        mock_config_obj = Mock()
        mock_config_obj.network.camera_ip_range = "192.168.50.0/24"
        mock_config_obj.network.firewall_rule_name = "Allow Camera Network"
        mock_config_obj.network.firewall_timeout = 30
        mock_hw_config.get_config.return_value = mock_config_obj
        mock_config.return_value = mock_hw_config

        # Mock Linux platform
        mock_platform.return_value = "Linux"

        setup = CameraSystemSetup()
        custom_ip = "10.0.0.0/24"

        with patch.object(setup, "_configure_linux_firewall") as mock_linux_fw:
            mock_linux_fw.return_value = True

            result = setup.configure_firewall(custom_ip)

            # Should use custom IP range
            mock_linux_fw.assert_called_once_with(custom_ip)
            assert result is True

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config")
    @patch("platform.system")
    def test_configure_firewall_unsupported_platform(self, mock_platform, mock_config):
        """Test firewall configuration on unsupported platform."""
        # Mock hardware config
        mock_hw_config = Mock()
        mock_config_obj = Mock()
        mock_config_obj.network.camera_ip_range = "192.168.50.0/24"
        mock_config_obj.network.firewall_rule_name = "Allow Camera Network"
        mock_config_obj.network.firewall_timeout = 30
        mock_hw_config.get_config.return_value = mock_config_obj
        mock_config.return_value = mock_hw_config

        # Mock unsupported platform
        mock_platform.return_value = "Darwin"  # macOS

        setup = CameraSystemSetup()
        result = setup.configure_firewall()

        # Should return False for unsupported platform
        assert result is False

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config")
    @patch("subprocess.run")
    def test_configure_windows_firewall_success(self, mock_subprocess, mock_config):
        """Test successful Windows firewall configuration."""
        # Mock hardware config
        mock_hw_config = Mock()
        mock_config_obj = Mock()
        mock_config_obj.network.camera_ip_range = "192.168.50.0/24"
        mock_config_obj.network.firewall_rule_name = "Allow Camera Network"
        mock_config_obj.network.firewall_timeout = 30
        mock_hw_config.get_config.return_value = mock_config_obj
        mock_config.return_value = mock_hw_config

        # Mock successful firewall command (rule doesn't exist)
        mock_result = Mock()
        mock_result.stdout = "No rules match the specified criteria"
        mock_subprocess.return_value = mock_result

        setup = CameraSystemSetup()
        result = setup._configure_windows_firewall("192.168.50.0/24")

        # Should return True for successful configuration
        assert result is True
        assert mock_subprocess.call_count >= 1  # At least one call for checking

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config")
    @patch("subprocess.run")
    def test_configure_windows_firewall_rule_exists(self, mock_subprocess, mock_config):
        """Test Windows firewall configuration when rule already exists."""
        # Mock hardware config
        mock_hw_config = Mock()
        mock_config_obj = Mock()
        mock_config_obj.network.camera_ip_range = "192.168.50.0/24"
        mock_config_obj.network.firewall_rule_name = "Allow Camera Network"
        mock_config_obj.network.firewall_timeout = 30
        mock_hw_config.get_config.return_value = mock_config_obj
        mock_config.return_value = mock_hw_config

        # Mock firewall command showing rule exists
        mock_result = Mock()
        mock_result.stdout = "Rule Name: Allow Camera Network"
        mock_subprocess.return_value = mock_result

        setup = CameraSystemSetup()
        result = setup._configure_windows_firewall("192.168.50.0/24")

        # Should return True when rule already exists
        assert result is True

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config")
    @patch("subprocess.run")
    def test_configure_windows_firewall_timeout(self, mock_subprocess, mock_config):
        """Test Windows firewall configuration timeout."""
        # Mock hardware config
        mock_hw_config = Mock()
        mock_config_obj = Mock()
        mock_config_obj.network.camera_ip_range = "192.168.50.0/24"
        mock_config_obj.network.firewall_rule_name = "Allow Camera Network"
        mock_config_obj.network.firewall_timeout = 30
        mock_hw_config.get_config.return_value = mock_config_obj
        mock_config.return_value = mock_hw_config

        # Mock timeout exception
        mock_subprocess.side_effect = subprocess.TimeoutExpired("cmd", 30)

        setup = CameraSystemSetup()
        result = setup._configure_windows_firewall("192.168.50.0/24")

        # Should return False on timeout
        assert result is False

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config")
    @patch("subprocess.run")
    def test_configure_linux_firewall_success(self, mock_subprocess, mock_config):
        """Test successful Linux firewall configuration."""
        # Mock hardware config
        mock_hw_config = Mock()
        mock_config_obj = Mock()
        mock_config_obj.network.camera_ip_range = "192.168.50.0/24"
        mock_config_obj.network.firewall_rule_name = "Allow Camera Network"
        mock_config_obj.network.firewall_timeout = 30
        mock_hw_config.get_config.return_value = mock_config_obj
        mock_config.return_value = mock_hw_config

        # Mock successful UFW commands
        mock_status_result = Mock()
        mock_status_result.returncode = 0
        mock_status_result.stdout = "Status: active"

        mock_add_result = Mock()
        mock_add_result.returncode = 0

        # First call is status check, second is add rule
        mock_subprocess.side_effect = [mock_status_result, mock_add_result]

        setup = CameraSystemSetup()
        result = setup._configure_linux_firewall("192.168.50.0/24")

        # Should return True for successful configuration
        assert result is True

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config")
    @patch("subprocess.run")
    def test_configure_linux_firewall_rule_exists(self, mock_subprocess, mock_config):
        """Test Linux firewall configuration when rule already exists."""
        # Mock hardware config
        mock_hw_config = Mock()
        mock_config_obj = Mock()
        mock_config_obj.network.camera_ip_range = "192.168.50.0/24"
        mock_config_obj.network.firewall_rule_name = "Allow Camera Network"
        mock_config_obj.network.firewall_timeout = 30
        mock_hw_config.get_config.return_value = mock_config_obj
        mock_config.return_value = mock_hw_config

        # Mock UFW status showing rule exists
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Status: active\n192.168.50.0/24 ALLOW IN"
        mock_subprocess.return_value = mock_result

        setup = CameraSystemSetup()
        result = setup._configure_linux_firewall("192.168.50.0/24")

        # Should return True when rule already exists
        assert result is True

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config")
    @patch("subprocess.run")
    def test_configure_linux_firewall_ufw_not_installed(self, mock_subprocess, mock_config):
        """Test Linux firewall configuration when UFW is not installed."""
        # Mock hardware config
        mock_hw_config = Mock()
        mock_config_obj = Mock()
        mock_config_obj.network.camera_ip_range = "192.168.50.0/24"
        mock_config_obj.network.firewall_rule_name = "Allow Camera Network"
        mock_config_obj.network.firewall_timeout = 30
        mock_hw_config.get_config.return_value = mock_config_obj
        mock_config.return_value = mock_hw_config

        # Mock UFW not available
        mock_result = Mock()
        mock_result.returncode = 1  # Command failed
        mock_subprocess.return_value = mock_result

        setup = CameraSystemSetup()
        result = setup._configure_linux_firewall("192.168.50.0/24")

        # Should return False when UFW is not available
        assert result is False


class TestModuleFunctions:
    """Test module-level functions (via Typer CLI)."""

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup")
    def test_configure_firewall_function(self, mock_setup_class):
        """Test configure_firewall via CLI."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.configure_firewall.return_value = True
        mock_setup_class.return_value = mock_setup

        result = runner.invoke(app, ["configure-firewall", "--ip-range", "10.0.0.0/24"])

        # Should create setup instance and call configure_firewall
        mock_setup_class.assert_called_once()
        mock_setup.configure_firewall.assert_called_once_with("10.0.0.0/24")
        assert result.exit_code == 0

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup")
    def test_configure_firewall_function_no_ip_range(self, mock_setup_class):
        """Test configure_firewall function without IP range."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.configure_firewall.return_value = True
        mock_setup_class.return_value = mock_setup

        result = runner.invoke(app, ["configure-firewall"])

        # Should create setup instance and call configure_firewall with None
        mock_setup_class.assert_called_once()
        mock_setup.configure_firewall.assert_called_once_with(None)
        assert result.exit_code == 0


class TestMainFunction:
    """Test main function and CLI argument parsing (via Typer CLI)."""

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup")
    def test_main_default_install(self, mock_setup_class):
        """Test install command with default behavior."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.install_all_sdks.return_value = True
        mock_setup.configure_firewall.return_value = True
        mock_setup_class.return_value = mock_setup

        result = runner.invoke(app, ["install"])

        # Should call install and firewall configuration, then exit with 0
        mock_setup.install_all_sdks.assert_called_once_with("v1.0-stable")
        mock_setup.configure_firewall.assert_called_once_with(None)
        assert result.exit_code == 0

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup")
    def test_main_uninstall(self, mock_setup_class):
        """Test uninstall command."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.uninstall_all_sdks.return_value = True
        mock_setup_class.return_value = mock_setup

        result = runner.invoke(app, ["uninstall"])

        # Should call uninstall only, then exit with 0
        mock_setup.uninstall_all_sdks.assert_called_once()
        mock_setup.configure_firewall.assert_not_called()
        assert result.exit_code == 0

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup")
    def test_main_configure_firewall_only(self, mock_setup_class):
        """Test configure-firewall command."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.configure_firewall.return_value = True
        mock_setup_class.return_value = mock_setup

        result = runner.invoke(app, ["configure-firewall"])

        # Should call configure_firewall only, then exit with 0
        mock_setup.configure_firewall.assert_called_once_with(None)
        mock_setup.install_all_sdks.assert_not_called()
        mock_setup.uninstall_all_sdks.assert_not_called()
        assert result.exit_code == 0

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup")
    def test_main_custom_ip_range(self, mock_setup_class):
        """Test install command with custom IP range."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.install_all_sdks.return_value = True
        mock_setup.configure_firewall.return_value = True
        mock_setup_class.return_value = mock_setup

        result = runner.invoke(app, ["install", "--ip-range", "10.0.0.0/24"])

        # Should use custom IP range
        mock_setup.configure_firewall.assert_called_once_with("10.0.0.0/24")
        assert result.exit_code == 0

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup")
    def test_main_custom_version(self, mock_setup_class):
        """Test install command with custom SDK version."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.install_all_sdks.return_value = True
        mock_setup.configure_firewall.return_value = True
        mock_setup_class.return_value = mock_setup

        result = runner.invoke(app, ["install", "--version", "v2.0-test"])

        # Should use custom version
        mock_setup.install_all_sdks.assert_called_once_with("v2.0-test")
        assert result.exit_code == 0

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup")
    def test_main_verbose_logging(self, mock_setup_class):
        """Test install command with verbose logging."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.install_all_sdks.return_value = True
        mock_setup.configure_firewall.return_value = True
        mock_setup_class.return_value = mock_setup

        result = runner.invoke(app, ["install", "--verbose"])

        # Should set debug logging level
        mock_setup.logger.setLevel.assert_called_once()
        assert result.exit_code == 0

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup")
    def test_main_install_failure(self, mock_setup_class):
        """Test install command when installation fails."""
        # Mock CameraSystemSetup instance with failed installation
        mock_setup = Mock()
        mock_setup.install_all_sdks.return_value = False
        mock_setup_class.return_value = mock_setup

        result = runner.invoke(app, ["install"])

        # Should exit with error code 1
        mock_setup.install_all_sdks.assert_called_once_with("v1.0-stable")
        mock_setup.configure_firewall.assert_not_called()  # Should not configure firewall after failed install
        assert result.exit_code == 1

    @patch("mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup")
    def test_main_firewall_failure_after_install(self, mock_setup_class):
        """Test install command when firewall configuration fails after successful install."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.install_all_sdks.return_value = True
        mock_setup.configure_firewall.return_value = False  # Firewall fails
        mock_setup_class.return_value = mock_setup

        result = runner.invoke(app, ["install"])

        # Should call both install and firewall, then exit with error code 1
        mock_setup.install_all_sdks.assert_called_once_with("v1.0-stable")
        mock_setup.configure_firewall.assert_called_once_with(None)
        assert result.exit_code == 1


class TestScriptIntegration:
    """Test script integration and error handling."""

    def test_script_has_main_guard(self):
        """Test that script has proper main guard."""
        # Read the script file
        import mindtrace.hardware.cameras.setup.setup_cameras as setup_script

        # Should be runnable as script
        assert hasattr(setup_script, "main")
        assert callable(setup_script.main)

    def test_configure_firewall_function_integration(self):
        """Test integration of configure_firewall CLI command."""
        # Mock the function to avoid actual system calls
        with patch("mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup") as mock_class:
            mock_setup = Mock()
            mock_setup.configure_firewall.return_value = True
            mock_class.return_value = mock_setup

            result = runner.invoke(app, ["configure-firewall", "--ip-range", "192.168.1.0/24"])

            assert result.exit_code == 0
            mock_class.assert_called_once()
            mock_setup.configure_firewall.assert_called_once_with("192.168.1.0/24")

    def test_exception_handling_in_main_operations(self):
        """Test exception handling in main operations."""
        # Mock the CameraSystemSetup to test exception handling
        with patch("mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup") as mock_class:
            mock_setup = Mock()

            # Test firewall configuration with exception
            mock_setup.configure_firewall.side_effect = Exception("Test exception")
            mock_class.return_value = mock_setup

            # With Typer CLI, exceptions are caught and displayed as errors
            result = runner.invoke(app, ["configure-firewall"])
            # Exception should cause non-zero exit code
            assert result.exit_code != 0 or "Test exception" in str(result.exception)
