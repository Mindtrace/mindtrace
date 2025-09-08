"""Tests for Camera Setup and Configuration Script."""

import argparse
import platform
import subprocess
from unittest.mock import patch, Mock, MagicMock
import pytest

from mindtrace.hardware.cameras.setup.setup_cameras import (
    CameraSystemSetup,
    configure_firewall,
    main,
)


class TestCameraSystemSetup:
    """Test cases for CameraSystemSetup class."""

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config')
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
        from mindtrace.core.base.mindtrace_base import Mindtrace
        assert isinstance(setup, Mindtrace)
        
        # Should have expected attributes
        assert hasattr(setup, 'logger')
        assert hasattr(setup, 'hardware_config')
        assert hasattr(setup, 'platform')
        assert setup.logger is not None

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config')
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
        assert hasattr(setup, 'install_all_sdks')
        assert hasattr(setup, 'uninstall_all_sdks')
        assert hasattr(setup, 'configure_firewall')
        assert callable(setup.install_all_sdks)
        assert callable(setup.uninstall_all_sdks)
        assert callable(setup.configure_firewall)

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config')
    @patch('mindtrace.hardware.cameras.setup.setup_cameras.install_pylon_sdk')
    def test_install_all_sdks_success(self, mock_install_pylon, mock_config):
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
        mock_install_pylon.return_value = True
        
        setup = CameraSystemSetup()
        result = setup.install_all_sdks()
        
        # Should call install_pylon_sdk and return success
        mock_install_pylon.assert_called_once_with("v1.0-stable")
        assert result is False  # Currently 1/2 SDKs succeed (only Basler implemented)

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config')
    @patch('mindtrace.hardware.cameras.setup.setup_cameras.install_pylon_sdk')
    def test_install_all_sdks_failure(self, mock_install_pylon, mock_config):
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
        mock_install_pylon.return_value = False
        
        setup = CameraSystemSetup()
        result = setup.install_all_sdks()
        
        # Should call install_pylon_sdk and return failure
        mock_install_pylon.assert_called_once_with("v1.0-stable")
        assert result is False

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config')
    @patch('mindtrace.hardware.cameras.setup.setup_cameras.uninstall_pylon_sdk')
    def test_uninstall_all_sdks_success(self, mock_uninstall_pylon, mock_config):
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
        mock_uninstall_pylon.return_value = True
        
        setup = CameraSystemSetup()
        result = setup.uninstall_all_sdks()
        
        # Should call uninstall_pylon_sdk and return partial success
        mock_uninstall_pylon.assert_called_once()
        assert result is False  # Currently 1/2 SDKs succeed (only Basler implemented)

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config')
    @patch('mindtrace.hardware.cameras.setup.setup_cameras.uninstall_pylon_sdk')
    def test_uninstall_all_sdks_failure(self, mock_uninstall_pylon, mock_config):
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
        mock_uninstall_pylon.return_value = False
        
        setup = CameraSystemSetup()
        result = setup.uninstall_all_sdks()
        
        # Should call uninstall_pylon_sdk and return failure
        mock_uninstall_pylon.assert_called_once()
        assert result is False

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config')
    @patch('platform.system')
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
        with patch.object(setup, '_configure_windows_firewall') as mock_windows_fw:
            mock_windows_fw.return_value = True
            
            result = setup.configure_firewall()
            
            # Should call Windows firewall configuration
            mock_windows_fw.assert_called_once_with("192.168.50.0/24")
            assert result is True

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config')
    @patch('platform.system')
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
        with patch.object(setup, '_configure_linux_firewall') as mock_linux_fw:
            mock_linux_fw.return_value = True
            
            result = setup.configure_firewall()
            
            # Should call Linux firewall configuration
            mock_linux_fw.assert_called_once_with("192.168.50.0/24")
            assert result is True

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config')
    @patch('platform.system')
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
        
        with patch.object(setup, '_configure_linux_firewall') as mock_linux_fw:
            mock_linux_fw.return_value = True
            
            result = setup.configure_firewall(custom_ip)
            
            # Should use custom IP range
            mock_linux_fw.assert_called_once_with(custom_ip)
            assert result is True

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config')
    @patch('platform.system')
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

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config')
    @patch('subprocess.run')
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

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config')
    @patch('subprocess.run')
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

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config')
    @patch('subprocess.run')
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

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config')
    @patch('subprocess.run')
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

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config')
    @patch('subprocess.run')
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

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.get_hardware_config')
    @patch('subprocess.run')
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
    """Test module-level functions."""

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup')
    def test_configure_firewall_function(self, mock_setup_class):
        """Test configure_firewall module function."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.configure_firewall.return_value = True
        mock_setup_class.return_value = mock_setup
        
        result = configure_firewall("10.0.0.0/24")
        
        # Should create setup instance and call configure_firewall
        mock_setup_class.assert_called_once()
        mock_setup.configure_firewall.assert_called_once_with("10.0.0.0/24")
        assert result is True

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup')
    def test_configure_firewall_function_no_ip_range(self, mock_setup_class):
        """Test configure_firewall function without IP range."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.configure_firewall.return_value = True
        mock_setup_class.return_value = mock_setup
        
        result = configure_firewall()
        
        # Should create setup instance and call configure_firewall with None
        mock_setup_class.assert_called_once()
        mock_setup.configure_firewall.assert_called_once_with(None)
        assert result is True


