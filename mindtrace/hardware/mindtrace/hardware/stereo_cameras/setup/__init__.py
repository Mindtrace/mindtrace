"""Setup scripts for stereo camera SDKs.

This module provides installation scripts for stereo camera systems.

Available CLI commands (after package installation):
    mindtrace-stereo-basler install     # Install Stereo ace package
    mindtrace-stereo-basler uninstall   # Uninstall Stereo ace package

Each setup script uses Typer for CLI and can be run independently.
"""

from mindtrace.hardware.stereo_cameras.setup.setup_stereo_ace import StereoAceInstaller

__all__ = ["StereoAceInstaller"]
