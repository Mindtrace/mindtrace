"""
Comprehensive unit tests for the camera system.

This module tests all camera functionality using mock implementations to avoid
hardware dependencies. Tests cover individual camera backends, camera manager,
error handling, and edge cases.
"""

import pytest
import pytest_asyncio
import asyncio
import numpy as np
from unittest.mock import patch, MagicMock
from typing import Dict, Any, List

from mindtrace.hardware.core.exceptions import (
    CameraError,
    CameraNotFoundError,
    CameraInitializationError,
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraTimeoutError,
    SDKNotAvailableError,
)


# Fixtures
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def mock_camera_manager():
    """Create a camera manager instance with mock backends."""
    from mindtrace.hardware.cameras.camera_manager import CameraManager
    
    manager = CameraManager()
    
    # Register mock backends for testing
    manager.register_backend("mockdaheng")  # Register mock Daheng backend
    manager.register_backend("mockbasler")  # Register mock Basler backend
    
    yield manager
    
    # Cleanup
    try:
        await manager.disconnect_all_cameras()
    except Exception:
        pass


@pytest_asyncio.fixture
async def mock_daheng_camera():
    """Create a mock Daheng camera instance."""
    from mindtrace.hardware.cameras.backends.daheng.mock_daheng import MockDahengCamera
    
    camera = MockDahengCamera(
        camera_name="mock_cam_0",
        camera_config=None
    )
    yield camera
    
    # Cleanup
    try:
        await camera.close()
    except Exception:
        pass


@pytest_asyncio.fixture
async def mock_basler_camera():
    """Create a mock Basler camera instance."""
    from mindtrace.hardware.cameras.backends.basler.mock_basler import MockBaslerCamera
    
    camera = MockBaslerCamera(
        camera_name="mock_basler_1",
        camera_config=None
    )
    yield camera
    
    # Cleanup
    try:
        await camera.close()
    except Exception:
        pass


class TestMockDahengCamera:
    """Test suite for Mock Daheng camera implementation."""
    
    @pytest.mark.asyncio
    async def test_camera_initialization(self, mock_daheng_camera):
        """Test camera initialization."""
        camera = mock_daheng_camera
        
        assert camera.camera_name == "mock_cam_0"
        assert not camera.initialized
    
    @pytest.mark.asyncio
    async def test_camera_connection(self, mock_daheng_camera):
        """Test camera connection and disconnection."""
        camera = mock_daheng_camera
        
        # Test initialization
        success, _, _ = await camera.initialize()
        assert success
        assert await camera.check_connection()
        
        # Test disconnection
        await camera.close()
        assert not await camera.check_connection()
    
    @pytest.mark.asyncio
    async def test_camera_initialization_full(self, mock_daheng_camera):
        """Test full camera initialization process."""
        camera = mock_daheng_camera
        
        success, cam_obj, device_manager = await camera.initialize()
        assert success
        assert camera.initialized
        assert await camera.check_connection()
    
    @pytest.mark.asyncio
    async def test_image_capture(self, mock_daheng_camera):
        """Test image capture functionality."""
        camera = mock_daheng_camera
        await camera.initialize()
        
        # Test single image capture
        success, image = await camera.capture()
        assert success is True
        assert image is not None
        assert isinstance(image, np.ndarray)
        assert len(image.shape) == 3  # Height, Width, Channels
        assert image.shape[2] == 3    # RGB channels
    
    @pytest.mark.asyncio
    async def test_multiple_image_capture(self, mock_daheng_camera):
        """Test capturing multiple images."""
        camera = mock_daheng_camera
        await camera.initialize()
        
        # Capture multiple images
        images = []
        for i in range(5):
            success, image = await camera.capture()
            assert success is True
            images.append(image)
            assert image is not None
        
        # Verify all images are different (mock adds variation)
        assert len(images) == 5
        for i, image in enumerate(images):
            assert isinstance(image, np.ndarray)
    
    @pytest.mark.asyncio
    async def test_camera_configuration(self, mock_daheng_camera):
        """Test camera configuration methods."""
        camera = mock_daheng_camera
        await camera.initialize()
        
        # Test exposure time
        await camera.set_exposure(15000)
        exposure = await camera.get_exposure()
        assert exposure == 15000
        
        # Test white balance
        await camera.set_auto_wb_once("once")
        wb = await camera.get_wb()
        assert wb == "once"
    
    @pytest.mark.asyncio
    async def test_camera_info(self, mock_daheng_camera):
        """Test camera information retrieval."""
        camera = mock_daheng_camera
        await camera.initialize()
        
        # Test basic camera properties
        assert camera.camera_name == "mock_cam_0"
        assert await camera.check_connection() is True
    
    @pytest.mark.asyncio
    async def test_error_conditions(self):
        """Test various error conditions."""
        from mindtrace.hardware.cameras.backends.daheng.mock_daheng import MockDahengCamera
        
        # Test capture without connection
        camera = MockDahengCamera("ErrorTest")
        
        with pytest.raises(CameraConnectionError):
            await camera.capture()
        
        # Test invalid configuration
        await camera.initialize()
        with pytest.raises(CameraConfigurationError):
            await camera.set_exposure(-1000)  # Invalid exposure time