class TestMainFunction:
    """Test main function and CLI argument parsing."""

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup')
    @patch('sys.argv', ['setup_cameras.py'])
    def test_main_default_install(self, mock_setup_class):
        """Test main function with default install behavior."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.install_all_sdks.return_value = True
        mock_setup.configure_firewall.return_value = True
        mock_setup.hardware_config.get_config.return_value.network.camera_ip_range = "192.168.50.0/24"
        mock_setup.hardware_config.get_config.return_value.network.firewall_rule_name = "Allow Camera Network"
        mock_setup.hardware_config.get_config.return_value.network.firewall_timeout = 30
        mock_setup_class.return_value = mock_setup
        
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        # Should call install and firewall configuration, then exit with 0
        mock_setup.install_all_sdks.assert_called_once_with("v1.0-stable")
        mock_setup.configure_firewall.assert_called_once_with(None)
        assert exc_info.value.code == 0

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup')
    @patch('sys.argv', ['setup_cameras.py', '--uninstall'])
    def test_main_uninstall(self, mock_setup_class):
        """Test main function with uninstall flag."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.uninstall_all_sdks.return_value = True
        mock_setup.hardware_config.get_config.return_value.network.camera_ip_range = "192.168.50.0/24"
        mock_setup.hardware_config.get_config.return_value.network.firewall_rule_name = "Allow Camera Network"
        mock_setup.hardware_config.get_config.return_value.network.firewall_timeout = 30
        mock_setup_class.return_value = mock_setup
        
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        # Should call uninstall only, then exit with 0
        mock_setup.uninstall_all_sdks.assert_called_once()
        mock_setup.configure_firewall.assert_not_called()
        assert exc_info.value.code == 0

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup')
    @patch('sys.argv', ['setup_cameras.py', '--configure-firewall'])
    def test_main_configure_firewall_only(self, mock_setup_class):
        """Test main function with configure-firewall flag only."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.configure_firewall.return_value = True
        mock_setup.hardware_config.get_config.return_value.network.camera_ip_range = "192.168.50.0/24"
        mock_setup.hardware_config.get_config.return_value.network.firewall_rule_name = "Allow Camera Network"
        mock_setup.hardware_config.get_config.return_value.network.firewall_timeout = 30
        mock_setup_class.return_value = mock_setup
        
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        # Should call configure_firewall only, then exit with 0
        mock_setup.configure_firewall.assert_called_once_with(None)
        mock_setup.install_all_sdks.assert_not_called()
        mock_setup.uninstall_all_sdks.assert_not_called()
        assert exc_info.value.code == 0

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup')
    @patch('sys.argv', ['setup_cameras.py', '--ip-range', '10.0.0.0/24'])
    def test_main_custom_ip_range(self, mock_setup_class):
        """Test main function with custom IP range."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.install_all_sdks.return_value = True
        mock_setup.configure_firewall.return_value = True
        mock_setup.hardware_config.get_config.return_value.network.camera_ip_range = "192.168.50.0/24"
        mock_setup.hardware_config.get_config.return_value.network.firewall_rule_name = "Allow Camera Network"
        mock_setup.hardware_config.get_config.return_value.network.firewall_timeout = 30
        mock_setup_class.return_value = mock_setup
        
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        # Should use custom IP range
        mock_setup.configure_firewall.assert_called_once_with("10.0.0.0/24")
        assert exc_info.value.code == 0

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup')
    @patch('sys.argv', ['setup_cameras.py', '--version', 'v2.0-test'])
    def test_main_custom_version(self, mock_setup_class):
        """Test main function with custom SDK version."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.install_all_sdks.return_value = True
        mock_setup.configure_firewall.return_value = True
        mock_setup.hardware_config.get_config.return_value.network.camera_ip_range = "192.168.50.0/24"
        mock_setup.hardware_config.get_config.return_value.network.firewall_rule_name = "Allow Camera Network"
        mock_setup.hardware_config.get_config.return_value.network.firewall_timeout = 30
        mock_setup_class.return_value = mock_setup
        
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        # Should use custom version
        mock_setup.install_all_sdks.assert_called_once_with("v2.0-test")
        assert exc_info.value.code == 0

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup')
    @patch('sys.argv', ['setup_cameras.py', '--verbose'])
    def test_main_verbose_logging(self, mock_setup_class):
        """Test main function with verbose logging."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.install_all_sdks.return_value = True
        mock_setup.configure_firewall.return_value = True
        mock_setup.hardware_config.get_config.return_value.network.camera_ip_range = "192.168.50.0/24"
        mock_setup.hardware_config.get_config.return_value.network.firewall_rule_name = "Allow Camera Network"
        mock_setup.hardware_config.get_config.return_value.network.firewall_timeout = 30
        mock_setup_class.return_value = mock_setup
        
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        # Should set debug logging level
        mock_setup.logger.setLevel.assert_called_once()
        assert exc_info.value.code == 0

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup')
    @patch('sys.argv', ['setup_cameras.py'])
    def test_main_install_failure(self, mock_setup_class):
        """Test main function when installation fails."""
        # Mock CameraSystemSetup instance with failed installation
        mock_setup = Mock()
        mock_setup.install_all_sdks.return_value = False
        mock_setup.hardware_config.get_config.return_value.network.camera_ip_range = "192.168.50.0/24"
        mock_setup.hardware_config.get_config.return_value.network.firewall_rule_name = "Allow Camera Network"
        mock_setup.hardware_config.get_config.return_value.network.firewall_timeout = 30
        mock_setup_class.return_value = mock_setup
        
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        # Should exit with error code 1
        mock_setup.install_all_sdks.assert_called_once_with("v1.0-stable")
        mock_setup.configure_firewall.assert_not_called()  # Should not configure firewall after failed install
        assert exc_info.value.code == 1

    @patch('mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup')
    @patch('sys.argv', ['setup_cameras.py'])
    def test_main_firewall_failure_after_install(self, mock_setup_class):
        """Test main function when firewall configuration fails after successful install."""
        # Mock CameraSystemSetup instance
        mock_setup = Mock()
        mock_setup.install_all_sdks.return_value = True
        mock_setup.configure_firewall.return_value = False  # Firewall fails
        mock_setup.hardware_config.get_config.return_value.network.camera_ip_range = "192.168.50.0/24"
        mock_setup.hardware_config.get_config.return_value.network.firewall_rule_name = "Allow Camera Network"
        mock_setup.hardware_config.get_config.return_value.network.firewall_timeout = 30
        mock_setup_class.return_value = mock_setup
        
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        # Should call both install and firewall, then exit with error code 1
        mock_setup.install_all_sdks.assert_called_once_with("v1.0-stable")
        mock_setup.configure_firewall.assert_called_once_with(None)
        assert exc_info.value.code == 1


