"""Tests for stereo_cameras module __init__ exports."""

import pytest


def test_core_interfaces_importable():
    """Test that core stereo camera interfaces can be imported."""
    from mindtrace.hardware.stereo_cameras import AsyncStereoCamera, StereoCamera

    assert StereoCamera is not None
    assert AsyncStereoCamera is not None


def test_data_models_importable():
    """Test that data models can be imported."""
    from mindtrace.hardware.stereo_cameras import (
        PointCloudData,
        StereoCalibrationData,
        StereoGrabResult,
    )

    assert StereoGrabResult is not None
    assert StereoCalibrationData is not None
    assert PointCloudData is not None


def test_basler_backend_importable():
    """Test that Basler backend can be imported."""
    try:
        from mindtrace.hardware.stereo_cameras import BaslerStereoAceBackend

        assert BaslerStereoAceBackend is not None
    except ImportError as e:
        if "pypylon" in str(e):
            pytest.skip("pypylon not available")
        raise


def test_all_exports():
    """Test that __all__ contains expected exports."""
    import mindtrace.hardware.stereo_cameras

    expected_exports = [
        # Core interfaces
        "StereoCamera",
        "AsyncStereoCamera",
        # Data models
        "StereoGrabResult",
        "StereoCalibrationData",
        "PointCloudData",
        # Backends
        "BaslerStereoAceBackend",
    ]

    assert set(mindtrace.hardware.stereo_cameras.__all__) == set(expected_exports)


def test_direct_imports_work():
    """Test that direct imports from module work."""
    # This simulates: from mindtrace.hardware.stereo_cameras import StereoCamera
    from mindtrace.hardware.stereo_cameras import (
        AsyncStereoCamera,
        BaslerStereoAceBackend,
        PointCloudData,
        StereoCalibrationData,
        StereoCamera,
        StereoGrabResult,
    )

    # Verify all are not None
    assert StereoCamera is not None
    assert AsyncStereoCamera is not None
    assert StereoGrabResult is not None
    assert StereoCalibrationData is not None
    assert PointCloudData is not None
    assert BaslerStereoAceBackend is not None
