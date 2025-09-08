"""Tests for hardware response models."""

import pytest
from datetime import datetime, timezone
from typing import Dict, Any, List

from mindtrace.hardware.models.responses import (
    BaseResponse,
    BoolResponse,
    ListResponse,
    DictResponse,
    FloatResponse,
    StringResponse,
    IntResponse,
    CameraInfo,
    CameraProperties,
    CaptureResponse,
    HDRCaptureResponse,
    ErrorResponse,
    CameraInfoResponse,
    CameraPropertiesResponse,
    CameraListResponse,
    BackendInfoResponse,
    NetworkBandwidthResponse,
    RangeResponse,
    PixelFormatListResponse,
    WhiteBalanceListResponse,
    BatchOperationResponse,
    ConfigurationResponse,
    StatusResponse,
)


class TestBaseResponse:
    """Test base response model."""

    def test_valid_response(self):
        """Test valid base response."""
        response = BaseResponse(success=True, message="Operation successful")
        assert response.success is True
        assert response.message == "Operation successful"
        assert isinstance(response.timestamp, datetime)

    def test_custom_timestamp(self):
        """Test response with custom timestamp."""
        custom_time = datetime(2023, 1, 1, 12, 0, 0)
        response = BaseResponse(
            success=True,
            message="Test",
            timestamp=custom_time
        )
        assert response.timestamp == custom_time

    def test_failed_response(self):
        """Test failed response."""
        response = BaseResponse(success=False, message="Operation failed")
        assert response.success is False
        assert response.message == "Operation failed"


class TestBoolResponse:
    """Test boolean response model."""

    def test_bool_response(self):
        """Test boolean response inherits base functionality."""
        response = BoolResponse(success=True, message="Success")
        assert response.success is True
        assert response.message == "Success"
        assert isinstance(response.timestamp, datetime)


class TestListResponse:
    """Test list response model."""

    def test_string_list(self):
        """Test response with string list."""
        data = ["item1", "item2", "item3"]
        response = ListResponse(
            success=True,
            message="List retrieved",
            data=data
        )
        assert response.data == data
        assert len(response.data) == 3

    def test_empty_list(self):
        """Test response with empty list."""
        response = ListResponse(
            success=True,
            message="Empty list",
            data=[]
        )
        assert response.data == []
        assert len(response.data) == 0

    def test_camera_names_list(self):
        """Test typical camera names list."""
        cameras = ["Basler:Camera001", "Basler:Camera002", "Mock:TestCamera"]
        response = ListResponse(
            success=True,
            message="Cameras discovered",
            data=cameras
        )
        assert all(":" in name for name in response.data)


class TestDictResponse:
    """Test dictionary response model."""

    def test_simple_dict(self):
        """Test response with simple dictionary."""
        data = {"key1": "value1", "key2": 42, "key3": True}
        response = DictResponse(
            success=True,
            message="Data retrieved",
            data=data
        )
        assert response.data == data

    def test_nested_dict(self):
        """Test response with nested dictionary."""
        data = {
            "config": {"exposure": 10000, "gain": 1.5},
            "status": {"connected": True, "errors": []}
        }
        response = DictResponse(
            success=True,
            message="Complex data",
            data=data
        )
        assert response.data["config"]["exposure"] == 10000
        assert response.data["status"]["connected"] is True


class TestFloatResponse:
    """Test float response model."""

    def test_float_value(self):
        """Test response with float value."""
        response = FloatResponse(
            success=True,
            message="Float value retrieved",
            data=123.456
        )
        assert response.data == 123.456

    def test_integer_coerced_to_float(self):
        """Test integer value in float response."""
        response = FloatResponse(
            success=True,
            message="Integer as float",
            data=42
        )
        assert response.data == 42.0
        assert isinstance(response.data, float)


class TestStringResponse:
    """Test string response model."""

    def test_string_value(self):
        """Test response with string value."""
        response = StringResponse(
            success=True,
            message="String retrieved",
            data="test string"
        )
        assert response.data == "test string"

    def test_empty_string(self):
        """Test response with empty string."""
        response = StringResponse(
            success=True,
            message="Empty string",
            data=""
        )
        assert response.data == ""


