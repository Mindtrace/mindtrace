#!/usr/bin/env python3
"""Camera Setup and Configuration Script

This script provides a unified interface for installing and configuring all
camera SDKs and related network settings for the Mindtrace hardware system.
It combines Basler SDK installation with firewall configuration
for camera network communication.

Features:
- Combined installation of all camera SDKs (Basler Pylon, Matrix Vision GenICam CTI)
- Firewall configuration for camera network communication
- Cross-platform support (Windows, Linux, and macOS)
- Individual SDK uninstallation support
- Comprehensive logging and error handling
- Configurable IP range and firewall settings
- Integration with Mindtrace configuration system

Configuration:
    The script uses the Mindtrace hardware configuration system for default values.
    Settings can be customized via:

    1. Environment Variables:
       - MINDTRACE_HW_NETWORK_CAMERA_IP_RANGE: IP range for firewall rules (default: 192.168.50.0/24)
       - MINDTRACE_HW_NETWORK_FIREWALL_RULE_NAME: Name for firewall rules (default: "Allow Camera Network")

    2. Configuration File (hardware_config.json):
       {
         "network": {
           "camera_ip_range": "192.168.50.0/24",
           "firewall_rule_name": "Allow Camera Network"
         }
       }

    3. Command Line Arguments (highest priority)

Usage:
    python setup_cameras.py                           # Install all SDKs
    python setup_cameras.py --uninstall               # Uninstall all SDKs
    python setup_cameras.py --configure-firewall      # Configure firewall only
    python setup_cameras.py --ip-range 10.0.0.0/24   # Use custom IP range
    mindtrace-setup-cameras                            # Console script

Network Configuration:
    The script configures firewall rules to allow camera communication on the
    specified IP range. This is essential for GigE Vision cameras that
    communicate over Ethernet. The default IP range (192.168.50.0/24) follows
    industrial camera networking standards.
"""

import logging
import platform
import subprocess
from typing import Optional

import typer

from mindtrace.core import Mindtrace
from mindtrace.hardware.cameras.setup.setup_basler import PylonSDKInstaller
from mindtrace.hardware.cameras.setup.setup_genicam import install_genicam_cti, uninstall_genicam_cti
from mindtrace.hardware.core.config import get_hardware_config

# Infrastructure setup constants
FIREWALL_OPERATION_TIMEOUT = 30.0  # Timeout for firewall setup operations in seconds

# Typer app instance
app = typer.Typer(
    name="camera-setup",
    help="Install and configure camera SDKs and network settings",
    add_completion=False,
    rich_markup_mode="rich",
)


