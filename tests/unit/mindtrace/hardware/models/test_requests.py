"""Tests for hardware request models."""

import pytest
from typing import Dict, Any
from pydantic import ValidationError

from mindtrace.hardware.models.requests import (
    CameraInitializeRequest,
    BatchCameraInitializeRequest,
    CameraConfigRequest,
    BatchCameraConfigRequest,
    CaptureRequest,
    BatchCaptureRequest,
    HDRCaptureRequest,
    BatchHDRCaptureRequest,
    ConfigFileRequest,
    ExposureRequest,
    GainRequest,
    ROIRequest,
    TriggerModeRequest,
    PixelFormatRequest,
    WhiteBalanceRequest,
    ImageEnhancementRequest,
    NetworkConcurrentLimitRequest,
    CameraQueryRequest,
    BackendFilterRequest,
    CameraPropertiesRequest,
)


class TestCameraInitializeRequest:
    """Test camera initialization request model."""

    def test_valid_request(self):
        """Test valid camera initialize request."""
        request = CameraInitializeRequest(
            camera="Basler:Camera001",
            test_connection=True
        )
        assert request.camera == "Basler:Camera001"
        assert request.test_connection is True

    def test_valid_request_without_test_connection(self):
        """Test request with default test_connection."""
        request = CameraInitializeRequest(camera="Basler:Camera001")
        assert request.camera == "Basler:Camera001"
        assert request.test_connection is True  # Default value

    def test_invalid_request_missing_camera(self):
        """Test request fails without camera name."""
        with pytest.raises(ValidationError):
            CameraInitializeRequest()

    def test_camera_name_formats(self):
        """Test various camera name formats."""
        valid_names = [
            "Basler:Camera001",
            "Mock:TestCamera",
            "OpenCV:0",
            "Backend123:Device456"
        ]
        for name in valid_names:
            request = CameraInitializeRequest(camera=name)
            assert request.camera == name


class TestBatchCameraInitializeRequest:
    """Test batch camera initialization request model."""

    def test_valid_request(self):
        """Test valid batch request."""
        cameras = ["Basler:Camera001", "Basler:Camera002", "Mock:Test"]
        request = BatchCameraInitializeRequest(
            cameras=cameras,
            test_connections=False
        )
        assert request.cameras == cameras
        assert request.test_connections is False

    def test_default_test_connections(self):
        """Test default test_connections value."""
        request = BatchCameraInitializeRequest(cameras=["Basler:Camera001"])
        assert request.test_connections is True

    def test_empty_camera_list(self):
        """Test with empty camera list."""
        request = BatchCameraInitializeRequest(cameras=[])
        assert request.cameras == []

    def test_invalid_request_missing_cameras(self):
        """Test request fails without cameras."""
        with pytest.raises(ValidationError):
            BatchCameraInitializeRequest()


class TestCameraConfigRequest:
    """Test camera configuration request model."""

    def test_valid_request(self):
        """Test valid configuration request."""
        properties = {"exposure": 10000, "gain": 1.5, "trigger_mode": "continuous"}
        request = CameraConfigRequest(
            camera="Basler:Camera001",
            properties=properties
        )
        assert request.camera == "Basler:Camera001"
        assert request.properties == properties

    def test_empty_properties(self):
        """Test with empty properties."""
        request = CameraConfigRequest(
            camera="Basler:Camera001",
            properties={}
        )
        assert request.properties == {}

    def test_complex_properties(self):
        """Test with complex property values."""
        properties = {
            "exposure": 10000,
            "gain": 1.5,
            "roi": {"x": 0, "y": 0, "width": 1920, "height": 1080},
            "trigger_mode": "continuous",
            "pixel_format": "BGR8",
            "white_balance": "auto",
            "image_enhancement": True
        }
        request = CameraConfigRequest(
            camera="Basler:Camera001",
            properties=properties
        )
        assert request.properties == properties


