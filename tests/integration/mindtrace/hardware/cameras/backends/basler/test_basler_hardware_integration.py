"""Integration tests for BaslerCameraBackend with real pypylon SDK and physical cameras.

These tests validate that the BaslerCameraBackend correctly integrates with actual Basler cameras
when they are connected. They test full initialization, capture, configuration, and lifecycle
management with real hardware.

Note: These tests will be skipped if no Basler cameras are detected.
"""

import pytest
import numpy as np
from mindtrace.core.utils.checks import check_libs

# Skip all tests in this module if pypylon is not available
missing_libs = check_libs(["pypylon"])
if missing_libs:
    pytest.skip(f"Required libraries are not installed: {', '.join(missing_libs)}. Skipping test.", allow_module_level=True)


def get_connected_cameras():
    """Get list of connected Basler cameras for testing."""
    try:
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        return BaslerCameraBackend.get_available_cameras()
    except Exception:
        return []


# Skip all tests if no cameras are connected
connected_cameras = get_connected_cameras()
if not connected_cameras:
    pytest.skip("No Basler cameras detected. Skipping Basler hardware integration tests.", allow_module_level=True)


@pytest.fixture
def camera_name():
    """Fixture providing the name of the first connected camera."""
    return connected_cameras[0]


@pytest.fixture
async def basler_camera(camera_name):
    """Fixture providing an initialized Basler camera."""
    from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
    
    camera = BaslerCameraBackend(camera_name)
    success, cam_obj, remote_obj = await camera.initialize()
    
    if not success:
        pytest.skip(f"Failed to initialize camera {camera_name}")
    
    yield camera
    
    # Cleanup
    try:
        await camera.close()
    except Exception:
        pass  # Best effort cleanup


class TestHardwareDiscovery:
    """Test camera discovery with real hardware."""
    
    def test_hardware_discovery_finds_cameras(self):
        """Test that discovery finds the connected cameras."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        cameras = BaslerCameraBackend.get_available_cameras()
        assert isinstance(cameras, list)
        assert len(cameras) > 0
        
        # All discovered cameras should be strings
        for camera in cameras:
            assert isinstance(camera, str)
            assert len(camera) > 0

    def test_hardware_discovery_with_details(self):
        """Test that detailed discovery provides camera information."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        details = BaslerCameraBackend.get_available_cameras(include_details=True)
        assert isinstance(details, dict)
        assert len(details) > 0
        
        # Check that each camera has expected detail fields
        for camera_name, info in details.items():
            assert isinstance(camera_name, str)
            assert isinstance(info, dict)
            
            expected_fields = ["serial_number", "model", "vendor", "device_class", 
                             "interface", "friendly_name", "user_defined_name"]
            for field in expected_fields:
                assert field in info


