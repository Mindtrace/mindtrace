import asyncio
import json
import os
import tempfile
from unittest.mock import patch

import numpy as np
import pytest
import pytest_asyncio

from mindtrace.hardware.cameras.backends.basler import MockBaslerCameraBackend
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraInitializationError,
    CameraTimeoutError,
)


@pytest_asyncio.fixture
async def mock_basler_camera():
    camera = MockBaslerCameraBackend(camera_name="mock_basler_1", camera_config=None)
    yield camera
    try:
        await camera.close()
    except Exception:
        pass


@pytest_asyncio.fixture
async def temp_config_file():
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
    try:
        yield temp_path
    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_camera_initialization(mock_basler_camera):
    camera = mock_basler_camera
    assert camera.camera_name == "mock_basler_1"
    assert not camera.initialized


@pytest.mark.asyncio
async def test_camera_connection(mock_basler_camera):
    camera = mock_basler_camera
    success, _, _ = await camera.initialize()
    assert success
    assert camera.initialized
    assert await camera.check_connection()


@pytest.mark.asyncio
async def test_basler_specific_features(mock_basler_camera):
    camera = mock_basler_camera
    await camera.initialize()
    await camera.set_triggermode("trigger")
    trigger_mode = await camera.get_triggermode()
    assert trigger_mode == "trigger"
    gain_range = await camera.get_gain_range()
    assert isinstance(gain_range, list) and len(gain_range) == 2
    pixel_formats = await camera.get_pixel_format_range()
    assert isinstance(pixel_formats, list) and "BGR8" in pixel_formats


@pytest.mark.asyncio
async def test_configuration_compatibility(mock_basler_camera, temp_config_file):
    camera = mock_basler_camera
    await camera.initialize()
    await camera.import_config(temp_config_file)
    assert await camera.get_exposure() == 15000.0
    assert await camera.get_gain() == 2.5


@pytest.mark.asyncio
async def test_common_format_export(mock_basler_camera):
    camera = mock_basler_camera
    await camera.initialize()
    await camera.set_exposure(30000)
    await camera.set_gain(4.0)
    await camera.set_triggermode("trigger")
    await camera.set_image_quality_enhancement(True)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        export_path = f.name

    try:
        await camera.export_config(export_path)
        with open(export_path, "r") as f:
            config = json.load(f)
        assert config["exposure_time"] == 30000
        assert config["gain"] == 4.0
        assert config["trigger_mode"] == "trigger"
        assert config["image_enhancement"] is True
    finally:
        os.unlink(export_path)


class TestMockBaslerErrorSimulation:
    """Test error simulation capabilities."""

    @pytest.mark.asyncio
    async def test_constructor_error_simulation_flags(self):
        """Test constructor-based error simulation."""
        # Test initialization failure simulation
        camera = MockBaslerCameraBackend("test_cam", simulate_fail_init=True)
        with pytest.raises(CameraInitializationError, match="Simulated initialization failure"):
            await camera.initialize()

        # Test capture failure simulation
        camera = MockBaslerCameraBackend("test_cam", simulate_fail_capture=True)
        await camera.initialize()
        with pytest.raises(CameraCaptureError, match="Simulated capture failure"):
            await camera.capture()

        # Test timeout simulation
        camera = MockBaslerCameraBackend("test_cam", simulate_timeout=True)
        await camera.initialize()
        with pytest.raises(CameraTimeoutError, match="Simulated timeout"):
            await camera.capture()

    @pytest.mark.asyncio
    async def test_environment_variable_error_simulation(self, monkeypatch):
        """Test environment variable-based error simulation."""
        # Test environment variable override
        monkeypatch.setenv("MOCK_BASLER_FAIL_INIT", "true")
        camera = MockBaslerCameraBackend("test_cam")
        with pytest.raises(CameraInitializationError):
            await camera.initialize()

        # Test constructor override of environment
        camera = MockBaslerCameraBackend(
            "test_cam",
            simulate_fail_init=False,  # Should override env
        )
        success, _, _ = await camera.initialize()
        assert success is True

    @pytest.mark.asyncio
    async def test_cancellation_simulation(self):
        """Test asyncio cancellation simulation."""
        camera = MockBaslerCameraBackend("test_cam", simulate_cancel=True)
        await camera.initialize()
        with pytest.raises(asyncio.CancelledError):
            await camera.capture()


