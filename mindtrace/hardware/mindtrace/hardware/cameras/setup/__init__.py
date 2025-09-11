"""
Camera Setup Module

This module provides setup scripts for various camera SDKs and utilities
for configuring camera hardware in the Mindtrace system.

Available setup scripts:
- Basler Pylon SDK installation and configuration
- Basler Pylon SDK installation and configuration
- Combined camera setup and firewall configuration

Each setup script can be run independently or through console commands
defined in the project's pyproject.toml file.
"""

from mindtrace.hardware.cameras.setup.setup_basler import install_pylon_sdk, uninstall_pylon_sdk
from mindtrace.hardware.cameras.setup.setup_cameras import configure_firewall
from mindtrace.hardware.cameras.setup.setup_cameras import main as setup_all_cameras

__all__ = [
    # Basler SDK setup
    "install_pylon_sdk",
    "uninstall_pylon_sdk",
    # Combined camera setup
    "setup_all_cameras",
    "configure_firewall",
]
