"""Basler Camera Backend

Provides support for Basler cameras via pypylon SDK with mock implementation for testing.

Components:
    - BaslerCameraBackend: Real Basler camera implementation (requires pypylon SDK)
    - MockBaslerCameraBackend: Mock implementation for testing and development

Requirements:
    - Real cameras: pypylon SDK (Pylon SDK for Python)
    - Mock cameras: No additional dependencies

Installation:
    1. Install Pylon SDK from Basler
    2. pip install pypylon
    3. Configure camera permissions (Linux may require udev rules)

Usage:
    from mindtrace.hardware.cameras.backends.basler import BaslerCameraBackend, MockBaslerCameraBackend

    # Real camera
    if BASLER_AVAILABLE:
        camera = BaslerCameraBackend("camera_name")
        success, cam_obj, remote_obj = await camera.initialize()  # Initialize first
        if success:
            image = await camera.capture()
            await camera.close()

    # Mock camera (always available)
    mock_camera = MockBaslerCameraBackend("mock_cam_0")
    success, cam_obj, remote_obj = await mock_camera.initialize()  # Initialize first
    if success:
        image = await mock_camera.capture()
        await mock_camera.close()
"""

# Try to import real Basler camera implementation
try:
    from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import (
        PYPYLON_AVAILABLE,
        BaslerCameraBackend,
    )

    BASLER_AVAILABLE = PYPYLON_AVAILABLE
except ImportError:
    BaslerCameraBackend = None
    BASLER_AVAILABLE = False

# Import mock camera (always available)
from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend

__all__ = ["BaslerCameraBackend", "MockBaslerCameraBackend", "BASLER_AVAILABLE"]