class TestHardwareInitialization:
    """Test camera initialization with real hardware."""
    
    @pytest.mark.asyncio
    async def test_hardware_initialization_success(self, camera_name):
        """Test successful initialization of connected camera."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        camera = BaslerCameraBackend(camera_name)
        success, cam_obj, remote_obj = await camera.initialize()
        
        try:
            assert success is True
            assert cam_obj is not None
            assert camera.initialized is True
            assert camera.camera is not None
        finally:
            await camera.close()

    @pytest.mark.asyncio
    async def test_hardware_initialization_with_configuration(self, camera_name):
        """Test initialization with custom configuration."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        camera = BaslerCameraBackend(
            camera_name,
            img_quality_enhancement=True,
            retrieve_retry_count=3,
            buffer_count=10,
            timeout_ms=2000
        )
        
        success, cam_obj, remote_obj = await camera.initialize()
        
        try:
            assert success is True
            assert camera.img_quality_enhancement is True
            assert camera.retrieve_retry_count == 3
            assert camera.buffer_count == 10
            assert camera.timeout_ms == 2000
        finally:
            await camera.close()

    @pytest.mark.asyncio
    async def test_hardware_double_initialization(self, camera_name):
        """Test that double initialization is handled gracefully."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConnectionError
        
        camera = BaslerCameraBackend(camera_name)
        
        try:
            success1, _, _ = await camera.initialize()
            assert success1 is True
            
            # Second initialization should also succeed
            success2, _, _ = await camera.initialize()
            assert success2 is True
        except CameraConnectionError as e:
            if "controlled by another application" in str(e):
                pytest.skip(f"Camera {camera_name} is controlled by another application")
            else:
                raise
        finally:
            await camera.close()


class TestHardwareCapture:
    """Test image capture with real hardware."""
    
    @pytest.mark.asyncio
    async def test_hardware_basic_capture(self, basler_camera):
        """Test basic image capture from real hardware."""
        success, image = await basler_camera.capture()
        
        assert success is True
        assert image is not None
        assert isinstance(image, np.ndarray)
        assert image.ndim == 3  # Should be color image (H, W, C)
        assert image.shape[2] == 3  # Should have 3 channels
        assert image.dtype == np.uint8
        assert image.size > 0

    @pytest.mark.asyncio
    async def test_hardware_multiple_captures(self, basler_camera):
        """Test multiple consecutive captures."""
        images = []
        
        for i in range(3):
            success, image = await basler_camera.capture()
            assert success is True
            assert image is not None
            images.append(image)
        
        # All images should have same dimensions
        shapes = [img.shape for img in images]
        assert all(shape == shapes[0] for shape in shapes)
        
        # Images should not be identical (unless camera is looking at static scene)
        # We'll just verify they're all valid arrays
        for image in images:
            assert isinstance(image, np.ndarray)
            assert image.size > 0

    @pytest.mark.asyncio
    async def test_hardware_capture_after_configuration(self, basler_camera):
        """Test capture after changing camera configuration."""
        # Get original exposure
        original_exposure = await basler_camera.get_exposure()
        assert isinstance(original_exposure, (int, float))
        
        # Change exposure
        new_exposure = min(50000, original_exposure * 2)  # Double exposure, cap at 50ms
        success = await basler_camera.set_exposure(new_exposure)
        assert success is True
        
        # Verify exposure changed
        current_exposure = await basler_camera.get_exposure()
        assert abs(current_exposure - new_exposure) < 1000  # Allow for small differences
        
        # Capture should still work
        success, image = await basler_camera.capture()
        assert success is True
        assert image is not None


class TestHardwareConfiguration:
    """Test camera configuration with real hardware."""
    
    @pytest.mark.asyncio
    async def test_hardware_exposure_control(self, basler_camera):
        """Test exposure time control."""
        # Get exposure range
        exp_range = await basler_camera.get_exposure_range()
        assert isinstance(exp_range, (list, tuple))
        assert len(exp_range) == 2
        min_exp, max_exp = exp_range
        assert min_exp < max_exp
        
        # Test setting exposure within range
        test_exposure = min_exp + (max_exp - min_exp) * 0.25  # 25% of range
        success = await basler_camera.set_exposure(test_exposure)
        assert success is True
        
        # Verify exposure was set
        current_exposure = await basler_camera.get_exposure()
        assert abs(current_exposure - test_exposure) < 1000  # Allow small tolerance

    @pytest.mark.asyncio
    async def test_hardware_gain_control(self, basler_camera):
        """Test gain control.""" 
        # Get current gain
        original_gain = await basler_camera.get_gain()
        assert isinstance(original_gain, (int, float))
        
        # Set new gain
        new_gain = max(0.0, min(10.0, original_gain + 1.0))  # Stay within reasonable range
        success = await basler_camera.set_gain(new_gain)
        assert success is True
        
        # Verify gain was set
        current_gain = await basler_camera.get_gain()
        assert abs(current_gain - new_gain) < 0.1  # Allow small tolerance

    @pytest.mark.asyncio
    async def test_hardware_trigger_mode(self, basler_camera):
        """Test trigger mode configuration."""
        # Test continuous mode
        success = await basler_camera.set_triggermode("continuous")
        assert success is True
        
        mode = await basler_camera.get_triggermode()
        assert mode == "continuous"
        
        # Capture should work in continuous mode
        success, image = await basler_camera.capture()
        assert success is True
        assert image is not None

    @pytest.mark.asyncio
    async def test_hardware_roi_configuration(self, basler_camera):
        """Test ROI (Region of Interest) configuration."""
        from mindtrace.hardware.core.exceptions import CameraConfigurationError
        
        # Get current ROI
        original_roi = await basler_camera.get_ROI()
        assert isinstance(original_roi, dict)
        assert all(key in original_roi for key in ["x", "y", "width", "height"])
        
        # Calculate a smaller ROI (center quarter) based on current ROI position
        new_width = original_roi["width"] // 2
        new_height = original_roi["height"] // 2
        new_x = original_roi["x"] + (original_roi["width"] // 4)
        new_y = original_roi["y"] + (original_roi["height"] // 4)
        
        # Set ROI - handle cameras that don't support offsets by using (0,0)
        try:
            success = await basler_camera.set_ROI(new_x, new_y, new_width, new_height)
            assert success is True
        except CameraConfigurationError as e:
            if "out of range" in str(e):
                # Try with (0,0) offsets if camera doesn't support offsets
                success = await basler_camera.set_ROI(0, 0, new_width, new_height)
                assert success is True
                new_x, new_y = 0, 0  # Update expected values
            else:
                raise
        
        # Verify ROI was set
        current_roi = await basler_camera.get_ROI()
        assert abs(current_roi["x"] - new_x) <= 4  # Allow for alignment
        assert abs(current_roi["y"] - new_y) <= 4
        assert abs(current_roi["width"] - new_width) <= 4
        assert abs(current_roi["height"] - new_height) <= 4
        
        # Capture should work with new ROI
        success, image = await basler_camera.capture()
        assert success is True
        assert image is not None
        
        # Reset ROI
        success = await basler_camera.reset_ROI()
        assert success is True


class TestHardwareAdvancedFeatures:
    """Test advanced camera features with real hardware."""
    
    @pytest.mark.asyncio
    async def test_hardware_pixel_formats(self, basler_camera):
        """Test pixel format functionality."""
        # Get available pixel formats
        formats = await basler_camera.get_pixel_format_range()
        assert isinstance(formats, list)
        assert len(formats) > 0
        
        # All formats should be strings
        for fmt in formats:
            assert isinstance(fmt, str)

    @pytest.mark.asyncio
    async def test_hardware_white_balance(self, basler_camera):
        """Test white balance functionality."""
        # Get current white balance mode
        wb_mode = await basler_camera.get_wb()
        assert isinstance(wb_mode, str)
        assert wb_mode in ["auto", "manual", "off", "once", "continuous"]
        
        # Try setting auto white balance
        success = await basler_camera.set_auto_wb_once("once")
        assert isinstance(success, bool)  # May succeed or fail depending on camera

    @pytest.mark.asyncio
    async def test_hardware_image_enhancement(self, basler_camera):
        """Test image quality enhancement."""
        # Test enabling enhancement
        success = await basler_camera.set_image_quality_enhancement(True)
        assert success is True
        assert await basler_camera.get_image_quality_enhancement() is True
        
        # Capture with enhancement
        success, enhanced_image = await basler_camera.capture()
        assert success is True
        assert enhanced_image is not None
        
        # Test disabling enhancement
        success = await basler_camera.set_image_quality_enhancement(False)
        assert success is True
        assert await basler_camera.get_image_quality_enhancement() is False
        
        # Capture without enhancement
        success, normal_image = await basler_camera.capture()
        assert success is True
        assert normal_image is not None


class TestHardwareConnectionManagement:
    """Test connection management with real hardware."""
    
    @pytest.mark.asyncio
    async def test_hardware_connection_check(self, basler_camera):
        """Test connection checking."""
        is_connected = await basler_camera.check_connection()
        assert is_connected is True

    @pytest.mark.asyncio
    async def test_hardware_close_and_reconnect(self, camera_name):
        """Test closing and reconnecting to camera."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        camera = BaslerCameraBackend(camera_name)
        
        # Initialize
        success, _, _ = await camera.initialize()
        assert success is True
        
        # Capture to verify it works
        success, image = await camera.capture()
        assert success is True
        assert image is not None
        
        # Close
        await camera.close()
        assert camera.initialized is False
        
        # Re-initialize
        success, _, _ = await camera.initialize()
        assert success is True
        
        # Capture should work again
        success, image = await camera.capture()
        assert success is True
        assert image is not None
        
        # Final cleanup
        await camera.close()