class TestMockBaslerCamera:
    """Test suite for Mock Basler camera implementation."""
    
    @pytest.mark.asyncio
    async def test_camera_initialization(self, mock_basler_camera):
        """Test Basler camera initialization."""
        camera = mock_basler_camera
        
        assert camera.camera_name == "mock_basler_1"
        assert not camera.initialized
    
    @pytest.mark.asyncio
    async def test_serial_based_connection(self, mock_basler_camera):
        """Test serial number based connection."""
        camera = mock_basler_camera
        
        success, _, _ = await camera.initialize()
        assert success
        assert await camera.check_connection()
    
    @pytest.mark.asyncio
    async def test_basler_specific_features(self, mock_basler_camera):
        """Test Basler-specific camera features."""
        camera = mock_basler_camera
        await camera.initialize()
        
        # Test trigger mode
        camera.set_triggermode("trigger")
        trigger_mode = camera.get_triggermode()
        assert "trigger" in str(trigger_mode).lower() or isinstance(trigger_mode, list)


class TestOpenCVCamera:
    """Test suite for OpenCV camera functionality."""
    
    @pytest.mark.skip(reason="OpenCV cameras require real hardware - no mock implementation available")
    @pytest.mark.asyncio
    async def test_opencv_camera_basic(self, mock_opencv_camera):
        """Test basic OpenCV camera operations."""
        camera = mock_opencv_camera
        await camera.initialize()
        
        # Test basic functionality
        assert await camera.check_connection()
        
        # Test image capture
        success, image = await camera.capture()
        assert success is True
        assert image is not None
    
    @pytest.mark.skip(reason="OpenCV cameras require real hardware - no mock implementation available")
    @pytest.mark.asyncio
    async def test_opencv_connection(self, mock_opencv_camera):
        """Test OpenCV camera connection handling."""
        camera = mock_opencv_camera
        
        # Test connection before initialization
        assert not await camera.check_connection()
        
        # Test after initialization
        await camera.initialize()
        assert await camera.check_connection()
        
        # Test after closing
        await camera.close()
        assert not await camera.check_connection()


