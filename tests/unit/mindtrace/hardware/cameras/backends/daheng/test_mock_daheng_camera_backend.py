"""Tests for Mock Daheng Camera Backend.

Tests the mock Daheng camera implementation for testing and development,
covering initialization, capture, configuration, error simulation, and lifecycle.
"""

import asyncio
import json
import os
import tempfile

import numpy as np
import pytest
import pytest_asyncio

from mindtrace.hardware.cameras.backends.daheng.mock_daheng_camera_backend import MockDahengCameraBackend
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraInitializationError,
    CameraTimeoutError,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def mock_camera():
    """Create a mock Daheng camera instance with fast mode for testing."""
    camera = MockDahengCameraBackend("mock_daheng_1", fast_mode=True)
    try:
        yield camera
    finally:
        if camera.initialized:
            await camera.close()


@pytest_asyncio.fixture
async def initialized_camera():
    """Create and initialize a mock Daheng camera."""
    camera = MockDahengCameraBackend("mock_daheng_1", fast_mode=True)
    await camera.initialize()
    try:
        yield camera
    finally:
        if camera.initialized:
            await camera.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Initialization Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMockDahengInitialization:
    """Test mock Daheng camera initialization."""

    @pytest.mark.asyncio
    async def test_basic_initialization(self, mock_camera):
        """Test that a mock camera can be initialized."""
        success, cam_obj, _ = await mock_camera.initialize()
        assert success is True
        assert cam_obj is not None
        assert mock_camera.initialized is True

    @pytest.mark.asyncio
    async def test_initialization_returns_camera_info(self, mock_camera):
        """Test that initialization returns camera information."""
        success, cam_obj, _ = await mock_camera.initialize()
        assert cam_obj["name"] == "mock_daheng_1"
        assert cam_obj["model"] == "MER2-G-P"
        assert cam_obj["connected"] is True

    @pytest.mark.asyncio
    async def test_initialization_failure_simulation(self):
        """Test simulated initialization failure."""
        camera = MockDahengCameraBackend("test_cam", fast_mode=True, simulate_fail_init=True)
        with pytest.raises(CameraInitializationError):
            await camera.initialize()

    @pytest.mark.asyncio
    async def test_custom_camera_name_allowed(self):
        """Test that custom camera names are allowed for testing flexibility."""
        camera = MockDahengCameraBackend("custom_test_name", fast_mode=True)
        success, _, _ = await camera.initialize()
        assert success is True
        await camera.close()

    @pytest.mark.asyncio
    async def test_default_state(self, mock_camera):
        """Test default state before initialization."""
        assert mock_camera.initialized is False
        assert mock_camera.camera is None
        assert mock_camera.exposure_time == 20000.0
        assert mock_camera.gain == 1.0


class TestMockDahengDiscovery:
    """Test mock Daheng camera discovery."""

    def test_get_available_cameras(self):
        """Test listing available mock cameras."""
        cameras = MockDahengCameraBackend.get_available_cameras()
        assert len(cameras) == 5
        assert "mock_daheng_1" in cameras
        assert "mock_daheng_5" in cameras

    def test_get_available_cameras_with_details(self):
        """Test listing cameras with detailed information."""
        details = MockDahengCameraBackend.get_available_cameras(include_details=True)
        assert len(details) == 5
        assert "mock_daheng_1" in details

        cam_info = details["mock_daheng_1"]
        assert cam_info["vendor"] == "Daheng Imaging"
        assert cam_info["model"] == "MER2-G-P"
        assert "serial_number" in cam_info
        assert "interface" in cam_info


