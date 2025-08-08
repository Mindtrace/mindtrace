"""
Camera Setup Module

This module provides setup scripts for various camera SDKs and utilities
for configuring camera hardware in the Mindtrace system.

Available setup scripts:
- Basler Pylon SDK installation and configuration
- Daheng Galaxy SDK installation and configuration
- Combined camera setup and firewall configuration

Each setup script can be run independently or through console commands
defined in the project's pyproject.toml file.
"""

from .setup_basler import install_pylon_sdk, uninstall_pylon_sdk
from .setup_cameras import configure_firewall
from .setup_cameras import main as setup_all_cameras
from .setup_daheng import install_daheng_sdk, uninstall_daheng_sdk

__all__ = [
    # Basler SDK setup
    "install_pylon_sdk",
    "uninstall_pylon_sdk",
    # Daheng SDK setup
    "install_daheng_sdk",
    "uninstall_daheng_sdk",
    # Combined camera setup
    "setup_all_cameras",
    "configure_firewall",
]
