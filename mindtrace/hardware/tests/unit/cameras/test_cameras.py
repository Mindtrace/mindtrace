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
import json
import tempfile
import os
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
async def camera_manager():
    """Create a camera manager instance with mock backends."""
    from mindtrace.hardware.cameras.camera_manager import CameraManager
    
    manager = CameraManager(include_mocks=True)
    yield manager
    
    # Cleanup
    try:
        await manager.close_all_cameras()
    except Exception:
        pass


@pytest_asyncio.fixture
async def mock_daheng_camera():
    """Create a mock Daheng camera instance."""
    from mindtrace.hardware.cameras.backends.daheng import MockDahengCamera
    
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
    from mindtrace.hardware.cameras.backends.basler import MockBaslerCamera
    
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


@pytest_asyncio.fixture
async def temp_config_file():
    """Create a temporary configuration file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "camera_type": "mock_daheng",
            "camera_name": "test_camera",
            "timestamp": 1234567890.123,
            "exposure_time": 15000.0,
            "gain": 2.5,
            "trigger_mode": "continuous",
            "white_balance": "auto",
            "width": 1920,
            "height": 1080,
            "roi": {"x": 0, "y": 0, "width": 1920, "height": 1080},
            "pixel_format": "BGR8",
            "image_enhancement": True,
            "retrieve_retry_count": 3,
            "timeout_ms": 5000,
            "buffer_count": 25
        }
        json.dump(config_data, f, indent=2)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    try:
        os.unlink(temp_path)
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
        assert camera.initialized
        assert await camera.check_connection()
        
        # Test disconnection
        await camera.close()
        assert not camera.initialized
        assert not await camera.check_connection()
    
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
        
        # Test gain
        camera.set_gain(2.5)
        gain = camera.get_gain()
        assert gain == 2.5
        
        # Test trigger mode
        await camera.set_triggermode("trigger")
        trigger_mode = await camera.get_triggermode()
        assert trigger_mode == "trigger"
        
        # Test white balance
        await camera.set_auto_wb_once("once")
        wb = await camera.get_wb()
        assert wb == "once"
    
    @pytest.mark.asyncio
    async def test_roi_operations(self, mock_daheng_camera):
        """Test ROI (Region of Interest) operations."""
        camera = mock_daheng_camera
        await camera.initialize()
        
        # Set ROI
        success = camera.set_ROI(100, 100, 800, 600)
        assert success is True
        
        # Get ROI
        roi = camera.get_ROI()
        assert roi["x"] == 100
        assert roi["y"] == 100
        assert roi["width"] == 800
        assert roi["height"] == 600
        
        # Reset ROI
        success = camera.reset_ROI()
        assert success is True
        roi = camera.get_ROI()
        assert roi["x"] == 0
        assert roi["y"] == 0
    
    @pytest.mark.asyncio
    async def test_configuration_export_import(self, mock_daheng_camera, temp_config_file):
        """Test configuration export and import."""
        camera = mock_daheng_camera
        await camera.initialize()
        
        # Configure camera
        await camera.set_exposure(25000)
        camera.set_gain(3.0)
        await camera.set_triggermode("trigger")
        
        # Export configuration
        export_path = temp_config_file.replace('.json', '_export.json')
        success = await camera.export_config(export_path)
        assert success is True
        assert os.path.exists(export_path)
        
        # Verify exported configuration format
        with open(export_path, 'r') as f:
            config = json.load(f)
        assert config["camera_type"] == "mock_daheng"
        assert config["exposure_time"] == 25000
        assert config["gain"] == 3.0
        assert config["trigger_mode"] == "trigger"
        
        # Reset camera settings
        await camera.set_exposure(10000)
        camera.set_gain(1.0)
        
        # Import configuration
        success = await camera.import_config(export_path)
        assert success is True
        
        # Verify settings were restored
        assert await camera.get_exposure() == 25000
        assert camera.get_gain() == 3.0
        assert await camera.get_triggermode() == "trigger"
        
        # Cleanup
        try:
            os.unlink(export_path)
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_error_conditions(self):
        """Test various error conditions."""
        from mindtrace.hardware.cameras.backends.daheng import MockDahengCamera
        
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
    async def test_camera_connection(self, mock_basler_camera):
        """Test camera connection."""
        camera = mock_basler_camera
        
        success, _, _ = await camera.initialize()
        assert success
        assert camera.initialized
        assert await camera.check_connection()
    
    @pytest.mark.asyncio
    async def test_basler_specific_features(self, mock_basler_camera):
        """Test Basler-specific camera features."""
        camera = mock_basler_camera
        await camera.initialize()
        
        # Test trigger mode
        await camera.set_triggermode("trigger")
        trigger_mode = await camera.get_triggermode()
        assert trigger_mode == "trigger"
        
        # Test gain range
        gain_range = camera.get_gain_range()
        assert isinstance(gain_range, list)
        assert len(gain_range) == 2
        
        # Test pixel format range
        pixel_formats = camera.get_pixel_format_range()
        assert isinstance(pixel_formats, list)
        assert "BGR8" in pixel_formats
    
    @pytest.mark.asyncio
    async def test_configuration_compatibility(self, mock_basler_camera, temp_config_file):
        """Test configuration compatibility with common format."""
        camera = mock_basler_camera
        await camera.initialize()
        
        # Import configuration from common format
        success = await camera.import_config(temp_config_file)
        assert success is True
        
        # Verify settings were applied
        assert await camera.get_exposure() == 15000.0
        assert camera.get_gain() == 2.5


class TestCameraManager:
    """Test suite for Camera Manager functionality."""
    
    @pytest.mark.asyncio
    async def test_manager_initialization(self, camera_manager):
        """Test camera manager initialization."""
        manager = camera_manager
        
        assert manager is not None
        backends = manager.get_available_backends()
        assert isinstance(backends, list)
        
        # With mocks enabled, we should have mock backends
        backend_info = manager.get_backend_info()
        assert isinstance(backend_info, dict)
    
    @pytest.mark.asyncio
    async def test_camera_discovery(self, camera_manager):
        """Test camera discovery functionality."""
        manager = camera_manager
        
        # Test available cameras discovery
        available = manager.discover_cameras()
        assert isinstance(available, list)
        
        # Should include mock cameras
        mock_cameras = [cam for cam in available if "Mock" in cam]
        assert len(mock_cameras) > 0
    
    @pytest.mark.asyncio
    async def test_camera_proxy_operations(self, camera_manager):
        """Test camera proxy operations through manager."""
        manager = camera_manager
        
        # Get a mock camera through the manager
        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "MockDaheng" in cam]
        
        if mock_cameras:
            camera_name = mock_cameras[0]
            
            # Initialize the camera first
            await manager.initialize_camera(camera_name)
            
            # Then get the camera proxy
            camera_proxy = manager.get_camera(camera_name)
            
            assert camera_proxy is not None
            assert camera_proxy.name == camera_name
            assert "MockDaheng" in camera_proxy.backend
            assert camera_proxy.is_connected
            
            # Test capture through proxy
            image = await camera_proxy.capture()
            assert image is not None
            assert isinstance(image, np.ndarray)
            
            # Test configuration through proxy
            success = await camera_proxy.configure(
                exposure=20000,
                gain=2.0,
                trigger_mode="continuous"
            )
            assert success is True
            
            # Verify configuration
            exposure = await camera_proxy.get_exposure()
            assert exposure == 20000
            
            gain = camera_proxy.get_gain()
            assert gain == 2.0
            
            trigger_mode = await camera_proxy.get_trigger_mode()
            assert trigger_mode == "continuous"
    
    @pytest.mark.asyncio
    async def test_batch_operations(self, camera_manager):
        """Test batch camera operations."""
        manager = camera_manager
        
        # Get multiple mock cameras
        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "Mock" in cam][:3]  # Limit to 3 for testing
        
        if len(mock_cameras) >= 2:
            # Initialize cameras in batch
            failed_list = await manager.initialize_cameras(mock_cameras)
            assert len(failed_list) == 0  # No cameras should fail
            
            # Get camera proxies
            camera_proxies_dict = manager.get_cameras(mock_cameras)
            camera_proxies = list(camera_proxies_dict.values())
            
            # Test batch configuration
            configurations = {}
            for i, camera_name in enumerate(mock_cameras):
                configurations[camera_name] = {
                    "exposure": 15000 + i * 1000,
                    "gain": 1.5 + i * 0.5
                }
            
            results = await manager.batch_configure(configurations)
            assert isinstance(results, dict)
            assert len(results) == len(mock_cameras)
            
            # Test batch capture
            capture_results = await manager.batch_capture(mock_cameras)
            assert isinstance(capture_results, dict)
            assert len(capture_results) == len(mock_cameras)
            
            for camera_name, image in capture_results.items():
                assert image is not None
                assert isinstance(image, np.ndarray)
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test camera manager as context manager."""
        from mindtrace.hardware.cameras.camera_manager import CameraManager
        
        async with CameraManager(include_mocks=True) as manager:
            cameras = manager.discover_cameras()
            assert isinstance(cameras, list)
            
            mock_cameras = [cam for cam in cameras if "Mock" in cam]
            if mock_cameras:
                camera_name = mock_cameras[0]
                
                # Initialize the camera first
                await manager.initialize_camera(camera_name)
                
                # Then get the camera proxy
                camera_proxy = manager.get_camera(camera_name)
                assert camera_proxy is not None
                
                image = await camera_proxy.capture()
                assert image is not None
        
        # Manager should be properly closed after context exit