class TestIntResponse:
    """Test integer response model."""

    def test_int_value(self):
        """Test response with integer value."""
        response = IntResponse(
            success=True,
            message="Integer retrieved",
            data=42
        )
        assert response.data == 42

    def test_zero_value(self):
        """Test response with zero value."""
        response = IntResponse(
            success=True,
            message="Zero value",
            data=0
        )
        assert response.data == 0


class TestCameraInfo:
    """Test camera info model."""

    def test_valid_camera_info(self):
        """Test valid camera info."""
        info = CameraInfo(
            name="Basler:Camera001",
            backend="Basler",
            device_name="Camera001",
            active=True,
            connected=True
        )
        assert info.name == "Basler:Camera001"
        assert info.backend == "Basler"
        assert info.device_name == "Camera001"
        assert info.active is True
        assert info.connected is True

    def test_inactive_disconnected_camera(self):
        """Test inactive and disconnected camera."""
        info = CameraInfo(
            name="Mock:TestCamera",
            backend="Mock",
            device_name="TestCamera",
            active=False,
            connected=False
        )
        assert info.active is False
        assert info.connected is False


class TestCameraProperties:
    """Test camera properties model."""

    def test_all_properties_set(self):
        """Test with all properties set."""
        props = CameraProperties(
            exposure=10000.0,
            gain=1.5,
            roi=(100, 150, 800, 600),
            trigger_mode="continuous",
            pixel_format="BGR8",
            white_balance="auto",
            image_enhancement=True
        )
        assert props.exposure == 10000.0
        assert props.gain == 1.5
        assert props.roi == (100, 150, 800, 600)
        assert props.trigger_mode == "continuous"
        assert props.pixel_format == "BGR8"
        assert props.white_balance == "auto"
        assert props.image_enhancement is True

    def test_minimal_properties(self):
        """Test with minimal properties."""
        props = CameraProperties()
        assert props.exposure is None
        assert props.gain is None
        assert props.roi is None
        assert props.trigger_mode is None
        assert props.pixel_format is None
        assert props.white_balance is None
        assert props.image_enhancement is None

    def test_partial_properties(self):
        """Test with some properties set."""
        props = CameraProperties(
            exposure=5000.0,
            trigger_mode="trigger",
            pixel_format="Mono8"
        )
        assert props.exposure == 5000.0
        assert props.trigger_mode == "trigger"
        assert props.pixel_format == "Mono8"
        assert props.gain is None  # Not set


class TestCaptureResponse:
    """Test capture response model."""

    def test_capture_with_save_path(self):
        """Test capture response with save path."""
        response = CaptureResponse(
            success=True,
            message="Image captured",
            save_path="/tmp/image.jpg",
            media_type="image/jpeg"
        )
        assert response.save_path == "/tmp/image.jpg"
        assert response.media_type == "image/jpeg"
        assert response.image_data is None

    def test_capture_with_image_data(self):
        """Test capture response with base64 image data."""
        image_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        response = CaptureResponse(
            success=True,
            message="Image captured",
            image_data=image_data,
            media_type="image/png"
        )
        assert response.image_data == image_data
        assert response.media_type == "image/png"

    def test_default_media_type(self):
        """Test default media type."""
        response = CaptureResponse(success=True, message="Test")
        assert response.media_type == "image/jpeg"


class TestHDRCaptureResponse:
    """Test HDR capture response model."""

    def test_successful_hdr_capture(self):
        """Test successful HDR capture."""
        images = ["image1_base64", "image2_base64", "image3_base64"]
        exposure_levels = [1000.0, 2000.0, 4000.0]
        
        response = HDRCaptureResponse(
            success=True,
            message="HDR capture complete",
            images=images,
            exposure_levels=exposure_levels,
            successful_captures=3
        )
        assert response.images == images
        assert response.exposure_levels == exposure_levels
        assert response.successful_captures == 3

    def test_partial_hdr_capture(self):
        """Test partial HDR capture success."""
        response = HDRCaptureResponse(
            success=False,
            message="Partial HDR capture",
            successful_captures=2
        )
        assert response.successful_captures == 2
        assert response.images is None
        assert response.exposure_levels is None

    def test_failed_hdr_capture(self):
        """Test completely failed HDR capture."""
        response = HDRCaptureResponse(
            success=False,
            message="HDR capture failed",
            successful_captures=0
        )
        assert response.successful_captures == 0


