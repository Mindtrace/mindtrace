"""Tests for CameraManagerService API layer.

These tests focus on real business logic:
- Request validation and error handling
- Response formatting and data conversion
- Service lifecycle and camera manager integration
- Error mapping from internal exceptions to API responses
"""

import asyncio
import numpy as np
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
import pytest

from mindtrace.hardware.core.exceptions import (
    CameraNotFoundError,
    CameraInitializationError,
    CameraConnectionError,
    CameraConfigurationError
)

# Mock heavy dependencies before importing service
with patch.dict('sys.modules', {
    'mindtrace.services.core.connection_manager': Mock(),
    'mindtrace.core.utils.conversions': Mock(),
    'cv2': Mock(),
}):
    from mindtrace.hardware.api.cameras.service import CameraManagerService
    from mindtrace.hardware.api.cameras.models.requests import (
        BackendFilterRequest,
        CameraOpenRequest,
        CameraCloseRequest,
        CameraQueryRequest,
        CameraConfigureRequest,
        CaptureImageRequest
    )


class TestCameraManagerServiceInitialization:
    """Test service initialization and lifecycle management."""

    @pytest.mark.asyncio
    async def test_service_initialization_attributes(self):
        """Test service is initialized with correct attributes."""
        service = CameraManagerService(include_mocks=True)
        
        # Check attributes exist
        assert hasattr(service, 'include_mocks')
        assert hasattr(service, '_camera_manager')
        assert hasattr(service, '_startup_time')
        assert hasattr(service, 'logger')
        
        # Check values
        assert service.include_mocks is True
        assert service._camera_manager is None  # Lazy initialization
        assert isinstance(service._startup_time, (int, float))
        
        await service.shutdown_cleanup()

    @pytest.mark.asyncio
    async def test_service_without_mocks(self):
        """Test service initialization without mocks."""
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
        assert hasattr(service, 'logger')
        assert hasattr(service, 'shutdown_cleanup')
        
        # Camera service specific attributes
        assert service.__class__.__name__ == "CameraManagerService"
        assert hasattr(service, '_camera_manager')
        assert hasattr(service, 'include_mocks')
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
            "OpenCV": {"available": True, "type": "usb", "sdk_required": False}
        }
        mock_manager.discover.return_value = ["MockBasler:Camera1", "OpenCV:Camera2"]
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
            "OpenCV": {"available": False, "type": "usb", "sdk_required": True}
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
        mock_manager.discover.return_value = ["MockBasler:Cam1", "OpenCV:Cam2"]
        
        # Test without backend filter
        request = BackendFilterRequest()
        response = await service.discover_cameras(request)
        
        assert response.success is True
        assert "Found 2 cameras from all backends" in response.message
        assert response.data == ["MockBasler:Cam1", "OpenCV:Cam2"]
        
        # Verify manager called with correct parameters
        mock_manager.discover.assert_called_with(
            backends=None,  # No backend filter
            include_mocks=True  # Service was created with include_mocks=True
        )

    @pytest.mark.asyncio
    async def test_discover_cameras_with_backend_filter(self, service_with_mock_manager):
        """Test camera discovery with backend filter processes request correctly."""
        service, mock_manager = service_with_mock_manager
        mock_manager.discover.return_value = ["MockBasler:Camera1"]
        
        # Test with backend filter
        request = BackendFilterRequest(backend="MockBasler")
        response = await service.discover_cameras(request)
        
        assert response.success is True
        assert "Found 1 cameras from backend 'MockBasler'" in response.message
        assert response.data == ["MockBasler:Camera1"]
        
        # Verify backend filter was passed correctly
        mock_manager.discover.assert_called_with(
            backends="MockBasler",
            include_mocks=True
        )

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
        
        from mindtrace.hardware.api.cameras.models.requests import CameraOpenBatchRequest
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
            upload_to_gcs=False,  # Default value
            output_format="numpy"  # Default value
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
        
        request = CameraConfigureRequest(
            camera="ActiveCamera",
            properties={"exposure": 1000, "gain": 2.5}
        )
        
        response = await service.configure_camera(request)
        
        # Test business logic: validation and response
        assert response.success is True
        assert "Camera 'ActiveCamera' configured successfully" in response.message
        assert response.data is True
        
        # Test business logic: properties passed correctly
        mock_camera.configure.assert_called_once_with(exposure=1000, gain=2.5)
    
    @pytest.mark.asyncio
    async def test_configure_camera_inactive_camera_error(self, service_with_mock_manager):
        """Test configure camera rejects inactive cameras."""
        service, mock_manager = service_with_mock_manager
        mock_manager.active_cameras = ["ActiveCamera"]
        
        request = CameraConfigureRequest(
            camera="InactiveCamera",
            properties={"exposure": 1000}
        )
        
        with pytest.raises(CameraNotFoundError, match="InactiveCamera.*not initialized"):
            await service.configure_camera(request)

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
    async def test_configure_camera_failure_handling(self, service_with_mock_manager):
        """Test configure camera handles configuration failures correctly."""
        service, mock_manager = service_with_mock_manager
        
        # Set up camera that fails configuration
        mock_camera = AsyncMock()
        mock_camera.configure.return_value = False  # Configuration failed
        mock_manager.active_cameras = ["TestCamera"]
        mock_manager.open = AsyncMock(return_value=mock_camera)
        
        request = CameraConfigureRequest(
            camera="TestCamera",
            properties={"exposure": 1000}
        )
        
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
        """Test configuration errors are properly propagated."""
        service, mock_manager = service_with_mock_manager
        mock_manager.active_cameras = ["TestCamera"]
        
        mock_camera = AsyncMock()
        mock_camera.configure.side_effect = CameraConfigurationError("Invalid config")
        # Make sure open is an async mock that returns the camera
        mock_manager.open = AsyncMock(return_value=mock_camera)
        
        request = CameraConfigureRequest(
            camera="TestCamera",
            properties={"invalid_param": "bad_value"}
        )
        
        with pytest.raises(CameraConfigurationError, match="Invalid config"):
            await service.configure_camera(request)

class TestCameraManagerServiceResponseModels:
    """Test response model creation and data formatting."""
    
    @pytest.fixture
    def service_with_mock_manager(self):
        service = CameraManagerService(include_mocks=True)
        mock_manager = Mock()
        service._camera_manager = mock_manager
        return service, mock_manager
    
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
    
    @pytest.mark.asyncio
    async def test_set_bandwidth_limit_processing(self, service_with_mock_manager):
        """Test bandwidth limit setting processes request correctly."""
        service, mock_manager = service_with_mock_manager
        
        from mindtrace.hardware.api.cameras.models.requests import BandwidthLimitRequest
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
            "recommended_settings": {"jumbo_frames": True}
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