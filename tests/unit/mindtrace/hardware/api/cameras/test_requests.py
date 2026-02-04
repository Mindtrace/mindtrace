"""Tests for mindtrace.hardware.api.cameras.models.requests module."""

import pytest
from pydantic import ValidationError

from mindtrace.hardware.api.cameras.models.requests import (
    BackendFilterRequest,
    BandwidthLimitCameraRequest,
    BandwidthLimitRequest,
    CameraCloseBatchRequest,
    CameraCloseRequest,
    CameraConfigureBatchRequest,
    CameraConfigureRequest,
    CameraOpenBatchRequest,
    CameraOpenRequest,
    CameraQueryRequest,
    CaptureBatchRequest,
    CaptureHDRBatchRequest,
    CaptureHDRRequest,
    CaptureImageRequest,
    ConfigFileExportRequest,
    ConfigFileImportRequest,
    ExposureRequest,
    GainRequest,
    ImageEnhancementRequest,
    InterPacketDelayRequest,
    PacketSizeRequest,
    PixelFormatRequest,
    ROIRequest,
    TriggerModeRequest,
    WhiteBalanceRequest,
)


class TestBackendFilterRequest:
    """Tests for BackendFilterRequest model."""

    def test_backend_filter_request_with_backend(self):
        """Test BackendFilterRequest with backend specified."""
        request = BackendFilterRequest(backend="Basler")
        assert request.backend == "Basler"

    def test_backend_filter_request_without_backend(self):
        """Test BackendFilterRequest without backend (optional)."""
        request = BackendFilterRequest()
        assert request.backend is None


class TestCameraOpenRequest:
    """Tests for CameraOpenRequest model."""

    def test_camera_open_request_required_fields(self):
        """Test CameraOpenRequest with required fields."""
        request = CameraOpenRequest(camera="Basler:device1")
        assert request.camera == "Basler:device1"
        assert request.test_connection is False  # Default value

    def test_camera_open_request_with_test_connection(self):
        """Test CameraOpenRequest with test_connection set."""
        request = CameraOpenRequest(camera="Basler:device1", test_connection=False)
        assert request.camera == "Basler:device1"
        assert request.test_connection is False


class TestCameraOpenBatchRequest:
    """Tests for CameraOpenBatchRequest model."""

    def test_camera_open_batch_request(self):
        """Test CameraOpenBatchRequest with cameras list."""
        request = CameraOpenBatchRequest(cameras=["Basler:device1", "OpenCV:device2"])
        assert request.cameras == ["Basler:device1", "OpenCV:device2"]
        assert request.test_connection is False  # Default value


class TestCameraCloseRequest:
    """Tests for CameraCloseRequest model."""

    def test_camera_close_request(self):
        """Test CameraCloseRequest with camera name."""
        request = CameraCloseRequest(camera="Basler:device1")
        assert request.camera == "Basler:device1"


class TestCameraCloseBatchRequest:
    """Tests for CameraCloseBatchRequest model."""

    def test_camera_close_batch_request(self):
        """Test CameraCloseBatchRequest with cameras list."""
        request = CameraCloseBatchRequest(cameras=["Basler:device1", "OpenCV:device2"])
        assert request.cameras == ["Basler:device1", "OpenCV:device2"]


class TestCameraConfigureRequest:
    """Tests for CameraConfigureRequest model."""

    def test_camera_configure_request(self):
        """Test CameraConfigureRequest with camera and properties."""
        request = CameraConfigureRequest(camera="Basler:device1", properties={"gain": 1.5, "exposure": 1000})
        assert request.camera == "Basler:device1"
        assert request.properties == {"gain": 1.5, "exposure": 1000}


class TestCameraConfigureBatchRequest:
    """Tests for CameraConfigureBatchRequest model."""

    def test_camera_configure_batch_request(self):
        """Test CameraConfigureBatchRequest with configurations."""
        configs = {
            "Basler:device1": {"gain": 1.5},
            "OpenCV:device2": {"exposure": 1000},
        }
        request = CameraConfigureBatchRequest(configurations=configs)
        assert request.configurations == configs


class TestCameraQueryRequest:
    """Tests for CameraQueryRequest model."""

    def test_camera_query_request(self):
        """Test CameraQueryRequest with camera name."""
        request = CameraQueryRequest(camera="Basler:device1")
        assert request.camera == "Basler:device1"


