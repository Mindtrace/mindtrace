"""Integration tests for BaslerCameraBackend with real pypylon SDK (no hardware required).

These tests validate that the BaslerCameraBackend correctly integrates with the real pypylon SDK without requiring 
physical cameras to be connected. They test SDK availability, camera discovery (expecting empty results), 
initialization failure modes, and error handling with real pypylon exception types.
"""

import os

import pytest

from tests.utils.pypylon.client import get_pypylon_proxy, is_pypylon_available, PyPylonClientError

# Note: Service availability will be checked at test time via TCP connection


@pytest.fixture
def pypylon_proxy():
    """Fixture providing pypylon proxy (Docker service only)."""
    import time
    import os
    
    # Quick availability check via TCP connection
    
    # Try to connect with a short timeout
    max_wait = 5  # seconds (much shorter than before)
    wait_interval = 0.5  # second
    
    for _ in range(max_wait * 2):  # 0.5s intervals for 5 seconds = 10 attempts
        if is_pypylon_available():
            return get_pypylon_proxy()
        time.sleep(wait_interval)
    
    # If we get here, service is not responding
    pytest.skip("Pypylon service not responding within 5 seconds. Check Docker service status.")


class TestPyPylonProxySystem:
    """Test the pypylon proxy system itself."""
    
    def test_proxy_backend_detection(self, pypylon_proxy):
        """Test that proxy correctly detects its backend type."""
        backend_type = pypylon_proxy.get_backend_type()
        assert backend_type == 'service'  # Always Docker service, never local
        
        # Verify proxy is available
        assert pypylon_proxy.is_available() is True
    
    def test_proxy_basic_functionality(self, pypylon_proxy):
        """Test basic proxy functionality works."""
        # Import test should work
        result = pypylon_proxy.import_test()
        assert result['success'] is True
        
        # Device enumeration should work (may be empty)
        device_result = pypylon_proxy.enumerate_devices()
        assert isinstance(device_result, dict)
        assert 'devices' in device_result
        
        # Factory should be accessible
        factory_available = pypylon_proxy.get_factory()
        assert factory_available is True


class TestPylonSDKIntegration:
    """Test real pypylon SDK integration and import functionality."""
    
    def test_real_pypylon_imports(self, pypylon_proxy):
        """Test that pypylon SDK imports correctly and modules are available."""
        # Test import functionality through proxy
        result = pypylon_proxy.import_test()
        assert result['success'] is True
        assert result['pylon_available'] is True
        assert result['genicam_available'] is True
        assert result['factory_available'] is True
        
        # Test that we can get the factory
        factory_available = pypylon_proxy.get_factory()
        assert factory_available is True

    def test_real_basler_backend_constructor(self):
        """Test BaslerCameraBackend constructor with real pypylon SDK."""
        try:
            from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
            
            # Should not raise SDKNotAvailableError when pypylon is available
            camera = BaslerCameraBackend("test_camera")
            assert camera.camera_name == "test_camera"
            assert hasattr(camera, 'default_pixel_format')
            assert hasattr(camera, 'buffer_count')
            assert hasattr(camera, 'timeout_ms')
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise

    def test_real_basler_backend_configuration(self):
        """Test BaslerCameraBackend constructor with various configurations."""
        try:
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
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise


class TestPylonAPIAvailability:
    """Test that pypylon API components are available and functional."""
    
    def test_real_pylon_factory_methods(self, pypylon_proxy):
        """Test real pypylon factory methods work as expected."""
        # Test device enumeration (should work even without cameras)
        device_result = pypylon_proxy.enumerate_devices()
        assert isinstance(device_result, dict)
        assert 'device_count' in device_result
        assert 'devices' in device_result
        assert 'hardware_available' in device_result
        assert isinstance(device_result['devices'], list)
        
        # Test interface enumeration 
        interfaces = pypylon_proxy.enumerate_interfaces()
        assert isinstance(interfaces, list)

    def test_real_pylon_grabbing_strategies(self, pypylon_proxy):
        """Test that pylon grabbing strategy constants are available."""
        strategies = pypylon_proxy.get_grabbing_strategies()
        assert isinstance(strategies, dict)
        
        # These should be available as constants
        assert 'GrabStrategy_LatestImageOnly' in strategies
        assert 'GrabStrategy_OneByOne' in strategies
        assert 'GrabStrategy_LatestImages' in strategies

    def test_real_pylon_pixel_formats(self, pypylon_proxy):
        """Test that pypylon pixel format constants are available."""
        formats = pypylon_proxy.get_pixel_formats()
        assert isinstance(formats, dict)
        
        # Test common pixel formats exist
        assert 'PixelType_BGR8packed' in formats
        assert 'PixelType_RGB8packed' in formats
        assert 'PixelType_Mono8' in formats

    def test_real_image_format_converter(self, pypylon_proxy):
        """Test that pypylon ImageFormatConverter can be created."""
        result = pypylon_proxy.create_converter()
        assert result['converter_created'] is True
        assert result['pixel_format_set'] is True

    def test_real_pylon_timeout_exceptions(self, pypylon_proxy):
        """Test that real pypylon timeout exceptions exist."""
        exceptions = pypylon_proxy.test_exceptions()
        assert isinstance(exceptions, dict)
        
        # Test exception types are available
        assert 'pylon.TimeoutException' in exceptions
        assert 'pylon.RuntimeException' in exceptions
        
        # Test they are creatable
        timeout_info = exceptions['pylon.TimeoutException']
        assert timeout_info['available'] is True
        assert timeout_info['creatable'] is True
        assert "Test exception" in timeout_info['message']

    def test_real_genicam_exceptions(self, pypylon_proxy):
        """Test that real genicam exceptions exist.""" 
        exceptions = pypylon_proxy.test_exceptions()
        assert isinstance(exceptions, dict)
        
        assert 'genicam.GenericException' in exceptions
        assert 'genicam.InvalidArgumentException' in exceptions
        
        # Test they are creatable
        generic_info = exceptions['genicam.GenericException']
        assert generic_info['available'] is True
        assert generic_info['creatable'] is True
        assert "Test error" in generic_info['message']


class TestCameraDiscoveryNoHardware:
    """Test camera discovery functionality when no cameras are connected."""
    
    def test_real_discovery_no_cameras(self, pypylon_proxy):
        """Test camera discovery returns empty results when no cameras connected."""
        # Test through proxy first
        device_result = pypylon_proxy.enumerate_devices()
        assert isinstance(device_result, dict)
        assert device_result['device_count'] >= 0  # May be 0 (no cameras) or more (cameras present)
        assert isinstance(device_result['devices'], list)
        
        # Also test the BaslerCameraBackend directly
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        cameras = BaslerCameraBackend.get_available_cameras()
        assert isinstance(cameras, list)
        # May be empty (no cameras) or contain cameras if hardware is present

    def test_real_discovery_with_details_no_cameras(self, pypylon_proxy):
        """Test detailed discovery works regardless of camera presence.""" 
        # Test through proxy first
        device_result = pypylon_proxy.enumerate_devices()
        devices = device_result['devices']
        
        for device in devices:
            # Verify device info structure (regardless if cameras are present)
            expected_fields = ['serial_number', 'model_name', 'vendor_name', 
                             'device_class', 'friendly_name', 'user_defined_name',
                             'interface', 'ip_address', 'mac_address']
            for field in expected_fields:
                assert field in device
        
        # Also test the BaslerCameraBackend directly
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        details = BaslerCameraBackend.get_available_cameras(include_details=True)
        assert isinstance(details, dict)

    def test_discovery_error_handling_with_real_sdk(self):
        """Test that discovery properly handles errors with real SDK."""
        try:
            from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
            from mindtrace.hardware.core.exceptions import HardwareOperationError
            
            # This should work normally and return empty list
            try:
                cameras = BaslerCameraBackend.get_available_cameras()
                assert isinstance(cameras, list)
            except HardwareOperationError:
                # If discovery fails due to SDK issues, that's also valid behavior
                pytest.skip("Discovery failed due to SDK configuration - this is expected in some environments")
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise


class TestInitializationFailureModesNoHardware:
    """Test initialization failure modes with real pypylon but no hardware."""
    
    @pytest.mark.asyncio
    async def test_real_initialization_camera_not_found(self):
        """Test initialization fails gracefully with CameraNotFoundError when camera doesn't exist."""
        try:
            from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
            from mindtrace.hardware.core.exceptions import CameraNotFoundError
            
            camera = BaslerCameraBackend("nonexistent_camera_12345")
            
            with pytest.raises(CameraNotFoundError):
                await camera.initialize()
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise

    @pytest.mark.asyncio 
    async def test_real_initialization_serial_not_found(self):
        """Test initialization fails with invalid serial number."""
        try:
            from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
            from mindtrace.hardware.core.exceptions import CameraNotFoundError
            
            camera = BaslerCameraBackend("999999999")  # Invalid serial
            
            with pytest.raises(CameraNotFoundError):
                await camera.initialize()
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise

    @pytest.mark.asyncio
    async def test_real_initialization_empty_name(self):
        """Test initialization fails with empty camera name."""
        try:
            from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
            from mindtrace.hardware.core.exceptions import CameraNotFoundError
            
            camera = BaslerCameraBackend("")
            
            with pytest.raises(CameraNotFoundError):
                await camera.initialize()
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise


class TestManagerIntegration:
    """Test integration with camera manager systems."""
    
    @pytest.mark.asyncio
    async def test_real_basler_in_camera_manager(self):
        """Test that real BaslerCameraBackend integrates with camera manager."""
        try:
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
                # sdk_required changed from list to boolean
                assert info["Basler"]["sdk_required"] is True
            finally:
                manager.close()
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise

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
        try:
            from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
            from pypylon import pylon
            
            camera = BaslerCameraBackend("test_camera")
            
            # Test that real exception types are available for testing
            assert hasattr(pylon, 'TimeoutException')
            assert hasattr(pylon, 'RuntimeException')
            
            # The actual error handling is tested in unit tests with mocks,
            # but this verifies the exception types exist for integration
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise

    def test_real_exception_inheritance(self):
        """Test that real pypylon exceptions have expected inheritance."""
        try:
            from pypylon import pylon, genicam
            
            # Test exception hierarchy
            timeout_ex = pylon.TimeoutException("test")
            runtime_ex = pylon.RuntimeException("test")
            generic_ex = genicam.GenericException("test", "file.cpp", 42)
            
            # These should be proper exception types
            assert isinstance(timeout_ex, Exception)
            assert isinstance(runtime_ex, Exception) 
            assert isinstance(generic_ex, Exception)
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise


class TestConfigurationWithRealSDK:
    """Test configuration handling with real pypylon SDK."""
    
    def test_real_pixel_format_validation(self):
        """Test that pixel format constants work with real SDK."""
        try:
            from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
            from pypylon import pylon
            
            # Test common pixel formats are accepted
            camera1 = BaslerCameraBackend("test", pixel_format="BGR8")
            assert camera1.default_pixel_format == "BGR8"
            
            camera2 = BaslerCameraBackend("test", pixel_format="RGB8")
            assert camera2.default_pixel_format == "RGB8"
            
            camera3 = BaslerCameraBackend("test", pixel_format="Mono8")
            assert camera3.default_pixel_format == "Mono8"
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise

    def test_real_grabbing_mode_constants(self):
        """Test that grabbing mode constants are available."""
        try:
            from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
            from pypylon import pylon
            
            camera = BaslerCameraBackend("test")
            
            # Test that grabbing strategy constants exist
            assert hasattr(pylon, 'GrabStrategy_LatestImageOnly')
            
            # The backend should have a default grabbing mode
            assert hasattr(camera, 'grabbing_mode')
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise

    def test_buffer_count_configuration(self):
        """Test buffer count configuration with reasonable values."""
        try:
            from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
            
            # Test various buffer counts
            camera1 = BaslerCameraBackend("test", buffer_count=5)
            assert camera1.buffer_count == 5
            
            camera2 = BaslerCameraBackend("test", buffer_count=25)
            assert camera2.buffer_count == 25
            
            camera3 = BaslerCameraBackend("test", buffer_count=50)
            assert camera3.buffer_count == 50
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise 