class TestMockBaslerImageGeneration:
    """Test synthetic image generation features."""

    @pytest.mark.asyncio
    async def test_different_image_patterns(self):
        """Test different synthetic image patterns."""
        patterns = ["gradient", "checkerboard", "circular", "noise"]

        for pattern in patterns:
            camera = MockBaslerCameraBackend(
                f"test_cam_{pattern}",
                synthetic_pattern=pattern,
            )
            await camera.initialize()

            image = await camera.capture()
            assert isinstance(image, np.ndarray)
            assert len(image.shape) == 3  # Should be 3D array (height, width, channels)
            assert image.shape[2] == 3  # Should have 3 color channels
            assert image.dtype == np.uint8

            # Verify pattern-specific characteristics exist (non-zero variance indicates pattern)
            assert image.var() > 0, f"Pattern {pattern} should produce varied pixel values"

            await camera.close()

    @pytest.mark.asyncio
    async def test_auto_pattern_rotation(self):
        """Test automatic pattern rotation in auto mode."""
        camera = MockBaslerCameraBackend("test_cam", synthetic_pattern="auto")
        await camera.initialize()

        # Capture multiple images to test pattern rotation
        images = []
        image_stats = []
        for i in range(8):  # Capture more images to ensure we see rotation
            image = await camera.capture()
            images.append(image)
            # Track statistics to detect pattern changes
            stats = (image.mean(), image.std(), image.min(), image.max())
            image_stats.append(stats)

        # Check that we have variation in image statistics (indicating different patterns)
        unique_stats = set(image_stats)
        assert len(unique_stats) > 1, (
            f"Expected pattern rotation to create different images, got {len(unique_stats)} unique patterns from {len(image_stats)} captures"
        )
        await camera.close()

    @pytest.mark.asyncio
    async def test_checkerboard_size_parameter(self):
        """Test configurable checkerboard size."""
        camera = MockBaslerCameraBackend("test_cam", synthetic_pattern="checkerboard", synthetic_checker_size=100)
        await camera.initialize()

        await camera.capture()
        assert camera.synthetic_checker_size == 100
        await camera.close()

    @pytest.mark.asyncio
    async def test_text_overlay_toggle(self):
        """Test text overlay enable/disable."""
        # With text overlay
        camera_with_text = MockBaslerCameraBackend("test_cam_text", synthetic_overlay_text=True)
        await camera_with_text.initialize()

        # Without text overlay
        camera_no_text = MockBaslerCameraBackend("test_cam_no_text", synthetic_overlay_text=False)
        await camera_no_text.initialize()

        # Both should work
        _ = await camera_with_text.capture()
        _ = await camera_no_text.capture()

        await camera_with_text.close()
        await camera_no_text.close()

    @pytest.mark.asyncio
    async def test_exposure_and_gain_effects_on_image(self):
        """Test that exposure and gain settings affect the generated image."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Use more extreme exposure values to ensure visible difference
        await camera.set_exposure(50)  # Very low exposure
        image1 = await camera.capture()
        stats1 = (image1.mean(), image1.std())

        await camera.set_exposure(500000)  # Very high exposure
        image2 = await camera.capture()
        stats2 = (image2.mean(), image2.std())

        # Check that exposure affects image statistics
        assert stats1 != stats2, f"Exposure should affect image: low_exp={stats1}, high_exp={stats2}"

        # Test gain effects with more extreme values
        await camera.set_gain(1.0)  # Low gain
        image3 = await camera.capture()
        stats3 = (image3.mean(), image3.std())

        await camera.set_gain(12.0)  # High gain
        image4 = await camera.capture()
        stats4 = (image4.mean(), image4.std())

        # Check that gain affects image statistics
        assert stats3 != stats4, f"Gain should affect image: low_gain={stats3}, high_gain={stats4}"

        await camera.close()


class TestMockBaslerROIOperations:
    """Test Region of Interest (ROI) functionality."""

    @pytest.mark.asyncio
    async def test_roi_validation(self):
        """Test ROI parameter validation."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Test invalid dimensions
        with pytest.raises(CameraConfigurationError, match="Invalid ROI dimensions"):
            await camera.set_ROI(0, 0, 0, 480)  # Width = 0

        with pytest.raises(CameraConfigurationError, match="Invalid ROI dimensions"):
            await camera.set_ROI(0, 0, 640, -10)  # Negative height

        # Test invalid offsets
        with pytest.raises(CameraConfigurationError, match="Invalid ROI offset"):
            await camera.set_ROI(-10, 0, 640, 480)  # Negative x

        with pytest.raises(CameraConfigurationError, match="Invalid ROI offset"):
            await camera.set_ROI(0, -5, 640, 480)  # Negative y

        await camera.close()

    @pytest.mark.asyncio
    async def test_roi_get_set_cycle(self):
        """Test ROI set and get operations."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Get initial ROI
        initial_roi = await camera.get_ROI()
        _initial_width, _initial_height = initial_roi["width"], initial_roi["height"]

        # Set custom ROI
        roi_params = (100, 50, 800, 600)
        await camera.set_ROI(*roi_params)

        # Get ROI and verify
        roi = await camera.get_ROI()
        assert roi["x"] == 100
        assert roi["y"] == 50
        assert roi["width"] == 800
        assert roi["height"] == 600

        # Test image generation with custom ROI
        image = await camera.capture()
        # ROI should affect the generated image size
        assert image.shape == (600, 800, 3), f"Expected (600, 800, 3) for custom ROI, got {image.shape}"

        await camera.close()

    @pytest.mark.asyncio
    async def test_roi_reset(self):
        """Test ROI reset functionality."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Set custom ROI
        await camera.set_ROI(100, 100, 640, 480)

        # Reset ROI
        await camera.reset_ROI()

        # Verify reset to full size
        roi = await camera.get_ROI()
        assert roi["x"] == 0
        assert roi["y"] == 0
        assert roi["width"] == 1920
        assert roi["height"] == 1080

        await camera.close()


