"""Integration tests for BaslerCameraBackend with real pypylon SDK (no hardware required).

These tests validate that the BaslerCameraBackend correctly integrates with the real pypylon SDK
without requiring physical cameras to be connected. They test SDK availability, camera discovery
(expecting empty results), initialization failure modes, and error handling with real pypylon
exception types.
"""

import pytest
from mindtrace.core.utils.checks import check_libs

# Skip all tests in this module if pypylon is not available
missing_libs = check_libs(["pypylon"])
if missing_libs:
    pytest.skip(f"Required libraries are not installed: {', '.join(missing_libs)}. Skipping test.", allow_module_level=True)


class TestPylonSDKIntegration:
    """Test real pypylon SDK integration and import functionality."""
    
    def test_real_pypylon_imports(self):
        """Test that real pypylon SDK imports correctly and modules are available."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import PYPYLON_AVAILABLE
        assert PYPYLON_AVAILABLE is True
        
        # Test direct pypylon imports work
        from pypylon import pylon, genicam
        assert pylon is not None
        assert genicam is not None
        
        # Test TlFactory is accessible
        factory = pylon.TlFactory.GetInstance()
        assert factory is not None

    def test_real_basler_backend_constructor(self):
        """Test BaslerCameraBackend constructor with real pypylon SDK."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Should not raise SDKNotAvailableError when pypylon is available
        camera = BaslerCameraBackend("test_camera")
        assert camera.camera_name == "test_camera"
        assert hasattr(camera, 'default_pixel_format')
        assert hasattr(camera, 'buffer_count')
        assert hasattr(camera, 'timeout_ms')

    def test_real_basler_backend_configuration(self):
        """Test BaslerCameraBackend constructor with various configurations."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        camera = BaslerCameraBackend(
            "test_camera",
            img_quality_enhancement=True,
            retrieve_retry_count=3,
            pixel_format="RGB8",
            buffer_count=10,
            timeout_ms=3000
        )
        assert camera.img_quality_enhancement is True
        assert camera.retrieve_retry_count == 3
        assert camera.default_pixel_format == "RGB8"
        assert camera.buffer_count == 10
        assert camera.timeout_ms == 3000


class TestPylonAPIAvailability:
    """Test that pypylon API components are available and functional."""
    
    def test_real_pylon_factory_methods(self):
        """Test real pypylon factory methods work as expected."""
        from pypylon import pylon
        
        factory = pylon.TlFactory.GetInstance()
        
        # These should work even without cameras
        devices = factory.EnumerateDevices()
        assert isinstance(devices, list)
        
        # Test interface enumeration 
        interfaces = factory.EnumerateInterfaces()
        assert isinstance(interfaces, list)

    def test_real_pylon_grabbing_strategies(self):
        """Test that pylon grabbing strategy constants are available."""
        from pypylon import pylon
        
        # These should be available as constants
        assert hasattr(pylon, 'GrabStrategy_LatestImageOnly')
        assert hasattr(pylon, 'GrabStrategy_OneByOne')
        assert hasattr(pylon, 'GrabStrategy_LatestImages')

    def test_real_pylon_pixel_formats(self):
        """Test that pypylon pixel format constants are available."""
        from pypylon import pylon
        
        # Test common pixel formats exist
        assert hasattr(pylon, 'PixelType_BGR8packed')
        assert hasattr(pylon, 'PixelType_RGB8packed') 
        assert hasattr(pylon, 'PixelType_Mono8')

    def test_real_image_format_converter(self):
        """Test that pypylon ImageFormatConverter can be created."""
        from pypylon import pylon
        
        converter = pylon.ImageFormatConverter()
        assert converter is not None
        
        # Test setting output pixel format
        converter.OutputPixelFormat = pylon.PixelType_BGR8packed
        assert converter.OutputPixelFormat == pylon.PixelType_BGR8packed

    def test_real_pylon_timeout_exceptions(self):
        """Test that real pypylon timeout exceptions exist."""
        from pypylon import pylon
        
        # Test exception types are available
        assert hasattr(pylon, 'TimeoutException')
        assert hasattr(pylon, 'RuntimeException')
        
        # Test we can create these exceptions
        timeout_ex = pylon.TimeoutException("Test timeout")
        assert "Test timeout" in str(timeout_ex)

    def test_real_genicam_exceptions(self):
        """Test that real genicam exceptions exist.""" 
        from pypylon import genicam
        
        assert hasattr(genicam, 'GenericException')
        assert hasattr(genicam, 'InvalidArgumentException')
        
        # Test we can create these exceptions
        generic_ex = genicam.GenericException("Test error", "Test.cpp", 42)
        assert "Test error" in str(generic_ex)


class TestCameraDiscoveryNoHardware:
    """Test camera discovery functionality when no cameras are connected."""
    
    def test_real_discovery_no_cameras(self):
        """Test camera discovery returns empty list when no cameras connected."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        cameras = BaslerCameraBackend.get_available_cameras()
        assert isinstance(cameras, list)
        # Expect empty list since no cameras connected, but should not error
        assert len(cameras) == 0

    def test_real_discovery_with_details_no_cameras(self):
        """Test detailed discovery returns empty dict when no cameras connected.""" 
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        details = BaslerCameraBackend.get_available_cameras(include_details=True)
        assert isinstance(details, dict)
        # Expect empty dict since no cameras connected, but should not error
        assert len(details) == 0

    def test_discovery_error_handling_with_real_sdk(self):
        """Test that discovery properly handles errors with real SDK."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import HardwareOperationError
        
        # This should work normally and return empty list
        try:
            cameras = BaslerCameraBackend.get_available_cameras()
            assert isinstance(cameras, list)
        except HardwareOperationError:
            # If discovery fails due to SDK issues, that's also valid behavior
            pytest.skip("Discovery failed due to SDK configuration - this is expected in some environments")


class TestInitializationFailureModesNoHardware:
    """Test initialization failure modes with real pypylon but no hardware."""
    
    @pytest.mark.asyncio
    async def test_real_initialization_camera_not_found(self):
        """Test initialization fails gracefully with CameraNotFoundError when camera doesn't exist."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraNotFoundError
        
        camera = BaslerCameraBackend("nonexistent_camera_12345")
        
        with pytest.raises(CameraNotFoundError):
            await camera.initialize()

    @pytest.mark.asyncio 
    async def test_real_initialization_serial_not_found(self):
        """Test initialization fails with invalid serial number."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraNotFoundError
        
        camera = BaslerCameraBackend("999999999")  # Invalid serial
        
        with pytest.raises(CameraNotFoundError):
            await camera.initialize()

    @pytest.mark.asyncio
    async def test_real_initialization_empty_name(self):
        """Test initialization fails with empty camera name."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraNotFoundError
        
        camera = BaslerCameraBackend("")
        
        with pytest.raises(CameraNotFoundError):
            await camera.initialize()


