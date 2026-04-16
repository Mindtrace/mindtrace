"""Tests for CameraManagerService API layer.

These tests focus on real business logic:
- Request validation and error handling
- Response formatting and data conversion
- Service lifecycle and camera manager integration
- Error mapping from internal exceptions to API responses
"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest

from mindtrace.hardware.core.exceptions import (
    CameraConfigurationError,
    CameraConnectionError,
    CameraInitializationError,
    CameraNotFoundError,
)
from mindtrace.hardware.core.types import ServiceStatus
from mindtrace.hardware.services.cameras.models.requests import (
    BackendFilterRequest,
    CameraCloseRequest,
    CameraConfigureBatchRequest,
    CameraConfigureRequest,
    CameraOpenRequest,
    CameraQueryRequest,
    CaptureBatchRequest,
    CaptureHDRBatchRequest,
    CaptureHDRRequest,
    CaptureImageRequest,
    ConfigFileExportRequest,
    ConfigFileImportRequest,
    HomographyCalibrateCheckerboardRequest,
    HomographyCalibrateCorrespondencesRequest,
    HomographyCalibrateMultiViewRequest,
    HomographyMeasureBatchRequest,
    HomographyMeasureBoundingBoxRequest,
    HomographyMeasureDistanceRequest,
)
from mindtrace.hardware.services.cameras.service import CameraManagerService


def _make_homography_calibration(world_unit: str = "mm"):
    calibration = Mock()
    calibration.H = np.eye(3, dtype=np.float64)
    calibration.world_unit = world_unit
    calibration.save = Mock()
    return calibration


def _patch_hardware_exports(monkeypatch, **attrs):
    import mindtrace.hardware as hardware_pkg

    for name, value in attrs.items():
        monkeypatch.setattr(hardware_pkg, name, value, raising=False)


class TestCameraManagerServiceInitialization:
    """Test service initialization and lifecycle management."""

    @pytest.mark.asyncio
    async def test_service_initialization_attributes(self):
        """Test service is initialized with correct attributes."""
        service = CameraManagerService(include_mocks=True)

        # Check attributes exist
        assert hasattr(service, "include_mocks")
        assert hasattr(service, "_camera_manager")
        assert hasattr(service, "_startup_time")
        assert hasattr(service, "logger")

        # Check values
        assert service.include_mocks is True
        assert service._camera_manager is None  # Lazy initialization
        assert isinstance(service._startup_time, (int, float))

        await service.shutdown_cleanup()

    @pytest.mark.asyncio
    async def test_service_include_mocks_flag(self, monkeypatch):
        """Test service initialization with include_mocks=False flag (but still mock hardware for unit test)."""
        # Even though we set include_mocks=False, we still mock hardware for unit testing
        # This tests the flag setting, not actual hardware interaction
        try:
            from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend

            monkeypatch.setattr(
                BaslerCameraBackend,
                "get_available_cameras",
                staticmethod(lambda include_details=False: {} if include_details else []),
                raising=False,
            )
        except Exception:
            pass

        try:
            from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import OpenCVCameraBackend

            monkeypatch.setattr(
                OpenCVCameraBackend,
                "get_available_cameras",
                staticmethod(lambda include_details=False: {} if include_details else []),
                raising=False,
            )
        except Exception:
            pass

        service = CameraManagerService(include_mocks=False)
        assert service.include_mocks is False
        await service.shutdown_cleanup()

    @pytest.mark.asyncio
    async def test_camera_manager_lazy_initialization(self):
        """Test lazy initialization creates manager only when needed."""
        service = CameraManagerService(include_mocks=True)

        # Manager should not exist initially
        assert service._camera_manager is None

        # First call creates manager
        manager1 = await service._get_camera_manager()
        assert manager1 is not None
        assert service._camera_manager is manager1

        # Second call returns same instance
        manager2 = await service._get_camera_manager()
        assert manager2 is manager1

        await service.shutdown_cleanup()

    @pytest.mark.asyncio
    async def test_shutdown_cleanup_with_manager(self):
        """Test shutdown properly cleans up camera manager."""
        service = CameraManagerService(include_mocks=True)

        # Create a mock manager
        mock_manager = AsyncMock()
        service._camera_manager = mock_manager

        # Test shutdown
        await service.shutdown_cleanup()

        # Verify cleanup was called and manager was cleared
        mock_manager.__aexit__.assert_called_once_with(None, None, None)
        assert service._camera_manager is None

    @pytest.mark.asyncio
    async def test_shutdown_cleanup_handles_errors(self):
        """Test shutdown gracefully handles cleanup errors."""
        service = CameraManagerService(include_mocks=True)

        # Mock manager that raises on cleanup
        mock_manager = AsyncMock()
        mock_manager.__aexit__.side_effect = Exception("Cleanup failed")
        service._camera_manager = mock_manager

        # Should not raise - must handle gracefully
        await service.shutdown_cleanup()

        # Manager should still be cleared even if cleanup failed
        assert service._camera_manager is None

    @pytest.mark.asyncio
    async def test_shutdown_cleanup_without_manager(self):
        """Test shutdown when no manager exists."""
        service = CameraManagerService(include_mocks=True)

        # No manager created - should handle gracefully
        assert service._camera_manager is None
        await service.shutdown_cleanup()
        assert service._camera_manager is None

    def test_service_inheritance_and_attributes(self):
        """Test service properly inherits and has required attributes."""
        service = CameraManagerService(include_mocks=False)

        # Service base class attributes
        assert hasattr(service, "logger")
        assert hasattr(service, "shutdown_cleanup")

        # Camera service specific attributes
        assert service.__class__.__name__ == "CameraManagerService"
        assert hasattr(service, "_camera_manager")
        assert hasattr(service, "include_mocks")
        assert service.include_mocks is False


class TestCameraManagerServiceBusinessLogic:
    """Test real business logic: error handling, request validation, response formatting."""

    @pytest.fixture
    def service_with_mock_manager(self):
        """Create service with controlled mock manager for testing business logic."""
        service = CameraManagerService(include_mocks=True)

        # Create mock manager that we can control for specific test scenarios
        mock_manager = Mock()

        # Set up basic successful responses by default
        mock_manager.backends.return_value = ["MockBasler", "OpenCV"]
        mock_manager.backend_info.return_value = {
            "MockBasler": {"available": True, "type": "mock", "sdk_required": False},
            "OpenCV": {"available": True, "type": "usb", "sdk_required": False},
        }
        mock_manager.discover_async = AsyncMock(return_value=["MockBasler:Camera1", "OpenCV:Camera2"])
        mock_manager.active_cameras = ["MockBasler:Camera1"]
        mock_manager.max_concurrent_captures = 4

        # Mock async methods - these need to be properly configured AsyncMocks
        mock_manager.open = AsyncMock()
        mock_manager.close = AsyncMock()

        service._camera_manager = mock_manager
        return service, mock_manager

    @pytest.mark.asyncio
    async def test_discover_backends_success(self, service_with_mock_manager):
        """Test backend discovery returns proper response format."""
        service, mock_manager = service_with_mock_manager
        mock_manager.backends.return_value = ["MockBasler", "OpenCV"]

        response = await service.discover_backends()

        # Test response structure and business logic
        assert response.success is True
        assert isinstance(response.data, list)
        assert "Found 2 available backends" in response.message
        assert response.data == ["MockBasler", "OpenCV"]

        # Verify manager was called correctly
        mock_manager.backends.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_backends_handles_errors(self, service_with_mock_manager):
        """Test backend discovery error handling and exception propagation."""
        service, mock_manager = service_with_mock_manager
        mock_manager.backends.side_effect = Exception("Backend discovery failed")

        # Should propagate exception for proper error handling
        with pytest.raises(Exception, match="Backend discovery failed"):
            await service.discover_backends()

    @pytest.mark.asyncio
    async def test_get_backend_info_data_conversion(self, service_with_mock_manager):
        """Test backend info converts internal data to proper response models."""
        service, mock_manager = service_with_mock_manager

        # Set up internal data format
        mock_manager.backend_info.return_value = {
            "MockBasler": {"available": True, "type": "mock", "sdk_required": False},
            "OpenCV": {"available": False, "type": "usb", "sdk_required": True},
        }

        response = await service.get_backend_info()

        # Test response format and data conversion
        assert response.success is True
        assert "Retrieved information for 2 backends" in response.message
        assert isinstance(response.data, dict)

        # Test data model conversion
        basler_info = response.data["MockBasler"]
        assert basler_info.name == "MockBasler"
        assert basler_info.available is True
        assert basler_info.type == "mock"
        assert basler_info.sdk_required is False

        opencv_info = response.data["OpenCV"]
        assert opencv_info.available is False
        assert opencv_info.sdk_required is True

    @pytest.mark.asyncio
    async def test_discover_cameras_request_processing(self, service_with_mock_manager):
        """Test camera discovery processes requests correctly."""
        service, mock_manager = service_with_mock_manager
        mock_manager.discover_async = AsyncMock(return_value=["MockBasler:Cam1", "OpenCV:Cam2"])

        # Test without backend filter
        request = BackendFilterRequest()
        response = await service.discover_cameras(request)

        assert response.success is True
        assert "Found 2 cameras from all backends" in response.message
        assert response.data == ["MockBasler:Cam1", "OpenCV:Cam2"]

        # Verify manager called with correct parameters
        mock_manager.discover_async.assert_called_with(
            backends=None,  # No backend filter
            include_mocks=True,  # Service was created with include_mocks=True
        )

    @pytest.mark.asyncio
    async def test_discover_cameras_with_backend_filter(self, service_with_mock_manager):
        """Test camera discovery with backend filter processes request correctly."""
        service, mock_manager = service_with_mock_manager
        mock_manager.discover_async = AsyncMock(return_value=["MockBasler:Camera1"])

        # Test with backend filter
        request = BackendFilterRequest(backend="MockBasler")
        response = await service.discover_cameras(request)

        assert response.success is True
        assert "Found 1 cameras from backend 'MockBasler'" in response.message
        assert response.data == ["MockBasler:Camera1"]

        # Verify backend filter was passed correctly
        mock_manager.discover_async.assert_called_with(backends="MockBasler", include_mocks=True)

    @pytest.mark.asyncio
    async def test_open_camera_request_validation(self, service_with_mock_manager):
        """Test camera open validates request and formats response."""
        service, mock_manager = service_with_mock_manager

        request = CameraOpenRequest(camera="TestCamera", test_connection=True)

        response = await service.open_camera(request)

        # Test business logic: response formatting
        assert response.success is True
        assert "Camera 'TestCamera' opened successfully" in response.message
        assert response.data is True

        # Test business logic: parameters passed correctly
        mock_manager.open.assert_called_once_with("TestCamera", test_connection=True)

    @pytest.mark.asyncio
    async def test_open_camera_error_handling(self, service_with_mock_manager):
        """Test camera open handles and propagates errors correctly."""
        service, mock_manager = service_with_mock_manager
        mock_manager.open.side_effect = CameraInitializationError("Camera init failed")

        request = CameraOpenRequest(camera="BadCamera")

        # Should propagate specific camera errors
        with pytest.raises(CameraInitializationError, match="Camera init failed"):
            await service.open_camera(request)

    @pytest.mark.asyncio
    async def test_batch_open_result_processing(self, service_with_mock_manager):
        """Test batch open processes results and creates proper response."""
        service, mock_manager = service_with_mock_manager

        from mindtrace.hardware.services.cameras.models.requests import CameraOpenBatchRequest

        request = CameraOpenBatchRequest(cameras=["Camera1", "Camera2", "Camera3"])

        # Mock partial success - only 2 of 3 cameras opened
        mock_manager.open.return_value = {"Camera1": Mock(), "Camera2": Mock()}

        response = await service.open_cameras_batch(request)

        # Test business logic: result processing
        assert response.success is False  # Not all cameras opened
        assert "2 successful, 1 failed" in response.message
        assert response.data.successful_count == 2
        assert response.data.failed_count == 1
        assert "Camera1" in response.data.successful
        assert "Camera2" in response.data.successful
        assert "Camera3" in response.data.failed
        assert response.data.results["Camera1"] is True
        assert response.data.results["Camera3"] is False

    @pytest.mark.asyncio
    async def test_close_camera_business_logic(self, service_with_mock_manager):
        """Test camera close request processing and response formatting."""
        service, mock_manager = service_with_mock_manager

        request = CameraCloseRequest(camera="TestCamera")

        response = await service.close_camera(request)

        # Test business logic: response formatting
        assert response.success is True
        assert "Camera 'TestCamera' closed successfully" in response.message
        assert response.data is True

        # Test business logic: manager called correctly
        mock_manager.close.assert_called_once_with("TestCamera")

    @pytest.mark.skip(reason="Active camera validation not yet implemented in service")
    @pytest.mark.asyncio
    async def test_capture_image_active_camera_validation(self, service_with_mock_manager):
        """Test capture validates camera is active before proceeding."""
        service, mock_manager = service_with_mock_manager

        # Set up active cameras list
        mock_manager.active_cameras = ["ActiveCamera"]

        # Test with inactive camera
        request = CaptureImageRequest(camera="InactiveCamera")

        with pytest.raises(CameraNotFoundError, match="InactiveCamera.*not initialized"):
            await service.capture_image(request)

        # Manager.open should not be called for inactive camera
        mock_manager.open.assert_not_called()

    @pytest.mark.asyncio
    async def test_capture_image_with_active_camera(self, service_with_mock_manager):
        """Test capture image business logic with active camera."""
        service, mock_manager = service_with_mock_manager

        # Set up active camera
        mock_camera = AsyncMock()
        mock_manager.active_cameras = ["ActiveCamera"]
        mock_manager.open = AsyncMock(return_value=mock_camera)

        request = CaptureImageRequest(camera="ActiveCamera", save_path="/tmp/test.jpg")

        response = await service.capture_image(request)

        # Test business logic: response formatting
        assert response.success is True
        assert "Image captured from camera 'ActiveCamera'" in response.message
        assert response.data.success is True
        assert response.data.image_path == "/tmp/test.jpg"
        assert isinstance(response.data.capture_time, datetime)

        # Test business logic: parameters passed correctly
        mock_camera.capture.assert_called_once_with(
            save_path="/tmp/test.jpg",
            output_format="pil",  # Default value
        )

    @pytest.mark.asyncio
    async def test_configure_camera_validation_and_processing(self, service_with_mock_manager):
        """Test configure camera validates active camera and processes request."""
        service, mock_manager = service_with_mock_manager

        # Set up active camera
        mock_camera = AsyncMock()
        mock_camera.configure.return_value = True
        mock_manager.active_cameras = ["ActiveCamera"]
        mock_manager.open = AsyncMock(return_value=mock_camera)

        request = CameraConfigureRequest(camera="ActiveCamera", properties={"exposure": 1000, "gain": 2.5})

        response = await service.configure_camera(request)

        # Test business logic: validation and response
        assert response.success is True
        assert "Camera 'ActiveCamera' configured successfully" in response.message
        assert response.data is True

        # Test business logic: properties passed correctly
        mock_camera.configure.assert_called_once_with(exposure=1000, gain=2.5)

    @pytest.mark.asyncio
    async def test_configure_camera_inactive_camera_error(self, service_with_mock_manager):
        """Test configure camera rejects inactive cameras with graceful error response."""
        service, mock_manager = service_with_mock_manager
        mock_manager.active_cameras = ["ActiveCamera"]

        request = CameraConfigureRequest(camera="InactiveCamera", properties={"exposure": 1000})

        # Graceful error handling: returns BoolResponse instead of raising
        response = await service.configure_camera(request)

        assert response.success is False
        assert "InactiveCamera" in response.message
        assert "not initialized" in response.message
        assert response.data is False

    @pytest.mark.asyncio
    async def test_get_active_cameras_response_format(self, service_with_mock_manager):
        """Test get active cameras returns proper response format."""
        service, mock_manager = service_with_mock_manager
        mock_manager.active_cameras = ["Camera1", "Camera2", "Camera3"]

        response = await service.get_active_cameras()

        # Test business logic: response formatting
        assert response.success is True
        assert "Found 3 active cameras" in response.message
        assert isinstance(response.data, list)
        assert response.data == ["Camera1", "Camera2", "Camera3"]

    @pytest.mark.asyncio
    async def test_get_camera_status_returns_connected_state(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_manager.active_cameras = ["MockBasler:Camera1"]
        mock_camera = AsyncMock()
        mock_camera.check_connection.return_value = True
        mock_manager.open = AsyncMock(return_value=mock_camera)

        response = await service.get_camera_status(CameraQueryRequest(camera="MockBasler:Camera1"))

        assert response.success is True
        assert response.data.camera == "MockBasler:Camera1"
        assert response.data.connected is True
        assert response.data.backend == "MockBasler"
        assert response.data.device_name == "Camera1"

    @pytest.mark.asyncio
    async def test_get_camera_info_sanitizes_sensor_info_backend(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_manager.active_cameras = ["MockBasler:Camera1"]
        mock_camera = AsyncMock()
        mock_camera.is_connected = True
        mock_camera.get_sensor_info.return_value = {
            "name": "MockBasler:Camera1",
            "backend": object(),
            "device_name": "Camera1",
            "connected": True,
        }
        mock_manager.open = AsyncMock(return_value=mock_camera)

        response = await service.get_camera_info(CameraQueryRequest(camera="MockBasler:Camera1"))

        assert response.success is True
        assert response.data.backend == "MockBasler"
        assert response.data.sensor_info["backend"] == "MockBasler"
        assert response.data.sensor_info["device_name"] == "Camera1"

    @pytest.mark.asyncio
    async def test_get_camera_capabilities_gracefully_degrades(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_manager.active_cameras = ["MockBasler:Camera1"]
        mock_camera = AsyncMock()
        mock_camera.get_exposure_range.return_value = [100.0, 5000.0]
        mock_camera.is_exposure_control_supported.return_value = False
        mock_camera.get_gain_range.side_effect = RuntimeError("no gain")
        mock_camera.get_available_pixel_formats.return_value = ["Mono8", "BGR8"]
        mock_camera.get_available_white_balance_modes.side_effect = RuntimeError("no wb")
        mock_camera.get_trigger_modes.return_value = ["continuous", "trigger"]
        mock_camera.get_width_range.return_value = [320, 1920]
        mock_camera.get_height_range.side_effect = RuntimeError("no height")
        mock_camera.get_bandwidth_limit_range.return_value = [1.0, 1000.0]
        mock_camera.get_packet_size_range.side_effect = RuntimeError("no packet")
        mock_camera.get_inter_packet_delay_range.return_value = [0, 65535]
        mock_manager.open = AsyncMock(return_value=mock_camera)

        response = await service.get_camera_capabilities(CameraQueryRequest(camera="MockBasler:Camera1"))

        assert response.success is True
        assert response.data.exposure_range is None
        assert response.data.gain_range is None
        assert response.data.pixel_formats == ["Mono8", "BGR8"]
        assert response.data.white_balance_modes is None
        assert response.data.trigger_modes == ["continuous", "trigger"]
        assert response.data.width_range == (320, 1920)
        assert response.data.height_range is None
        assert response.data.bandwidth_limit_range == (1.0, 1000.0)
        assert response.data.packet_size_range is None
        assert response.data.inter_packet_delay_range == (0, 65535)

    @pytest.mark.asyncio
    async def test_get_camera_configuration_gracefully_handles_missing_fields(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_manager.active_cameras = ["MockBasler:Camera1"]
        mock_camera = AsyncMock()
        mock_camera.get_roi.return_value = {"x": 1, "y": 2, "width": 640, "height": 480}
        mock_camera.get_exposure.return_value = 1500
        mock_camera.get_gain.side_effect = RuntimeError("no gain")
        mock_camera.get_trigger_mode.return_value = "continuous"
        mock_camera.get_pixel_format.side_effect = RuntimeError("no pixel format")
        mock_camera.get_white_balance.return_value = "auto"
        mock_camera.get_image_enhancement.side_effect = RuntimeError("no enhancement")
        mock_camera.get_bandwidth_limit.return_value = 800.0
        mock_camera.get_packet_size.side_effect = RuntimeError("no packet")
        mock_camera.get_inter_packet_delay.return_value = 100
        mock_manager.open = AsyncMock(return_value=mock_camera)

        response = await service.get_camera_configuration(CameraQueryRequest(camera="MockBasler:Camera1"))

        assert response.success is True
        assert response.data.roi == (1, 2, 640, 480)
        assert response.data.exposure_time == 1500
        assert response.data.gain is None
        assert response.data.trigger_mode == "continuous"
        assert response.data.pixel_format is None
        assert response.data.white_balance == "auto"
        assert response.data.image_enhancement is None
        assert response.data.bandwidth_limit == 800.0
        assert response.data.packet_size is None
        assert response.data.inter_packet_delay == 100

    @pytest.mark.asyncio
    async def test_import_and_export_camera_config_delegate_to_proxy(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_manager.active_cameras = ["MockBasler:Camera1"]
        mock_camera = AsyncMock()
        mock_camera.load_config.return_value = True
        mock_camera.save_config.return_value = False
        mock_manager.open = AsyncMock(return_value=mock_camera)

        import_response = await service.import_camera_config(
            ConfigFileImportRequest(camera="MockBasler:Camera1", config_path="/tmp/camera.json")
        )
        export_response = await service.export_camera_config(
            ConfigFileExportRequest(camera="MockBasler:Camera1", config_path="/tmp/camera.json")
        )

        assert import_response.success is True
        assert import_response.data.operation == "import"
        assert import_response.data.file_path == "/tmp/camera.json"
        assert export_response.success is False
        assert export_response.data.operation == "export"
        assert export_response.data.success is False

    @pytest.mark.asyncio
    async def test_configure_camera_failure_handling(self, service_with_mock_manager):
        """Test configure camera handles configuration failures correctly."""
        service, mock_manager = service_with_mock_manager

        # Set up camera that fails configuration
        mock_camera = AsyncMock()
        mock_camera.configure.return_value = False  # Configuration failed
        mock_manager.active_cameras = ["TestCamera"]
        mock_manager.open = AsyncMock(return_value=mock_camera)

        request = CameraConfigureRequest(camera="TestCamera", properties={"exposure": 1000})

        response = await service.configure_camera(request)

        # Test business logic: failure response
        assert response.success is False
        assert "Configuration failed for 'TestCamera'" in response.message
        assert response.data is False


class TestCameraManagerServiceErrorHandling:
    """Test error handling and exception mapping in service layer."""

    @pytest.fixture
    def service_with_mock_manager(self):
        """Service with mock manager for error testing."""
        service = CameraManagerService(include_mocks=True)
        mock_manager = Mock()
        mock_manager.active_cameras = []
        service._camera_manager = mock_manager
        return service, mock_manager

    @pytest.mark.asyncio
    async def test_camera_not_found_error_propagation(self, service_with_mock_manager):
        """Test CameraNotFoundError is properly propagated to API layer."""
        service, mock_manager = service_with_mock_manager
        mock_manager.active_cameras = []  # No active cameras

        request = CameraQueryRequest(camera="NonExistentCamera")

        # Should raise CameraNotFoundError for inactive camera
        with pytest.raises(CameraNotFoundError, match="NonExistentCamera.*not initialized"):
            await service.get_camera_info(request)

    @pytest.mark.asyncio
    async def test_camera_connection_error_propagation(self, service_with_mock_manager):
        """Test connection errors are properly propagated."""
        service, mock_manager = service_with_mock_manager
        mock_manager.open.side_effect = CameraConnectionError("Connection failed")

        request = CameraOpenRequest(camera="TestCamera")

        with pytest.raises(CameraConnectionError, match="Connection failed"):
            await service.open_camera(request)

    @pytest.mark.asyncio
    async def test_configuration_error_propagation(self, service_with_mock_manager):
        """Test configuration errors return graceful error response."""
        service, mock_manager = service_with_mock_manager
        mock_manager.active_cameras = ["TestCamera"]

        mock_camera = AsyncMock()
        mock_camera.configure.side_effect = CameraConfigurationError("Invalid config")
        # Make sure open is an async mock that returns the camera
        mock_manager.open = AsyncMock(return_value=mock_camera)

        request = CameraConfigureRequest(camera="TestCamera", properties={"invalid_param": "bad_value"})

        # Graceful error handling: returns BoolResponse instead of raising
        response = await service.configure_camera(request)

        assert response.success is False
        assert "Invalid config" in response.message
        assert response.data is False


class TestCameraManagerServiceResponseModels:
    """Test response model creation and data formatting."""

    @pytest.fixture
    def service_with_mock_manager(self):
        service = CameraManagerService(include_mocks=True)
        mock_manager = Mock()
        service._camera_manager = mock_manager
        return service, mock_manager

    @pytest.mark.skip(reason="get_bandwidth_settings API method not yet implemented")
    @pytest.mark.asyncio
    async def test_bandwidth_settings_response_model(self, service_with_mock_manager):
        """Test bandwidth settings creates proper response model."""
        service, mock_manager = service_with_mock_manager
        mock_manager.max_concurrent_captures = 4
        mock_manager.active_cameras = ["cam1", "cam2"]  # 2 active cameras

        response = await service.get_bandwidth_settings()

        # Test response model creation and calculation logic
        assert response.success is True
        assert response.data.max_concurrent_captures == 4
        assert response.data.current_active_captures == 2
        assert response.data.available_slots == 2  # 4 - 2
        assert response.data.recommended_limit == 2

    @pytest.mark.skip(reason="set_bandwidth_limit API method not yet implemented")
    @pytest.mark.asyncio
    async def test_set_bandwidth_limit_processing(self, service_with_mock_manager):
        """Test bandwidth limit setting processes request correctly."""
        service, mock_manager = service_with_mock_manager

        from mindtrace.hardware.services.cameras.models.requests import BandwidthLimitRequest

        request = BandwidthLimitRequest(max_concurrent_captures=8)

        response = await service.set_bandwidth_limit(request)

        # Test business logic: setting is applied
        assert mock_manager.max_concurrent_captures == 8
        assert response.success is True
        assert "Bandwidth limit set to 8" in response.message
        assert response.data is True

    @pytest.mark.asyncio
    async def test_system_diagnostics_data_aggregation(self, service_with_mock_manager):
        """Test system diagnostics aggregates data from multiple sources."""
        service, mock_manager = service_with_mock_manager

        # Mock diagnostics data
        mock_manager.diagnostics.return_value = {
            "active_cameras": 3,
            "max_concurrent_captures": 5,
            "gige_cameras": 2,
            "bandwidth_management_enabled": True,
            "recommended_settings": {"jumbo_frames": True},
        }
        mock_manager.backends.return_value = ["MockBasler", "OpenCV"]

        # Set startup time for uptime calculation
        service._startup_time = service._startup_time  # Use existing startup time

        response = await service.get_system_diagnostics()

        # Test business logic: data aggregation and calculation
        assert response.success is True
        assert response.data.active_cameras == 3
        assert response.data.max_concurrent_captures == 5
        assert response.data.gige_cameras == 2
        assert response.data.bandwidth_management_enabled is True
        assert "jumbo_frames" in response.data.recommended_settings
        assert isinstance(response.data.uptime_seconds, (int, float))
        assert response.data.uptime_seconds >= 0

        # Test backend status mapping
        assert "MockBasler" in response.data.backend_status
        assert "OpenCV" in response.data.backend_status
        assert response.data.backend_status["MockBasler"] is True

    @pytest.mark.asyncio
    async def test_get_network_diagnostics_counts_only_supported_gige_cameras(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_manager.active_cameras = ["Basler:gige", "OpenCV:usb", "Broken:cam"]

        gige_camera = AsyncMock()
        gige_camera.supports_feature.return_value = True
        usb_camera = AsyncMock()
        usb_camera.supports_feature.return_value = False

        async def get_camera(camera_name):
            if camera_name == "Basler:gige":
                return gige_camera
            if camera_name == "OpenCV:usb":
                return usb_camera
            raise RuntimeError("camera lookup failed")

        mock_manager.get_camera = AsyncMock(side_effect=get_camera)

        response = await service.get_network_diagnostics()

        assert response.success is True
        assert response.data.gige_cameras_count == 1
        assert response.data.total_bandwidth_usage == 0.0
        assert response.data.jumbo_frames_enabled is True
        assert response.data.multicast_enabled is True


class TestCameraManagerServiceCaptureAndHomography:
    """Additional capture, health, and homography service coverage."""

    @pytest.fixture
    def service_with_mock_manager(self):
        service = CameraManagerService(include_mocks=True)
        mock_manager = Mock()
        mock_manager.active_cameras = ["Basler:cam1", "Basler:cam2"]
        mock_manager.open = AsyncMock()
        mock_manager.close = AsyncMock()
        mock_manager.batch_capture = AsyncMock()
        mock_manager.batch_capture_hdr = AsyncMock()
        mock_manager.batch_configure = AsyncMock()
        mock_manager.backends.return_value = ["Basler", "OpenCV"]
        mock_manager.diagnostics.return_value = {
            "active_cameras": 2,
            "max_concurrent_captures": 4,
            "gige_cameras": 1,
            "bandwidth_management_enabled": True,
            "recommended_settings": {"jumbo_frames": True},
        }
        service._camera_manager = mock_manager
        return service, mock_manager

    def test_register_endpoints_registers_all_routes(self):
        endpoints = CameraManagerService.__endpoints__
        assert "health" in endpoints
        assert "cameras/capture" in endpoints
        assert "cameras/stream/start" in endpoints
        assert "stream/{camera_name}" in endpoints
        assert "cameras/homography/measure/distance" in endpoints
        assert "cameras/capture-groups/configure" in endpoints
        assert "cameras/capture-groups" in endpoints
        assert "cameras/capture-groups/remove" in endpoints

    @pytest.mark.asyncio
    async def test_configure_cameras_batch_formats_partial_results(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_manager.batch_configure.return_value = {"Basler:cam1": True, "Basler:cam2": False}

        response = await service.configure_cameras_batch(
            CameraConfigureBatchRequest(configurations={"Basler:cam1": {"gain": 1.0}, "Basler:cam2": {"gain": 2.0}})
        )

        assert response.success is False
        assert response.data.successful == ["Basler:cam1"]
        assert response.data.failed == ["Basler:cam2"]
        assert response.data.results == {"Basler:cam1": True, "Basler:cam2": False}

    @pytest.mark.asyncio
    async def test_import_export_config_inactive_camera_raise(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_manager.active_cameras = []

        with pytest.raises(CameraNotFoundError):
            await service.import_camera_config(
                ConfigFileImportRequest(camera="Basler:missing", config_path="/tmp/in.json")
            )
        with pytest.raises(CameraNotFoundError):
            await service.export_camera_config(
                ConfigFileExportRequest(camera="Basler:missing", config_path="/tmp/out.json")
            )

    @pytest.mark.asyncio
    async def test_capture_image_timeout_returns_failed_response(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_manager.open.return_value = AsyncMock()

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            response = await service.capture_image(CaptureImageRequest(camera="Basler:cam1"))

        assert response.success is False
        assert "Capture timeout after 15.0s" in response.message
        assert response.data.success is False
        assert "lower exposure time" in response.data.error

    @pytest.mark.asyncio
    async def test_capture_image_inactive_camera_returns_failed_response(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_manager.active_cameras = []

        response = await service.capture_image(CaptureImageRequest(camera="Basler:missing"))

        assert response.success is False
        assert "not initialized" in response.message
        assert response.data.success is False

    @pytest.mark.asyncio
    async def test_capture_image_generic_error_returns_failed_response(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_camera = AsyncMock()
        mock_camera.capture.side_effect = RuntimeError("capture exploded")
        mock_manager.open.return_value = mock_camera

        response = await service.capture_image(CaptureImageRequest(camera="Basler:cam1"))

        assert response.success is False
        assert response.message == "Capture failed: capture exploded"
        assert response.data.error == "capture exploded"

    @pytest.mark.asyncio
    async def test_capture_images_batch_formats_saved_paths(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_manager.batch_capture.return_value = {"Basler:cam1": "/tmp/cam1.jpg", "Basler:cam2": None}

        response = await service.capture_images_batch(
            CaptureBatchRequest(cameras=["Basler:cam1", "Basler:cam2"], save_path_pattern="/tmp/{camera}.jpg")
        )

        assert response.success is True
        assert response.successful_count == 1
        assert response.failed_count == 1
        assert response.data["Basler:cam1"].image_path == "/tmp/cam1.jpg"
        assert response.data["Basler:cam2"].success is False

    @pytest.mark.asyncio
    async def test_capture_images_batch_without_path_omits_image_path(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_manager.batch_capture.return_value = {"Basler:cam1": object()}

        response = await service.capture_images_batch(CaptureBatchRequest(cameras=["Basler:cam1"]))

        assert response.success is True
        assert response.data["Basler:cam1"].success is True
        assert response.data["Basler:cam1"].image_path is None

    @pytest.mark.asyncio
    async def test_capture_hdr_image_sanitizes_images(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_camera = AsyncMock()
        mock_camera.capture_hdr.return_value = {
            "success": True,
            "images": ["img-a", object()],
            "image_paths": ["/tmp/a.jpg"],
            "exposure_levels": [1.0, 2.0],
            "successful_captures": 1,
        }
        mock_manager.open.return_value = mock_camera

        response = await service.capture_hdr_image(CaptureHDRRequest(camera="Basler:cam1"))

        assert response.success is True
        assert response.data.images == ["img-a"]
        assert response.data.image_paths == ["/tmp/a.jpg"]
        assert response.data.successful_captures == 1

    @pytest.mark.asyncio
    async def test_capture_hdr_image_inactive_camera_returns_failed_response(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_manager.active_cameras = []

        response = await service.capture_hdr_image(CaptureHDRRequest(camera="Basler:missing"))

        assert response.success is False
        assert "not initialized" in response.message
        assert response.data.successful_captures == 0

    @pytest.mark.asyncio
    async def test_capture_hdr_image_generic_failure_returns_failed_response(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_camera = AsyncMock()
        mock_camera.capture_hdr.side_effect = RuntimeError("hdr failed")
        mock_manager.open.return_value = mock_camera

        response = await service.capture_hdr_image(CaptureHDRRequest(camera="Basler:cam1"))

        assert response.success is False
        assert response.message == "HDR capture failed: hdr failed"
        assert response.data.successful_captures == 0

    @pytest.mark.asyncio
    async def test_capture_hdr_images_batch_sanitizes_results(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_manager.batch_capture_hdr.return_value = {
            "Basler:cam1": {
                "success": True,
                "images": ["img-a", 123],
                "image_paths": ["/tmp/a.jpg"],
                "exposure_levels": [1.0, 2.0],
                "successful_captures": 2,
            },
            "Basler:cam2": None,
        }

        response = await service.capture_hdr_images_batch(
            CaptureHDRBatchRequest(cameras=["Basler:cam1", "Basler:cam2"])
        )

        assert response.success is True
        assert response.successful_count == 1
        assert response.failed_count == 1
        assert response.data["Basler:cam1"].images == ["img-a"]
        assert response.data["Basler:cam2"].success is False

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy_payload(self, service_with_mock_manager):
        service, _ = service_with_mock_manager

        response = await service.health_check()

        assert response.status == ServiceStatus.HEALTHY
        assert response.service == "camera-manager"
        assert response.backends == ["Basler", "OpenCV"]
        assert response.active_cameras == 2
        assert response.uptime_seconds >= 0

    @pytest.mark.asyncio
    async def test_health_check_returns_unhealthy_on_error(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_manager.backends.side_effect = RuntimeError("backend probe failed")

        response = await service.health_check()

        assert response.status == ServiceStatus.UNHEALTHY
        assert response.error == "backend probe failed"

    @pytest.mark.asyncio
    async def test_get_system_diagnostics_propagates_errors(self, service_with_mock_manager):
        service, mock_manager = service_with_mock_manager
        mock_manager.diagnostics.side_effect = RuntimeError("diag failed")

        with pytest.raises(RuntimeError, match="diag failed"):
            await service.get_system_diagnostics()

    @pytest.mark.asyncio
    async def test_calibrate_homography_checkerboard_success(self, service_with_mock_manager, monkeypatch):
        service, mock_manager = service_with_mock_manager
        mock_camera = AsyncMock()
        calibration_image = np.zeros((4, 4, 3), dtype=np.uint8)
        mock_camera.capture.return_value = calibration_image
        mock_manager.open.return_value = mock_camera

        calibrator = Mock()
        calibration = _make_homography_calibration("mm")
        calibrator.calibrate_checkerboard.return_value = calibration
        _patch_hardware_exports(monkeypatch, HomographyCalibrator=Mock(return_value=calibrator))

        response = await service.calibrate_homography_checkerboard(
            HomographyCalibrateCheckerboardRequest(
                camera="Basler:cam1",
                board_size_cols=7,
                board_size_rows=5,
                square_size=2.5,
                world_unit="mm",
                refine_corners=True,
                save_path="/tmp/checkerboard.json",
            )
        )

        assert response.success is True
        assert response.data.calibration_path == "/tmp/checkerboard.json"
        assert response.data.homography_matrix_summary["shape"] == [3, 3]
        calibrator.calibrate_checkerboard.assert_called_once_with(
            image=calibration_image,
            board_size=(7, 5),
            square_size=2.5,
            world_unit="mm",
            refine_corners=True,
        )
        calibration.save.assert_called_once_with("/tmp/checkerboard.json")

    @pytest.mark.asyncio
    async def test_calibrate_homography_checkerboard_failure_response(self, service_with_mock_manager, monkeypatch):
        service, mock_manager = service_with_mock_manager
        mock_manager.active_cameras = []
        _patch_hardware_exports(monkeypatch, HomographyCalibrator=Mock())

        response = await service.calibrate_homography_checkerboard(
            HomographyCalibrateCheckerboardRequest(camera="Basler:missing")
        )

        assert response.success is False
        assert response.data.success is False
        assert "not initialized" in response.message

    def test_calibrate_homography_correspondences_success(self, service_with_mock_manager, monkeypatch):
        service, _ = service_with_mock_manager
        calibrator = Mock()
        calibration = _make_homography_calibration("cm")
        calibrator.calibrate_from_correspondences.return_value = calibration
        _patch_hardware_exports(monkeypatch, HomographyCalibrator=Mock(return_value=calibrator))

        response = service.calibrate_homography_correspondences(
            HomographyCalibrateCorrespondencesRequest(
                camera="Basler:cam1",
                world_points=[[0, 0], [1, 0], [1, 1], [0, 1]],
                image_points=[[10, 10], [20, 10], [20, 20], [10, 20]],
                world_unit="cm",
                save_path="/tmp/correspondences.json",
            )
        )

        assert response.success is True
        assert response.data.inlier_count == 4
        assert response.data.total_points == 4
        calibration.save.assert_called_once_with("/tmp/correspondences.json")

    def test_calibrate_homography_correspondences_failure_response(self, service_with_mock_manager, monkeypatch):
        service, _ = service_with_mock_manager
        calibrator = Mock()
        calibrator.calibrate_from_correspondences.side_effect = RuntimeError("bad correspondences")
        _patch_hardware_exports(monkeypatch, HomographyCalibrator=Mock(return_value=calibrator))

        response = service.calibrate_homography_correspondences(
            HomographyCalibrateCorrespondencesRequest(
                camera="Basler:cam1",
                world_points=[[0, 0], [1, 0], [1, 1], [0, 1]],
                image_points=[[10, 10], [20, 10], [20, 20], [10, 20]],
            )
        )

        assert response.success is False
        assert response.data.success is False
        assert "bad correspondences" in response.message

    def test_calibrate_homography_multi_view_success(self, service_with_mock_manager, monkeypatch):
        service, _ = service_with_mock_manager
        calibrator = Mock()
        calibration = _make_homography_calibration("mm")
        calibrator.calibrate_checkerboard_multi_view.return_value = calibration
        config = SimpleNamespace(homography=SimpleNamespace(checkerboard_cols=4, checkerboard_rows=3))

        _patch_hardware_exports(monkeypatch, HomographyCalibrator=Mock(return_value=calibrator))

        with patch("PIL.Image.open", side_effect=[object(), object()]):
            with patch("mindtrace.hardware.core.config.get_hardware_config") as mock_get_config:
                mock_get_config.return_value.get_config.return_value = config
                response = service.calibrate_homography_multi_view(
                    HomographyCalibrateMultiViewRequest(
                        image_paths=["/tmp/1.png", "/tmp/2.png"],
                        positions=[{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}],
                        output_path="/tmp/multi.json",
                    )
                )

        assert response.success is True
        assert response.data.total_points == 24
        assert response.data.inlier_count == 24
        calibration.save.assert_called_once_with("/tmp/multi.json")

    def test_calibrate_homography_multi_view_failure_response(self, service_with_mock_manager):
        service, _ = service_with_mock_manager

        with patch("PIL.Image.open", side_effect=OSError("cannot open")):
            response = service.calibrate_homography_multi_view(
                HomographyCalibrateMultiViewRequest(
                    image_paths=["/tmp/missing.png"],
                    positions=[{"x": 0.0, "y": 0.0}],
                    output_path="/tmp/multi.json",
                )
            )

        assert response.success is False
        assert response.data.success is False
        assert "Failed to load image 1" in response.message

    def test_measure_homography_box_success(self, service_with_mock_manager, monkeypatch):
        service, _ = service_with_mock_manager
        measured = SimpleNamespace(
            corners_world=np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 1.0], [0.0, 1.0]]),
            width_world=2.0,
            height_world=1.0,
            area_world=2.0,
            unit="cm",
        )
        measurer = Mock()
        measurer.measure_bounding_box.return_value = measured
        _patch_hardware_exports(
            monkeypatch,
            CalibrationData=SimpleNamespace(load=Mock(return_value=object())),
            HomographyMeasurer=Mock(return_value=measurer),
            BoundingBox=Mock(return_value=Mock()),
        )

        response = service.measure_homography_box(
            HomographyMeasureBoundingBoxRequest(calibration_path="/tmp/cal.json", x=1, y=2, width=3, height=4)
        )

        assert response.success is True
        assert response.data.width_world == 2.0
        assert response.data.area_world == 2.0

    def test_measure_homography_batch_handles_partial_distance_failures(self, service_with_mock_manager, monkeypatch):
        service, _ = service_with_mock_manager
        measured_box = SimpleNamespace(
            corners_world=np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 1.0], [0.0, 1.0]]),
            width_world=2.0,
            height_world=1.0,
            area_world=2.0,
            unit="mm",
        )
        measurer = Mock()
        measurer.measure_bounding_boxes.return_value = [measured_box]

        def measure_distance(point1, point2, target_unit=None):
            if point1 == (0.0, 0.0):
                return 5.0, "mm"
            raise RuntimeError("distance failed")

        measurer.measure_distance.side_effect = measure_distance
        measurer.pixels_to_world.return_value = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)

        _patch_hardware_exports(
            monkeypatch,
            CalibrationData=SimpleNamespace(load=Mock(return_value=object())),
            HomographyMeasurer=Mock(return_value=measurer),
            BoundingBox=Mock(side_effect=lambda **kwargs: SimpleNamespace(**kwargs)),
        )

        response = service.measure_homography_batch(
            HomographyMeasureBatchRequest(
                calibration_path="/tmp/cal.json",
                bounding_boxes=[{"x": 1, "y": 2, "width": 3, "height": 4}],
                point_pairs=[[[0.0, 0.0], [1.0, 1.0]], [[5.0, 5.0], [7.0, 9.0]]],
            )
        )

        assert response.success is True
        assert response.data.successful_boxes == 1
        assert response.data.successful_distances == 1
        assert len(response.data.distance_measurements) == 2
        assert response.data.distance_measurements[0].success is True
        assert response.data.distance_measurements[1].success is False

    def test_measure_homography_batch_failure_response(self, service_with_mock_manager, monkeypatch):
        service, _ = service_with_mock_manager
        _patch_hardware_exports(
            monkeypatch,
            CalibrationData=SimpleNamespace(load=Mock(side_effect=RuntimeError("load failed"))),
            HomographyMeasurer=Mock(),
            BoundingBox=Mock(),
        )

        response = service.measure_homography_batch(
            HomographyMeasureBatchRequest(
                calibration_path="/tmp/cal.json", bounding_boxes=[{"x": 1, "y": 2, "width": 3, "height": 4}]
            )
        )

        assert response.success is False
        assert "load failed" in response.message

    def test_measure_homography_distance_success(self, service_with_mock_manager, monkeypatch):
        service, _ = service_with_mock_manager
        measurer = Mock()
        measurer.measure_distance.return_value = (12.5, "mm")
        measurer.pixels_to_world.return_value = np.array([[1.0, 2.0], [5.0, 8.0]], dtype=np.float64)

        _patch_hardware_exports(
            monkeypatch,
            CalibrationData=SimpleNamespace(load=Mock(return_value=object())),
            HomographyMeasurer=Mock(return_value=measurer),
        )

        response = service.measure_homography_distance(
            HomographyMeasureDistanceRequest(
                calibration_path="/tmp/cal.json", point1_x=1.0, point1_y=2.0, point2_x=3.0, point2_y=4.0
            )
        )

        assert response.success is True
        assert response.data.distance == 12.5
        assert response.data.point1_world == [1.0, 2.0]
        assert response.data.point2_world == [5.0, 8.0]

    def test_measure_homography_distance_failure_response(self, service_with_mock_manager, monkeypatch):
        service, _ = service_with_mock_manager
        _patch_hardware_exports(
            monkeypatch,
            CalibrationData=SimpleNamespace(load=Mock(side_effect=RuntimeError("distance load failed"))),
            HomographyMeasurer=Mock(),
        )

        response = service.measure_homography_distance(
            HomographyMeasureDistanceRequest(
                calibration_path="/tmp/cal.json", point1_x=1.0, point1_y=2.0, point2_x=3.0, point2_y=4.0
            )
        )

        assert response.success is False
        assert response.data.success is False
        assert "distance load failed" in response.message
