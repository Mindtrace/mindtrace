#!/usr/bin/env python3
"""
OpenCV Camera Backend

Provides support for USB cameras and webcams via OpenCV with comprehensive error handling.

Components:
    - OpenCVCamera: OpenCV camera implementation (requires opencv-python)

Requirements:
    - opencv-python: For camera access and image processing
    - numpy: For image array operations

Installation:
    pip install opencv-python numpy

Usage:
    from mindtrace.hardware.cameras.backends.opencv import OpenCVCamera
    
    # USB camera (index 0)
    if OPENCV_AVAILABLE:
        camera = OpenCVCamera("0")
        success, image = camera.capture()
        camera.close()
"""

# Try to import OpenCV camera implementation
try:
    from .opencv_camera import OpenCVCamera, OPENCV_AVAILABLE
except ImportError:
    OpenCVCamera = None
    OPENCV_AVAILABLE = False

__all__ = ["OpenCVCamera", "OPENCV_AVAILABLE"] 