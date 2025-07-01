#!/usr/bin/env python3
"""
Basler Camera Backend

Provides support for Basler cameras via pypylon SDK with mock implementation for testing.

Components:
    - BaslerCamera: Real Basler camera implementation (requires pypylon SDK)
    - MockBaslerCamera: Mock implementation for testing and development

Requirements:
    - Real cameras: pypylon SDK (Pylon SDK for Python)
    - Mock cameras: No additional dependencies

Installation:
    1. Install Pylon SDK from Basler
    2. pip install pypylon
    3. Configure camera permissions (Linux may require udev rules)

Usage:
    from mindtrace.hardware.cameras.backends.basler import BaslerCamera, MockBaslerCamera
    
    # Real camera
    if BASLER_AVAILABLE:
        camera = BaslerCamera("camera_name")
        success, image = camera.capture()
        camera.close()
    
    # Mock camera (always available)
    mock_camera = MockBaslerCamera("mock_cam_0")
    success, image = mock_camera.capture()
    mock_camera.close()
"""

# Try to import real Basler camera implementation
try:
    from .basler_camera import BaslerCamera, PYPYLON_AVAILABLE
    BASLER_AVAILABLE = PYPYLON_AVAILABLE
except ImportError:
    BaslerCamera = None
    BASLER_AVAILABLE = False

# Import mock camera (always available)
from .mock_basler import MockBaslerCamera

__all__ = ["BaslerCamera", "MockBaslerCamera", "BASLER_AVAILABLE"] 