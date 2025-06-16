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
    2. pip install gxipy
    3. Configure camera permissions (Linux may require udev rules)

Usage:
    from mindtrace.hardware.cameras.backends.daheng import DahengCamera, MockDahengCamera
    
    # Real camera
    if DAHENG_AVAILABLE:
        camera = DahengCamera("camera_name")
        success, image = camera.capture()
        camera.close()
    
    # Mock camera (always available)
    mock_camera = MockDahengCamera("mock_cam_0")
    success, image = mock_camera.capture()
    mock_camera.close()
"""

# Try to import real Daheng camera implementation
try:
    from .daheng_camera import DahengCamera, GXIPY_AVAILABLE
    DAHENG_AVAILABLE = GXIPY_AVAILABLE
except ImportError:
    DahengCamera = None
    DAHENG_AVAILABLE = False

# Import mock camera (always available)
from .mock_daheng import MockDahengCamera

__all__ = ["DahengCamera", "MockDahengCamera", "DAHENG_AVAILABLE"] 