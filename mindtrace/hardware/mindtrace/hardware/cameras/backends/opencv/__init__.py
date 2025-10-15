"""OpenCV Camera Backend

Provides support for USB cameras and webcams via OpenCV with comprehensive error handling.

Components:
    - OpenCVCameraBackend: OpenCV camera implementation (requires opencv-python)

Requirements:
    - opencv-python: For camera access and image processing
    - numpy: For image array operations

Installation:
    pip install opencv-python numpy

Usage:
    from mindtrace.hardware.cameras.backends.opencv import OpenCVCameraBackend

    # USB camera (index 0)
    if OPENCV_AVAILABLE:
        camera = OpenCVCameraBackend("0")
        success, cam_obj, remote_obj = await camera.initialize()  # Initialize first
        if success:
            image = await camera.capture()
            await camera.close()
"""

# Try to import OpenCV camera implementation
try:
    from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import (
        OPENCV_AVAILABLE,
        OpenCVCameraBackend,
    )
except ImportError:
    OpenCVCameraBackend = None
    OPENCV_AVAILABLE = False

__all__ = ["OpenCVCameraBackend", "OPENCV_AVAILABLE"]