class TestMockBaslerConfigurationValidation:
    """Test configuration parameter validation."""

    def test_constructor_parameter_validation(self):
        """Test constructor parameter validation."""
        # Test invalid buffer count
        with pytest.raises(CameraConfigurationError, match="Buffer count must be at least 1"):
            MockBaslerCameraBackend("test_cam", buffer_count=0)

        # Test invalid timeout
        with pytest.raises(CameraConfigurationError, match="Timeout must be at least 100ms"):
            MockBaslerCameraBackend("test_cam", timeout_ms=50)

    @pytest.mark.asyncio
    async def test_exposure_range_validation(self):
        """Test exposure time range validation."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Test valid exposure
        await camera.set_exposure(20000)

        # Test exposure too low
        with pytest.raises(CameraConfigurationError, match="Exposure.*out of range"):
            await camera.set_exposure(10)  # Below minimum

        # Test exposure too high
        with pytest.raises(CameraConfigurationError, match="Exposure.*out of range"):
            await camera.set_exposure(2000000)  # Above maximum

        await camera.close()

    @pytest.mark.asyncio
    async def test_gain_range_validation(self):
        """Test gain range validation."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Test valid gain
        await camera.set_gain(8.0)

        # Test gain too low
        with pytest.raises(CameraConfigurationError, match="Gain.*out of range"):
            await camera.set_gain(0.5)

        # Test gain too high
        with pytest.raises(CameraConfigurationError, match="Gain.*out of range"):
            await camera.set_gain(20.0)

        await camera.close()

    @pytest.mark.asyncio
    async def test_trigger_mode_validation(self):
        """Test trigger mode validation."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Test valid trigger modes
        await camera.set_triggermode("continuous")
        await camera.set_triggermode("trigger")

        # Test invalid trigger mode
        with pytest.raises(CameraConfigurationError, match="Invalid trigger mode"):
            await camera.set_triggermode("invalid_mode")

        await camera.close()

    @pytest.mark.asyncio
    async def test_pixel_format_validation(self):
        """Test pixel format validation."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Test valid pixel format
        await camera.set_pixel_format("BGR8")

        # Test invalid pixel format
        with pytest.raises(CameraConfigurationError, match="Unsupported pixel format"):
            await camera.set_pixel_format("INVALID_FORMAT")

        await camera.close()


