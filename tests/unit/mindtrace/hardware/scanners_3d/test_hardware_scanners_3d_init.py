"""Tests for scanners_3d module __init__ exports."""

import pytest


def test_core_interfaces_importable():
    """Test that core 3D scanner interfaces can be imported."""
    from mindtrace.hardware.scanners_3d import AsyncScanner3D, Scanner3D

    assert Scanner3D is not None
    assert AsyncScanner3D is not None


def test_data_models_importable():
    """Test that data models can be imported."""
    from mindtrace.hardware.scanners_3d import (
        CoordinateMap,
        PointCloudData,
        ScanComponent,
        ScanResult,
    )

    assert ScanResult is not None
    assert ScanComponent is not None
    assert CoordinateMap is not None
    assert PointCloudData is not None


def test_photoneo_backend_importable():
    """Test that Photoneo backend can be imported."""
    try:
        from mindtrace.hardware.scanners_3d import PhotoneoBackend

        assert PhotoneoBackend is not None
    except ImportError as e:
        if "harvesters" in str(e):
            pytest.skip("harvesters not available")
        raise


def test_all_exports():
    """Test that __all__ contains expected exports."""
    import mindtrace.hardware.scanners_3d

    expected_exports = [
        # Core interfaces
        "Scanner3D",
        "AsyncScanner3D",
        # Data models
        "ScanResult",
        "ScanComponent",
        "CoordinateMap",
        "PointCloudData",
        # Backends
        "PhotoneoBackend",
    ]

    assert set(mindtrace.hardware.scanners_3d.__all__) == set(expected_exports)


def test_direct_imports_work():
    """Test that direct imports from module work."""
    from mindtrace.hardware.scanners_3d import (
        AsyncScanner3D,
        CoordinateMap,
        PhotoneoBackend,
        PointCloudData,
        ScanComponent,
        Scanner3D,
        ScanResult,
    )

    # Verify all are not None
    assert Scanner3D is not None
    assert AsyncScanner3D is not None
    assert ScanResult is not None
    assert ScanComponent is not None
    assert CoordinateMap is not None
    assert PointCloudData is not None
    assert PhotoneoBackend is not None


def test_scan_component_enum_values():
    """Test that ScanComponent enum has expected values."""
    from mindtrace.hardware.scanners_3d import ScanComponent

    assert ScanComponent.RANGE.value == "Range"
    assert ScanComponent.INTENSITY.value == "Intensity"
    assert ScanComponent.CONFIDENCE.value == "Confidence"
    assert ScanComponent.NORMAL.value == "Normal"
    assert ScanComponent.COLOR.value == "ColorCamera"


def test_configuration_enums_importable():
    """Test that configuration enums can be imported from core models."""
    from mindtrace.hardware.scanners_3d.core.models import (
        CameraSpace,
        CodingQuality,
        CodingStrategy,
        HardwareTriggerSignal,
        OperationMode,
        OutputTopology,
        ScannerCapabilities,
        ScannerConfiguration,
        TextureSource,
        TriggerMode,
    )

    # Verify enums exist
    assert OperationMode.CAMERA.value == "Camera"
    assert CodingStrategy.NORMAL.value == "Normal"
    assert CodingQuality.ULTRA.value == "Ultra"
    assert TextureSource.LED.value == "LED"
    assert OutputTopology.RAW.value == "Raw"
    assert CameraSpace.PRIMARY_CAMERA.value == "PrimaryCamera"
    assert TriggerMode.SOFTWARE.value == "Software"
    assert HardwareTriggerSignal.RISING.value == "Rising"

    # Verify dataclasses exist
    assert ScannerConfiguration is not None
    assert ScannerCapabilities is not None
