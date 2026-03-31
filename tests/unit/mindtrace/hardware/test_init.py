"""Tests for mindtrace.hardware.__init__.py module."""

import pytest


class TestHardwareModuleLazyImports:
    """Tests for lazy import functionality in hardware module."""

    def test_camera_manager_lazy_import(self):
        """Test that CameraManager is lazily imported."""
        from mindtrace.hardware import CameraManager

        assert CameraManager is not None
        assert hasattr(CameraManager, "__name__")

    def test_camera_lazy_import(self):
        """Test that Camera is lazily imported."""
        from mindtrace.hardware import Camera

        assert Camera is not None
        assert hasattr(Camera, "__name__")

    def test_camera_backend_lazy_import(self):
        """Test that CameraBackend is lazily imported."""
        from mindtrace.hardware import CameraBackend

        assert CameraBackend is not None
        assert hasattr(CameraBackend, "__name__")

    def test_plc_manager_lazy_import(self):
        """Test that PLCManager is lazily imported."""
        from mindtrace.hardware import PLCManager

        assert PLCManager is not None
        assert hasattr(PLCManager, "__name__")

    def test_sensor_manager_lazy_import(self):
        """Test that SensorManager is lazily imported."""
        from mindtrace.hardware import SensorManager

        assert SensorManager is not None
        assert hasattr(SensorManager, "__name__")

    def test_homography_calibrator_lazy_import(self):
        """Test that HomographyCalibrator is lazily imported."""
        from mindtrace.hardware import HomographyCalibrator

        assert HomographyCalibrator is not None
        assert hasattr(HomographyCalibrator, "__name__")

    def test_calibration_data_lazy_import(self):
        """Test that CalibrationData is lazily imported."""
        from mindtrace.hardware import CalibrationData

        assert CalibrationData is not None
        assert hasattr(CalibrationData, "__name__")

    def test_planar_homography_measurer_lazy_import(self):
        """Test that PlanarHomographyMeasurer is lazily imported."""
        from mindtrace.hardware import PlanarHomographyMeasurer

        assert PlanarHomographyMeasurer is not None
        assert hasattr(PlanarHomographyMeasurer, "__name__")

    def test_measured_box_lazy_import(self):
        """Test that MeasuredBox is lazily imported."""
        from mindtrace.hardware import MeasuredBox

        assert MeasuredBox is not None
        assert hasattr(MeasuredBox, "__name__")

    def test_invalid_attribute_raises_attribute_error(self):
        """Test that accessing invalid attribute raises AttributeError."""
        import mindtrace.hardware as hardware_module

        with pytest.raises(AttributeError, match="module 'mindtrace.hardware' has no attribute 'InvalidAttribute'"):
            _ = hardware_module.InvalidAttribute

    def test_all_exports_are_available(self):
        """Test that all items in __all__ are importable."""
        import mindtrace.hardware as hardware_module

        expected_exports = [
            "CameraManager",
            "PLCManager",
            "SensorManager",
            "HomographyCalibrator",
            "CalibrationData",
            "PlanarHomographyMeasurer",
            "MeasuredBox",
        ]

        for export in expected_exports:
            assert hasattr(hardware_module, export), f"{export} should be available in hardware module"
            obj = getattr(hardware_module, export)
            assert obj is not None, f"{export} should not be None"

    def test_lazy_import_returns_same_object(self):
        """Test that multiple imports return the same object."""
        from mindtrace.hardware import CameraManager as CM1
        from mindtrace.hardware import CameraManager as CM2

        assert CM1 is CM2

    def test_homography_imports_are_correct(self):
        """Test that homography-related imports return correct types."""
        from mindtrace.hardware import (
            CalibrationData,
            HomographyCalibrator,
            MeasuredBox,
            PlanarHomographyMeasurer,
        )

        # Verify they are classes/types
        assert isinstance(HomographyCalibrator, type) or callable(HomographyCalibrator)
        assert isinstance(CalibrationData, type) or callable(CalibrationData)
        assert isinstance(PlanarHomographyMeasurer, type) or callable(PlanarHomographyMeasurer)
        assert isinstance(MeasuredBox, type) or callable(MeasuredBox)