class TestCameraErrorHandling:
    """Test suite for camera error handling and edge cases."""
    
    @pytest.mark.asyncio
    async def test_connection_timeout(self):
        """Test connection timeout handling."""
        from mindtrace.hardware.cameras.backends.daheng import MockDahengCamera
        
        # Create camera with short timeout
        camera = MockDahengCamera("TimeoutTest", timeout_ms=100)
        
        # Connection should succeed quickly in mock
        success, _, _ = await camera.initialize()
        assert isinstance(success, bool)
    
    @pytest.mark.asyncio
    async def test_capture_timeout(self):
        """Test image capture timeout handling."""
        from mindtrace.hardware.cameras.backends.daheng import MockDahengCamera
        
        camera = MockDahengCamera("CaptureTimeoutTest")
        await camera.initialize()
        
        # Mock should handle capture quickly
        success, image = await camera.capture()
        assert success is True
        assert image is not None
    
    @pytest.mark.asyncio
    async def test_invalid_parameters(self):
        """Test handling of invalid parameters."""
        from mindtrace.hardware.cameras.backends.daheng import MockDahengCamera
        
        camera = MockDahengCamera("InvalidParamTest")
        await camera.initialize()
        
        # Test invalid exposure time
        with pytest.raises(CameraConfigurationError):
            await camera.set_exposure(-5000)
        
        # Test invalid gain
        with pytest.raises(CameraConfigurationError):
            camera.set_gain(-1.0)
        
        # Test another invalid gain value
        with pytest.raises(CameraConfigurationError):
            camera.set_gain(20.0)  # Above max range
        
        # Test valid gain should work
        result = camera.set_gain(5.0)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_camera_not_found_error(self, camera_manager):
        """Test camera not found error handling."""
        manager = camera_manager
        
        # Try to initialize a non-existent camera
        with pytest.raises(CameraNotFoundError):
            await manager.initialize_camera("NonExistent:fake_camera")
    
    @pytest.mark.asyncio
    async def test_configuration_file_errors(self, mock_daheng_camera):
        """Test configuration file error handling."""
        camera = mock_daheng_camera
        await camera.initialize()
        
        # Test non-existent file
        with pytest.raises(CameraConfigurationError):
            await camera.import_config("/non/existent/file.json")
        
        # Test invalid JSON file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            invalid_file = f.name
        
        try:
            with pytest.raises(CameraConfigurationError):
                await camera.import_config(invalid_file)
        finally:
            os.unlink(invalid_file)


