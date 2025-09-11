"""Tests for cameras module __init__.py lazy imports."""

import pytest


def test_direct_imports():
    """Test that direct imports work correctly."""
    from mindtrace.hardware.cameras import (
        AsyncCamera,
        AsyncCameraManager,
        Camera,
        CameraBackend,
        CameraManager,
    )

    # Verify imports are not None
    assert CameraManager is not None
    assert AsyncCameraManager is not None
    assert CameraBackend is not None
    assert Camera is not None
    assert AsyncCamera is not None


def test_availability_flags():
    """Test that availability flags work correctly."""
    from mindtrace.hardware.cameras import BASLER_AVAILABLE, OPENCV_AVAILABLE, SETUP_AVAILABLE

    # These should return boolean values
    assert isinstance(BASLER_AVAILABLE, bool)
    assert isinstance(OPENCV_AVAILABLE, bool)
    assert isinstance(SETUP_AVAILABLE, bool)


def test_setup_functions():
    """Test that setup functions can be imported when available."""
    # Test each function individually to cover different code paths
    import mindtrace.hardware.cameras

    setup_functions = [
        "install_pylon_sdk",
        "uninstall_pylon_sdk",
        "setup_all_cameras",
        "configure_firewall",
    ]

    for func_name in setup_functions:
        try:
            func = getattr(mindtrace.hardware.cameras, func_name)
            assert func is not None
        except AttributeError:
            # Expected if setup module is not available
            pass


def test_setup_available_flag():
    """Test SETUP_AVAILABLE flag behavior."""
    from mindtrace.hardware.cameras import SETUP_AVAILABLE

    assert isinstance(SETUP_AVAILABLE, bool)


def test_import_error_handling():
    """Test import error handling for unavailable backends."""
    # These might trigger the ImportError branches in __getattr__
    import mindtrace.hardware.cameras

    # Try to access backends to trigger import attempts
    basler_available = mindtrace.hardware.cameras.BASLER_AVAILABLE
    opencv_available = mindtrace.hardware.cameras.OPENCV_AVAILABLE

    assert isinstance(basler_available, bool)
    assert isinstance(opencv_available, bool)


def test_invalid_attribute_raises_error():
    """Test that accessing invalid attributes raises AttributeError."""
    import mindtrace.hardware.cameras

    with pytest.raises(
        AttributeError, match="module 'mindtrace.hardware.cameras' has no attribute 'NonExistentFunction'"
    ):
        _ = mindtrace.hardware.cameras.NonExistentFunction


def test_all_exports():
    """Test that __all__ contains expected exports."""
    import mindtrace.hardware.cameras

    expected_exports = [
        # Core camera functionality
        "CameraManager",
        "AsyncCameraManager",
        "CameraBackend",
        "Camera",
        "AsyncCamera",
        # Availability flags
        "BASLER_AVAILABLE",
        "OPENCV_AVAILABLE",
        "SETUP_AVAILABLE",
        # Setup utilities
        "install_pylon_sdk",
        "uninstall_pylon_sdk",
        "setup_all_cameras",
        "configure_firewall",
    ]

    assert mindtrace.hardware.cameras.__all__ == expected_exports