class TestBatchCameraConfigRequest:
    """Test batch camera configuration request model."""

    def test_valid_request(self):
        """Test valid batch configuration request."""
        configurations = {
            "Basler:Camera001": {"exposure": 10000, "gain": 1.5},
            "Basler:Camera002": {"exposure": 5000, "gain": 2.0}
        }
        request = BatchCameraConfigRequest(configurations=configurations)
        assert request.configurations == configurations

    def test_empty_configurations(self):
        """Test with empty configurations."""
        request = BatchCameraConfigRequest(configurations={})
        assert request.configurations == {}


class TestCaptureRequest:
    """Test image capture request model."""

    def test_valid_request_with_save_path(self):
        """Test capture request with save path."""
        request = CaptureRequest(
            camera="Basler:Camera001",
            save_path="/tmp/image.jpg"
        )
        assert request.camera == "Basler:Camera001"
        assert request.save_path == "/tmp/image.jpg"

    def test_valid_request_without_save_path(self):
        """Test capture request without save path."""
        request = CaptureRequest(camera="Basler:Camera001")
        assert request.camera == "Basler:Camera001"
        assert request.save_path is None


class TestBatchCaptureRequest:
    """Test batch image capture request model."""

    def test_valid_request(self):
        """Test valid batch capture request."""
        cameras = ["Basler:Camera001", "Basler:Camera002"]
        request = BatchCaptureRequest(cameras=cameras)
        assert request.cameras == cameras

    def test_single_camera(self):
        """Test with single camera."""
        request = BatchCaptureRequest(cameras=["Basler:Camera001"])
        assert request.cameras == ["Basler:Camera001"]


class TestHDRCaptureRequest:
    """Test HDR image capture request model."""

    def test_valid_request_defaults(self):
        """Test HDR request with default values."""
        request = HDRCaptureRequest(camera="Basler:Camera001")
        assert request.camera == "Basler:Camera001"
        assert request.exposure_levels == 3
        assert request.exposure_multiplier == 2.0
        assert request.save_path_pattern is None
        assert request.return_images is True

    def test_valid_request_custom_values(self):
        """Test HDR request with custom values."""
        request = HDRCaptureRequest(
            camera="Basler:Camera001",
            exposure_levels=5,
            exposure_multiplier=1.5,
            save_path_pattern="/tmp/hdr_{exposure}.jpg",
            return_images=False
        )
        assert request.exposure_levels == 5
        assert request.exposure_multiplier == 1.5
        assert request.save_path_pattern == "/tmp/hdr_{exposure}.jpg"
        assert request.return_images is False

    def test_invalid_exposure_levels_too_low(self):
        """Test exposure levels validation - too low."""
        with pytest.raises(ValidationError):
            HDRCaptureRequest(
                camera="Basler:Camera001",
                exposure_levels=1  # Below minimum of 2
            )

    def test_invalid_exposure_levels_too_high(self):
        """Test exposure levels validation - too high."""
        with pytest.raises(ValidationError):
            HDRCaptureRequest(
                camera="Basler:Camera001",
                exposure_levels=11  # Above maximum of 10
            )

    def test_invalid_exposure_multiplier_too_low(self):
        """Test exposure multiplier validation - too low."""
        with pytest.raises(ValidationError):
            HDRCaptureRequest(
                camera="Basler:Camera001",
                exposure_multiplier=1.0  # Should be > 1.0
            )

    def test_invalid_exposure_multiplier_too_high(self):
        """Test exposure multiplier validation - too high."""
        with pytest.raises(ValidationError):
            HDRCaptureRequest(
                camera="Basler:Camera001",
                exposure_multiplier=5.1  # Above maximum of 5.0
            )


