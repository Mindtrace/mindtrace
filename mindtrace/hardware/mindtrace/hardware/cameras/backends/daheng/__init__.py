"""
Daheng Camera Backend

Provides support for Daheng cameras via gxipy SDK with mock implementation for testing.

Components:
    - DahengCamera: Real Daheng camera implementation (requires gxipy SDK)
    - MockDahengCamera: Mock implementation for testing and development

Requirements:
    - Real cameras: gxipy SDK (Galaxy SDK for Python)
    - Mock cameras: No additional dependencies

Installation:
    1. Install Galaxy SDK from Daheng Imaging
    2. pip install git+https://github.com/Mindtrace/gxipy.git@gxipy_deploy
    3. Configure camera permissions (Linux may require udev rules)

Usage:
    from mindtrace.hardware.cameras.backends.daheng import DahengCamera, MockDahengCamera

    # Real camera
    if DAHENG_AVAILABLE:
        camera = DahengCamera("camera_name")
        success, cam_obj, remote_obj = await camera.initialize()  # Initialize first
        if success:
            success, image = await camera.capture()
            await camera.close()

    # Mock camera (always available)
    mock_camera = MockDahengCamera("mock_cam_0")
    success, cam_obj, remote_obj = await mock_camera.initialize()  # Initialize first
    if success:
        success, image = await mock_camera.capture()
        await mock_camera.close()
"""

# Try to import real Daheng camera implementation
try:
    from .daheng_camera import GXIPY_AVAILABLE, DahengCamera

    DAHENG_AVAILABLE = GXIPY_AVAILABLE
except ImportError:
    DahengCamera = None
    DAHENG_AVAILABLE = False

# Import mock camera (always available)
from .mock_daheng import MockDahengCamera

__all__ = ["DahengCamera", "MockDahengCamera", "DAHENG_AVAILABLE"]