class TestErrorResponse:
    """Test error response model."""

    def test_basic_error(self):
        """Test basic error response."""
        response = ErrorResponse(
            message="Camera not found",
            error_type="CameraNotFoundError",
            error_code="CAMERA_404"
        )
        assert response.success is False  # Default value
        assert response.error_type == "CameraNotFoundError"
        assert response.error_code == "CAMERA_404"
        assert response.details is None
        assert response.traceback is None

    def test_detailed_error(self):
        """Test error response with details."""
        details = {"camera": "Basler:Camera001", "backend_status": "offline"}
        response = ErrorResponse(
            message="Connection failed",
            error_type="CameraConnectionError",
            error_code="CONNECTION_FAILED",
            details=details,
            traceback="Traceback (most recent call last)..."
        )
        assert response.details == details
        assert "Traceback" in response.traceback


class TestCameraInfoResponse:
    """Test camera info response model."""

    def test_camera_info_response(self):
        """Test camera info response."""
        info = CameraInfo(
            name="Basler:Camera001",
            backend="Basler",
            device_name="Camera001",
            active=True,
            connected=True
        )
        response = CameraInfoResponse(
            success=True,
            message="Camera info retrieved",
            data=info
        )
        assert isinstance(response.data, CameraInfo)
        assert response.data.name == "Basler:Camera001"


class TestCameraPropertiesResponse:
    """Test camera properties response model."""

    def test_properties_response(self):
        """Test camera properties response."""
        props = CameraProperties(
            exposure=10000.0,
            gain=1.5,
            trigger_mode="continuous"
        )
        response = CameraPropertiesResponse(
            success=True,
            message="Properties retrieved",
            data=props
        )
        assert isinstance(response.data, CameraProperties)
        assert response.data.exposure == 10000.0


class TestCameraListResponse:
    """Test camera list response model."""

    def test_camera_list_response(self):
        """Test camera list response."""
        cameras = [
            CameraInfo(
                name="Basler:Camera001",
                backend="Basler",
                device_name="Camera001",
                active=True,
                connected=True
            ),
            CameraInfo(
                name="Mock:TestCamera",
                backend="Mock",
                device_name="TestCamera",
                active=False,
                connected=False
            )
        ]
        response = CameraListResponse(
            success=True,
            message="Camera list retrieved",
            data=cameras
        )
        assert len(response.data) == 2
        assert all(isinstance(cam, CameraInfo) for cam in response.data)


class TestBackendInfoResponse:
    """Test backend info response model."""

    def test_backend_info_response(self):
        """Test backend info response."""
        data = {
            "Basler": {"available": True, "sdk_version": "6.3.0"},
            "OpenCV": {"available": True, "sdk_version": "4.8.0"},
            "Mock": {"available": True, "sdk_version": "1.0.0"}
        }
        response = BackendInfoResponse(
            success=True,
            message="Backend info retrieved",
            data=data
        )
        assert "Basler" in response.data
        assert response.data["Basler"]["available"] is True


class TestNetworkBandwidthResponse:
    """Test network bandwidth response model."""

    def test_bandwidth_response(self):
        """Test network bandwidth response."""
        data = {
            "current_usage": 75.5,
            "max_bandwidth": 1000.0,
            "active_streams": 3
        }
        response = NetworkBandwidthResponse(
            success=True,
            message="Bandwidth info retrieved",
            data=data
        )
        assert response.data["current_usage"] == 75.5
        assert response.data["active_streams"] == 3


class TestRangeResponse:
    """Test range response model."""

    def test_range_response(self):
        """Test parameter range response."""
        response = RangeResponse(
            success=True,
            message="Exposure range retrieved",
            data=(1000.0, 50000.0)
        )
        assert response.data == (1000.0, 50000.0)
        assert len(response.data) == 2

    def test_gain_range(self):
        """Test gain range response."""
        response = RangeResponse(
            success=True,
            message="Gain range",
            data=(0.0, 10.0)
        )
        assert response.data[0] == 0.0
        assert response.data[1] == 10.0