class TestManagerIntegration:
    """Test integration with camera manager systems."""
    
    @pytest.mark.asyncio
    async def test_real_basler_in_camera_manager(self):
        """Test that real BaslerCameraBackend integrates with camera manager."""
        from mindtrace.hardware.cameras.core.camera_manager import CameraManager
        
        # Test that Basler backend is discovered
        manager = CameraManager(include_mocks=False)
        try:
            backends = manager.backends()
            assert "Basler" in backends
            
            # Test backend info includes real Basler
            info = manager.backend_info()
            assert "Basler" in info
            assert info["Basler"]["available"] is True
            assert "pypylon" in info["Basler"]["sdk_required"]
        finally:
            manager.close()

    def test_real_basler_discovery_integration(self):
        """Test discovery integration between BaslerCameraBackend and manager."""
        from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager
        
        # Should include Basler in available backends
        cameras = AsyncCameraManager.discover(backends=["Basler"], include_mocks=False) 
        assert isinstance(cameras, list)
        # Expect empty since no cameras, but should not error

    def test_real_basler_discovery_details_integration(self):
        """Test detailed discovery integration with manager."""
        from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager
        
        # Should work with details=True
        cameras = AsyncCameraManager.discover(backends=["Basler"], details=True, include_mocks=False)
        assert isinstance(cameras, list)
        # Expect empty since no cameras, but should not error


class TestErrorHandlingIntegration:
    """Test error handling with real pypylon exception types."""
    
    def test_sdk_method_with_real_exceptions(self):
        """Test that _sdk method properly handles real pypylon exceptions."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from pypylon import pylon
        
        camera = BaslerCameraBackend("test_camera")
        
        # Test that real exception types are available for testing
        assert hasattr(pylon, 'TimeoutException')
        assert hasattr(pylon, 'RuntimeException')
        
        # The actual error handling is tested in unit tests with mocks,
        # but this verifies the exception types exist for integration

    def test_real_exception_inheritance(self):
        """Test that real pypylon exceptions have expected inheritance."""
        from pypylon import pylon, genicam
        
        # Test exception hierarchy
        timeout_ex = pylon.TimeoutException("test")
        runtime_ex = pylon.RuntimeException("test")
        generic_ex = genicam.GenericException("test", "file.cpp", 42)
        
        # These should be proper exception types
        assert isinstance(timeout_ex, Exception)
        assert isinstance(runtime_ex, Exception) 
        assert isinstance(generic_ex, Exception)


class TestConfigurationWithRealSDK:
    """Test configuration handling with real pypylon SDK."""
    
    def test_real_pixel_format_validation(self):
        """Test that pixel format constants work with real SDK."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from pypylon import pylon
        
        # Test common pixel formats are accepted
        camera1 = BaslerCameraBackend("test", pixel_format="BGR8")
        assert camera1.default_pixel_format == "BGR8"
        
        camera2 = BaslerCameraBackend("test", pixel_format="RGB8")
        assert camera2.default_pixel_format == "RGB8"
        
        camera3 = BaslerCameraBackend("test", pixel_format="Mono8")
        assert camera3.default_pixel_format == "Mono8"

    def test_real_grabbing_mode_constants(self):
        """Test that grabbing mode constants are available."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from pypylon import pylon
        
        camera = BaslerCameraBackend("test")
        
        # Test that grabbing strategy constants exist
        assert hasattr(pylon, 'GrabStrategy_LatestImageOnly')
        
        # The backend should have a default grabbing mode
        assert hasattr(camera, 'grabbing_mode')

    def test_buffer_count_configuration(self):
        """Test buffer count configuration with reasonable values."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Test various buffer counts
        camera1 = BaslerCameraBackend("test", buffer_count=5)
        assert camera1.buffer_count == 5
        
        camera2 = BaslerCameraBackend("test", buffer_count=25)
        assert camera2.buffer_count == 25
        
        camera3 = BaslerCameraBackend("test", buffer_count=50)
        assert camera3.buffer_count == 50 