# ═══════════════════════════════════════════════════════════════════════════════
# Capture Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMockDahengCapture:
    """Test mock Daheng camera capture."""

    @pytest.mark.asyncio
    async def test_basic_capture(self, initialized_camera):
        """Test capturing a single image."""
        image = await initialized_camera.capture()
        assert image is not None
        assert isinstance(image, np.ndarray)
        assert len(image.shape) == 3
        assert image.shape[2] == 3  # BGR

    @pytest.mark.asyncio
    async def test_capture_dimensions(self, initialized_camera):
        """Test that captured image has correct dimensions."""
        image = await initialized_camera.capture()
        assert image.shape[0] == initialized_camera.roi["height"]
        assert image.shape[1] == initialized_camera.roi["width"]

    @pytest.mark.asyncio
    async def test_capture_increments_counter(self, initialized_camera):
        """Test that image counter increments with each capture."""
        assert initialized_camera.image_counter == 0
        await initialized_camera.capture()
        assert initialized_camera.image_counter == 1
        await initialized_camera.capture()
        assert initialized_camera.image_counter == 2

    @pytest.mark.asyncio
    async def test_capture_without_initialization(self):
        """Test that capture fails when camera is not initialized."""
        camera = MockDahengCameraBackend("test_cam", fast_mode=True)
        with pytest.raises(CameraConnectionError):
            await camera.capture()

    @pytest.mark.asyncio
    async def test_capture_failure_simulation(self):
        """Test simulated capture failure."""
        camera = MockDahengCameraBackend("test_cam", fast_mode=True, simulate_fail_capture=True)
        await camera.initialize()
        with pytest.raises(CameraCaptureError):
            await camera.capture()
        await camera.close()

    @pytest.mark.asyncio
    async def test_capture_timeout_simulation(self):
        """Test simulated capture timeout."""
        camera = MockDahengCameraBackend("test_cam", fast_mode=True, simulate_timeout=True)
        await camera.initialize()
        with pytest.raises(CameraTimeoutError):
            await camera.capture()
        await camera.close()

    @pytest.mark.asyncio
    async def test_capture_cancellation_simulation(self):
        """Test simulated asyncio cancellation."""
        camera = MockDahengCameraBackend("test_cam", fast_mode=True, simulate_cancel=True)
        await camera.initialize()
        with pytest.raises(asyncio.CancelledError):
            await camera.capture()
        await camera.close()

    @pytest.mark.asyncio
    async def test_multiple_captures(self, initialized_camera):
        """Test multiple sequential captures."""
        images = []
        for _ in range(5):
            img = await initialized_camera.capture()
            images.append(img)

        assert len(images) == 5
        for img in images:
            assert img is not None
            assert isinstance(img, np.ndarray)


# ═══════════════════════════════════════════════════════════════════════════════
# Exposure Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMockDahengExposure:
    """Test mock Daheng exposure control."""

    @pytest.mark.asyncio
    async def test_get_exposure(self, initialized_camera):
        """Test getting exposure time."""
        exposure = await initialized_camera.get_exposure()
        assert exposure == 20000.0

    @pytest.mark.asyncio
    async def test_set_exposure(self, initialized_camera):
        """Test setting exposure time."""
        await initialized_camera.set_exposure(50000)
        exposure = await initialized_camera.get_exposure()
        assert exposure == 50000.0

    @pytest.mark.asyncio
    async def test_set_exposure_out_of_range(self, initialized_camera):
        """Test setting exposure time out of range."""
        with pytest.raises(CameraConfigurationError):
            await initialized_camera.set_exposure(10)  # Below minimum of 20

    @pytest.mark.asyncio
    async def test_get_exposure_range(self, initialized_camera):
        """Test getting exposure range."""
        exposure_range = await initialized_camera.get_exposure_range()
        assert len(exposure_range) == 2
        assert exposure_range[0] < exposure_range[1]