class TestConfigFileImportRequest:
    """Tests for ConfigFileImportRequest model."""

    def test_config_file_import_request(self):
        """Test ConfigFileImportRequest with camera and config_path."""
        request = ConfigFileImportRequest(camera="Basler:device1", config_path="/path/to/config.json")
        assert request.camera == "Basler:device1"
        assert request.config_path == "/path/to/config.json"


class TestConfigFileExportRequest:
    """Tests for ConfigFileExportRequest model."""

    def test_config_file_export_request(self):
        """Test ConfigFileExportRequest with camera and config_path."""
        request = ConfigFileExportRequest(camera="Basler:device1", config_path="/path/to/config.json")
        assert request.camera == "Basler:device1"
        assert request.config_path == "/path/to/config.json"


class TestCaptureImageRequest:
    """Tests for CaptureImageRequest model."""

    def test_capture_image_request_minimal(self):
        """Test CaptureImageRequest with minimal required fields."""
        request = CaptureImageRequest(camera="Basler:device1")
        assert request.camera == "Basler:device1"
        assert request.save_path is None
        assert request.output_format == "pil"

    def test_capture_image_request_all_fields(self):
        """Test CaptureImageRequest with all fields."""
        request = CaptureImageRequest(
            camera="Basler:device1",
            save_path="/path/to/image.jpg",
            output_format="numpy",
        )
        assert request.camera == "Basler:device1"
        assert request.save_path == "/path/to/image.jpg"
        assert request.output_format == "numpy"

    def test_capture_image_request_output_format_numpy(self):
        """Test CaptureImageRequest with numpy output format."""
        request = CaptureImageRequest(camera="Basler:device1", output_format="numpy")
        assert request.output_format == "numpy"

    def test_capture_image_request_output_format_pil(self):
        """Test CaptureImageRequest with pil output format."""
        request = CaptureImageRequest(camera="Basler:device1", output_format="pil")
        assert request.output_format == "pil"

    def test_capture_image_request_output_format_case_insensitive(self):
        """Test CaptureImageRequest with case-insensitive output format."""
        request = CaptureImageRequest(camera="Basler:device1", output_format="NUMPY")
        assert request.output_format == "numpy"

        request2 = CaptureImageRequest(camera="Basler:device1", output_format="PIL")
        assert request2.output_format == "pil"

    def test_capture_image_request_invalid_output_format(self):
        """Test CaptureImageRequest with invalid output format raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            CaptureImageRequest(camera="Basler:device1", output_format="invalid")

        errors = exc_info.value.errors()
        assert len(errors) > 0
        # Check that the error is about output_format
        assert any("output_format" in str(error) for error in errors)


class TestCaptureBatchRequest:
    """Tests for CaptureBatchRequest model."""

    def test_capture_batch_request_minimal(self):
        """Test CaptureBatchRequest with minimal required fields."""
        request = CaptureBatchRequest(cameras=["Basler:device1", "OpenCV:device2"])
        assert request.cameras == ["Basler:device1", "OpenCV:device2"]
        assert request.output_format == "pil"

    def test_capture_batch_request_all_fields(self):
        """Test CaptureBatchRequest with all fields."""
        request = CaptureBatchRequest(
            cameras=["Basler:device1"],
            output_format="numpy",
        )
        assert request.cameras == ["Basler:device1"]
        assert request.output_format == "numpy"

    def test_capture_batch_request_invalid_output_format(self):
        """Test CaptureBatchRequest with invalid output format raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            CaptureBatchRequest(cameras=["Basler:device1"], output_format="invalid")

        errors = exc_info.value.errors()
        assert len(errors) > 0
        # Check that the error is about output_format
        assert any("output_format" in str(error) for error in errors)