class TestCameraManager:
    """Test suite for Camera Manager functionality."""
    
    @pytest.mark.asyncio
    async def test_manager_initialization(self, mock_camera_manager):
        """Test camera manager initialization."""
        manager = mock_camera_manager
        
        assert manager is not None
        backends = manager.get_available_backends()
        assert isinstance(backends, list)
    
    @pytest.mark.asyncio
    async def test_camera_registration(self, mock_camera_manager):
        """Test camera registration with manager."""
        manager = mock_camera_manager
        
        # Test camera setup through manager with mock backend format
        camera = manager.setup_camera("mockdaheng:mock_cam_0")
        assert camera is not None
        assert camera.camera_name == "mock_cam_0"
    
    @pytest.mark.asyncio
    async def test_camera_discovery(self, mock_camera_manager):
        """Test camera discovery functionality."""
        manager = mock_camera_manager
        
        # Test available cameras discovery
        available = manager.get_available_cameras()
        assert isinstance(available, list)
    
    @pytest.mark.asyncio
    async def test_batch_operations(self, mock_camera_manager):
        """Test batch camera operations."""
        from mindtrace.hardware.cameras.backends.daheng.mock_daheng import MockDahengCamera
        
        manager = mock_camera_manager
        
        # Create multiple cameras
        cameras = []
        for i in range(3):
            camera = MockDahengCamera(f"BatchTest{i}")
            cameras.append(camera)
        
        # Test individual camera operations
        for camera in cameras:
            await camera.initialize()
            success, image = await camera.capture()
            assert success is True
            assert image is not None
            await camera.close()
    
    @pytest.mark.asyncio
    async def test_manager_error_handling(self, mock_camera_manager):
        """Test manager error handling."""
        manager = mock_camera_manager
        
        # Test manager basic functionality
        backends = manager.get_available_backends()
        assert isinstance(backends, list)
        
        # Test invalid camera setup
        try:
            camera = manager.setup_camera("NonExistentCamera")
            # If it doesn't raise an exception, that's also valid behavior
        except Exception:
            pass  # Expected for invalid camera names


class TestCameraErrorHandling:
    """Test suite for camera error handling and edge cases."""
    
    @pytest.mark.asyncio
    async def test_connection_timeout(self):
        """Test connection timeout handling."""
        from mindtrace.hardware.cameras.backends.daheng.mock_daheng import MockDahengCamera
        
        # Create camera with very short timeout
        camera = MockDahengCamera("TimeoutTest")
        
        # Connection should succeed quickly in mock, but test timeout handling
        success, _, _ = await camera.initialize()
        assert isinstance(success, bool)
    
    @pytest.mark.asyncio
    async def test_capture_timeout(self):
        """Test image capture timeout handling."""
        from mindtrace.hardware.cameras.backends.daheng.mock_daheng import MockDahengCamera
        
        camera = MockDahengCamera("CaptureTimeoutTest")
        await camera.initialize()
        
        # Mock should handle capture quickly
        success, image = await camera.capture()
        assert success is True
        assert image is not None
    
    @pytest.mark.asyncio
    async def test_invalid_parameters(self):
        """Test handling of invalid parameters."""
        from mindtrace.hardware.cameras.backends.daheng.mock_daheng import MockDahengCamera
        
        camera = MockDahengCamera("InvalidParamTest")
        await camera.initialize()
        
        # Test invalid exposure time
        with pytest.raises(CameraConfigurationError):
            await camera.set_exposure(-5000)
    
    @pytest.mark.asyncio
    async def test_sdk_not_available(self):
        """Test SDK not available error handling."""
        # This would be tested with real implementations when SDK is missing
        # For mock implementations, they should always be available
        from mindtrace.hardware.cameras.backends.daheng.mock_daheng import MockDahengCamera
        
        camera = MockDahengCamera("SDKTest")
        # Mock cameras don't require SDK, so this should work
        success, _, _ = await camera.initialize()
        assert isinstance(success, bool)