class CameraSystemSetup(Mindtrace):
    """Unified camera system setup and configuration manager.

    This class handles the installation and configuration of all camera SDKs and related network settings for the
    Mindtrace hardware system.
    """

    def __init__(self):
        """Initialize the camera system setup manager."""
        # Initialize base class first
        super().__init__()

        # Get hardware configuration
        self.hardware_config = get_hardware_config()

        self.platform = platform.system()

        self.logger.info(f"Initializing camera system setup for {self.platform}")
        self.logger.debug(f"Camera IP range: {self.hardware_config.get_config().network.camera_ip_range}")
        self.logger.debug(f"Firewall rule name: {self.hardware_config.get_config().network.firewall_rule_name}")

    def install_all_sdks(self, release_version: str = "v1.0-stable") -> bool:
        """Install all camera SDKs.

        Args:
            release_version: SDK release version to install

        Returns:
            True if all installations successful, False otherwise
        """
        self.logger.info("Starting installation of all camera SDKs")

        success_count = 0
        total_sdks = 2

        # Install Basler Pylon SDK
        self.logger.info("Installing Basler Pylon SDK")
        try:
            pylon_installer = PylonSDKInstaller()
            if pylon_installer.install():
                self.logger.info("Basler Pylon SDK installation completed successfully")
                success_count += 1
            else:
                self.logger.error("Basler Pylon SDK installation failed")
        except Exception as e:
            self.logger.error(f"Basler Pylon SDK installation failed: {e}")

        # Install Matrix Vision GenICam CTI
        self.logger.info("Installing Matrix Vision GenICam CTI")
        if install_genicam_cti(release_version):
            self.logger.info("Matrix Vision GenICam CTI installation completed successfully")
            success_count += 1
        else:
            self.logger.error("Matrix Vision GenICam CTI installation failed")

        # Log summary
        if success_count == total_sdks:
            self.logger.info(f"All {total_sdks} camera SDKs installed successfully")
            return True
        elif success_count > 0:
            self.logger.warning(f"Partial success: {success_count}/{total_sdks} SDKs installed")
            return False
        else:
            self.logger.error("All camera SDK installations failed")
            return False

    def uninstall_all_sdks(self) -> bool:
        """Uninstall all camera SDKs.

        Returns:
            True if all uninstallations successful, False otherwise
        """
        self.logger.info("Starting uninstallation of all camera SDKs")

        success_count = 0
        total_sdks = 2

        # Uninstall Basler Pylon SDK
        self.logger.info("Uninstalling Basler Pylon SDK")
        try:
            pylon_installer = PylonSDKInstaller()
            if pylon_installer.uninstall():
                self.logger.info("Basler Pylon SDK uninstallation completed successfully")
                success_count += 1
            else:
                self.logger.error("Basler Pylon SDK uninstallation failed")
        except Exception as e:
            self.logger.error(f"Basler Pylon SDK uninstallation failed: {e}")

        # Uninstall Matrix Vision GenICam CTI
        self.logger.info("Uninstalling Matrix Vision GenICam CTI")
        if uninstall_genicam_cti():
            self.logger.info("Matrix Vision GenICam CTI uninstallation completed successfully")
            success_count += 1
        else:
            self.logger.error("Matrix Vision GenICam CTI uninstallation failed")

        # Log summary
        if success_count == total_sdks:
            self.logger.info(f"All {total_sdks} camera SDKs uninstalled successfully")
            return True
        elif success_count > 0:
            self.logger.warning(f"Partial success: {success_count}/{total_sdks} SDKs uninstalled")
            return False
        else:
            self.logger.error("All camera SDK uninstallations failed")
            return False

    def configure_firewall(self, ip_range: Optional[str] = None) -> bool:
        """Configure firewall rules to allow camera communication.

        This method configures platform-specific firewall rules to allow communication with GigE Vision cameras on the
        specified IP range.

        Args:
            ip_range: IP range to allow (uses config default if None)

        Returns:
            True if firewall configuration successful, False otherwise
        """
        # Use provided IP range or fall back to config default
        target_ip_range = ip_range or self.hardware_config.get_config().network.camera_ip_range

        self.logger.info(f"Configuring firewall for camera communication on {target_ip_range}")

        try:
            if self.platform == "Windows":
                return self._configure_windows_firewall(target_ip_range)
            elif self.platform == "Linux":
                return self._configure_linux_firewall(target_ip_range)
            else:
                self.logger.error(f"Unsupported operating system: {self.platform}")
                self.logger.info("Firewall configuration is only supported on Windows and Linux")
                return False

        except Exception as e:
            self.logger.error(f"Firewall configuration failed with unexpected error: {e}")
            return False

    def _configure_windows_firewall(self, ip_range: str) -> bool:
        """Configure Windows firewall rules.

        Args:
            ip_range: IP range to allow

        Returns:
            True if successful, False otherwise
        """
        self.logger.info("Configuring Windows firewall rules")

        rule_name = self.hardware_config.get_config().network.firewall_rule_name
        timeout = FIREWALL_OPERATION_TIMEOUT

        try:
            # Check if rule already exists
            self.logger.debug(f"Checking for existing firewall rule: {rule_name}")
            check_cmd = f'netsh advfirewall firewall show rule name="{rule_name}"'
            result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True, timeout=timeout)

            if "No rules match the specified criteria" in result.stdout:
                # Create new rule
                self.logger.info(f"Creating new Windows firewall rule for {ip_range}")
                cmd = f'netsh advfirewall firewall add rule name="{rule_name}" dir=in action=allow remoteip={ip_range}'

                result = subprocess.run(cmd, shell=True, check=True, timeout=timeout)
                self.logger.info(f"Successfully added Windows firewall rule for {ip_range}")
                return True
            else:
                self.logger.info("Windows firewall rule already exists")
                return True

        except subprocess.TimeoutExpired:
            self.logger.error(f"Windows firewall configuration timed out after {timeout}s")
            return False
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error configuring Windows firewall: {e}")
            self.logger.error("Make sure you're running with administrator privileges")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error configuring Windows firewall: {e}")
            return False

    def _configure_linux_firewall(self, ip_range: str) -> bool:
        """Configure Linux UFW firewall rules.

        Args:
            ip_range: IP range to allow

        Returns:
            True if successful, False otherwise
        """
        self.logger.info("Configuring Linux UFW firewall rules")

        timeout = FIREWALL_OPERATION_TIMEOUT

        try:
            # Check if UFW is installed and active
            self.logger.debug("Checking UFW status")
            status_result = subprocess.run(["sudo", "ufw", "status"], capture_output=True, text=True, timeout=timeout)

            if status_result.returncode != 0:
                self.logger.warning("UFW is not installed or not accessible")
                self.logger.info("Please install UFW or configure firewall manually")
                return False

            # Check if rule already exists
            self.logger.debug(f"Checking for existing UFW rule for {ip_range}")
            if ip_range in status_result.stdout:
                self.logger.info("Linux UFW rule already exists")
                return True

            # Add new rule
            self.logger.info(f"Creating new Linux UFW rule for {ip_range}")
            cmd = ["sudo", "ufw", "allow", "from", ip_range]

            _ = subprocess.run(cmd, check=True, timeout=timeout)
            self.logger.info(f"Successfully added Linux UFW rule for {ip_range}")
            return True

        except subprocess.TimeoutExpired:
            self.logger.error(f"Linux firewall configuration timed out after {timeout}s")
            return False
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error configuring Linux firewall: {e}")
            self.logger.error("Make sure you have sudo privileges and UFW is installed")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error configuring Linux firewall: {e}")
            return False