class TestMockBaslerStateManagement:
    """Test camera state management and grabbing operations."""

    @pytest.mark.asyncio
    async def test_grabbing_state_management(self):
        """Test grabbing state management."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Initially not grabbing
        assert camera.IsGrabbing() is False

        # Start grabbing
        camera.StartGrabbing("LatestImageOnly")
        assert camera.IsGrabbing() is True
        assert camera.grabbing_mode == "LatestImageOnly"

        # Stop grabbing
        camera.StopGrabbing()
        assert camera.IsGrabbing() is False

        await camera.close()

    @pytest.mark.asyncio
    async def test_auto_grabbing_on_capture(self):
        """Test automatic grabbing start during capture."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Ensure not grabbing initially
        camera.StopGrabbing()
        assert camera.IsGrabbing() is False

        # Capture should auto-start grabbing
        await camera.capture()
        assert camera.IsGrabbing() is True

        await camera.close()

    @pytest.mark.asyncio
    async def test_connection_check_with_uninitialized_camera(self):
        """Test connection check behavior with uninitialized camera."""
        camera = MockBaslerCameraBackend("test_cam")

        # Should return False when not initialized
        is_connected = await camera.check_connection()
        assert is_connected is False

    @pytest.mark.asyncio
    async def test_capture_without_initialization(self):
        """Test capture attempt without initialization."""
        camera = MockBaslerCameraBackend("test_cam")

        with pytest.raises(CameraConnectionError, match="is not initialized"):
            await camera.capture()


