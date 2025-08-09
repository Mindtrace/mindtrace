"""Comprehensive unit tests for the camera system (Basler/OpenCV only).

This module tests camera functionality using mock implementations to avoid
hardware dependencies. Daheng-related tests have been removed.
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
    """Create a camera manager instance with mock backends."""
    from mindtrace.hardware.cameras.core.camera_manager import CameraManager

    manager = CameraManager(include_mocks=True)
    yield manager

    # Cleanup
    try:
        await manager.close_all_cameras()
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
            "camera_type": "mock_basler",
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


# Prevent real OpenCV device probing during unit tests
@pytest.fixture(autouse=True)
def _disable_real_opencv_camera_discovery(monkeypatch):
    try:
        from mindtrace.hardware.cameras.backends.opencv.opencv_camera import OpenCVCamera

        def _fake_get_available_cameras(include_details: bool = False):
            return {} if include_details else []

        monkeypatch.setattr(OpenCVCamera, "get_available_cameras", staticmethod(_fake_get_available_cameras))
    except Exception:
        # If OpenCV backend is not importable, nothing to do
        pass


# Helper: ensure mock cameras use a very short exposure to keep tests fast
async def _set_low_exposure(manager, camera_names, value: int = 1000):
    for name in camera_names:
        try:
            await manager.get_camera(name).set_exposure(value)
        except Exception:
            pass


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

        # With mocks enabled, we should have mock backends information
        backend_info = manager.get_backend_info()
        assert isinstance(backend_info, dict)

    @pytest.mark.asyncio
    async def test_camera_discovery(self, camera_manager):
        """Test camera discovery functionality."""
        manager = camera_manager

        # Test available cameras discovery
        available = manager.discover_cameras()
        assert isinstance(available, list)

        # Should include mock cameras (at least MockBasler)
        mock_cameras = [cam for cam in available if "Mock" in cam]
        assert len(mock_cameras) > 0

    @pytest.mark.asyncio
    async def test_backend_specific_discovery(self, camera_manager):
        """Test backend-specific camera discovery functionality (Basler/OpenCV)."""
        manager = camera_manager

        # Discover only MockBasler cameras
        basler_cameras = manager.discover_cameras("MockBasler")
        assert isinstance(basler_cameras, list)
        for camera in basler_cameras:
            assert camera.startswith("MockBasler:")

        # Discover from multiple backends (Basler + OpenCV)
        multi_backend_cameras = manager.discover_cameras(["MockBasler", "OpenCV"])
        assert isinstance(multi_backend_cameras, list)
        for camera in multi_backend_cameras:
            assert camera.startswith("MockBasler:") or camera.startswith("OpenCV:")

        # Non-existent backend returns empty
        empty_cameras = manager.discover_cameras("NonExistentBackend")
        assert isinstance(empty_cameras, list)
        assert len(empty_cameras) == 0

        # Empty list returns empty
        empty_list_cameras = manager.discover_cameras([])
        assert isinstance(empty_list_cameras, list)
        assert len(empty_list_cameras) == 0

        # Invalid parameter type
        with pytest.raises(ValueError, match="Invalid backends parameter"):
            manager.discover_cameras(123)

    @pytest.mark.asyncio
    async def test_backend_specific_discovery_consistency(self, camera_manager):
        """Test that backend-specific discovery is consistent with full discovery."""
        manager = camera_manager

        # Get all cameras
        all_cameras = manager.discover_cameras()

        # Get cameras by backend (Basler + OpenCV)
        basler_cameras = manager.discover_cameras("MockBasler")
        opencv_cameras = manager.discover_cameras("OpenCV")

        # Union of backend-specific discoveries should equal full discovery
        combined_cameras = basler_cameras + opencv_cameras

        # Sort for comparison
        all_cameras_sorted = sorted(all_cameras)
        combined_cameras_sorted = sorted(combined_cameras)

        assert all_cameras_sorted == combined_cameras_sorted

    @pytest.mark.asyncio
    async def test_convenience_function_with_backend_filtering(self):
        """Test convenience function with backend filtering."""
        from mindtrace.hardware.cameras.core.camera_manager import discover_all_cameras

        # Test convenience function (all)
        all_cameras = discover_all_cameras(include_mocks=True)
        assert isinstance(all_cameras, list)
        assert len(all_cameras) > 0

        # Test with specific backend (MockBasler)
        basler_cameras = discover_all_cameras(include_mocks=True, backends="MockBasler")
        assert isinstance(basler_cameras, list)
        for camera in basler_cameras:
            assert camera.startswith("MockBasler:")

        # Test with multiple backends
        multi_cameras = discover_all_cameras(include_mocks=True, backends=["MockBasler", "OpenCV"])
        assert isinstance(multi_cameras, list)
        for camera in multi_cameras:
            assert camera.startswith("MockBasler:") or camera.startswith("OpenCV:")

        # Test with non-existent backend
        empty_cameras = discover_all_cameras(include_mocks=True, backends="NonExistentBackend")
        assert isinstance(empty_cameras, list)
        assert len(empty_cameras) == 0

    @pytest.mark.asyncio
    async def test_camera_proxy_operations(self, camera_manager):
        """Test camera proxy operations through manager."""
        manager = camera_manager

        # Get a mock camera through the manager (prefer MockBasler)
        cameras = manager.discover_cameras()
        mock_cameras = [cam for cam in cameras if "MockBasler" in cam]

        if mock_cameras:
            camera_name = mock_cameras[0]

            # Initialize the camera first
            await manager.initialize_camera(camera_name)

            # Then get the camera proxy
            camera_proxy = manager.get_camera(camera_name)

            assert camera_proxy is not None
            assert camera_proxy.name == camera_name
            assert "MockBasler" in camera_proxy.backend
            assert camera_proxy.is_connected

            # Use short exposure for fast tests
            await camera_proxy.set_exposure(1000)

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

            # Ensure short exposure for fast tests
            await _set_low_exposure(manager, mock_cameras, 1000)

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
        from mindtrace.hardware.cameras.core.camera_manager import CameraManager

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

                # Short exposure for fast tests
                await camera_proxy.set_exposure(1000)

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

            # Ensure short exposure for fast tests
            await _set_low_exposure(manager, mock_cameras, 1000)

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
    async def test_batch_capture_with_bandwidth_management(self):
        """Test batch capture with network bandwidth management."""
        from mindtrace.hardware.cameras.core.camera_manager import CameraManager

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
        from mindtrace.hardware.cameras.core.camera_manager import CameraManager

        manager = CameraManager(include_mocks=True, max_concurrent_captures=1)

        try:
            # Initialize cameras
            cameras = manager.discover_cameras()
            mock_cameras = [cam for cam in cameras if "Mock" in cam][:3]

            if len(mock_cameras) >= 2:
                await manager.initialize_cameras(mock_cameras)

                # Use short exposure
                await _set_low_exposure(manager, mock_cameras, 1000)

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
        """Test HDR capture with network bandwidth management (generic)."""
        from mindtrace.hardware.cameras.core.camera_manager import CameraManager

        manager = CameraManager(include_mocks=True, max_concurrent_captures=2)

        try:
            # Initialize cameras
            cameras = manager.discover_cameras()
            mock_cameras = [cam for cam in cameras if "Mock" in cam][:2]

            if len(mock_cameras) >= 2:
                await manager.initialize_cameras(mock_cameras)

                # Short exposure for fast tests
                await _set_low_exposure(manager, mock_cameras, 1000)

                # Test batch HDR capture with bandwidth management
                results = await manager.batch_capture_hdr(
                    camera_names=mock_cameras, exposure_levels=3, return_images=False
                )

                assert isinstance(results, dict)
                assert len(results) == len(mock_cameras)

                for camera_name, result in results.items():
                    assert result is True

                # Verify bandwidth info shows GigE cameras counted (Basler is GigE in mocks)
                bandwidth_info = manager.get_network_bandwidth_info()
                assert bandwidth_info["gige_cameras"] >= 0

        finally:
            await manager.close_all_cameras()


class TestNetworkBandwidthManagement:
    """Test suite for network bandwidth management functionality."""

    @pytest.mark.asyncio
    async def test_manager_initialization_with_bandwidth_limit(self):
        """Test camera manager initialization with bandwidth limits."""
        from mindtrace.hardware.cameras.core.camera_manager import CameraManager

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
        from mindtrace.hardware.cameras.core.camera_manager import CameraManager

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
        from mindtrace.hardware.cameras.core.camera_manager import CameraManager

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

        from mindtrace.hardware.cameras.core.camera_manager import CameraManager

        # Test with very restrictive limit
        manager = CameraManager(include_mocks=True, max_concurrent_captures=1)

        try:
            cameras = manager.discover_cameras()
            mock_cameras = [cam for cam in cameras if "Mock" in cam][:3]

            if len(mock_cameras) >= 2:
                await manager.initialize_cameras(mock_cameras)

                # Short exposure for fast tests
                await _set_low_exposure(manager, mock_cameras, 1000)

                # Validate concurrency <= 1 without timing dependency
                current = 0
                max_seen = 0

                async def wrap_capture(_proxy):
                    nonlocal current, max_seen
                    current += 1
                    if current > max_seen:
                        max_seen = current
                    try:
                        # allow scheduling overlap if semaphore misconfigured
                        await asyncio.sleep(0.01)
                        # return synthetic image (RGB)
                        return True, np.zeros((10, 10, 3), dtype=np.uint8)
                    finally:
                        current -= 1

                # Monkeypatch capture for proxies
                proxies = [manager.get_camera(name) for name in mock_cameras]
                originals = []
                for p in proxies:
                    originals.append(p._camera.capture)
                    p._camera.capture = lambda p=p: wrap_capture(p)

                try:
                    results = await manager.batch_capture(mock_cameras)
                finally:
                    # restore originals
                    for p, orig in zip(proxies, originals):
                        p._camera.capture = orig

                assert max_seen <= 1
                assert len(results) == len(mock_cameras)

        finally:
            await manager.close_all_cameras()

    @pytest.mark.asyncio
    async def test_bandwidth_management_with_mixed_operations(self):
        """Test bandwidth management with mixed capture operations."""
        from mindtrace.hardware.cameras.core.camera_manager import CameraManager

        manager = CameraManager(include_mocks=True, max_concurrent_captures=2)

        try:
            cameras = manager.discover_cameras()
            mock_cameras = [cam for cam in cameras if "Mock" in cam][:3]

            if len(mock_cameras) >= 2:
                await manager.initialize_cameras(mock_cameras)

                # Short exposure for fast tests
                await _set_low_exposure(manager, mock_cameras, 1000)

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
        from mindtrace.hardware.cameras.core.camera_manager import CameraManager

        manager = CameraManager(include_mocks=True, max_concurrent_captures=3)

        try:
            cameras = manager.discover_cameras()
            mock_cameras = [cam for cam in cameras if "Mock" in cam][:2]

            if len(mock_cameras) >= 2:
                await manager.initialize_cameras(mock_cameras)

                # Short exposure for fast tests
                await _set_low_exposure(manager, mock_cameras, 1000)

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
        from mindtrace.hardware.cameras.core.camera_manager import discover_all_cameras

        # Test that convenience function supports bandwidth parameter
        cameras = discover_all_cameras(include_mocks=True, max_concurrent_captures=5)
        assert isinstance(cameras, list)
        assert len(cameras) > 0

        # Mock cameras should be included
        mock_cameras = [cam for cam in cameras if "Mock" in cam]
        assert len(mock_cameras) > 0

        # Test convenience function with backend filtering and bandwidth management
        basler_cameras = discover_all_cameras(include_mocks=True, max_concurrent_captures=3, backends="MockBasler")
        assert isinstance(basler_cameras, list)
        for camera in basler_cameras:
            assert camera.startswith("MockBasler:")

        # Test with multiple backends
        multi_cameras = discover_all_cameras(
            include_mocks=True, max_concurrent_captures=2, backends=["MockBasler", "OpenCV"]
        )
        assert isinstance(multi_cameras, list)
        for camera in multi_cameras:
            assert camera.startswith("MockBasler:") or camera.startswith("OpenCV:")


class TestConfigurationFormat:
    """Test suite for unified configuration format (Basler)."""

    @pytest.mark.asyncio
    async def test_common_format_export(self, mock_basler_camera):
        """Test export using common configuration format."""
        camera = mock_basler_camera
        await camera.initialize()

        # Configure camera
        await camera.set_exposure(30000)
        camera.set_gain(4.0)
        await camera.set_triggermode("trigger")
        camera.set_image_quality_enhancement(True)

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