# ═══════════════════════════════════════════════════════════════════════════════
# Gain Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMockDahengGain:
    """Test mock Daheng gain control."""

    @pytest.mark.asyncio
    async def test_get_gain(self, initialized_camera):
        """Test getting gain value."""
        gain = await initialized_camera.get_gain()
        assert gain == 1.0

    @pytest.mark.asyncio
    async def test_set_gain(self, initialized_camera):
        """Test setting gain value."""
        await initialized_camera.set_gain(5.0)
        gain = await initialized_camera.get_gain()
        assert gain == 5.0

    @pytest.mark.asyncio
    async def test_set_gain_out_of_range(self, initialized_camera):
        """Test setting gain out of range."""
        with pytest.raises(CameraConfigurationError):
            await initialized_camera.set_gain(30.0)

    @pytest.mark.asyncio
    async def test_get_gain_range(self, initialized_camera):
        """Test getting gain range."""
        gain_range = await initialized_camera.get_gain_range()
        assert len(gain_range) == 2
        assert gain_range[0] == 0.0
        assert gain_range[1] == 24.0


# ═══════════════════════════════════════════════════════════════════════════════
# Trigger Mode Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMockDahengTriggerMode:
    """Test mock Daheng trigger mode control."""

    @pytest.mark.asyncio
    async def test_get_triggermode(self, initialized_camera):
        """Test getting trigger mode."""
        mode = await initialized_camera.get_triggermode()
        assert mode in ["continuous", "trigger"]

    @pytest.mark.asyncio
    async def test_set_triggermode_continuous(self, initialized_camera):
        """Test setting continuous trigger mode."""
        await initialized_camera.set_triggermode("continuous")
        mode = await initialized_camera.get_triggermode()
        assert mode == "continuous"

    @pytest.mark.asyncio
    async def test_set_triggermode_trigger(self, initialized_camera):
        """Test setting software trigger mode."""
        await initialized_camera.set_triggermode("trigger")
        mode = await initialized_camera.get_triggermode()
        assert mode == "trigger"

    @pytest.mark.asyncio
    async def test_set_invalid_triggermode(self, initialized_camera):
        """Test setting invalid trigger mode."""
        with pytest.raises(CameraConfigurationError):
            await initialized_camera.set_triggermode("invalid")


