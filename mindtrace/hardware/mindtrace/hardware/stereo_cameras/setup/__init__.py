"""Setup scripts for stereo camera SDKs.

This module provides installation scripts for stereo camera systems.
"""

from mindtrace.hardware.stereo_cameras.setup.setup_stereo_ace import (
    install_stereo_ace,
    uninstall_stereo_ace,
)

__all__ = ["install_stereo_ace", "uninstall_stereo_ace"]
