"""Integration tests for BaslerCameraBackend with real pypylon SDK (no hardware required).

These tests validate that the BaslerCameraBackend correctly integrates with the real pypylon SDK without requiring
physical cameras to be connected. They test SDK availability, camera discovery (expecting empty results),
initialization failure modes, and error handling with real pypylon exception types.
"""

import pytest

from mindtrace.core import check_libs
from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend


class TestBaslerSDKIntegration:
    """Test real pypylon SDK integration with BaslerCameraBackend."""

    def test_real_basler_backend_constructor(self):
        """Test BaslerCameraBackend constructor with real pypylon SDK."""
        missing_libs = check_libs(["pypylon"])
        if missing_libs:
            pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

        try:
            # Should not raise SDKNotAvailableError when pypylon is available
            camera = BaslerCameraBackend("test_camera")
            assert camera.camera_name == "test_camera"
            assert hasattr(camera, "default_pixel_format")
            assert hasattr(camera, "buffer_count")
            assert hasattr(camera, "timeout_ms")
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise

    def test_real_basler_backend_configuration(self):
        """Test BaslerCameraBackend constructor with various configurations."""
        missing_libs = check_libs(["pypylon"])
        if missing_libs:
            pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

        try:
            camera = BaslerCameraBackend(
                "test_camera",
                img_quality_enhancement=True,
                retrieve_retry_count=3,
                pixel_format="RGB8",
                buffer_count=10,
                timeout_ms=3000,
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

    def test_pypylon_basic_imports(self):
        """Test that pypylon SDK can be imported and basic modules are available."""
        missing_libs = check_libs(["pypylon"])
        if missing_libs:
            pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

        try:
            from pypylon import genicam, pylon
            
            # Test that basic classes are available
            assert hasattr(pylon, 'TlFactory')
            assert hasattr(pylon, 'InstantCamera')
            assert hasattr(pylon, 'TimeoutException')
            assert hasattr(pylon, 'RuntimeException')
            assert hasattr(genicam, 'GenericException')
            
            # Test that factory can be created
            factory = pylon.TlFactory.GetInstance()
            assert factory is not None
            
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise

    def test_pypylon_device_enumeration(self):
        """Test that pypylon can enumerate devices (should work even without cameras)."""
        missing_libs = check_libs(["pypylon"])
        if missing_libs:
            pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

        try:
            from pypylon import pylon
            
            # Get factory and enumerate devices
            factory = pylon.TlFactory.GetInstance()
            devices = factory.EnumerateDevices()
            
            # Should return an iterable container (may be empty if no cameras connected)
            # pypylon returns a SWIG-generated container, not necessarily a Python list
            assert hasattr(devices, '__iter__'), f"Expected iterable, got {type(devices)}"
            assert hasattr(devices, '__len__'), f"Expected container with length, got {type(devices)}"
            
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise

    def test_basler_discovery_integration(self):
        """Test that BaslerCameraBackend discovery works with real SDK."""
        missing_libs = check_libs(["pypylon"])
        if missing_libs:
            pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

        try:
            # Test discovery (should work even without cameras)
            cameras = BaslerCameraBackend.get_available_cameras()
            assert isinstance(cameras, list)
            
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise


class TestInitializationFailureModesNoHardware:
    """Test initialization failure modes with real pypylon but no hardware."""

    @pytest.mark.asyncio
    async def test_real_initialization_camera_not_found(self):
        """Test initialization fails gracefully with CameraNotFoundError when camera doesn't exist."""
        missing_libs = check_libs(["pypylon"])
        if missing_libs:
            pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

        try:
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
        missing_libs = check_libs(["pypylon"])
        if missing_libs:
            pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

        try:
            from mindtrace.hardware.core.exceptions import CameraNotFoundError

            camera = BaslerCameraBackend("test_camera", serial_number="invalid_serial_123456")

            with pytest.raises(CameraNotFoundError):
                await camera.initialize()
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise

    @pytest.mark.asyncio
    async def test_real_initialization_empty_name(self):
        """Test initialization fails with empty camera name."""
        missing_libs = check_libs(["pypylon"])
        if missing_libs:
            pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

        try:
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
        missing_libs = check_libs(["pypylon"])
        if missing_libs:
            pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

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
        missing_libs = check_libs(["pypylon"])
        if missing_libs:
            pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

        from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager

        # Should include Basler in available backends
        cameras = AsyncCameraManager.discover(backends=["Basler"], include_mocks=False)
        assert isinstance(cameras, list)

    def test_real_basler_discovery_details_integration(self):
        """Test detailed discovery integration with manager."""
        missing_libs = check_libs(["pypylon"])
        if missing_libs:
            pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

        from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager

        # Should work with details=True
        cameras = AsyncCameraManager.discover(backends=["Basler"], details=True, include_mocks=False)
        assert isinstance(cameras, list)


class TestErrorHandlingIntegration:
    """Test error handling with real pypylon exception types."""

    def test_sdk_method_with_real_exceptions(self):
        """Test that _sdk method properly handles real pypylon exceptions."""
        missing_libs = check_libs(["pypylon"])
        if missing_libs:
            pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

        try:
            from pypylon import pylon

            _ = BaslerCameraBackend("test_camera")

            # Test that real exception types are available for testing
            assert hasattr(pylon, "TimeoutException")
            assert hasattr(pylon, "RuntimeException")

            # The actual error handling is tested in unit tests with mocks,
            # but this verifies the exception types exist for integration
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise

    def test_real_exception_inheritance(self):
        """Test that real pypylon exceptions have expected inheritance."""
        missing_libs = check_libs(["pypylon"])
        if missing_libs:
            pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

        try:
            from pypylon import genicam, pylon

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
        missing_libs = check_libs(["pypylon"])
        if missing_libs:
            pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

        try:
            # Test common pixel formats are accepted
            camera1 = BaslerCameraBackend("test", pixel_format="RGB8")
            assert camera1.default_pixel_format == "RGB8"

            camera2 = BaslerCameraBackend("test", pixel_format="BGR8")
            assert camera2.default_pixel_format == "BGR8"

            camera3 = BaslerCameraBackend("test", pixel_format="Mono8")
            assert camera3.default_pixel_format == "Mono8"
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise

    def test_real_grabbing_mode_constants(self):
        """Test that grabbing mode constants are available."""
        missing_libs = check_libs(["pypylon"])
        if missing_libs:
            pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

        try:
            from pypylon import pylon

            camera = BaslerCameraBackend("test")

            # Test that grabbing strategy constants exist
            assert hasattr(pylon, "GrabStrategy_LatestImageOnly")

            # The backend should have a default grabbing mode
            assert hasattr(camera, "grabbing_mode")
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise

    def test_buffer_count_configuration(self):
        """Test buffer count configuration with reasonable values."""
        missing_libs = check_libs(["pypylon"])
        if missing_libs:
            pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

        try:
            # Test various buffer counts
            camera1 = BaslerCameraBackend("test", buffer_count=5)
            assert camera1.buffer_count == 5

            camera2 = BaslerCameraBackend("test", buffer_count=20)
            assert camera2.buffer_count == 20

            # Test default buffer count
            camera3 = BaslerCameraBackend("test")
            assert isinstance(camera3.buffer_count, int)
            assert camera3.buffer_count > 0
        except Exception as e:
            if "SDKNotAvailableError" in str(type(e)) or "SDK 'pypylon' is not available" in str(e):
                pytest.skip(f"Pypylon SDK not available: {e}")
            raise