# ═══════════════════════════════════════════════════════════════════════════════
# ROI Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMockDahengROI:
    """Test mock Daheng ROI control."""

    @pytest.mark.asyncio
    async def test_get_roi(self, initialized_camera):
        """Test getting ROI."""
        roi = await initialized_camera.get_ROI()
        assert "x" in roi
        assert "y" in roi
        assert "width" in roi
        assert "height" in roi

    @pytest.mark.asyncio
    async def test_set_roi(self, initialized_camera):
        """Test setting ROI."""
        await initialized_camera.set_ROI(100, 100, 800, 600)
        roi = await initialized_camera.get_ROI()
        assert roi["x"] == 100
        assert roi["y"] == 100
        assert roi["width"] == 800
        assert roi["height"] == 600

    @pytest.mark.asyncio
    async def test_set_invalid_roi(self, initialized_camera):
        """Test setting invalid ROI."""
        with pytest.raises(CameraConfigurationError):
            await initialized_camera.set_ROI(0, 0, -1, 100)

    @pytest.mark.asyncio
    async def test_reset_roi(self, initialized_camera):
        """Test resetting ROI."""
        await initialized_camera.set_ROI(100, 100, 800, 600)
        await initialized_camera.reset_ROI()
        roi = await initialized_camera.get_ROI()
        assert roi["x"] == 0
        assert roi["y"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# White Balance Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMockDahengWhiteBalance:
    """Test mock Daheng white balance control."""

    @pytest.mark.asyncio
    async def test_get_wb(self, initialized_camera):
        """Test getting white balance mode."""
        wb = await initialized_camera.get_wb()
        assert wb in ["off", "once", "continuous"]

    @pytest.mark.asyncio
    async def test_set_wb(self, initialized_camera):
        """Test setting white balance mode."""
        await initialized_camera.set_auto_wb_once("continuous")
        wb = await initialized_camera.get_wb()
        assert wb == "continuous"

    @pytest.mark.asyncio
    async def test_get_wb_range(self, initialized_camera):
        """Test getting available white balance modes."""
        wb_range = await initialized_camera.get_wb_range()
        assert "off" in wb_range
        assert "once" in wb_range
        assert "continuous" in wb_range


# ═══════════════════════════════════════════════════════════════════════════════
# Pixel Format Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMockDahengPixelFormat:
    """Test mock Daheng pixel format control."""

    @pytest.mark.asyncio
    async def test_get_pixel_format(self, initialized_camera):
        """Test getting current pixel format."""
        fmt = await initialized_camera.get_current_pixel_format()
        assert isinstance(fmt, str)

    @pytest.mark.asyncio
    async def test_set_pixel_format(self, initialized_camera):
        """Test setting pixel format."""
        await initialized_camera.set_pixel_format("Mono8")
        fmt = await initialized_camera.get_current_pixel_format()
        assert fmt == "Mono8"

    @pytest.mark.asyncio
    async def test_set_unsupported_pixel_format(self, initialized_camera):
        """Test setting unsupported pixel format."""
        with pytest.raises(CameraConfigurationError):
            await initialized_camera.set_pixel_format("UnsupportedFormat")

    @pytest.mark.asyncio
    async def test_get_pixel_format_range(self, initialized_camera):
        """Test getting available pixel formats."""
        formats = await initialized_camera.get_pixel_format_range()
        assert len(formats) > 0
        assert "BGR8" in formats


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration Import/Export Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMockDahengConfiguration:
    """Test mock Daheng configuration import/export."""

    @pytest.mark.asyncio
    async def test_export_config(self, initialized_camera):
        """Test exporting camera configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "daheng_config.json")
            await initialized_camera.export_config(config_path)
            assert os.path.exists(config_path)

            with open(config_path) as f:
                config = json.load(f)
            assert config["camera_type"] == "mock_daheng"
            assert config["camera_name"] == "mock_daheng_1"
            assert "exposure_time" in config
            assert "gain" in config

    @pytest.mark.asyncio
    async def test_import_config(self, initialized_camera):
        """Test importing camera configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "daheng_config.json")
            config_data = {
                "exposure_time": 50000.0,
                "gain": 5.0,
                "trigger_mode": "continuous",
            }
            with open(config_path, "w") as f:
                json.dump(config_data, f)

            await initialized_camera.import_config(config_path)
            assert initialized_camera.exposure_time == 50000.0
            assert initialized_camera.gain == 5.0
            assert initialized_camera.triggermode == "continuous"

    @pytest.mark.asyncio
    async def test_import_nonexistent_config(self, initialized_camera):
        """Test importing from nonexistent file."""
        with pytest.raises(CameraConfigurationError):
            await initialized_camera.import_config("/nonexistent/path/config.json")


# ═══════════════════════════════════════════════════════════════════════════════
# Connection Check Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMockDahengConnection:
    """Test mock Daheng connection checking."""

    @pytest.mark.asyncio
    async def test_check_connection_initialized(self, initialized_camera):
        """Test connection check when initialized."""
        result = await initialized_camera.check_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_connection_not_initialized(self, mock_camera):
        """Test connection check when not initialized."""
        result = await mock_camera.check_connection()
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# Capture Timeout Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMockDahengTimeout:
    """Test mock Daheng capture timeout control."""

    @pytest.mark.asyncio
    async def test_get_capture_timeout(self, initialized_camera):
        """Test getting capture timeout."""
        timeout = await initialized_camera.get_capture_timeout()
        assert timeout > 0

    @pytest.mark.asyncio
    async def test_set_capture_timeout(self, initialized_camera):
        """Test setting capture timeout."""
        await initialized_camera.set_capture_timeout(10000)
        timeout = await initialized_camera.get_capture_timeout()
        assert timeout == 10000

    @pytest.mark.asyncio
    async def test_set_negative_timeout(self, initialized_camera):
        """Test setting negative timeout."""
        with pytest.raises(ValueError):
            await initialized_camera.set_capture_timeout(-1)


