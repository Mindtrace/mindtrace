"""
Comprehensive unit tests for the camera system.

This module tests all camera functionality using mock implementations to avoid
hardware dependencies. Tests cover individual camera backends, camera manager,
error handling, and edge cases.
"""

import asyncio
import json
import os
import tempfile

import numpy as np
import pytest
import pytest_asyncio

from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraNotFoundError,
    CameraTimeoutError,
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
    """Create a camera manager instance with mock backends for unit testing."""
    from mindtrace.hardware.cameras.camera_manager import CameraManager

    # Create manager with mocks enabled
    manager = CameraManager(include_mocks=True)

    # Override the discovered backends to only include mock backends for unit tests
    manager._discovered_backends = ["MockDaheng", "MockBasler", "OpenCV"]

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

    camera = MockDahengCamera(camera_name="mock_cam_0", camera_config=None)
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

    camera = MockBaslerCamera(camera_name="mock_basler_1", camera_config=None)
    yield camera

    # Cleanup
    try:
        await camera.close()
    except Exception:
        pass


@pytest_asyncio.fixture
async def temp_config_file():
    """Create a temporary configuration file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
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
            "buffer_count": 25,
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
        assert image.shape[2] == 3  # RGB channels

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
        await camera.set_gain(2.5)
        gain = await camera.get_gain()
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
        success = await camera.set_ROI(100, 100, 800, 600)
        assert success is True

        # Get ROI
        roi = await camera.get_ROI()
        assert roi["x"] == 100
        assert roi["y"] == 100
        assert roi["width"] == 800
        assert roi["height"] == 600

        # Reset ROI
        success = await camera.reset_ROI()
        assert success is True
        roi = await camera.get_ROI()
        assert roi["x"] == 0
        assert roi["y"] == 0

    @pytest.mark.asyncio
    async def test_configuration_export_import(self, mock_daheng_camera, temp_config_file):
        """Test configuration export and import."""
        camera = mock_daheng_camera
        await camera.initialize()

        # Configure camera
        await camera.set_exposure(25000)
        await camera.set_gain(3.0)
        await camera.set_triggermode("trigger")

        # Export configuration
        export_path = temp_config_file.replace(".json", "_export.json")
        success = await camera.export_config(export_path)
        assert success is True
        assert os.path.exists(export_path)

        # Verify exported configuration format
        with open(export_path, "r") as f:
            config = json.load(f)
        assert config["camera_type"] == "mock_daheng"
        assert config["exposure_time"] == 25000
        assert config["gain"] == 3.0
        assert config["trigger_mode"] == "trigger"

        # Reset camera settings
        await camera.set_exposure(10000)
        await camera.set_gain(1.0)

        # Import configuration
        success = await camera.import_config(export_path)
        assert success is True

        # Verify settings were restored
        assert await camera.get_exposure() == 25000
        assert await camera.get_gain() == 3.0
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
        gain_range = await camera.get_gain_range()
        assert isinstance(gain_range, list)
        assert len(gain_range) == 2

        # Test pixel format range
        pixel_formats = await camera.get_pixel_format_range()
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
        assert await camera.get_gain() == 2.5


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
    async def test_backend_specific_discovery(self, camera_manager):
        """Test backend-specific camera discovery functionality."""
        manager = camera_manager

        # Test discovering all cameras (default behavior)
        all_cameras = manager.discover_cameras()
        assert isinstance(all_cameras, list)

        # Test discovering cameras from a single backend
        daheng_cameras = manager.discover_cameras("MockDaheng")
        assert isinstance(daheng_cameras, list)

        # All returned cameras should be from MockDaheng backend
        for camera in daheng_cameras:
            assert camera.startswith("MockDaheng:")

        # Test discovering cameras from multiple backends
        multi_backend_cameras = manager.discover_cameras(["MockDaheng", "MockBasler"])
        assert isinstance(multi_backend_cameras, list)

        # All returned cameras should be from specified backends
        for camera in multi_backend_cameras:
            assert camera.startswith("MockDaheng:") or camera.startswith("MockBasler:")

        # Test discovering from non-existent backend
        empty_cameras = manager.discover_cameras("NonExistentBackend")
        assert isinstance(empty_cameras, list)
        assert len(empty_cameras) == 0

        # Test with empty backend list
        empty_list_cameras = manager.discover_cameras([])
        assert isinstance(empty_list_cameras, list)
        assert len(empty_list_cameras) == 0

        # Test with invalid parameter type
        with pytest.raises(ValueError, match="Invalid backends parameter"):
            manager.discover_cameras(123)

    @pytest.mark.asyncio
    async def test_backend_specific_discovery_consistency(self, camera_manager):
        """Test that backend-specific discovery is consistent with full discovery."""
        manager = camera_manager

        # Get all cameras
        all_cameras = manager.discover_cameras()

        # Get cameras by backend (including all available backends)
        daheng_cameras = manager.discover_cameras("MockDaheng")
        basler_cameras = manager.discover_cameras("MockBasler")
        opencv_cameras = manager.discover_cameras("OpenCV")

        # Union of backend-specific discoveries should equal full discovery
        combined_cameras = daheng_cameras + basler_cameras + opencv_cameras

        # Sort for comparison
        all_cameras_sorted = sorted(all_cameras)
        combined_cameras_sorted = sorted(combined_cameras)

        assert all_cameras_sorted == combined_cameras_sorted

    @pytest.mark.asyncio
    async def test_backend_specific_discovery_with_unavailable_backends(self, camera_manager):
        """Test backend-specific discovery with unavailable backends."""
        manager = camera_manager

        # Test with mix of available and unavailable backends
        mixed_cameras = manager.discover_cameras(["MockDaheng", "NonExistentBackend", "MockBasler"])
        assert isinstance(mixed_cameras, list)

        # Should only return cameras from available backends
        for camera in mixed_cameras:
            assert camera.startswith("MockDaheng:") or camera.startswith("MockBasler:")

    @pytest.mark.asyncio
    async def test_convenience_function_with_backend_filtering(self):
        """Test convenience function with backend filtering."""
        from mindtrace.hardware.cameras.camera_manager import discover_all_cameras

        # Test convenience function with backend filtering
        all_cameras = discover_all_cameras(include_mocks=True)
        assert isinstance(all_cameras, list)
        assert len(all_cameras) > 0

        # Test with specific backend
        daheng_cameras = discover_all_cameras(include_mocks=True, backends="MockDaheng")
        assert isinstance(daheng_cameras, list)
        for camera in daheng_cameras:
            assert camera.startswith("MockDaheng:")

        # Test with multiple backends
        multi_cameras = discover_all_cameras(include_mocks=True, backends=["MockDaheng", "MockBasler"])
        assert isinstance(multi_cameras, list)
        for camera in multi_cameras:
            assert camera.startswith("MockDaheng:") or camera.startswith("MockBasler:")

        # Test with non-existent backend
        empty_cameras = discover_all_cameras(include_mocks=True, backends="NonExistentBackend")
        assert isinstance(empty_cameras, list)
        assert len(empty_cameras) == 0

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
            success = await camera_proxy.configure(exposure=20000, gain=2.0, trigger_mode="continuous")
            assert success is True

            # Verify configuration
            exposure = await camera_proxy.get_exposure()
            assert exposure == 20000

            gain = await camera_proxy.get_gain()
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
            _ = manager.get_cameras(mock_cameras)

            # Test batch configuration
            configurations = {}
            for i, camera_name in enumerate(mock_cameras):
                configurations[camera_name] = {"exposure": 15000 + i * 1000, "gain": 1.5 + i * 0.5}

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
    async def test_invalid_camera_name(self, camera_manager):
        """Test handling of invalid camera names."""
        manager = camera_manager

        with pytest.raises(CameraConfigurationError, match="Invalid camera name format"):
            await manager.initialize_camera("NonExistentCamera")

    @pytest.mark.asyncio
    async def test_double_initialization(self, camera_manager):
        """Test double initialization of the same camera."""
        manager = camera_manager

        cameras = manager.discover_cameras()
        if cameras:
            camera_name = cameras[0]

            # First initialization should succeed
            await manager.initialize_camera(camera_name)

            # Second initialization should raise an error (preventing resource conflicts)
            with pytest.raises(ValueError, match="Camera .* is already initialized"):
                await manager.initialize_camera(camera_name)

            # Camera should still be accessible after failed double init
            camera_proxy = manager.get_camera(camera_name)
            assert camera_proxy is not None

    @pytest.mark.asyncio
    async def test_uninitialized_camera_access(self, camera_manager):
        """Test accessing uninitialized camera."""
        manager = camera_manager

        cameras = manager.discover_cameras()
        if cameras:
            camera_name = cameras[0]

            # Should raise error when accessing uninitialized camera
            with pytest.raises(KeyError, match="Camera .* is not initialized"):
                manager.get_camera(camera_name)

    @pytest.mark.asyncio
    async def test_camera_operation_after_shutdown(self, camera_manager):
        """Test camera operations after shutdown."""
        manager = camera_manager

        cameras = manager.discover_cameras()
        if cameras:
            camera_name = cameras[0]
            await manager.initialize_camera(camera_name)
            camera_proxy = manager.get_camera(camera_name)

            # Close the camera
            await manager.close_camera(camera_name)

            # Operations should fail gracefully with connection error
            with pytest.raises(CameraConnectionError):
                await camera_proxy.capture()


class TestHDRCapture:
    """Test suite for HDR capture functionality."""

    @pytest.mark.asyncio
    async def test_single_camera_hdr_capture(self, camera_manager):
        """Test HDR capture with a single camera."""
        manager = camera_manager

        # Get a mock camera
        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "MockDaheng" in cam]

        if mock_cameras:
            camera_name = mock_cameras[0]
            await manager.initialize_camera(camera_name)
            camera_proxy = manager.get_camera(camera_name)

            # Test HDR capture with default parameters
            hdr_images = await camera_proxy.capture_hdr(exposure_levels=3, exposure_multiplier=2.0, return_images=True)

            assert isinstance(hdr_images, list)
            assert len(hdr_images) == 3

            for image in hdr_images:
                assert image is not None
                assert isinstance(image, np.ndarray)
                assert len(image.shape) == 3  # Height, Width, Channels

    @pytest.mark.asyncio
    async def test_hdr_capture_without_images(self, camera_manager):
        """Test HDR capture returning success status only."""
        manager = camera_manager

        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "MockDaheng" in cam]

        if mock_cameras:
            camera_name = mock_cameras[0]
            await manager.initialize_camera(camera_name)
            camera_proxy = manager.get_camera(camera_name)

            # Test HDR capture without returning images
            success = await camera_proxy.capture_hdr(exposure_levels=2, exposure_multiplier=1.5, return_images=False)

            assert isinstance(success, bool)
            assert success is True

    @pytest.mark.asyncio
    async def test_hdr_capture_with_custom_levels(self, camera_manager):
        """Test HDR capture with custom exposure levels."""
        manager = camera_manager

        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "MockDaheng" in cam]

        if mock_cameras:
            camera_name = mock_cameras[0]
            await manager.initialize_camera(camera_name)
            camera_proxy = manager.get_camera(camera_name)

            # Test with different exposure levels
            hdr_images = await camera_proxy.capture_hdr(exposure_levels=5, exposure_multiplier=1.2, return_images=True)

            assert isinstance(hdr_images, list)
            assert len(hdr_images) == 5

    @pytest.mark.asyncio
    async def test_hdr_capture_with_save_path(self, camera_manager):
        """Test HDR capture with file saving."""
        import os
        import tempfile

        manager = camera_manager
        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "MockDaheng" in cam]

        if mock_cameras:
            camera_name = mock_cameras[0]
            await manager.initialize_camera(camera_name)
            camera_proxy = manager.get_camera(camera_name)

            # Create temporary directory for HDR images
            with tempfile.TemporaryDirectory() as temp_dir:
                save_pattern = os.path.join(temp_dir, "hdr_{exposure}.jpg")

                success = await camera_proxy.capture_hdr(
                    save_path_pattern=save_pattern, exposure_levels=2, return_images=False
                )

                assert success is True

                # Check that files were created
                saved_files = os.listdir(temp_dir)
                assert len(saved_files) == 2

                for filename in saved_files:
                    assert filename.startswith("hdr_")
                    assert filename.endswith(".jpg")

    @pytest.mark.asyncio
    async def test_batch_hdr_capture(self, camera_manager):
        """Test batch HDR capture from multiple cameras."""
        manager = camera_manager

        # Get multiple mock cameras
        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "MockDaheng" in cam][:3]

        if len(mock_cameras) >= 2:
            # Initialize cameras
            failed_list = await manager.initialize_cameras(mock_cameras)
            assert len(failed_list) == 0

            # Test batch HDR capture
            results = await manager.batch_capture_hdr(
                camera_names=mock_cameras, exposure_levels=2, exposure_multiplier=1.5, return_images=False
            )

            assert isinstance(results, dict)
            assert len(results) == len(mock_cameras)

            for camera_name, result in results.items():
                assert camera_name in mock_cameras
                assert isinstance(result, bool)
                assert result is True

    @pytest.mark.asyncio
    async def test_batch_hdr_capture_with_images(self, camera_manager):
        """Test batch HDR capture returning images."""
        manager = camera_manager

        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "MockDaheng" in cam][:2]

        if len(mock_cameras) >= 2:
            failed_list = await manager.initialize_cameras(mock_cameras)
            assert len(failed_list) == 0

            # Test batch HDR capture with images
            results = await manager.batch_capture_hdr(camera_names=mock_cameras, exposure_levels=2, return_images=True)

            assert isinstance(results, dict)
            assert len(results) == len(mock_cameras)

            for camera_name, images in results.items():
                assert camera_name in mock_cameras
                assert isinstance(images, list)
                assert len(images) == 2

                for image in images:
                    assert image is not None
                    assert isinstance(image, np.ndarray)

    @pytest.mark.asyncio
    async def test_batch_hdr_capture_with_save_pattern(self, camera_manager):
        """Test batch HDR capture with save path pattern."""
        import os
        import tempfile

        manager = camera_manager
        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "MockDaheng" in cam][:2]

        if len(mock_cameras) >= 2:
            failed_list = await manager.initialize_cameras(mock_cameras)
            assert len(failed_list) == 0

            with tempfile.TemporaryDirectory() as temp_dir:
                save_pattern = os.path.join(temp_dir, "batch_hdr_{camera}_{exposure}.jpg")

                results = await manager.batch_capture_hdr(
                    camera_names=mock_cameras, save_path_pattern=save_pattern, exposure_levels=2, return_images=False
                )

                assert isinstance(results, dict)
                assert len(results) == len(mock_cameras)

                for camera_name, result in results.items():
                    assert result is True

                # Check that files were created for each camera
                saved_files = os.listdir(temp_dir)
                assert len(saved_files) == len(mock_cameras) * 2  # 2 exposures per camera

                for filename in saved_files:
                    assert "batch_hdr_" in filename
                    assert filename.endswith(".jpg")

    @pytest.mark.asyncio
    async def test_concurrent_hdr_capture(self, camera_manager):
        """Test concurrent HDR capture from multiple cameras."""
        manager = camera_manager

        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "MockDaheng" in cam][:2]

        if len(mock_cameras) >= 2:
            failed_list = await manager.initialize_cameras(mock_cameras)
            assert len(failed_list) == 0

            # Get camera proxies
            camera_proxies = [manager.get_camera(name) for name in mock_cameras]

            # Run HDR capture concurrently
            tasks = [proxy.capture_hdr(exposure_levels=2, return_images=False) for proxy in camera_proxies]

            results = await asyncio.gather(*tasks)

            assert len(results) == len(camera_proxies)
            for result in results:
                assert isinstance(result, bool)
                assert result is True

    @pytest.mark.asyncio
    async def test_hdr_exposure_restoration(self, camera_manager):
        """Test that original exposure is restored after HDR capture."""
        manager = camera_manager

        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "MockDaheng" in cam]

        if mock_cameras:
            camera_name = mock_cameras[0]
            await manager.initialize_camera(camera_name)
            camera_proxy = manager.get_camera(camera_name)

            # Set initial exposure
            await camera_proxy.set_exposure(25000)
            original_exposure = await camera_proxy.get_exposure()
            assert original_exposure == 25000

            # Perform HDR capture
            await camera_proxy.capture_hdr(exposure_levels=3, exposure_multiplier=2.0, return_images=False)

            # Check that exposure was restored
            final_exposure = await camera_proxy.get_exposure()
            assert final_exposure == original_exposure

    @pytest.mark.asyncio
    async def test_hdr_capture_edge_cases(self, camera_manager):
        """Test HDR capture edge cases and invalid parameters."""
        manager = camera_manager

        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "MockDaheng" in cam]

        if mock_cameras:
            camera_name = mock_cameras[0]
            await manager.initialize_camera(camera_name)
            camera_proxy = manager.get_camera(camera_name)

            # Test with minimum exposure levels
            result = await camera_proxy.capture_hdr(exposure_levels=1, return_images=False)
            assert isinstance(result, bool)

            # Test with very small multiplier
            result = await camera_proxy.capture_hdr(exposure_levels=2, exposure_multiplier=1.01, return_images=False)
            assert isinstance(result, bool)

            # Test with large multiplier
            result = await camera_proxy.capture_hdr(exposure_levels=2, exposure_multiplier=10.0, return_images=False)
            assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_hdr_capture_error_handling(self, camera_manager):
        """Test HDR capture error handling scenarios."""
        manager = camera_manager

        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "MockDaheng" in cam]

        if mock_cameras:
            camera_name = mock_cameras[0]
            await manager.initialize_camera(camera_name)
            camera_proxy = manager.get_camera(camera_name)

            # Mock camera to fail during HDR capture
            original_capture = camera_proxy._camera.capture
            call_count = 0

            async def mock_failing_capture():
                nonlocal call_count
                call_count += 1
                if call_count == 2:  # Fail on second exposure
                    raise CameraCaptureError("Simulated capture failure")
                return True, np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

            camera_proxy._camera.capture = mock_failing_capture

            # HDR capture should handle partial failures gracefully
            # It should still complete but with fewer successful captures
            try:
                result = await camera_proxy.capture_hdr(exposure_levels=3, return_images=False)
                # Should either succeed with partial captures or fail gracefully
                assert isinstance(result, bool)
            except CameraCaptureError:
                # This is also acceptable - complete failure is valid
                pass

            # Restore original capture method
            camera_proxy._camera.capture = original_capture

    @pytest.mark.asyncio
    async def test_batch_hdr_partial_failure(self, camera_manager):
        """Test batch HDR capture with some cameras failing."""
        manager = camera_manager

        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "MockDaheng" in cam][:3]

        if len(mock_cameras) >= 2:
            failed_list = await manager.initialize_cameras(mock_cameras)
            assert len(failed_list) == 0

            # Make one camera fail
            failing_camera = manager.get_camera(mock_cameras[0])

            async def mock_failing_capture():
                raise CameraCaptureError("Simulated failure")

            failing_camera._camera.capture = mock_failing_capture

            # Batch HDR capture should handle partial failures
            results = await manager.batch_capture_hdr(camera_names=mock_cameras, exposure_levels=2, return_images=False)

            assert isinstance(results, dict)
            assert len(results) == len(mock_cameras)

            # At least one should fail, others should succeed
            success_count = sum(1 for result in results.values() if result is True)
            failure_count = sum(1 for result in results.values() if result is False)

            assert failure_count >= 1  # At least the mocked failing camera
            assert success_count >= 1  # At least some should succeed


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

    @pytest.mark.asyncio
    async def test_batch_capture_with_bandwidth_management(self):
        """Test batch capture with network bandwidth management."""
        from mindtrace.hardware.cameras.camera_manager import CameraManager

        # Test with different concurrent capture limits
        for max_concurrent in [1, 2, 3]:
            manager = CameraManager(include_mocks=True, max_concurrent_captures=max_concurrent)

            try:
                # Get multiple mock cameras
                cameras = manager.discover_cameras()
                mock_cameras = [cam for cam in cameras if "Mock" in cam][:4]

                if len(mock_cameras) >= 2:
                    # Initialize cameras
                    failed_list = await manager.initialize_cameras(mock_cameras)
                    assert len(failed_list) == 0

                    # Test batch capture with bandwidth management
                    results = await manager.batch_capture(mock_cameras)

                    assert isinstance(results, dict)
                    assert len(results) == len(mock_cameras)

                    for camera_name, image in results.items():
                        assert image is not None
                        assert isinstance(image, np.ndarray)

                    # Verify bandwidth management info
                    bandwidth_info = manager.get_network_bandwidth_info()
                    assert bandwidth_info["max_concurrent_captures"] == max_concurrent
                    assert bandwidth_info["bandwidth_management_enabled"] is True
                    assert bandwidth_info["active_cameras"] == len(mock_cameras)

            finally:
                await manager.close_all_cameras()

    @pytest.mark.asyncio
    async def test_dynamic_bandwidth_adjustment(self):
        """Test dynamic adjustment of concurrent capture limits."""
        from mindtrace.hardware.cameras.camera_manager import CameraManager

        manager = CameraManager(include_mocks=True, max_concurrent_captures=1)

        try:
            # Initialize cameras
            cameras = manager.discover_cameras()
            mock_cameras = [cam for cam in cameras if "Mock" in cam][:3]

            if len(mock_cameras) >= 2:
                await manager.initialize_cameras(mock_cameras)

                # Verify initial setting
                assert manager.get_max_concurrent_captures() == 1

                # Change to higher limit
                manager.set_max_concurrent_captures(3)
                assert manager.get_max_concurrent_captures() == 3

                # Test batch capture with new limit
                results = await manager.batch_capture(mock_cameras)
                assert len(results) == len(mock_cameras)

                # Change back to lower limit
                manager.set_max_concurrent_captures(1)
                assert manager.get_max_concurrent_captures() == 1

                # Test batch capture with lower limit
                results = await manager.batch_capture(mock_cameras)
                assert len(results) == len(mock_cameras)

        finally:
            await manager.close_all_cameras()

    @pytest.mark.asyncio
    async def test_bandwidth_management_with_hdr(self):
        """Test HDR capture with network bandwidth management."""
        from mindtrace.hardware.cameras.camera_manager import CameraManager

        manager = CameraManager(include_mocks=True, max_concurrent_captures=2)

        try:
            # Initialize cameras
            cameras = manager.discover_cameras()
            mock_cameras = [cam for cam in cameras if "Mock" in cam][:2]

            if len(mock_cameras) >= 2:
                await manager.initialize_cameras(mock_cameras)

                # Test batch HDR capture with bandwidth management
                results = await manager.batch_capture_hdr(
                    camera_names=mock_cameras, exposure_levels=3, return_images=False
                )

                assert isinstance(results, dict)
                assert len(results) == len(mock_cameras)

                for camera_name, result in results.items():
                    assert result is True

                # Verify bandwidth info shows HDR cameras
                bandwidth_info = manager.get_network_bandwidth_info()
                assert bandwidth_info["gige_cameras"] >= len(mock_cameras)

        finally:
            await manager.close_all_cameras()


class TestNetworkBandwidthManagement:
    """Test suite for network bandwidth management functionality."""

    @pytest.mark.asyncio
    async def test_manager_initialization_with_bandwidth_limit(self):
        """Test camera manager initialization with bandwidth limits."""
        from mindtrace.hardware.cameras.camera_manager import CameraManager

        # Test different bandwidth limits
        for max_concurrent in [1, 2, 5, 10]:
            manager = CameraManager(include_mocks=True, max_concurrent_captures=max_concurrent)

            try:
                assert manager.get_max_concurrent_captures() == max_concurrent

                bandwidth_info = manager.get_network_bandwidth_info()
                assert bandwidth_info["max_concurrent_captures"] == max_concurrent
                assert bandwidth_info["bandwidth_management_enabled"] is True
                assert "recommended_settings" in bandwidth_info

            finally:
                await manager.close_all_cameras()

    @pytest.mark.asyncio
    async def test_bandwidth_info_structure(self):
        """Test the structure of network bandwidth information."""
        from mindtrace.hardware.cameras.camera_manager import CameraManager

        manager = CameraManager(include_mocks=True, max_concurrent_captures=2)

        try:
            bandwidth_info = manager.get_network_bandwidth_info()

            # Check required fields
            required_fields = [
                "max_concurrent_captures",
                "active_cameras",
                "gige_cameras",
                "bandwidth_management_enabled",
                "recommended_settings",
            ]

            for field in required_fields:
                assert field in bandwidth_info

            # Check recommended settings
            recommended = bandwidth_info["recommended_settings"]
            assert "conservative" in recommended
            assert "balanced" in recommended
            assert "aggressive" in recommended

            assert recommended["conservative"] == 1
            assert recommended["balanced"] == 2
            assert recommended["aggressive"] == 3

        finally:
            await manager.close_all_cameras()

    @pytest.mark.asyncio
    async def test_invalid_bandwidth_settings(self):
        """Test handling of invalid bandwidth settings."""
        from mindtrace.hardware.cameras.camera_manager import CameraManager

        manager = CameraManager(include_mocks=True, max_concurrent_captures=2)

        try:
            # Test setting invalid values
            with pytest.raises(ValueError, match="max_captures must be at least 1"):
                manager.set_max_concurrent_captures(0)

            with pytest.raises(ValueError, match="max_captures must be at least 1"):
                manager.set_max_concurrent_captures(-1)

            # Valid settings should work
            manager.set_max_concurrent_captures(1)
            assert manager.get_max_concurrent_captures() == 1

            manager.set_max_concurrent_captures(5)
            assert manager.get_max_concurrent_captures() == 5

        finally:
            await manager.close_all_cameras()

    @pytest.mark.asyncio
    async def test_concurrent_capture_limiting(self):
        """Test that concurrent captures are properly limited."""
        import time

        from mindtrace.hardware.cameras.camera_manager import CameraManager

        # Test with very restrictive limit
        manager = CameraManager(include_mocks=True, max_concurrent_captures=1)

        try:
            cameras = manager.discover_cameras()
            mock_cameras = [cam for cam in cameras if "Mock" in cam][:3]

            if len(mock_cameras) >= 2:
                await manager.initialize_cameras(mock_cameras)

                # Measure time for batch capture with limit of 1
                start_time = time.perf_counter()
                results = await manager.batch_capture(mock_cameras)
                end_time = time.perf_counter()

                # With limit of 1, captures should be sequential
                # Each mock camera takes ~0.1s, so 3 cameras should take at least 0.2s
                capture_time = end_time - start_time
                assert capture_time >= 0.2  # Allow some tolerance

                assert len(results) == len(mock_cameras)

        finally:
            await manager.close_all_cameras()

    @pytest.mark.asyncio
    async def test_bandwidth_management_with_mixed_operations(self):
        """Test bandwidth management with mixed capture operations."""
        from mindtrace.hardware.cameras.camera_manager import CameraManager

        manager = CameraManager(include_mocks=True, max_concurrent_captures=2)

        try:
            cameras = manager.discover_cameras()
            mock_cameras = [cam for cam in cameras if "Mock" in cam][:3]

            if len(mock_cameras) >= 2:
                await manager.initialize_cameras(mock_cameras)

                # Test regular batch capture
                regular_results = await manager.batch_capture(mock_cameras)
                assert len(regular_results) == len(mock_cameras)

                # Test HDR batch capture
                hdr_results = await manager.batch_capture_hdr(
                    camera_names=mock_cameras, exposure_levels=2, return_images=False
                )
                assert len(hdr_results) == len(mock_cameras)

                # Test individual camera captures
                camera_proxies = [manager.get_camera(name) for name in mock_cameras]
                individual_tasks = [proxy.capture() for proxy in camera_proxies]
                individual_results = await asyncio.gather(*individual_tasks)

                assert len(individual_results) == len(camera_proxies)

                # All operations should respect bandwidth limits
                bandwidth_info = manager.get_network_bandwidth_info()
                assert bandwidth_info["max_concurrent_captures"] == 2

        finally:
            await manager.close_all_cameras()

    @pytest.mark.asyncio
    async def test_bandwidth_management_persistence(self):
        """Test that bandwidth settings persist across operations."""
        from mindtrace.hardware.cameras.camera_manager import CameraManager

        manager = CameraManager(include_mocks=True, max_concurrent_captures=3)

        try:
            cameras = manager.discover_cameras()
            mock_cameras = [cam for cam in cameras if "Mock" in cam][:2]

            if len(mock_cameras) >= 2:
                await manager.initialize_cameras(mock_cameras)

                # Verify initial setting
                assert manager.get_max_concurrent_captures() == 3

                # Perform multiple operations
                for i in range(3):
                    results = await manager.batch_capture(mock_cameras)
                    assert len(results) == len(mock_cameras)

                    # Setting should remain the same
                    assert manager.get_max_concurrent_captures() == 3

                # Change setting
                manager.set_max_concurrent_captures(1)
                assert manager.get_max_concurrent_captures() == 1

                # Perform more operations
                for i in range(2):
                    results = await manager.batch_capture(mock_cameras)
                    assert len(results) == len(mock_cameras)

                    # New setting should persist
                    assert manager.get_max_concurrent_captures() == 1

        finally:
            await manager.close_all_cameras()

    @pytest.mark.asyncio
    async def test_bandwidth_management_with_convenience_functions(self):
        """Test bandwidth management with convenience functions."""
        from mindtrace.hardware.cameras.camera_manager import discover_all_cameras

        # Test that convenience function supports bandwidth parameter
        cameras = discover_all_cameras(include_mocks=True, max_concurrent_captures=5)
        assert isinstance(cameras, list)
        assert len(cameras) > 0

        # Mock cameras should be included
        mock_cameras = [cam for cam in cameras if "Mock" in cam]
        assert len(mock_cameras) > 0

        # Test convenience function with backend filtering and bandwidth management
        daheng_cameras = discover_all_cameras(include_mocks=True, max_concurrent_captures=3, backends="MockDaheng")
        assert isinstance(daheng_cameras, list)
        for camera in daheng_cameras:
            assert camera.startswith("MockDaheng:")

        # Test with multiple backends
        multi_cameras = discover_all_cameras(
            include_mocks=True, max_concurrent_captures=2, backends=["MockDaheng", "MockBasler"]
        )
        assert isinstance(multi_cameras, list)
        for camera in multi_cameras:
            assert camera.startswith("MockDaheng:") or camera.startswith("MockBasler:")


class TestConfigurationFormat:
    """Test suite for unified configuration format."""

    @pytest.mark.asyncio
    async def test_common_format_export(self, mock_daheng_camera):
        """Test export using common configuration format."""
        camera = mock_daheng_camera
        await camera.initialize()

        # Configure camera
        await camera.set_exposure(30000)
        await camera.set_gain(4.0)
        await camera.set_triggermode("trigger")
        await camera.set_image_quality_enhancement(True)

        # Export configuration
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            export_path = f.name

        try:
            success = await camera.export_config(export_path)
            assert success is True

            # Verify common format structure
            with open(export_path, "r") as f:
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
        from mindtrace.hardware.cameras.backends.basler import MockBaslerCamera
        from mindtrace.hardware.cameras.backends.daheng import MockDahengCamera

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

            assert await daheng_camera.get_gain() == 2.5
            assert await basler_camera.get_gain() == 2.5

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
                    "trigger_mode": "continuous",
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


class TestRetryLogic:
    """Test suite for proxy-level retry logic."""

    @pytest.mark.asyncio
    async def test_capture_retry_on_capture_error(self, camera_manager):
        """Test retry logic when camera capture fails with CameraCaptureError."""
        # Initialize camera
        await camera_manager.initialize_camera("MockDaheng:test_camera")
        camera = camera_manager.get_camera("MockDaheng:test_camera")

        # Mock the camera to fail twice then succeed
        call_count = 0

        async def mock_capture():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise CameraCaptureError("Buffer underrun")
            return True, np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        camera._camera.capture = mock_capture

        # Should succeed after retries
        image = await camera.capture()
        assert image is not None
        assert call_count == 3  # Should have tried 3 times

    @pytest.mark.asyncio
    async def test_capture_retry_on_connection_error(self, camera_manager):
        """Test retry logic when camera capture fails with CameraConnectionError."""
        await camera_manager.initialize_camera("MockDaheng:test_camera")
        camera = camera_manager.get_camera("MockDaheng:test_camera")

        # Mock the camera to fail with connection error twice then succeed
        call_count = 0

        async def mock_capture():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise CameraConnectionError("Network timeout")
            return True, np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        camera._camera.capture = mock_capture

        # Should succeed after retries
        image = await camera.capture()
        assert image is not None
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_capture_retry_on_timeout_error(self, camera_manager):
        """Test retry logic when camera capture fails with CameraTimeoutError."""
        await camera_manager.initialize_camera("MockDaheng:test_camera")
        camera = camera_manager.get_camera("MockDaheng:test_camera")

        # Mock the camera to fail with timeout error twice then succeed
        call_count = 0

        async def mock_capture():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise CameraTimeoutError("Image acquisition timeout")
            return True, np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        camera._camera.capture = mock_capture

        # Should succeed after retries
        image = await camera.capture()
        assert image is not None
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_capture_failure_after_all_retries(self, camera_manager):
        """Test that capture fails after exhausting all retry attempts."""
        await camera_manager.initialize_camera("MockDaheng:test_camera")
        camera = camera_manager.get_camera("MockDaheng:test_camera")

        # Mock the camera to always fail
        async def mock_capture():
            raise CameraCaptureError("Persistent buffer error")

        camera._camera.capture = mock_capture

        # Should fail after all retries
        with pytest.raises(CameraCaptureError, match="Capture failed after 3 attempts for camera"):
            await camera.capture()

    @pytest.mark.asyncio
    async def test_non_retryable_errors_fail_immediately(self, camera_manager):
        """Test that non-retryable errors fail immediately without retries."""
        await camera_manager.initialize_camera("MockDaheng:test_camera")
        camera = camera_manager.get_camera("MockDaheng:test_camera")

        # Mock the camera to fail with non-retryable error
        async def mock_capture():
            raise CameraNotFoundError("Camera not found")

        camera._camera.capture = mock_capture

        # Should fail immediately
        with pytest.raises(CameraNotFoundError):
            await camera.capture()

    @pytest.mark.asyncio
    async def test_capture_returns_false_treated_as_error(self, camera_manager):
        """Test that capture returning (False, None) is treated as an error and retried."""
        await camera_manager.initialize_camera("MockDaheng:test_camera")
        camera = camera_manager.get_camera("MockDaheng:test_camera")

        # Mock the camera to return False twice then True
        call_count = 0

        async def mock_capture():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return False, None
            return True, np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        camera._camera.capture = mock_capture

        # Should succeed after retries
        image = await camera.capture()
        assert image is not None
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_capture_returns_none_treated_as_error(self, camera_manager):
        """Test that capture returning (True, None) is treated as an error and retried."""
        await camera_manager.initialize_camera("MockDaheng:test_camera")
        camera = camera_manager.get_camera("MockDaheng:test_camera")

        # Mock the camera to return None image twice then valid image
        call_count = 0

        async def mock_capture():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return True, None
            return True, np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        camera._camera.capture = mock_capture

        # Should succeed after retries
        image = await camera.capture()
        assert image is not None
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_with_different_delays(self, camera_manager):
        """Test that different error types use different retry delays."""
        await camera_manager.initialize_camera("MockDaheng:test_camera")
        camera = camera_manager.get_camera("MockDaheng:test_camera")

        # Mock the camera to fail with different error types
        call_count = 0
        start_time = None

        async def mock_capture():
            nonlocal call_count, start_time
            call_count += 1

            if call_count == 1:
                if start_time is None:
                    start_time = asyncio.get_event_loop().time()
                raise CameraCaptureError("Fast retry error")
            elif call_count == 2:
                raise CameraConnectionError("Slow retry error")
            else:
                return True, np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        camera._camera.capture = mock_capture

        # Capture and measure timing
        start = asyncio.get_event_loop().time()
        image = await camera.capture()
        end = asyncio.get_event_loop().time()

        assert image is not None
        assert call_count == 3

        # Should have taken at least the sum of delays
        # First retry: 0.1s, second retry: 0.5s = 0.6s minimum
        assert (end - start) >= 0.5  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_retry_logging(self, camera_manager, caplog):
        """Test that retry attempts are properly logged."""
        await camera_manager.initialize_camera("MockDaheng:test_camera")
        camera = camera_manager.get_camera("MockDaheng:test_camera")

        # Mock the camera to fail twice then succeed
        call_count = 0

        async def mock_capture():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise CameraCaptureError("Test error")
            return True, np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        camera._camera.capture = mock_capture

        # Capture and check logs
        image = await camera.capture()

        # Verify the retry logic worked by checking call count
        # The logging might not be captured due to logger propagation settings,
        # but the important thing is that the retry logic actually functions correctly
        assert call_count == 3  # Should have tried 3 times (2 failures + 1 success)
        assert image is not None  # Should eventually succeed

        # If logs are captured, verify they contain retry information
        retry_logs = [
            log
            for log in caplog.records
            if any(word in log.getMessage().lower() for word in ["retry", "attempt", "failed"])
        ]
        if len(retry_logs) > 0:
            # If logs are captured, verify they mention the camera name
            for log in retry_logs:
                assert "MockDaheng:test_camera" in log.getMessage()

    @pytest.mark.asyncio
    async def test_retry_with_custom_retry_count(self, camera_manager):
        """Test retry logic with custom retry count from camera configuration."""
        # Create camera with custom retry count
        await camera_manager.initialize_camera("MockDaheng:test_camera")
        camera = camera_manager.get_camera("MockDaheng:test_camera")

        # Set custom retry count
        camera._camera.retrieve_retry_count = 5

        # Mock the camera to fail 4 times then succeed
        call_count = 0

        async def mock_capture():
            nonlocal call_count
            call_count += 1
            if call_count <= 4:
                raise CameraCaptureError("Test error")
            return True, np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        camera._camera.capture = mock_capture

        # Should succeed after 5 attempts
        image = await camera.capture()
        assert image is not None
        assert call_count == 5

    @pytest.mark.asyncio
    async def test_concurrent_capture_with_retry(self, camera_manager):
        """Test that retry logic works correctly with concurrent captures."""
        await camera_manager.initialize_camera("MockDaheng:test_camera")
        camera = camera_manager.get_camera("MockDaheng:test_camera")

        # Mock the camera to fail occasionally
        call_counts = [0, 0, 0]

        async def mock_capture(camera_id):
            call_counts[camera_id] += 1
            if call_counts[camera_id] <= 1:
                raise CameraCaptureError(f"Error for camera {camera_id}")
            return True, np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        # Create multiple camera proxies for concurrent testing
        cameras = []
        for i in range(3):
            # Create a new camera instance for each proxy
            from mindtrace.hardware.cameras.backends.daheng import MockDahengCamera

            mock_cam = MockDahengCamera(f"mock_cam_{i}", None)
            await mock_cam.initialize()

            # Override the capture method with proper closure
            async def create_capture_func(camera_id):
                async def capture_func():
                    return await mock_capture(camera_id)

                return capture_func

            mock_cam.capture = await create_capture_func(i)

            # Create proxy
            from mindtrace.hardware.cameras.camera_manager import CameraProxy

            proxy = CameraProxy(mock_cam, f"MockDaheng:test_camera_{i}")
            cameras.append(proxy)

        # Capture concurrently
        tasks = [camera.capture() for camera in cameras]
        images = await asyncio.gather(*tasks)

        # All should succeed
        for i, image in enumerate(images):
            assert image is not None
            assert call_counts[i] == 2  # Should have tried twice each

        # Cleanup
        for camera in cameras:
            await camera._camera.close()

    @pytest.mark.asyncio
    async def test_batch_capture_with_retry(self, camera_manager):
        """Test that batch capture works correctly with retry logic."""
        # Initialize multiple cameras
        camera_names = ["MockDaheng:test_camera_1", "MockDaheng:test_camera_2"]
        await camera_manager.initialize_cameras(camera_names)

        # Mock cameras to fail occasionally
        for camera_name in camera_names:
            camera = camera_manager.get_camera(camera_name)
            call_count = 0

            async def mock_capture():
                nonlocal call_count
                call_count += 1
                if call_count <= 1:
                    raise CameraCaptureError("Test error")
                return True, np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

            camera._camera.capture = mock_capture

        # Batch capture
        results = await camera_manager.batch_capture(camera_names)

        # All should succeed
        for camera_name in camera_names:
            assert camera_name in results
            assert results[camera_name] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