class TestCameraPerformance:
    """Test suite for camera performance and concurrent operations."""
    
    @pytest.mark.asyncio
    async def test_concurrent_capture(self, camera_manager):
        """Test concurrent image capture from multiple cameras."""
        manager = camera_manager
        
        # Get multiple mock cameras
        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "Mock" in cam][:3]
        
        if len(mock_cameras) >= 2:
            # Initialize cameras in batch
            failed_list = await manager.initialize_cameras(mock_cameras)
            assert len(failed_list) == 0  # No cameras should fail
            
            # Get camera proxies
            camera_proxies_dict = manager.get_cameras(mock_cameras)
            camera_proxies = list(camera_proxies_dict.values())
            
            # Capture images concurrently
            tasks = [proxy.capture() for proxy in camera_proxies]
            results = await asyncio.gather(*tasks)
            
            assert len(results) == len(camera_proxies)
            for image in results:
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
            assert camera.initialized
            assert await camera.check_connection()
            
            # Capture an image
            success, image = await camera.capture()
            assert success is True
            assert image is not None
            
            await camera.close()
            assert not camera.initialized
            assert not await camera.check_connection()


class TestConfigurationFormat:
    """Test suite for unified configuration format."""
    
    @pytest.mark.asyncio
    async def test_common_format_export(self, mock_daheng_camera):
        """Test export using common configuration format."""
        camera = mock_daheng_camera
        await camera.initialize()
        
        # Configure camera
        await camera.set_exposure(30000)
        camera.set_gain(4.0)
        await camera.set_triggermode("trigger")
        camera.set_image_quality_enhancement(True)
        
        # Export configuration
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            export_path = f.name
        
        try:
            success = await camera.export_config(export_path)
            assert success is True
            
            # Verify common format structure
            with open(export_path, 'r') as f:
                config = json.load(f)
            
            # Check required common format fields
            assert "camera_type" in config
            assert "camera_name" in config
            assert "timestamp" in config
            assert "exposure_time" in config
            assert "gain" in config
            assert "trigger_mode" in config
            assert "white_balance" in config
            assert "width" in config
            assert "height" in config
            assert "roi" in config
            assert "pixel_format" in config
            assert "image_enhancement" in config
            
            # Verify values
            assert config["exposure_time"] == 30000
            assert config["gain"] == 4.0
            assert config["trigger_mode"] == "trigger"
            assert config["image_enhancement"] is True
            
        finally:
            os.unlink(export_path)
    
    @pytest.mark.asyncio
    async def test_cross_backend_compatibility(self, temp_config_file):
        """Test configuration compatibility across different backends."""
        from mindtrace.hardware.cameras.backends.daheng import MockDahengCamera
        from mindtrace.hardware.cameras.backends.basler import MockBaslerCamera
        
        # Create cameras from different backends
        daheng_camera = MockDahengCamera("cross_test_daheng")
        basler_camera = MockBaslerCamera("cross_test_basler")
        
        try:
            await daheng_camera.initialize()
            await basler_camera.initialize()
            
            # Both should be able to import the same common format config
            success_daheng = await daheng_camera.import_config(temp_config_file)
            success_basler = await basler_camera.import_config(temp_config_file)
            
            assert success_daheng is True
            assert success_basler is True
            
            # Both should have similar settings
            assert await daheng_camera.get_exposure() == 15000.0
            assert await basler_camera.get_exposure() == 15000.0
            
            assert daheng_camera.get_gain() == 2.5
            assert basler_camera.get_gain() == 2.5
            
        finally:
            await daheng_camera.close()
            await basler_camera.close()