# ═══════════════════════════════════════════════════════════════════════════════
# Lifecycle Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMockDahengLifecycle:
    """Test mock Daheng camera lifecycle."""

    @pytest.mark.asyncio
    async def test_close(self, initialized_camera):
        """Test closing the camera."""
        await initialized_camera.close()
        assert initialized_camera.initialized is False
        assert initialized_camera.camera is None

    @pytest.mark.asyncio
    async def test_close_and_capture_fails(self, initialized_camera):
        """Test that capture fails after close."""
        await initialized_camera.close()
        with pytest.raises(CameraConnectionError):
            await initialized_camera.capture()

    @pytest.mark.asyncio
    async def test_image_quality_enhancement(self, initialized_camera):
        """Test image quality enhancement setting."""
        assert initialized_camera.get_image_quality_enhancement() is False

        initialized_camera.set_image_quality_enhancement(True)
        assert initialized_camera.get_image_quality_enhancement() is True

        # Capture with enhancement enabled
        image = await initialized_camera.capture()
        assert image is not None

    @pytest.mark.asyncio
    async def test_synthetic_image_patterns(self):
        """Test different synthetic image patterns."""
        for pattern in ["gradient", "checkerboard", "circular", "noise"]:
            camera = MockDahengCameraBackend(
                "test_cam", fast_mode=True, synthetic_pattern=pattern,
                synthetic_width=320, synthetic_height=240,
            )
            await camera.initialize()
            image = await camera.capture()
            assert image is not None
            assert image.shape == (240, 320, 3)
            await camera.close()

    @pytest.mark.asyncio
    async def test_fixture_image_path_returns_deterministic_frame(self):
        """If a fixture image is configured, the mock should return it (resized to ROI).

        Mirrors the MockBasler parity test — feeding a known BGR fixture must
        flow through ``_get_fixture_image`` and surface in ``capture()`` instead
        of the synthetic patterns.
        """
        import numpy as np

        fixture = np.zeros((12, 10, 3), dtype=np.uint8)
        fixture[:, :] = (40, 50, 60)  # BGR

        fd, fixture_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)

        try:
            from PIL import Image

            # Pillow expects RGB; our fixtures are BGR to match backend output.
            Image.fromarray(fixture[..., ::-1]).save(fixture_path)

            camera = MockDahengCameraBackend(
                "fixture_cam",
                mock_image_paths=[fixture_path],
                synthetic_pattern="noise",
                synthetic_overlay_text=False,
                fast_mode=True,
            )
            await camera.initialize()

            fixture_frame = camera._get_fixture_image(width=camera.roi["width"], height=camera.roi["height"])
            assert fixture_frame is not None
            cy = fixture_frame.shape[0] // 2
            cx = fixture_frame.shape[1] // 2
            assert tuple(int(x) for x in fixture_frame[cy, cx]) == (40, 50, 60)

            frame = await camera.capture()
            assert frame.ndim == 3
            assert frame.shape[2] == 3
        finally:
            try:
                os.unlink(fixture_path)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_fixture_image_unset_uses_synthetic(self):
        """Without ``mock_image_paths`` the mock falls back to synthetic patterns."""
        camera = MockDahengCameraBackend(
            "no_fixture_cam",
            synthetic_pattern="gradient",
            synthetic_width=64, synthetic_height=48,
            fast_mode=True,
        )
        await camera.initialize()
        assert camera._get_fixture_image(width=64, height=48) is None
        frame = await camera.capture()
        assert frame.shape == (48, 64, 3)
        await camera.close()

    @pytest.mark.asyncio
    async def test_constructor_validation(self):
        """Test constructor parameter validation."""
        with pytest.raises(CameraConfigurationError):
            MockDahengCameraBackend("test", buffer_count=0)

        with pytest.raises(CameraConfigurationError):
            MockDahengCameraBackend("test", timeout_ms=50)