class TestScriptIntegration:
    """Test script integration and error handling."""

    def test_script_has_main_guard(self):
        """Test that script has proper main guard."""
        # Read the script file
        import mindtrace.hardware.cameras.setup.setup_cameras as setup_script
        
        # Should be runnable as script
        assert hasattr(setup_script, 'main')
        assert callable(setup_script.main)

    def test_configure_firewall_function_integration(self):
        """Test integration of configure_firewall function."""
        # Mock the function to avoid actual system calls
        with patch('mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup') as mock_class:
            mock_setup = Mock()
            mock_setup.configure_firewall.return_value = True
            mock_class.return_value = mock_setup
            
            result = configure_firewall("192.168.1.0/24")
            
            assert result is True
            mock_class.assert_called_once()
            mock_setup.configure_firewall.assert_called_once_with("192.168.1.0/24")

    def test_exception_handling_in_main_operations(self):
        """Test exception handling in main operations."""
        # Mock the CameraSystemSetup to test exception handling
        with patch('mindtrace.hardware.cameras.setup.setup_cameras.CameraSystemSetup') as mock_class:
            mock_setup = Mock()
            
            # Test firewall configuration with exception
            mock_setup.configure_firewall.side_effect = Exception("Test exception")
            mock_class.return_value = mock_setup
            
            # Function doesn't handle exceptions, it propagates them
            # This is the expected behavior as the caller should handle
            with pytest.raises(Exception, match="Test exception"):
                configure_firewall()