class TestBatchHDRCaptureRequest:
    """Test batch HDR capture request model."""

    def test_valid_request(self):
        """Test valid batch HDR request."""
        cameras = ["Basler:Camera001", "Basler:Camera002"]
        request = BatchHDRCaptureRequest(
            cameras=cameras,
            exposure_levels=5,
            exposure_multiplier=1.5,
            save_path_pattern="/tmp/{camera}_hdr_{exposure}.jpg",
            return_images=False
        )
        assert request.cameras == cameras
        assert request.exposure_levels == 5
        assert request.exposure_multiplier == 1.5
        assert "{camera}" in request.save_path_pattern
        assert "{exposure}" in request.save_path_pattern


class TestConfigFileRequest:
    """Test configuration file request model."""

    def test_valid_request(self):
        """Test valid config file request."""
        request = ConfigFileRequest(
            camera="Basler:Camera001",
            config_path="/path/to/config.json"
        )
        assert request.camera == "Basler:Camera001"
        assert request.config_path == "/path/to/config.json"


class TestExposureRequest:
    """Test exposure request model."""

    def test_valid_request_int(self):
        """Test exposure request with integer value."""
        request = ExposureRequest(
            camera="Basler:Camera001",
            exposure=10000
        )
        assert request.camera == "Basler:Camera001"
        assert request.exposure == 10000

    def test_valid_request_float(self):
        """Test exposure request with float value."""
        request = ExposureRequest(
            camera="Basler:Camera001",
            exposure=10000.5
        )
        assert request.exposure == 10000.5


class TestGainRequest:
    """Test gain request model."""

    def test_valid_request_int(self):
        """Test gain request with integer value."""
        request = GainRequest(
            camera="Basler:Camera001",
            gain=2
        )
        assert request.gain == 2

    def test_valid_request_float(self):
        """Test gain request with float value."""
        request = GainRequest(
            camera="Basler:Camera001",
            gain=1.5
        )
        assert request.gain == 1.5


class TestROIRequest:
    """Test ROI request model."""

    def test_valid_request(self):
        """Test valid ROI request."""
        request = ROIRequest(
            camera="Basler:Camera001",
            x=100,
            y=150,
            width=800,
            height=600
        )
        assert request.x == 100
        assert request.y == 150
        assert request.width == 800
        assert request.height == 600

    def test_zero_coordinates(self):
        """Test ROI with zero coordinates."""
        request = ROIRequest(
            camera="Basler:Camera001",
            x=0,
            y=0,
            width=1920,
            height=1080
        )
        assert request.x == 0
        assert request.y == 0


class TestTriggerModeRequest:
    """Test trigger mode request model."""

    def test_valid_continuous_mode(self):
        """Test continuous trigger mode."""
        request = TriggerModeRequest(
            camera="Basler:Camera001",
            mode="continuous"
        )
        assert request.mode == "continuous"

    def test_valid_trigger_mode(self):
        """Test trigger mode."""
        request = TriggerModeRequest(
            camera="Basler:Camera001",
            mode="trigger"
        )
        assert request.mode == "trigger"


class TestPixelFormatRequest:
    """Test pixel format request model."""

    def test_valid_formats(self):
        """Test various pixel formats."""
        formats = ["BGR8", "RGB8", "Mono8", "Mono16", "YUV422"]
        for fmt in formats:
            request = PixelFormatRequest(
                camera="Basler:Camera001",
                format=fmt
            )
            assert request.format == fmt


class TestWhiteBalanceRequest:
    """Test white balance request model."""

    def test_valid_modes(self):
        """Test various white balance modes."""
        modes = ["auto", "once", "off", "manual"]
        for mode in modes:
            request = WhiteBalanceRequest(
                camera="Basler:Camera001",
                mode=mode
            )
            assert request.mode == mode


class TestImageEnhancementRequest:
    """Test image enhancement request model."""

    def test_enabled(self):
        """Test image enhancement enabled."""
        request = ImageEnhancementRequest(
            camera="Basler:Camera001",
            enabled=True
        )
        assert request.enabled is True

    def test_disabled(self):
        """Test image enhancement disabled."""
        request = ImageEnhancementRequest(
            camera="Basler:Camera001",
            enabled=False
        )
        assert request.enabled is False


