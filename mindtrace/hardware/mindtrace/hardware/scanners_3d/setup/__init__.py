"""Setup utilities for 3D scanners."""

from mindtrace.hardware.scanners_3d.setup.setup_photoneo import (
    PhotoneoSetup,
    install_photoneo_sdk,
    uninstall_photoneo_sdk,
    verify_photoneo_sdk,
)

__all__ = [
    "PhotoneoSetup",
    "install_photoneo_sdk",
    "uninstall_photoneo_sdk",
    "verify_photoneo_sdk",
]