class TestPixelFormatListResponse:
    """Test pixel format list response model."""

    def test_pixel_format_list(self):
        """Test pixel format list response."""
        formats = ["BGR8", "RGB8", "Mono8", "Mono16", "YUV422"]
        response = PixelFormatListResponse(
            success=True,
            message="Pixel formats retrieved",
            data=formats
        )
        assert response.data == formats
        assert "BGR8" in response.data


class TestWhiteBalanceListResponse:
    """Test white balance list response model."""

    def test_white_balance_list(self):
        """Test white balance list response."""
        modes = ["auto", "once", "off", "manual"]
        response = WhiteBalanceListResponse(
            success=True,
            message="White balance modes",
            data=modes
        )
        assert response.data == modes
        assert "auto" in response.data


class TestBatchOperationResponse:
    """Test batch operation response model."""

    def test_successful_batch_operation(self):
        """Test successful batch operation."""
        results = {
            "Basler:Camera001": True,
            "Basler:Camera002": True,
            "Mock:TestCamera": True
        }
        response = BatchOperationResponse(
            success=True,
            message="Batch operation completed",
            results=results,
            successful_count=3,
            failed_count=0
        )
        assert response.results == results
        assert response.successful_count == 3
        assert response.failed_count == 0

    def test_partial_batch_operation(self):
        """Test partially successful batch operation."""
        results = {
            "Basler:Camera001": True,
            "Basler:Camera002": False,
            "Mock:TestCamera": True
        }
        response = BatchOperationResponse(
            success=False,
            message="Batch operation partially failed",
            results=results,
            successful_count=2,
            failed_count=1
        )
        assert response.successful_count == 2
        assert response.failed_count == 1
        assert response.results["Basler:Camera002"] is False


class TestConfigurationResponse:
    """Test configuration response model."""

    def test_configuration_response(self):
        """Test configuration response."""
        config_data = {
            "exposure": 10000,
            "gain": 1.5,
            "trigger_mode": "continuous",
            "pixel_format": "BGR8"
        }
        response = ConfigurationResponse(
            success=True,
            message="Configuration retrieved",
            data=config_data
        )
        assert response.data == config_data
        assert response.data["exposure"] == 10000


class TestStatusResponse:
    """Test status response model."""

    def test_status_response(self):
        """Test status response."""
        status_data = {
            "camera_count": 5,
            "active_connections": 3,
            "system_health": "good",
            "last_error": None
        }
        response = StatusResponse(
            success=True,
            message="Status retrieved",
            data=status_data
        )
        assert response.data == status_data
        assert response.data["camera_count"] == 5


class TestResponseSerialization:
    """Test response model serialization."""

    def test_json_serialization(self):
        """Test that responses can be serialized to JSON-compatible format."""
        info = CameraInfo(
            name="Basler:Camera001",
            backend="Basler",
            device_name="Camera001",
            active=True,
            connected=True
        )
        response = CameraInfoResponse(
            success=True,
            message="Camera info",
            data=info
        )
        
        # Serialize to dict
        data = response.model_dump()
        assert data["success"] is True
        assert data["message"] == "Camera info"
        assert data["data"]["name"] == "Basler:Camera001"

    def test_timestamp_serialization(self):
        """Test timestamp serialization."""
        response = BaseResponse(success=True, message="Test")
        data = response.model_dump()
        
        # Timestamp should be serializable
        assert "timestamp" in data
        assert isinstance(data["timestamp"], datetime)

    def test_complex_response_serialization(self):
        """Test complex response serialization."""
        cameras = [
            CameraInfo(
                name="Basler:Camera001",
                backend="Basler",
                device_name="Camera001",
                active=True,
                connected=True
            )
        ]
        response = CameraListResponse(
            success=True,
            message="Camera list",
            data=cameras
        )
        
        data = response.model_dump()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "Basler:Camera001"