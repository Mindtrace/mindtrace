"""Tests for OpenCV backend __init__.py."""

import pytest


def test_opencv_imports():
    """Test OpenCV backend imports."""
    from mindtrace.hardware.cameras.backends.opencv import OpenCVCameraBackend, OPENCV_AVAILABLE
    
    # Should import successfully
    assert OPENCV_AVAILABLE in [True, False]  # Boolean value
    
    if OPENCV_AVAILABLE:
        assert OpenCVCameraBackend is not None
    else:
        # If not available, should be None
        assert OpenCVCameraBackend is None


def test_all_exports():
    """Test __all__ contains expected exports."""
    import mindtrace.hardware.cameras.backends.opencv
    
    expected_exports = ["OpenCVCameraBackend", "OPENCV_AVAILABLE"]
    assert mindtrace.hardware.cameras.backends.opencv.__all__ == expected_exports