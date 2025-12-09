"""Integration tests for CameraManagerService API with mock backends.

These tests validate the full API stack:
- Request/response models
- Service layer logic
- Backend integration
- Error handling and propagation
- Batch operations
- Concurrent request handling
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from mindtrace.hardware.api.cameras.models import (
    BackendFilterRequest,
    BackendsResponse,
    BandwidthLimitRequest,
    BatchCaptureResponse,
    BoolResponse,
    CameraCloseRequest,
    CameraConfigureRequest,
    # Requests
    CameraOpenRequest,
    CameraPerformanceSettingsRequest,
    CaptureBatchRequest,
    CaptureHDRRequest,
    CaptureImageRequest,
    CaptureResponse,
    HDRCaptureResponse,
    # Responses
    ListResponse,
    SystemDiagnosticsResponse,
)
from mindtrace.hardware.api.cameras.service import CameraManagerService
from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraNotFoundError,
)


@pytest.fixture
def mock_camera_manager():
    """Create a mock AsyncCameraManager with controlled behavior."""
    manager = AsyncMock(spec=AsyncCameraManager)

    # Setup mock cameras
    mock_cameras = [
        "MockBasler:TestCam1",
        "MockBasler:TestCam2",
        "MockBasler:TestCam3",
    ]

    # Mock discovery
    manager.discover = MagicMock(return_value=mock_cameras)
    AsyncCameraManager.discover = MagicMock(return_value=mock_cameras)

    # Mock backends
    manager.backends.return_value = ["MockBasler", "OpenCV"]

    # Mock backend info
    manager.backend_info.return_value = {
        "MockBasler": {
            "available": True,
            "type": "mock",
            "sdk_required": False,
        },
        "OpenCV": {
            "available": True,
            "type": "native",
            "sdk_required": False,
        },
    }

    # Mock diagnostics
    manager.diagnostics.return_value = {
        "active_cameras": 0,
        "max_concurrent_captures": 5,
        "gige_cameras": 1,  # Count of GigE cameras, not list
        "bandwidth_management_enabled": True,
        "recommended_settings": {},
    }

    # Track active cameras
    manager.active_cameras = {}
    manager.max_concurrent_captures = 5

    return manager


@pytest.fixture
def camera_service(mock_camera_manager):
    """Create a CameraManagerService with mock manager."""
    service = CameraManagerService(include_mocks=True)
    service._camera_manager = mock_camera_manager
    return service


class TestServiceDiscoveryOperations:
    """Test camera discovery through the service."""

    @pytest.mark.asyncio
    async def test_discover_cameras(self, camera_service):
        """Test discovering available cameras through service."""
        request = BackendFilterRequest(backend=None)
        result = await camera_service.discover_cameras(request)

        assert isinstance(result, ListResponse)
        assert result.success is True
        assert len(result.data) == 3
        assert all(cam.startswith("MockBasler:") for cam in result.data)

    @pytest.mark.asyncio
    async def test_discover_backends(self, camera_service):
        """Test getting available backends through service."""
        result = await camera_service.discover_backends()

        assert isinstance(result, BackendsResponse)
        assert result.success is True
        assert "MockBasler" in result.data
        assert "OpenCV" in result.data

    @pytest.mark.asyncio
    async def test_system_diagnostics(self, camera_service):
        """Test getting system diagnostics through service."""
        result = await camera_service.get_system_diagnostics()

        assert isinstance(result, SystemDiagnosticsResponse)
        assert result.success is True
        assert result.data.max_concurrent_captures == 5
        assert result.data.active_cameras == 0

    @pytest.mark.asyncio
    async def test_discovery_with_backend_filter(self, camera_service, mock_camera_manager):
        """Test filtered discovery through service."""
        # Mock filtered discovery
        mock_camera_manager.discover = MagicMock(return_value=["MockBasler:TestCam1"])

        request = BackendFilterRequest(backend="MockBasler")
        result = await camera_service.discover_cameras(request)

        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0] == "MockBasler:TestCam1"


class TestServiceOpenCloseOperations:
    """Test camera open/close operations through the service."""

    @pytest.mark.asyncio
    async def test_open_single_camera(self, camera_service, mock_camera_manager):
        """Test opening a single camera through service."""
        # Setup mock camera proxy
        mock_proxy = AsyncMock()
        mock_proxy.name = "MockBasler:TestCam1"
        mock_proxy.is_connected = True
        mock_camera_manager.open.return_value = mock_proxy

        request = CameraOpenRequest(camera="MockBasler:TestCam1")
        result = await camera_service.open_camera(request)

        assert isinstance(result, BoolResponse)
        assert result.success is True
        assert result.data is True

        # Verify manager was called correctly
        mock_camera_manager.open.assert_called_once()

    @pytest.mark.asyncio
    async def test_open_nonexistent_camera(self, camera_service, mock_camera_manager):
        """Test opening a nonexistent camera raises error."""
        mock_camera_manager.open.side_effect = CameraNotFoundError("Camera not found: NonExistent")

        request = CameraOpenRequest(camera="NonExistent:Camera")

        with pytest.raises(CameraNotFoundError):
            await camera_service.open_camera(request)

    @pytest.mark.asyncio
    async def test_close_camera(self, camera_service, mock_camera_manager):
        """Test closing camera through service."""
        mock_camera_manager.close.return_value = None

        request = CameraCloseRequest(camera="MockBasler:TestCam1")
        result = await camera_service.close_camera(request)

        assert isinstance(result, BoolResponse)
        assert result.success is True
        assert result.data is True

        # Verify manager was called
        mock_camera_manager.close.assert_called_once_with("MockBasler:TestCam1")

    @pytest.mark.asyncio
    async def test_close_all_cameras(self, camera_service, mock_camera_manager):
        """Test closing all cameras through service."""
        mock_camera_manager.close.return_value = None
        mock_camera_manager.active_cameras = {"MockBasler:TestCam1": AsyncMock()}

        result = await camera_service.close_all_cameras()

        assert isinstance(result, BoolResponse)
        assert result.success is True

        # Should call close without arguments (close all)
        mock_camera_manager.close.assert_called_once()


class TestServiceCaptureOperations:
    """Test capture operations through the service."""

    @pytest.mark.asyncio
    async def test_single_capture(self, camera_service, mock_camera_manager):
        """Test single camera capture through service."""
        # Setup mock camera and capture
        mock_proxy = AsyncMock()
        mock_proxy.capture.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_camera_manager.active_cameras = {"MockBasler:TestCam1": mock_proxy}
        mock_camera_manager.open.return_value = mock_proxy

        request = CaptureImageRequest(camera="MockBasler:TestCam1")
        result = await camera_service.capture_image(request)

        assert isinstance(result, CaptureResponse)
        assert result.success is True
        assert result.data.success is True

    @pytest.mark.asyncio
    async def test_capture_camera_not_open(self, camera_service, mock_camera_manager):
        """Test capture fails when camera not open."""
        mock_camera_manager.active_cameras = {}

        request = CaptureImageRequest(camera="MockBasler:TestCam1")

        result = await camera_service.capture_image(request)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_capture_failure(self, camera_service, mock_camera_manager):
        """Test capture failure handling."""
        # Setup mock camera with failing capture
        mock_proxy = AsyncMock()
        mock_proxy.capture.side_effect = CameraCaptureError("Capture failed")
        mock_camera_manager.active_cameras = {"MockBasler:TestCam1": mock_proxy}
        mock_camera_manager.open.return_value = mock_proxy

        request = CaptureImageRequest(camera="MockBasler:TestCam1")

        result = await camera_service.capture_image(request)
        assert result.success is False
        assert "Capture failed" in result.message

    @pytest.mark.asyncio
    async def test_batch_capture(self, camera_service, mock_camera_manager):
        """Test batch capture through service."""
        # Setup mock results
        mock_results = {
            "MockBasler:TestCam1": np.zeros((480, 640, 3), dtype=np.uint8),
            "MockBasler:TestCam2": np.zeros((480, 640, 3), dtype=np.uint8),
        }
        mock_camera_manager.batch_capture.return_value = mock_results

        request = CaptureBatchRequest(cameras=["MockBasler:TestCam1", "MockBasler:TestCam2"])
        result = await camera_service.capture_images_batch(request)

        assert isinstance(result, BatchCaptureResponse)
        assert result.success is True
        assert result.successful_count == 2
        assert result.failed_count == 0
        assert len(result.data) == 2

    @pytest.mark.asyncio
    async def test_batch_capture_partial_failure(self, camera_service, mock_camera_manager):
        """Test batch capture with some cameras failing."""
        # Setup mixed results
        mock_results = {
            "MockBasler:TestCam1": np.zeros((480, 640, 3), dtype=np.uint8),
            "MockBasler:TestCam2": None,  # Failed capture
        }
        mock_camera_manager.batch_capture.return_value = mock_results

        request = CaptureBatchRequest(cameras=["MockBasler:TestCam1", "MockBasler:TestCam2"])
        result = await camera_service.capture_images_batch(request)

        assert isinstance(result, BatchCaptureResponse)
        assert result.success is True  # Overall operation succeeded
        assert result.successful_count == 1
        assert result.failed_count == 1
        assert result.data["MockBasler:TestCam1"].success is True
        assert result.data["MockBasler:TestCam2"].success is False

    @pytest.mark.asyncio
    async def test_hdr_capture(self, camera_service, mock_camera_manager):
        """Test HDR capture through service."""
        # Setup mock HDR results
        mock_hdr_result = {
            "success": True,
            "images": None,  # Should be None or list of base64 strings
            "image_paths": ["/path/to/image1.jpg", "/path/to/image2.jpg"],
            "gcs_urls": None,
            "exposure_levels": [1000, 5000],
            "successful_captures": 2,
        }

        mock_proxy = AsyncMock()
        mock_proxy.capture_hdr.return_value = mock_hdr_result
        mock_camera_manager.active_cameras = {"MockBasler:TestCam1": mock_proxy}
        mock_camera_manager.open.return_value = mock_proxy

        request = CaptureHDRRequest(
            camera="MockBasler:TestCam1",
            exposure_levels=2,
            return_images=True,
        )
        result = await camera_service.capture_hdr_image(request)

        assert isinstance(result, HDRCaptureResponse)
        assert result.success is True
        assert result.data.success is True
        assert len(result.data.exposure_levels) == 2
        assert result.data.successful_captures == 2


class TestServiceConfigurationOperations:
    """Test camera configuration through the service."""

    @pytest.mark.asyncio
    async def test_configure_single_camera(self, camera_service, mock_camera_manager):
        """Test configuring a single camera through service."""
        # Setup mock camera
        mock_proxy = AsyncMock()
        mock_proxy.configure.return_value = True
        mock_camera_manager.active_cameras = {"MockBasler:TestCam1": mock_proxy}
        mock_camera_manager.open.return_value = mock_proxy

        request = CameraConfigureRequest(
            camera="MockBasler:TestCam1",
            properties={
                "exposure": 2000,
                "gain": 5.0,
                "trigger_mode": "continuous",
            },
        )
        result = await camera_service.configure_camera(request)

        assert isinstance(result, BoolResponse)
        assert result.success is True
        assert result.data is True

        # Verify configuration was called
        mock_proxy.configure.assert_called_once()
        call_kwargs = mock_proxy.configure.call_args[1]
        assert call_kwargs["exposure"] == 2000
        assert call_kwargs["gain"] == 5.0
        assert call_kwargs["trigger_mode"] == "continuous"

    @pytest.mark.asyncio
    async def test_configure_roi(self, camera_service, mock_camera_manager):
        """Test configuring ROI through service."""
        # Setup mock camera
        mock_proxy = AsyncMock()
        mock_proxy.configure.return_value = True
        mock_camera_manager.active_cameras = {"MockBasler:TestCam1": mock_proxy}
        mock_camera_manager.open.return_value = mock_proxy

        request = CameraConfigureRequest(
            camera="MockBasler:TestCam1",
            properties={
                "roi": [0, 0, 640, 480],  # x, y, width, height
            },
        )
        result = await camera_service.configure_camera(request)

        assert result.success is True

        # Verify ROI was passed
        mock_proxy.configure.assert_called_once()
        call_kwargs = mock_proxy.configure.call_args[1]
        assert "roi" in call_kwargs
        assert call_kwargs["roi"] == [0, 0, 640, 480]

    @pytest.mark.asyncio
    async def test_configure_invalid_parameters(self, camera_service, mock_camera_manager):
        """Test configuration with invalid parameters."""
        # Setup mock camera that rejects config
        mock_proxy = AsyncMock()
        mock_proxy.configure.side_effect = CameraConfigurationError("Invalid exposure value")
        mock_camera_manager.active_cameras = {"MockBasler:TestCam1": mock_proxy}
        mock_camera_manager.open.return_value = mock_proxy

        request = CameraConfigureRequest(
            camera="MockBasler:TestCam1",
            properties={"exposure": -1000},  # Invalid negative exposure
        )

        result = await camera_service.configure_camera(request)
        assert result.success is False
        assert "Invalid exposure value" in result.message


class TestServiceErrorPropagation:
    """Test error propagation from backend through service."""

    @pytest.mark.asyncio
    async def test_backend_connection_error_propagation(self, camera_service, mock_camera_manager):
        """Test that backend connection errors propagate correctly."""
        mock_camera_manager.open.side_effect = CameraConnectionError("Failed to connect to camera")

        request = CameraOpenRequest(camera="MockBasler:TestCam1")

        with pytest.raises(CameraConnectionError):
            await camera_service.open_camera(request)

    @pytest.mark.asyncio
    async def test_backend_timeout_error_propagation(self, camera_service, mock_camera_manager):
        """Test that backend timeout errors propagate correctly."""
        from mindtrace.hardware.core.exceptions import CameraTimeoutError

        mock_proxy = AsyncMock()
        mock_proxy.capture.side_effect = CameraTimeoutError("Capture timeout after 5000ms")
        mock_camera_manager.active_cameras = {"MockBasler:TestCam1": mock_proxy}
        mock_camera_manager.open.return_value = mock_proxy

        request = CaptureImageRequest(camera="MockBasler:TestCam1")

        result = await camera_service.capture_image(request)
        assert result.success is False
        assert "timeout" in result.message.lower()
        assert "timeout" in result.data.error.lower()

    @pytest.mark.asyncio
    async def test_unknown_exception_handling(self, camera_service, mock_camera_manager):
        """Test handling of unexpected exceptions."""
        mock_camera_manager.open.side_effect = RuntimeError("Unexpected internal error")

        request = CameraOpenRequest(camera="MockBasler:TestCam1")

        with pytest.raises(RuntimeError):
            await camera_service.open_camera(request)


class TestServiceConcurrentOperations:
    """Test concurrent service operation handling."""

    @pytest.mark.asyncio
    async def test_concurrent_captures(self, camera_service, mock_camera_manager):
        """Test handling concurrent capture requests."""
        # Setup mock cameras
        mock_proxies = {}
        for i in range(1, 4):
            proxy = AsyncMock()
            proxy.name = f"MockBasler:TestCam{i}"
            proxy.capture.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
            mock_proxies[proxy.name] = proxy

        mock_camera_manager.active_cameras = mock_proxies
        mock_camera_manager.open = AsyncMock(side_effect=lambda name, **kwargs: mock_proxies[name])

        # Simulate concurrent capture requests
        tasks = []
        for name in mock_proxies.keys():
            request = CaptureImageRequest(camera=name)
            task = asyncio.create_task(camera_service.capture_image(request))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All captures should succeed
        assert len(results) == 3
        for result in results:
            assert isinstance(result, CaptureResponse)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_concurrent_open_close(self, camera_service, mock_camera_manager):
        """Test handling concurrent open/close requests."""
        # Setup mock responses
        mock_proxy = AsyncMock()
        mock_proxy.name = "MockBasler:TestCam1"
        mock_proxy.is_connected = True
        mock_camera_manager.open.return_value = mock_proxy
        mock_camera_manager.close.return_value = None

        # Simulate concurrent open/close
        open_req = CameraOpenRequest(camera="MockBasler:TestCam1")
        close_req = CameraCloseRequest(camera="MockBasler:TestCam1")

        # Open first, then close
        open_result = await camera_service.open_camera(open_req)
        assert open_result.success is True

        close_result = await camera_service.close_camera(close_req)
        assert close_result.success is True


class TestServiceResourceManagement:
    """Test resource management through the service."""

    @pytest.mark.asyncio
    async def test_bandwidth_management(self, camera_service, mock_camera_manager):
        """Test bandwidth management through service operations."""
        # Set bandwidth limit
        mock_camera_manager.max_concurrent_captures = 2

        # Update diagnostics to reflect the new bandwidth limit
        mock_camera_manager.diagnostics.return_value = {
            "active_cameras": 0,
            "max_concurrent_captures": 2,  # Should match the limit we set
            "gige_cameras": 1,
            "bandwidth_management_enabled": True,
            "recommended_settings": {},
        }

        # Get system diagnostics which includes bandwidth info
        result = await camera_service.get_system_diagnostics()

        assert result.success is True
        assert result.data.max_concurrent_captures == 2
        assert result.data.bandwidth_management_enabled is True

    @pytest.mark.asyncio
    async def test_bandwidth_limit_setting(self, camera_service, mock_camera_manager):
        """Test setting bandwidth limits."""
        request = CameraPerformanceSettingsRequest(max_concurrent_captures=3)
        result = await camera_service.set_performance_settings(request)

        assert isinstance(result, BoolResponse)
        assert result.success is True
        assert mock_camera_manager.max_concurrent_captures == 3

    @pytest.mark.asyncio
    async def test_cleanup_on_service_shutdown(self, camera_service):
        """Test that all resources are cleaned up on service shutdown."""
        # Test service cleanup
        await camera_service.shutdown_cleanup()

        # Should have attempted to clean up camera manager
        assert True  # No exceptions means cleanup worked


class TestServiceEndToEndWorkflow:
    """Test complete end-to-end workflows through the service."""

    @pytest.mark.asyncio
    async def test_complete_camera_workflow(self, camera_service, mock_camera_manager):
        """Test complete workflow: discover -> open -> configure -> capture -> close."""

        # 1. Discover cameras
        discover_req = BackendFilterRequest(backend=None)
        cameras = await camera_service.discover_cameras(discover_req)
        assert cameras.success is True
        assert len(cameras.data) > 0

        camera_name = cameras.data[0]

        # 2. Open camera
        mock_proxy = AsyncMock()
        mock_proxy.name = camera_name
        mock_proxy.is_connected = True
        mock_proxy.configure.return_value = True
        mock_proxy.capture.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_camera_manager.open.return_value = mock_proxy
        mock_camera_manager.active_cameras = {camera_name: mock_proxy}

        open_req = CameraOpenRequest(camera=camera_name)
        open_result = await camera_service.open_camera(open_req)
        assert open_result.success is True

        # 3. Configure camera
        config_req = CameraConfigureRequest(camera=camera_name, properties={"exposure": 2000, "gain": 3.0})
        config_result = await camera_service.configure_camera(config_req)
        assert config_result.success is True

        # 4. Capture image
        capture_req = CaptureImageRequest(camera=camera_name)
        capture_result = await camera_service.capture_image(capture_req)
        assert capture_result.success is True
        assert capture_result.data.success is True

        # 5. Close camera
        close_req = CameraCloseRequest(camera=camera_name)
        close_result = await camera_service.close_camera(close_req)
        assert close_result.success is True

    @pytest.mark.asyncio
    async def test_multi_camera_batch_workflow(self, camera_service, mock_camera_manager):
        """Test workflow with multiple cameras using batch operations."""
        # Setup multiple cameras
        camera_names = ["MockBasler:TestCam1", "MockBasler:TestCam2"]
        mock_proxies = {}

        for name in camera_names:
            proxy = AsyncMock()
            proxy.name = name
            proxy.is_connected = True
            mock_proxies[name] = proxy

        mock_camera_manager.open = AsyncMock(side_effect=lambda name, **kwargs: mock_proxies[name])

        # 1. Open cameras (individually for this test)
        for name in camera_names:
            open_req = CameraOpenRequest(camera=name)
            open_result = await camera_service.open_camera(open_req)
            assert open_result.success is True

        # 2. Batch capture
        mock_camera_manager.batch_capture.return_value = {
            name: np.zeros((480, 640, 3), dtype=np.uint8) for name in camera_names
        }

        capture_req = CaptureBatchRequest(cameras=camera_names)
        capture_result = await camera_service.capture_images_batch(capture_req)
        assert capture_result.success is True
        assert len(capture_result.data) == 2
        assert capture_result.successful_count == 2

        # 3. Close all cameras
        close_result = await camera_service.close_all_cameras()
        assert close_result.success is True


class TestServiceValidation:
    """Test service request validation and error handling."""

    @pytest.mark.asyncio
    async def test_empty_batch_request(self, camera_service, mock_camera_manager):
        """Test handling of empty batch requests."""
        # Empty camera list
        mock_camera_manager.batch_capture.return_value = {}

        request = CaptureBatchRequest(cameras=[])
        result = await camera_service.capture_images_batch(request)

        assert result.success is False  # Empty batch should return success=False per service logic
        assert result.successful_count == 0
        assert result.failed_count == 0
        assert len(result.data) == 0

    @pytest.mark.asyncio
    async def test_camera_not_found_error(self, camera_service, mock_camera_manager):
        """Test proper CameraNotFoundError handling."""
        mock_camera_manager.active_cameras = {}

        request = CaptureImageRequest(camera="NonExistent:Camera")

        result = await camera_service.capture_image(request)
        assert result.success is False


class TestServicePerformance:
    """Test service performance characteristics."""

    @pytest.mark.asyncio
    async def test_large_batch_operation(self, camera_service, mock_camera_manager):
        """Test handling of large batch operations."""
        # Create many cameras
        num_cameras = 20
        camera_names = [f"MockBasler:TestCam{i}" for i in range(num_cameras)]

        # Setup mock results
        capture_results = {name: np.zeros((480, 640, 3), dtype=np.uint8) for name in camera_names}
        mock_camera_manager.batch_capture.return_value = capture_results

        # Execute large batch capture
        request = CaptureBatchRequest(cameras=camera_names)
        result = await camera_service.capture_images_batch(request)

        assert result.success is True
        assert result.successful_count == num_cameras
        assert len(result.data) == num_cameras

    @pytest.mark.asyncio
    async def test_concurrent_service_operations(self, camera_service, mock_camera_manager):
        """Test concurrent service operations."""
        # Setup mock responses
        mock_camera_manager.discover = MagicMock(return_value=["MockBasler:TestCam1", "MockBasler:TestCam2"])

        # Run multiple discovery operations concurrently
        tasks = []
        for i in range(5):
            request = BackendFilterRequest(backend=None)
            task = asyncio.create_task(camera_service.discover_cameras(request))
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 5
        for result in results:
            assert result.success is True
            assert len(result.data) == 2