def configure_firewall_helper(ip_range: Optional[str] = None) -> bool:
    """Configure firewall rules to allow camera communication.

    This function provides a simple interface to configure firewall rules for camera network communication. It works on
    both Windows and Linux.

    Args:
        ip_range: IP range to allow (uses config default if None)

    Returns:
        True if firewall configuration successful, False otherwise
    """
    setup = CameraSystemSetup()
    return setup.configure_firewall(ip_range)


@app.command()
def install(
    version: str = typer.Option(
        "v1.0-stable",
        "--version",
        help="SDK release version to install",
    ),
    ip_range: Optional[str] = typer.Option(
        None,
        "--ip-range",
        help="IP range to allow in firewall (uses config default if not specified)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """Install all camera SDKs and configure firewall.

    Installs Basler Pylon SDK and Matrix Vision GenICam CTI files,
    then configures firewall rules for GigE Vision camera communication.
    """
    setup = CameraSystemSetup()

    if verbose:
        setup.logger.setLevel(logging.DEBUG)
        setup.logger.debug("Verbose logging enabled")

    setup.logger.info("Starting camera SDK installation")
    success = setup.install_all_sdks(version)

    if success:
        setup.logger.info("SDKs installed successfully, configuring firewall")
        firewall_success = setup.configure_firewall(ip_range)
        if not firewall_success:
            setup.logger.warning("SDK installation succeeded but firewall configuration failed")
            success = False

    if success:
        setup.logger.info("Camera setup completed successfully")
    else:
        setup.logger.error("Camera setup completed with errors")

    raise typer.Exit(code=0 if success else 1)


@app.command()
def uninstall(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """Uninstall all camera SDKs."""
    setup = CameraSystemSetup()

    if verbose:
        setup.logger.setLevel(logging.DEBUG)

    setup.logger.info("Starting camera SDK uninstallation")
    success = setup.uninstall_all_sdks()

    if success:
        setup.logger.info("Camera SDKs uninstalled successfully")
    else:
        setup.logger.error("Camera SDK uninstallation completed with errors")

    raise typer.Exit(code=0 if success else 1)


@app.command("configure-firewall")
def configure_firewall(
    ip_range: Optional[str] = typer.Option(
        None,
        "--ip-range",
        help="IP range to allow in firewall (uses config default if not specified)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """Configure firewall rules for camera network communication.

    Configures platform-specific firewall rules to allow GigE Vision
    camera communication on the specified IP range.

    Windows: Uses netsh advfirewall commands
    Linux:   Uses UFW (Uncomplicated Firewall)
    """
    setup = CameraSystemSetup()

    if verbose:
        setup.logger.setLevel(logging.DEBUG)

    setup.logger.info("Configuring firewall only (no SDK installation)")
    success = setup.configure_firewall(ip_range)

    if success:
        setup.logger.info("Firewall configured successfully")
    else:
        setup.logger.error("Firewall configuration failed")

    raise typer.Exit(code=0 if success else 1)


def main() -> None:
    """Main entry point for the camera setup script."""
    app()


if __name__ == "__main__":
    main()
