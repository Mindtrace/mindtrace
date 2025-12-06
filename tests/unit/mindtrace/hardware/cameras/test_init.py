"""Tests for cameras module __init__.py lazy imports."""

import sys
from unittest.mock import patch

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


def test_basler_available_import_error(monkeypatch):
    """Test BASLER_AVAILABLE returns False when import fails.
    
    Tests the ImportError branch in __getattr__ for BASLER_AVAILABLE.
    """
    import mindtrace.hardware.cameras as cameras_module
    
    # Remove the module from sys.modules to force re-import
    basler_module_name = "mindtrace.hardware.cameras.backends.basler"
    if basler_module_name in sys.modules:
        del sys.modules[basler_module_name]
    
    # Mock the import to raise ImportError
    def mock_import(name, *args, **kwargs):
        if name == basler_module_name:
            raise ImportError("Basler module not available")
        return __import__(name, *args, **kwargs)
    
    monkeypatch.setattr("builtins.__import__", mock_import)
    
    # Access BASLER_AVAILABLE - should return False on ImportError
    result = cameras_module.BASLER_AVAILABLE
    assert result is False


def test_opencv_available_import_error(monkeypatch):
    """Test OPENCV_AVAILABLE returns False when import fails.
    
    Tests the ImportError branch in __getattr__ for OPENCV_AVAILABLE.
    """
    import mindtrace.hardware.cameras as cameras_module
    
    # Remove the module from sys.modules to force re-import
    opencv_module_name = "mindtrace.hardware.cameras.backends.opencv"
    if opencv_module_name in sys.modules:
        del sys.modules[opencv_module_name]
    
    # Mock the import to raise ImportError
    def mock_import(name, *args, **kwargs):
        if name == opencv_module_name:
            raise ImportError("OpenCV module not available")
        return __import__(name, *args, **kwargs)
    
    monkeypatch.setattr("builtins.__import__", mock_import)
    
    # Access OPENCV_AVAILABLE - should return False on ImportError
    result = cameras_module.OPENCV_AVAILABLE
    assert result is False


def test_setup_available_import_error(monkeypatch):
    """Test SETUP_AVAILABLE returns False when import fails.
    
    Tests the ImportError branch in __getattr__ for SETUP_AVAILABLE.
    """
    import mindtrace.hardware.cameras as cameras_module
    
    # Remove the module from sys.modules to force re-import
    setup_module_name = "mindtrace.hardware.cameras.setup"
    if setup_module_name in sys.modules:
        del sys.modules[setup_module_name]
    
    # Mock the import to raise ImportError
    def mock_import(name, *args, **kwargs):
        if name == setup_module_name:
            raise ImportError("Setup module not available")
        return __import__(name, *args, **kwargs)
    
    monkeypatch.setattr("builtins.__import__", mock_import)
    
    # Access SETUP_AVAILABLE - should return False on ImportError
    result = cameras_module.SETUP_AVAILABLE
    assert result is False


def test_setup_functions_import_error(monkeypatch):
    """Test setup functions raise AttributeError when import fails.
    
    Tests the ImportError branch in __getattr__ for setup functions.
    """
    import mindtrace.hardware.cameras as cameras_module
    
    # Remove the module from sys.modules to force re-import
    setup_module_name = "mindtrace.hardware.cameras.setup"
    if setup_module_name in sys.modules:
        del sys.modules[setup_module_name]
    
    # Mock the import to raise ImportError
    def mock_import(name, *args, **kwargs):
        if name == setup_module_name:
            raise ImportError("Setup module not available")
        return __import__(name, *args, **kwargs)
    
    monkeypatch.setattr("builtins.__import__", mock_import)
    
    # Access setup functions - should raise AttributeError on ImportError
    with pytest.raises(AttributeError, match="module 'mindtrace.hardware.cameras' has no attribute 'install_pylon_sdk'"):
        _ = cameras_module.install_pylon_sdk
    
    with pytest.raises(AttributeError, match="module 'mindtrace.hardware.cameras' has no attribute 'uninstall_pylon_sdk'"):
        _ = cameras_module.uninstall_pylon_sdk
    
    with pytest.raises(AttributeError, match="module 'mindtrace.hardware.cameras' has no attribute 'setup_all_cameras'"):
        _ = cameras_module.setup_all_cameras
    
    with pytest.raises(AttributeError, match="module 'mindtrace.hardware.cameras' has no attribute 'configure_firewall'"):
        _ = cameras_module.configure_firewall
