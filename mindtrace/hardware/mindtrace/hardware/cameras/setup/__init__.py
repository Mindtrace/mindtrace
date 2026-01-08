"""
Camera Setup Module

This module provides setup scripts for various camera SDKs and utilities
for configuring camera hardware in the Mindtrace system.

Available CLI commands (after package installation):
    mindtrace-camera-setup install      # Install all camera SDKs
    mindtrace-camera-setup uninstall    # Uninstall all camera SDKs
    mindtrace-camera-basler install     # Install Basler Pylon SDK
    mindtrace-camera-basler uninstall   # Uninstall Basler Pylon SDK
    mindtrace-camera-genicam install    # Install GenICam CTI files
    mindtrace-camera-genicam uninstall  # Uninstall GenICam SDK
    mindtrace-camera-genicam verify     # Verify GenICam installation

Each setup script uses Typer for CLI and can be run independently.
"""

from mindtrace.hardware.cameras.setup.setup_basler import PylonSDKInstaller
from mindtrace.hardware.cameras.setup.setup_cameras import CameraSystemSetup, configure_firewall_helper
from mindtrace.hardware.cameras.setup.setup_genicam import GenICamCTIInstaller

__all__ = [
    # Installer classes
    "PylonSDKInstaller",
    "GenICamCTIInstaller",
    "CameraSystemSetup",
    # Helper functions
    "configure_firewall_helper",
]
