"""Daheng Camera Backend

Provides support for Daheng Imaging cameras via the Galaxy SDK (gxipy) with mock implementation for testing.

Components:
    - DahengCameraBackend: Real Daheng camera implementation (requires gxipy + Galaxy SDK)
    - MockDahengCameraBackend: Mock implementation for testing and development

Requirements:
    - Real cameras: Galaxy SDK native libraries installed on system + gxipy Python package
    - Mock cameras: No additional dependencies

Installation:
    1. Install Galaxy SDK from https://en.daheng-imaging.com/list-59-1.html
    2. pip install iai-gxipy (or use gxipy from SDK samples)
    3. Configure camera permissions (Linux may require udev rules)

Usage:
    from mindtrace.hardware.cameras.backends.daheng import DahengCameraBackend, MockDahengCameraBackend

    # Real camera
    if DAHENG_AVAILABLE:
        camera = DahengCameraBackend("camera_serial_number")
        success, cam_obj, remote_obj = await camera.initialize()  # Initialize first
        if success:
            image = await camera.capture()
            await camera.close()

    # Mock camera (always available)
    mock_camera = MockDahengCameraBackend("mock_cam_0")
    success, cam_obj, remote_obj = await mock_camera.initialize()  # Initialize first
    if success:
        image = await mock_camera.capture()
        await mock_camera.close()
"""

# Try to import real Daheng camera implementation
try:
    from mindtrace.hardware.cameras.backends.daheng.daheng_camera_backend import (
        GXIPY_AVAILABLE,
        DahengCameraBackend,
    )

    DAHENG_AVAILABLE = GXIPY_AVAILABLE
except ImportError:
    DahengCameraBackend = None
    DAHENG_AVAILABLE = False

# Import mock camera (always available)
from mindtrace.hardware.cameras.backends.daheng.mock_daheng_camera_backend import MockDahengCameraBackend

__all__ = ["DahengCameraBackend", "MockDahengCameraBackend", "DAHENG_AVAILABLE"]