class TestNetworkConcurrentLimitRequest:
    """Test network concurrent limit request model."""

    def test_valid_limit_min(self):
        """Test minimum valid limit."""
        request = NetworkConcurrentLimitRequest(limit=1)
        assert request.limit == 1

    def test_valid_limit_max(self):
        """Test maximum valid limit."""
        request = NetworkConcurrentLimitRequest(limit=10)
        assert request.limit == 10

    def test_invalid_limit_too_low(self):
        """Test limit too low."""
        with pytest.raises(ValidationError):
            NetworkConcurrentLimitRequest(limit=0)

    def test_invalid_limit_too_high(self):
        """Test limit too high."""
        with pytest.raises(ValidationError):
            NetworkConcurrentLimitRequest(limit=11)


class TestCameraQueryRequest:
    """Test camera query request model."""

    def test_valid_request(self):
        """Test valid camera query request."""
        request = CameraQueryRequest(camera="Basler:Camera001")
        assert request.camera == "Basler:Camera001"


class TestBackendFilterRequest:
    """Test backend filter request model."""

    def test_with_backend(self):
        """Test with specific backend."""
        request = BackendFilterRequest(backend="Basler")
        assert request.backend == "Basler"

    def test_without_backend(self):
        """Test without backend (all backends)."""
        request = BackendFilterRequest()
        assert request.backend is None


class TestCameraPropertiesRequest:
    """Test camera properties request model."""

    def test_all_properties(self):
        """Test request with all properties."""
        request = CameraPropertiesRequest(
            camera="Basler:Camera001",
            exposure=10000,
            gain=1.5,
            roi=(100, 150, 800, 600),
            trigger_mode="continuous",
            pixel_format="BGR8",
            white_balance="auto",
            image_enhancement=True
        )
        assert request.exposure == 10000
        assert request.gain == 1.5
        assert request.roi == (100, 150, 800, 600)
        assert request.trigger_mode == "continuous"
        assert request.pixel_format == "BGR8"
        assert request.white_balance == "auto"
        assert request.image_enhancement is True

    def test_minimal_properties(self):
        """Test request with minimal properties."""
        request = CameraPropertiesRequest(camera="Basler:Camera001")
        assert request.camera == "Basler:Camera001"
        assert request.exposure is None
        assert request.gain is None
        assert request.roi is None

    def test_partial_properties(self):
        """Test request with some properties."""
        request = CameraPropertiesRequest(
            camera="Basler:Camera001",
            exposure=5000,
            trigger_mode="trigger"
        )
        assert request.exposure == 5000
        assert request.trigger_mode == "trigger"
        assert request.gain is None


class TestModelSerialization:
    """Test model serialization and deserialization."""

    def test_json_serialization(self):
        """Test that models can be serialized to/from JSON."""
        original = CameraInitializeRequest(
            camera="Basler:Camera001",
            test_connection=True
        )
        
        # Serialize to dict
        data = original.model_dump()
        assert data["camera"] == "Basler:Camera001"
        assert data["test_connection"] is True
        
        # Deserialize from dict
        restored = CameraInitializeRequest(**data)
        assert restored.camera == original.camera
        assert restored.test_connection == original.test_connection

    def test_complex_model_serialization(self):
        """Test serialization of complex models."""
        original = CameraPropertiesRequest(
            camera="Basler:Camera001",
            exposure=10000,
            roi=(100, 150, 800, 600),
            image_enhancement=True
        )
        
        data = original.model_dump()
        restored = CameraPropertiesRequest(**data)
        
        assert restored.camera == original.camera
        assert restored.exposure == original.exposure
        assert restored.roi == original.roi
        assert restored.image_enhancement == original.image_enhancement