class TestHardwareManagerIntegration:
    """Test integration with camera managers using real hardware."""
    
    @pytest.mark.asyncio
    async def test_hardware_with_camera_manager(self, camera_name):
        """Test using real Basler camera through camera manager."""
        from mindtrace.hardware.cameras.core.camera_manager import CameraManager
        
        manager = CameraManager(include_mocks=False)
        try:
            # Open camera through manager
            camera = manager.open(f"Basler:{camera_name}")
            assert camera is not None
            assert camera.is_connected
            
            # Basic operations
            image = camera.capture()
            assert image is not None
            assert isinstance(image, np.ndarray)
            
            # Configuration
            success = camera.set_exposure(20000)
            assert isinstance(success, bool)
            
        finally:
            manager.close()

    @pytest.mark.asyncio 
    async def test_hardware_with_async_manager(self, camera_name):
        """Test using real Basler camera through async camera manager."""
        from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager
        
        manager = AsyncCameraManager(include_mocks=False)
        try:
            # Open camera through manager
            camera = await manager.open(f"Basler:{camera_name}")
            assert camera is not None
            assert camera.is_connected
            
            # Basic operations
            image = await camera.capture()
            assert image is not None
            assert isinstance(image, np.ndarray)
            
            # Configuration
            success = await camera.set_exposure(20000)
            assert isinstance(success, bool)
            
        finally:
            await manager.close(None)