class TestCaptureHDRRequest:
    """Tests for CaptureHDRRequest model."""

    def test_capture_hdr_request_minimal(self):
        """Test CaptureHDRRequest with minimal required fields."""
        request = CaptureHDRRequest(camera="Basler:device1")
        assert request.camera == "Basler:device1"
        assert request.save_path_pattern is None
        assert request.exposure_levels == 3
        assert request.exposure_multiplier == 2.0
        assert request.return_images is True
        assert request.output_format == "pil"

    def test_capture_hdr_request_all_fields(self):
        """Test CaptureHDRRequest with all fields."""
        request = CaptureHDRRequest(
            camera="Basler:device1",
            save_path_pattern="/path/to/image_{exposure}.jpg",
            exposure_levels=5,
            exposure_multiplier=2.5,
            return_images=False,
            output_format="numpy",
        )
        assert request.camera == "Basler:device1"
        assert request.save_path_pattern == "/path/to/image_{exposure}.jpg"
        assert request.exposure_levels == 5
        assert request.exposure_multiplier == 2.5
        assert request.return_images is False
        assert request.output_format == "numpy"

    def test_capture_hdr_request_exposure_levels_bounds(self):
        """Test CaptureHDRRequest with exposure_levels at bounds."""
        # Minimum value
        request = CaptureHDRRequest(camera="Basler:device1", exposure_levels=2)
        assert request.exposure_levels == 2

        # Maximum value
        request = CaptureHDRRequest(camera="Basler:device1", exposure_levels=10)
        assert request.exposure_levels == 10

    def test_capture_hdr_request_exposure_multiplier_bounds(self):
        """Test CaptureHDRRequest with exposure_multiplier at bounds."""
        # Just above minimum
        request = CaptureHDRRequest(camera="Basler:device1", exposure_multiplier=1.1)
        assert request.exposure_multiplier == 1.1

        # Maximum value
        request = CaptureHDRRequest(camera="Basler:device1", exposure_multiplier=5.0)
        assert request.exposure_multiplier == 5.0

    def test_capture_hdr_request_invalid_output_format(self):
        """Test CaptureHDRRequest with invalid output format raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            CaptureHDRRequest(camera="Basler:device1", output_format="invalid")

        errors = exc_info.value.errors()
        assert len(errors) > 0
        # Check that the error is about output_format
        assert any("output_format" in str(error) for error in errors)


class TestCaptureHDRBatchRequest:
    """Tests for CaptureHDRBatchRequest model."""

    def test_capture_hdr_batch_request_minimal(self):
        """Test CaptureHDRBatchRequest with minimal required fields."""
        request = CaptureHDRBatchRequest(cameras=["Basler:device1", "OpenCV:device2"])
        assert request.cameras == ["Basler:device1", "OpenCV:device2"]
        assert request.save_path_pattern is None
        assert request.exposure_levels == 3
        assert request.exposure_multiplier == 2.0
        assert request.return_images is True
        assert request.output_format == "pil"

    def test_capture_hdr_batch_request_all_fields(self):
        """Test CaptureHDRBatchRequest with all fields."""
        request = CaptureHDRBatchRequest(
            cameras=["Basler:device1"],
            save_path_pattern="/path/to/{camera}_{exposure}.jpg",
            exposure_levels=4,
            exposure_multiplier=3.0,
            return_images=False,
            output_format="numpy",
        )
        assert request.cameras == ["Basler:device1"]
        assert request.save_path_pattern == "/path/to/{camera}_{exposure}.jpg"
        assert request.exposure_levels == 4
        assert request.exposure_multiplier == 3.0
        assert request.return_images is False
        assert request.output_format == "numpy"

    def test_capture_hdr_batch_request_invalid_output_format(self):
        """Test CaptureHDRBatchRequest with invalid output format raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            CaptureHDRBatchRequest(cameras=["Basler:device1"], output_format="invalid")

        errors = exc_info.value.errors()
        assert len(errors) > 0
        # Check that the error is about output_format
        assert any("output_format" in str(error) for error in errors)


class TestBandwidthLimitRequest:
    """Tests for BandwidthLimitRequest model."""

    def test_bandwidth_limit_request(self):
        """Test BandwidthLimitRequest with max_concurrent_captures."""
        request = BandwidthLimitRequest(max_concurrent_captures=5)
        assert request.max_concurrent_captures == 5

    def test_bandwidth_limit_request_bounds(self):
        """Test BandwidthLimitRequest with bounds."""
        # Minimum value
        request = BandwidthLimitRequest(max_concurrent_captures=1)
        assert request.max_concurrent_captures == 1

        # Maximum value
        request = BandwidthLimitRequest(max_concurrent_captures=10)
        assert request.max_concurrent_captures == 10


class TestExposureRequest:
    """Tests for ExposureRequest model."""

    def test_exposure_request_with_int(self):
        """Test ExposureRequest with integer exposure."""
        request = ExposureRequest(camera="Basler:device1", exposure=1000)
        assert request.camera == "Basler:device1"
        assert request.exposure == 1000

    def test_exposure_request_with_float(self):
        """Test ExposureRequest with float exposure."""
        request = ExposureRequest(camera="Basler:device1", exposure=1000.5)
        assert request.camera == "Basler:device1"
        assert request.exposure == 1000.5


