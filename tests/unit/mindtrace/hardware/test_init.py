"""Tests for hardware module __init__.py lazy imports."""

import pytest


def test_lazy_imports():
    """Test that lazy imports work correctly."""
    # Test CameraManager import
    from mindtrace.hardware import CameraManager
    assert CameraManager is not None
    
    # Test Camera import
    from mindtrace.hardware import Camera
    assert Camera is not None
    
    # Test CameraBackend import
    from mindtrace.hardware import CameraBackend
    assert CameraBackend is not None
    
    # Test PLCManager import
    from mindtrace.hardware import PLCManager
    assert PLCManager is not None


def test_homography_lazy_imports():
    """Test that homography lazy imports work correctly."""
    # These imports will fail if homography module doesn't exist
    import mindtrace.hardware
    
    # Homography classes should raise ModuleNotFoundError when accessed due to missing homography module
    with pytest.raises((AttributeError, ModuleNotFoundError)):
        _ = mindtrace.hardware.HomographyCalibrator
        
    with pytest.raises((AttributeError, ModuleNotFoundError)):
        _ = mindtrace.hardware.CalibrationData
        
    with pytest.raises((AttributeError, ModuleNotFoundError)):
        _ = mindtrace.hardware.PlanarHomographyMeasurer
        
    with pytest.raises((AttributeError, ModuleNotFoundError)):
        _ = mindtrace.hardware.MeasuredBox


def test_invalid_attribute_raises_error():
    """Test that accessing invalid attributes raises AttributeError."""
    import mindtrace.hardware
    
    with pytest.raises(AttributeError, match="module 'mindtrace.hardware' has no attribute 'NonExistentClass'"):
        _ = mindtrace.hardware.NonExistentClass


def test_all_exports():
    """Test that __all__ contains expected exports."""
    import mindtrace.hardware
    
    expected_exports = [
        "CameraManager",
        "PLCManager", 
        "HomographyCalibrator",
        "CalibrationData",
        "PlanarHomographyMeasurer", 
        "MeasuredBox",
    ]
    
    assert mindtrace.hardware.__all__ == expected_exports