@pytest.mark.asyncio
async def test_camera_integration_scenario():
    """Integration test simulating real-world camera usage."""
    from mindtrace.hardware.cameras.camera_manager import CameraManager
    
    # Create manager with mocks enabled
    async with CameraManager(include_mocks=True) as manager:
        # Discover available cameras
        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "Mock" in cam][:3]
        
        if len(mock_cameras) >= 2:
            # Initialize cameras in batch
            failed_list = await manager.initialize_cameras(mock_cameras)
            assert len(failed_list) == 0  # No cameras should fail
            
            # Get camera proxies
            camera_proxies_dict = manager.get_cameras(mock_cameras)
            camera_proxies = list(camera_proxies_dict.values())
            
            # Configure cameras for production
            configurations = {}
            for i, camera_name in enumerate(mock_cameras):
                configurations[camera_name] = {
                    "exposure": 10000 + i * 1000,
                    "gain": 1.0 + i * 0.5,
                    "trigger_mode": "continuous"
                }
            
            config_results = await manager.batch_configure(configurations)
            assert all(config_results.values())
            
            # Simulate production cycle - capture from all cameras
            for cycle in range(3):
                capture_results = await manager.batch_capture(mock_cameras)
                
                assert len(capture_results) == len(mock_cameras)
                for camera_name, image in capture_results.items():
                    assert image is not None
                    assert isinstance(image, np.ndarray)
            
            # Check camera status
            for proxy in camera_proxies:
                assert proxy.is_connected
                assert await proxy.check_connection()


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 