class TestMockBaslerConfigurationFiles:
    """Test configuration file import/export functionality."""

    @pytest.mark.asyncio
    async def test_import_config_missing_file(self):
        """Test importing from non-existent config file."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        with pytest.raises(CameraConfigurationError, match="Configuration file not found"):
            await camera.import_config("/nonexistent/path/config.json")

        await camera.close()

    @pytest.mark.asyncio
    async def test_import_config_invalid_json(self):
        """Test importing invalid JSON configuration."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Create invalid JSON file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json content {")
            invalid_path = f.name

        try:
            with pytest.raises(CameraConfigurationError, match="Invalid JSON configuration format"):
                await camera.import_config(invalid_path)
        finally:
            os.unlink(invalid_path)

        await camera.close()

    @pytest.mark.asyncio
    async def test_export_config_directory_creation(self):
        """Test config export with automatic directory creation."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Create path in non-existent directory
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "nested", "config.json")

            await camera.export_config(config_path)
            assert os.path.exists(config_path)

            # Verify content
            with open(config_path, "r") as f:
                config = json.load(f)
            assert config["camera_type"] == "mock_basler"
            assert config["camera_name"] == "test_cam"

        await camera.close()

    @pytest.mark.asyncio
    async def test_partial_configuration_import(self):
        """Test importing configuration with missing optional fields."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Create config with only some fields
        partial_config = {
            "exposure_time": 25000.0,
            "gain": 3.0,
            # Missing other optional fields
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(partial_config, f)
            partial_path = f.name

        try:
            await camera.import_config(partial_path)

            # Verify imported values
            assert await camera.get_exposure() == 25000.0
            assert await camera.get_gain() == 3.0
        finally:
            os.unlink(partial_path)

        await camera.close()


class TestMockBaslerWhiteBalance:
    """Test white balance functionality."""

    @pytest.mark.asyncio
    async def test_white_balance_get_set(self):
        """Test white balance get/set operations."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Test setting different white balance modes
        wb_modes = await camera.get_wb_range()
        assert isinstance(wb_modes, list)
        assert "off" in wb_modes

        for mode in wb_modes:
            await camera.set_auto_wb_once(mode)

            current_wb = await camera.get_wb()
            assert current_wb == mode

        await camera.close()


class TestMockBaslerImageEnhancement:
    """Test image enhancement functionality."""

    @pytest.mark.asyncio
    async def test_image_enhancement_toggle(self):
        """Test image enhancement enable/disable."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Test getting initial state
        initial_state = await camera.get_image_quality_enhancement()
        assert isinstance(initial_state, bool)

        # Test setting enhancement
        await camera.set_image_quality_enhancement(True)
        assert await camera.get_image_quality_enhancement() is True

        # Test disabling enhancement
        await camera.set_image_quality_enhancement(False)
        assert await camera.get_image_quality_enhancement() is False

        await camera.close()

    @pytest.mark.asyncio
    async def test_enhancement_initialization_marker(self):
        """Test that enhancement initialization marker is set."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Initially should not have enhancement marker
        assert not hasattr(camera, "_enhancement_initialized")

        # Enable enhancement should set marker
        await camera.set_image_quality_enhancement(True)
        assert hasattr(camera, "_enhancement_initialized")
        assert camera._enhancement_initialized is True

        await camera.close()

    @pytest.mark.asyncio
    async def test_image_enhancement_effects(self):
        """Test that image enhancement actually affects captured images."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Capture without enhancement
        await camera.set_image_quality_enhancement(False)
        image_no_enhancement = await camera.capture()

        # Capture with enhancement
        await camera.set_image_quality_enhancement(True)
        image_with_enhancement = await camera.capture()

        # Images should be the same size
        assert image_no_enhancement.shape == image_with_enhancement.shape

        # Note: We can't easily test if enhancement is "better", but we can test
        # that the process doesn't crash and produces valid images
        assert isinstance(image_with_enhancement, np.ndarray)
        assert image_with_enhancement.dtype == np.uint8

        await camera.close()


class TestMockBaslerPerformanceAndTiming:
    """Test performance and timing-related functionality."""

    @pytest.mark.asyncio
    async def test_capture_timing_simulation(self):
        """Test that capture timing is simulated based on exposure."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Set very short exposure
        await camera.set_exposure(1000)  # 1ms

        import time

        start_time = time.time()
        await camera.capture()
        short_duration = time.time() - start_time

        # Should be quick (but at least 0.01s due to minimum delay)
        assert short_duration >= 0.01
        assert short_duration < 0.2

        await camera.close()

    @pytest.mark.asyncio
    async def test_async_image_generation(self):
        """Test that image generation is properly async (uses asyncio.to_thread)."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Test multiple concurrent captures
        tasks = [camera.capture() for _ in range(3)]
        results = await asyncio.gather(*tasks)

        # All captures should succeed
        for image in results:
            assert isinstance(image, np.ndarray)

        await camera.close()


class TestMockBaslerDiscoveryAndStaticMethods:
    """Test static discovery methods."""

    def test_get_available_cameras_simple_list(self):
        """Test simple camera discovery."""
        cameras = MockBaslerCameraBackend.get_available_cameras(include_details=False)

        assert isinstance(cameras, list)
        assert len(cameras) == 5  # mock_basler_1 through mock_basler_5
        assert "mock_basler_1" in cameras
        assert "mock_basler_5" in cameras

    def test_get_available_cameras_with_details(self):
        """Test detailed camera discovery."""
        cameras = MockBaslerCameraBackend.get_available_cameras(include_details=True)

        assert isinstance(cameras, dict)
        assert len(cameras) == 5

        # Check first camera details
        cam1_details = cameras["mock_basler_1"]
        assert cam1_details["serial_number"] == "12345001"  # Actual format includes padding
        assert cam1_details["model"] == "acA1920-40uc"
        assert cam1_details["vendor"] == "Basler AG"
        assert cam1_details["device_class"] == "BaslerUsb"
        assert cam1_details["user_defined_name"] == "mock_basler_1"

    @pytest.mark.asyncio
    async def test_initialization_with_non_standard_camera_name(self):
        """Test initialization with camera name not in standard discovery list."""
        camera = MockBaslerCameraBackend("custom_mock_camera_name")

        # Should work despite not being in standard list
        success, cam_obj, remote_obj = await camera.initialize()
        assert success is True
        assert cam_obj is not None
        assert remote_obj is None

        await camera.close()


class TestMockBaslerCleanupAndResourceManagement:
    """Test resource cleanup and management."""

    @pytest.mark.asyncio
    async def test_close_cleanup(self):
        """Test proper cleanup on close."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Verify initialized state
        assert camera.initialized is True
        # Note: MockBaslerCameraBackend doesn't set camera attribute like real backend
        # It uses different internal state management

        # Close camera
        await camera.close()

        # Verify cleanup
        assert camera.initialized is False
        assert camera.camera is None  # Should remain None
        assert camera._grabbing is False

    @pytest.mark.asyncio
    async def test_multiple_close_calls(self):
        """Test that multiple close calls don't cause errors."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Multiple close calls should not raise errors
        await camera.close()
        await camera.close()
        await camera.close()

        assert camera.initialized is False

    @pytest.mark.asyncio
    async def test_capture_after_close(self):
        """Test capture attempt after close."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()
        await camera.close()

        # Should raise error
        with pytest.raises(CameraConnectionError, match="is not initialized"):
            await camera.capture()


class TestMockBaslerEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""

    @pytest.mark.asyncio
    async def test_image_generation_fallback(self):
        """Test image generation fallback on errors."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Test the actual error handling behavior by patching within the capture method
        # We need to patch the image generation at the right level to trigger fallback
        def failing_generation(self):
            # This should trigger the fallback in the actual implementation
            raise RuntimeError("Simulated image generation error")

        # The implementation catches exceptions and re-raises as CameraCaptureError
        # Let's test that the error handling works correctly
        with patch.object(camera, "_generate_synthetic_image", side_effect=failing_generation):
            with pytest.raises(CameraCaptureError, match="Failed to capture image from mock camera"):
                await camera.capture()

        await camera.close()

    @pytest.mark.asyncio
    async def test_enhancement_error_handling(self):
        """Test image enhancement error handling."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()
        await camera.set_image_quality_enhancement(True)

        # Mock cv2.cvtColor to raise an error during enhancement
        with patch("cv2.cvtColor", side_effect=RuntimeError("Enhancement error")):
            image = await camera.capture()

            # Should still succeed, using original image
            assert isinstance(image, np.ndarray)

        await camera.close()

    @pytest.mark.asyncio
    async def test_extreme_roi_values(self):
        """Test ROI with extreme but valid values."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Test very small ROI
        await camera.set_ROI(0, 0, 1, 1)

        image = await camera.capture()
        # ROI should affect the generated image size
        assert image.shape == (1, 1, 3), f"Expected (1, 1, 3) for 1x1 ROI, got {image.shape}"

        await camera.close()

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test concurrent camera operations."""
        camera = MockBaslerCameraBackend("test_cam")
        await camera.initialize()

        # Test concurrent captures and parameter changes
        async def capture_task():
            return await camera.capture()

        async def config_task():
            await camera.set_exposure(30000)
            await camera.set_gain(5.0)

        # Run concurrently
        capture_results, _ = await asyncio.gather(asyncio.gather(*[capture_task() for _ in range(3)]), config_task())

        # All captures should succeed
        for image in capture_results:
            assert isinstance(image, np.ndarray)

        await camera.close()