class TestHardwareErrorHandling:
    """Test error handling with real hardware."""
    
    @pytest.mark.asyncio
    async def test_hardware_invalid_exposure_handling(self, basler_camera):
        """Test handling of invalid exposure values."""
        from mindtrace.hardware.core.exceptions import CameraConfigurationError
        
        # Get valid range
        exp_range = await basler_camera.get_exposure_range()
        min_exp, max_exp = exp_range
        
        # Test exposure too high
        with pytest.raises(CameraConfigurationError):
            await basler_camera.set_exposure(max_exp * 2)
        
        # Test negative exposure
        with pytest.raises(CameraConfigurationError):
            await basler_camera.set_exposure(-1000)

    @pytest.mark.asyncio
    async def test_hardware_invalid_roi_handling(self, basler_camera):
        """Test handling of invalid ROI values."""
        from mindtrace.hardware.core.exceptions import CameraConfigurationError
        
        # Get current ROI to know valid bounds
        current_roi = await basler_camera.get_ROI()
        max_width = current_roi["width"]
        max_height = current_roi["height"]
        
        # Test ROI too large
        with pytest.raises(CameraConfigurationError):
            await basler_camera.set_ROI(0, 0, max_width * 2, max_height * 2)
        
        # Test negative coordinates
        with pytest.raises(CameraConfigurationError):
            await basler_camera.set_ROI(-100, -100, 100, 100)

    @pytest.mark.asyncio
    async def test_hardware_operations_on_closed_camera(self, camera_name):
        """Test that operations fail gracefully on closed camera."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConnectionError
        
        camera = BaslerCameraBackend(camera_name)
        success, _, _ = await camera.initialize()
        assert success is True
        
        # Close the camera
        await camera.close()
        
        # Operations should fail
        with pytest.raises(CameraConnectionError):
            await camera.capture()
        
        with pytest.raises(CameraConnectionError):
            await camera.set_exposure(20000) 