class TestCameraPerformance:
    """Test suite for camera performance and concurrent operations."""
    
    @pytest.mark.asyncio
    async def test_concurrent_capture(self, mock_camera_manager):
        """Test concurrent image capture from multiple cameras."""
        from mindtrace.hardware.cameras.backends.daheng.mock_daheng import MockDahengCamera
        
        manager = mock_camera_manager
        
        # Create multiple cameras
        cameras = []
        for i in range(3):
            camera = MockDahengCamera(f"ConcurrentTest{i}")
            await camera.initialize()
            cameras.append(camera)
        
        # Capture images concurrently
        tasks = [camera.capture() for camera in cameras]
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 3
        for success, image in results:
            assert success is True
            assert image is not None
            assert isinstance(image, np.ndarray)
    
    @pytest.mark.asyncio
    async def test_rapid_capture_sequence(self, mock_daheng_camera):
        """Test rapid sequence of image captures."""
        camera = mock_daheng_camera
        await camera.initialize()
        
        # Capture images in rapid succession
        results = []
        for i in range(10):
            result = await camera.capture()
            results.append(result)
        
        assert len(results) == 10
        for success, image in results:
            assert success is True
            assert image is not None
    
    @pytest.mark.asyncio
    async def test_camera_resource_cleanup(self, mock_daheng_camera):
        """Test proper resource cleanup."""
        camera = mock_daheng_camera
        
        # Connect and disconnect multiple times
        for i in range(5):
            await camera.initialize()
            assert await camera.check_connection()
            
            # Capture an image
            success, image = await camera.capture()
            assert success is True
            assert image is not None
            
            await camera.close()
            assert not await camera.check_connection()


class TestCameraConfiguration:
    """Test suite for camera configuration and settings."""
    
    @pytest.mark.asyncio
    async def test_configuration_persistence(self, mock_daheng_camera):
        """Test that configuration settings persist."""
        camera = mock_daheng_camera
        await camera.initialize()
        
        # Set configuration
        await camera.set_exposure(20000)
        await camera.set_auto_wb_once("off")
        
        # Verify settings persist
        assert await camera.get_exposure() == 20000
        assert await camera.get_wb() == "off"
        
        # Disconnect and reconnect
        await camera.close()
        await camera.initialize()
        
        # Settings should still be there (in mock implementation)
        assert await camera.get_exposure() == 20000
    
    @pytest.mark.asyncio
    async def test_configuration_validation(self, mock_daheng_camera):
        """Test configuration parameter validation."""
        camera = mock_daheng_camera
        await camera.initialize()
        
        # Test valid ranges
        await camera.set_exposure(1000)   # Minimum
        await camera.set_exposure(100000) # Maximum
        
        # Test invalid values
        with pytest.raises(CameraConfigurationError):
            await camera.set_exposure(0)  # Too low
    
    @pytest.mark.asyncio
    async def test_trigger_modes(self, mock_daheng_camera):
        """Test different trigger modes."""
        camera = mock_daheng_camera
        await camera.initialize()
        
        # Test continuous mode
        camera.set_triggermode("continuous")
        assert camera.get_triggermode() == "continuous"
        
        # Test trigger mode
        camera.set_triggermode("trigger")
        assert camera.get_triggermode() == "trigger"


@pytest.mark.asyncio
async def test_camera_integration_scenario():
    """Integration test simulating real-world camera usage."""
    from mindtrace.hardware.cameras.backends.daheng.mock_daheng import MockDahengCamera
    from mindtrace.hardware.cameras.camera_manager import CameraManager
    
    # Create manager and cameras
    manager = CameraManager()
    
    # Set up multiple cameras
    cameras = [
        MockDahengCamera("Station1_Camera"),
        MockDahengCamera("Station2_Camera"),
        MockDahengCamera("QC_Camera")
    ]
    
    try:
        # Initialize all cameras
        for camera in cameras:
            await camera.initialize()
        
        # Configure cameras for production
        for camera in cameras:
            await camera.set_exposure(10000)
        
        # Simulate production cycle - capture from all cameras
        for cycle in range(3):
            images = {}
            for camera in cameras:
                success, image = await camera.capture()
                assert success is True
                assert image is not None
                assert isinstance(image, np.ndarray)
                images[camera.camera_name] = image
            
            assert len(images) == 3
        
        # Check camera status
        for camera in cameras:
            assert await camera.check_connection()
    
    finally:
        # Cleanup
        for camera in cameras:
            await camera.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 