class TestGainRequest:
    """Tests for GainRequest model."""

    def test_gain_request_with_int(self):
        """Test GainRequest with integer gain."""
        request = GainRequest(camera="Basler:device1", gain=10)
        assert request.camera == "Basler:device1"
        assert request.gain == 10

    def test_gain_request_with_float(self):
        """Test GainRequest with float gain."""
        request = GainRequest(camera="Basler:device1", gain=1.5)
        assert request.camera == "Basler:device1"
        assert request.gain == 1.5


class TestROIRequest:
    """Tests for ROIRequest model."""

    def test_roi_request(self):
        """Test ROIRequest with all required fields."""
        request = ROIRequest(camera="Basler:device1", x=10, y=20, width=100, height=200)
        assert request.camera == "Basler:device1"
        assert request.x == 10
        assert request.y == 20
        assert request.width == 100
        assert request.height == 200


class TestTriggerModeRequest:
    """Tests for TriggerModeRequest model."""

    def test_trigger_mode_request_continuous(self):
        """Test TriggerModeRequest with continuous mode."""
        request = TriggerModeRequest(camera="Basler:device1", mode="continuous")
        assert request.camera == "Basler:device1"
        assert request.mode == "continuous"

    def test_trigger_mode_request_trigger(self):
        """Test TriggerModeRequest with trigger mode."""
        request = TriggerModeRequest(camera="Basler:device1", mode="trigger")
        assert request.camera == "Basler:device1"
        assert request.mode == "trigger"


class TestPixelFormatRequest:
    """Tests for PixelFormatRequest model."""

    def test_pixel_format_request(self):
        """Test PixelFormatRequest with format."""
        request = PixelFormatRequest(camera="Basler:device1", format="BGR8")
        assert request.camera == "Basler:device1"
        assert request.format == "BGR8"


class TestWhiteBalanceRequest:
    """Tests for WhiteBalanceRequest model."""

    def test_white_balance_request(self):
        """Test WhiteBalanceRequest with mode."""
        request = WhiteBalanceRequest(camera="Basler:device1", mode="auto")
        assert request.camera == "Basler:device1"
        assert request.mode == "auto"


class TestImageEnhancementRequest:
    """Tests for ImageEnhancementRequest model."""

    def test_image_enhancement_request_enabled(self):
        """Test ImageEnhancementRequest with enabled=True."""
        request = ImageEnhancementRequest(camera="Basler:device1", enabled=True)
        assert request.camera == "Basler:device1"
        assert request.enabled is True

    def test_image_enhancement_request_disabled(self):
        """Test ImageEnhancementRequest with enabled=False."""
        request = ImageEnhancementRequest(camera="Basler:device1", enabled=False)
        assert request.camera == "Basler:device1"
        assert request.enabled is False


class TestBandwidthLimitCameraRequest:
    """Tests for BandwidthLimitCameraRequest model."""

    def test_bandwidth_limit_camera_request_with_int(self):
        """Test BandwidthLimitCameraRequest with integer bandwidth_limit."""
        request = BandwidthLimitCameraRequest(camera="Basler:device1", bandwidth_limit=1000000)
        assert request.camera == "Basler:device1"
        assert request.bandwidth_limit == 1000000

    def test_bandwidth_limit_camera_request_with_float(self):
        """Test BandwidthLimitCameraRequest with float bandwidth_limit."""
        request = BandwidthLimitCameraRequest(camera="Basler:device1", bandwidth_limit=1000000.5)
        assert request.camera == "Basler:device1"
        assert request.bandwidth_limit == 1000000.5


class TestPacketSizeRequest:
    """Tests for PacketSizeRequest model."""

    def test_packet_size_request(self):
        """Test PacketSizeRequest with packet_size."""
        request = PacketSizeRequest(camera="Basler:device1", packet_size=1500)
        assert request.camera == "Basler:device1"
        assert request.packet_size == 1500


class TestInterPacketDelayRequest:
    """Tests for InterPacketDelayRequest model."""

    def test_inter_packet_delay_request_with_int(self):
        """Test InterPacketDelayRequest with integer delay."""
        request = InterPacketDelayRequest(camera="Basler:device1", delay=100)
        assert request.camera == "Basler:device1"
        assert request.delay == 100

    def test_inter_packet_delay_request_with_float(self):
        """Test InterPacketDelayRequest with float delay."""
        request = InterPacketDelayRequest(camera="Basler:device1", delay=100.5)
        assert request.camera == "Basler:device1"
        assert request.delay == 100.5
