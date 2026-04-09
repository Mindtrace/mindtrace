"""Focused tests for MockGenICamCameraBackend behavior."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

import mindtrace.hardware.cameras.backends.genicam.mock_genicam_camera_backend as mock_genicam_module
from mindtrace.hardware.cameras.backends.genicam.mock_genicam_camera_backend import MockGenICamCameraBackend
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraInitializationError,
    CameraNotFoundError,
    CameraTimeoutError,
)


@pytest.fixture(autouse=True)
def fast_backend_sleep(monkeypatch):
    async def _sleep(_delay):
        return None

    monkeypatch.setattr(mock_genicam_module.asyncio, "sleep", _sleep)


def make_camera(camera_name="MOCK_KEYENCE_001", **kwargs):
    kwargs.setdefault("synthetic_width", 8)
    kwargs.setdefault("synthetic_height", 6)
    kwargs.setdefault("synthetic_overlay_text", False)
    return MockGenICamCameraBackend(camera_name, **kwargs)


def test_available_cameras_formats():
    cams = MockGenICamCameraBackend.get_available_cameras()
    details = MockGenICamCameraBackend.get_available_cameras(include_details=True)
    assert isinstance(cams, list)
    assert "MOCK_KEYENCE_001" in cams
    assert isinstance(details, dict)
    assert details["MOCK_KEYENCE_001"]["vendor"] == "KEYENCE"


@pytest.mark.parametrize(
    ("vendor", "expected_integer_exposure"),
    [("KEYENCE", True), ("BASLER", False), ("FLIR", False)],
)
def test_vendor_quirks_match_vendor(vendor, expected_integer_exposure):
    cam = make_camera(vendor=vendor)
    assert cam.vendor_quirks["use_integer_exposure"] is expected_integer_exposure
    assert cam.vendor_quirks["exposure_node_name"] == "ExposureTime"
    assert cam.vendor_quirks["gain_node_name"] == "Gain"


def test_invalid_buffer_count_rejected():
    with pytest.raises(CameraConfigurationError):
        MockGenICamCameraBackend("MOCK_KEYENCE_001", buffer_count=0)


def test_invalid_timeout_rejected():
    with pytest.raises(CameraConfigurationError, match="Timeout must be at least 100ms"):
        MockGenICamCameraBackend("MOCK_KEYENCE_001", timeout_ms=99)


class TestInitialization:
    @pytest.mark.asyncio
    async def test_initialize_missing_camera_raises(self):
        cam = make_camera("does_not_exist")
        with pytest.raises(CameraNotFoundError):
            await cam.initialize()

    @pytest.mark.asyncio
    async def test_initialize_fail_init_raises(self):
        cam = make_camera("MOCK_KEYENCE_001", simulate_fail_init=True)
        with pytest.raises(CameraInitializationError, match="Simulated initialization failure"):
            await cam.initialize()

    @pytest.mark.asyncio
    async def test_initialize_success_returns_mock_objects(self):
        cam = make_camera("MOCK_KEYENCE_001", vendor="KEYENCE")

        success, camera_object, device_info = await cam.initialize()

        assert success is True
        assert cam.initialized is True
        assert camera_object == {"type": "mock_genicam", "name": "MOCK_KEYENCE_001"}
        assert device_info["serial_number"] == cam.serial_number
        assert device_info["vendor"] == "KEYENCE"

    @pytest.mark.asyncio
    async def test_initialize_imports_existing_config_file(self, tmp_path):
        config_path = tmp_path / "camera.json"
        config_path.write_text("{}")
        cam = make_camera("MOCK_KEYENCE_001", camera_config=str(config_path))
        cam.import_config = AsyncMock()

        await cam.initialize()

        cam.import_config.assert_awaited_once_with(str(config_path))


class TestExposureAndTrigger:
    @pytest.mark.asyncio
    async def test_get_exposure_range_requires_initialization(self):
        cam = make_camera("MOCK_KEYENCE_001")
        with pytest.raises(CameraConnectionError):
            await cam.get_exposure_range()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("vendor", "expected_range"),
        [
            ("KEYENCE", [10.0, 10000000.0]),
            ("BASLER", [1.0, 1000000.0]),
            ("FLIR", [1.0, 5000000.0]),
        ],
    )
    async def test_get_exposure_range_matches_vendor(self, vendor, expected_range):
        cam = make_camera("MOCK_KEYENCE_001", vendor=vendor)
        await cam.initialize()
        assert await cam.get_exposure_range() == expected_range

    @pytest.mark.asyncio
    async def test_set_exposure_requires_initialization(self):
        cam = make_camera("MOCK_KEYENCE_001")
        with pytest.raises(CameraConnectionError):
            await cam.set_exposure(1000)

    @pytest.mark.asyncio
    async def test_get_exposure_requires_initialization(self):
        cam = make_camera("MOCK_KEYENCE_001")
        with pytest.raises(CameraConnectionError):
            await cam.get_exposure()

    @pytest.mark.asyncio
    async def test_keyence_exposure_casts_to_int(self):
        cam = make_camera("MOCK_KEYENCE_001", vendor="KEYENCE")
        await cam.initialize()

        await cam.set_exposure(1234.9)

        assert cam.exposure_time == 1234.0
        assert await cam.get_exposure() == 1234.0

    @pytest.mark.asyncio
    async def test_non_keyence_exposure_keeps_float(self):
        cam = make_camera("MOCK_BASLER_001", vendor="BASLER")
        await cam.initialize()

        await cam.set_exposure(1234.9)

        assert cam.exposure_time == 1234.9
        assert await cam.get_exposure() == 1234.9

    @pytest.mark.asyncio
    async def test_exposure_out_of_range_raises(self):
        cam = make_camera("MOCK_BASLER_001", vendor="BASLER")
        await cam.initialize()
        with pytest.raises(CameraConfigurationError):
            await cam.set_exposure(2_000_000)

    @pytest.mark.asyncio
    async def test_get_triggermode_defaults_before_init(self):
        cam = make_camera("MOCK_KEYENCE_001")
        assert await cam.get_triggermode() == "continuous"

    @pytest.mark.asyncio
    async def test_set_triggermode_requires_initialization(self):
        cam = make_camera("MOCK_KEYENCE_001")
        with pytest.raises(CameraConnectionError):
            await cam.set_triggermode("trigger")

    @pytest.mark.asyncio
    async def test_set_triggermode_rejects_invalid_mode(self):
        cam = make_camera("MOCK_KEYENCE_001")
        await cam.initialize()
        with pytest.raises(CameraConfigurationError, match="Invalid trigger mode"):
            await cam.set_triggermode("invalid")

    @pytest.mark.asyncio
    async def test_set_triggermode_updates_mode(self):
        cam = make_camera("MOCK_KEYENCE_001")
        await cam.initialize()

        await cam.set_triggermode("trigger")

        assert await cam.get_triggermode() == "trigger"


class TestCaptureAndImages:
    @pytest.mark.asyncio
    async def test_capture_requires_initialization(self):
        cam = make_camera("MOCK_KEYENCE_001")
        with pytest.raises(CameraConnectionError):
            await cam.capture()

    @pytest.mark.asyncio
    async def test_capture_fail_capture_raises(self):
        cam = make_camera("MOCK_KEYENCE_001", simulate_fail_capture=True)
        await cam.initialize()
        with pytest.raises(CameraCaptureError, match="Simulated capture failure"):
            await cam.capture()

    @pytest.mark.asyncio
    async def test_capture_timeout_raises(self):
        cam = make_camera("MOCK_KEYENCE_001", simulate_timeout=True)
        await cam.initialize()
        with pytest.raises(CameraTimeoutError, match="Simulated timeout"):
            await cam.capture()

    @pytest.mark.asyncio
    async def test_capture_returns_image_and_increments_counter(self):
        cam = make_camera("MOCK_KEYENCE_001")
        await cam.initialize()

        image = await cam.capture()

        assert image.shape == (6, 8, 3)
        assert image.dtype == np.uint8
        assert cam.image_counter == 1

    @pytest.mark.asyncio
    async def test_capture_uses_enhancement_when_enabled(self):
        cam = make_camera("MOCK_KEYENCE_001", img_quality_enhancement=True)
        await cam.initialize()
        base_image = np.zeros((6, 8, 3), dtype=np.uint8)
        enhanced_image = np.ones((6, 8, 3), dtype=np.uint8)
        cam._generate_synthetic_image = AsyncMock(return_value=base_image)
        cam._enhance_image = AsyncMock(return_value=enhanced_image)

        image = await cam.capture()

        assert np.array_equal(image, enhanced_image)
        cam._enhance_image.assert_awaited_once_with(base_image)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("pattern", ["gradient", "checkerboard", "circular", "noise"])
    async def test_generate_synthetic_image_supports_explicit_patterns(self, pattern):
        width = 60 if pattern == "checkerboard" else 8
        height = 60 if pattern == "checkerboard" else 6
        cam = make_camera("MOCK_KEYENCE_001", synthetic_pattern=pattern, synthetic_width=width, synthetic_height=height)
        image = await cam._generate_synthetic_image()

        assert image.shape == (height, width, 3)
        assert image.dtype == np.uint8

    @pytest.mark.asyncio
    @pytest.mark.parametrize("vendor", ["KEYENCE", "BASLER", "FLIR"])
    async def test_generate_synthetic_image_auto_mode_handles_vendor_colors(self, vendor):
        cam = make_camera("MOCK_KEYENCE_001", vendor=vendor, synthetic_pattern="auto")

        image = await cam._generate_synthetic_image()

        assert image.shape == (6, 8, 3)
        assert image.dtype == np.uint8

    @pytest.mark.asyncio
    async def test_generate_synthetic_image_with_overlay_text(self):
        cam = make_camera("MOCK_KEYENCE_001", synthetic_pattern="gradient", synthetic_overlay_text=True)

        image = await cam._generate_synthetic_image()

        assert image.shape == (6, 8, 3)

    @pytest.mark.asyncio
    async def test_enhance_image_returns_enhanced_image(self):
        cam = make_camera("MOCK_KEYENCE_001")
        image = np.zeros((6, 8, 3), dtype=np.uint8)

        enhanced = await cam._enhance_image(image)

        assert enhanced.shape == image.shape
        assert enhanced.dtype == image.dtype

    @pytest.mark.asyncio
    async def test_enhance_image_returns_original_on_failure(self, monkeypatch):
        cam = make_camera("MOCK_KEYENCE_001")
        cam.logger.error = MagicMock()
        image = np.zeros((6, 8, 3), dtype=np.uint8)

        async def raise_from_to_thread(_func):
            raise RuntimeError("boom")

        monkeypatch.setattr(mock_genicam_module.asyncio, "to_thread", raise_from_to_thread)

        result = await cam._enhance_image(image)

        assert result is image
        cam.logger.error.assert_called_once()


class TestConnectionAndLifecycle:
    @pytest.mark.asyncio
    async def test_check_connection_false_when_uninitialized(self):
        cam = make_camera("MOCK_KEYENCE_001")
        assert await cam.check_connection() is False

    @pytest.mark.asyncio
    async def test_check_connection_true_with_valid_capture(self):
        cam = make_camera("MOCK_KEYENCE_001")
        await cam.initialize()
        cam.capture = AsyncMock(return_value=np.zeros((2, 2, 3), dtype=np.uint8))

        assert await cam.check_connection() is True

    @pytest.mark.asyncio
    async def test_check_connection_false_when_capture_raises(self):
        cam = make_camera("MOCK_KEYENCE_001")
        await cam.initialize()
        cam.capture = AsyncMock(side_effect=CameraCaptureError("boom"))
        cam.logger.warning = MagicMock()

        assert await cam.check_connection() is False
        cam.logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_resets_initialized_state(self):
        cam = make_camera("MOCK_KEYENCE_001")
        await cam.initialize()

        await cam.close()

        assert cam.initialized is False

    @pytest.mark.asyncio
    async def test_close_is_noop_when_uninitialized(self):
        cam = make_camera("MOCK_KEYENCE_001")
        await cam.close()
        assert cam.initialized is False


class TestGainRoiTimeoutAndConfig:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("vendor", "expected_range"),
        [("KEYENCE", [1.0, 7.0]), ("BASLER", [0.0, 48.0]), ("FLIR", [1.0, 16.0])],
    )
    async def test_get_gain_range_matches_vendor(self, vendor, expected_range):
        cam = make_camera("MOCK_KEYENCE_001", vendor=vendor)
        assert await cam.get_gain_range() == expected_range

    @pytest.mark.asyncio
    async def test_get_gain_requires_initialization(self):
        cam = make_camera("MOCK_KEYENCE_001")
        with pytest.raises(CameraConnectionError):
            await cam.get_gain()

    @pytest.mark.asyncio
    async def test_set_gain_requires_initialization(self):
        cam = make_camera("MOCK_KEYENCE_001")
        with pytest.raises(CameraConnectionError):
            await cam.set_gain(2.0)

    @pytest.mark.asyncio
    async def test_set_gain_rejects_out_of_range_value(self):
        cam = make_camera("MOCK_KEYENCE_001", vendor="KEYENCE")
        await cam.initialize()
        with pytest.raises(CameraConfigurationError, match="outside valid range"):
            await cam.set_gain(10.0)

    @pytest.mark.asyncio
    async def test_set_gain_updates_gain(self):
        cam = make_camera("MOCK_KEYENCE_001")
        await cam.initialize()

        await cam.set_gain(3.5)

        assert await cam.get_gain() == 3.5

    @pytest.mark.asyncio
    async def test_set_roi_requires_initialization(self):
        cam = make_camera("MOCK_KEYENCE_001")
        with pytest.raises(CameraConnectionError):
            await cam.set_ROI(0, 0, 4, 4)

    @pytest.mark.asyncio
    async def test_set_roi_rejects_invalid_dimensions(self):
        cam = make_camera("MOCK_KEYENCE_001")
        await cam.initialize()
        with pytest.raises(CameraConfigurationError, match="Invalid ROI dimensions"):
            await cam.set_ROI(0, 0, 0, 4)

    @pytest.mark.asyncio
    async def test_set_roi_rejects_invalid_offsets(self):
        cam = make_camera("MOCK_KEYENCE_001")
        await cam.initialize()
        with pytest.raises(CameraConfigurationError, match="Invalid ROI offsets"):
            await cam.set_ROI(-1, 0, 4, 4)

    @pytest.mark.asyncio
    async def test_set_roi_rejects_out_of_bounds_region(self):
        cam = make_camera("MOCK_KEYENCE_001")
        await cam.initialize()
        with pytest.raises(CameraConfigurationError, match="exceeds sensor bounds"):
            await cam.set_ROI(6, 4, 4, 4)

    @pytest.mark.asyncio
    async def test_get_roi_requires_initialization(self):
        cam = make_camera("MOCK_KEYENCE_001")
        with pytest.raises(CameraConnectionError):
            await cam.get_ROI()

    @pytest.mark.asyncio
    async def test_set_and_get_roi(self):
        cam = make_camera("MOCK_KEYENCE_001")
        await cam.initialize()

        await cam.set_ROI(1, 1, 4, 4)
        roi = await cam.get_ROI()
        roi["x"] = 99

        assert cam.roi == {"x": 1, "y": 1, "width": 4, "height": 4}

    @pytest.mark.asyncio
    async def test_reset_roi_requires_initialization(self):
        cam = make_camera("MOCK_KEYENCE_001")
        with pytest.raises(CameraConnectionError):
            await cam.reset_ROI()

    @pytest.mark.asyncio
    async def test_reset_roi_restores_full_sensor(self):
        cam = make_camera("MOCK_KEYENCE_001")
        await cam.initialize()
        await cam.set_ROI(1, 1, 4, 4)

        await cam.reset_ROI()

        assert cam.roi == {"x": 0, "y": 0, "width": 8, "height": 6}

    @pytest.mark.asyncio
    async def test_set_capture_timeout_rejects_negative_value(self):
        cam = make_camera("MOCK_KEYENCE_001")
        with pytest.raises(ValueError, match="non-negative"):
            await cam.set_capture_timeout(-1)

    @pytest.mark.asyncio
    async def test_capture_timeout_round_trip(self):
        cam = make_camera("MOCK_KEYENCE_001")

        await cam.set_capture_timeout(250)

        assert await cam.get_capture_timeout() == 250

    @pytest.mark.asyncio
    async def test_import_config_missing_file_raises(self, tmp_path):
        cam = make_camera("MOCK_KEYENCE_001")
        with pytest.raises(CameraConfigurationError, match="Configuration file not found"):
            await cam.import_config(str(tmp_path / "missing.json"))

    @pytest.mark.asyncio
    async def test_import_config_updates_camera_settings(self, tmp_path):
        config_path = tmp_path / "camera.json"
        config_path.write_text(
            json.dumps(
                {
                    "exposure_time": 1200,
                    "gain": 3.0,
                    "trigger_mode": "trigger",
                    "roi": {"x": 1, "y": 2, "width": 4, "height": 3},
                    "image_enhancement": True,
                }
            )
        )
        cam = make_camera("MOCK_KEYENCE_001")
        await cam.initialize()

        await cam.import_config(str(config_path))

        assert cam.exposure_time == 1200.0
        assert cam.gain == 3.0
        assert cam.triggermode == "trigger"
        assert cam.roi == {"x": 1, "y": 2, "width": 4, "height": 3}
        assert cam.img_quality_enhancement is True

    @pytest.mark.asyncio
    async def test_import_config_wraps_invalid_json(self, tmp_path):
        config_path = tmp_path / "invalid.json"
        config_path.write_text("{invalid json")
        cam = make_camera("MOCK_KEYENCE_001")
        await cam.initialize()

        with pytest.raises(CameraConfigurationError, match="Failed to import configuration"):
            await cam.import_config(str(config_path))

    @pytest.mark.asyncio
    async def test_export_config_requires_initialization(self, tmp_path):
        cam = make_camera("MOCK_KEYENCE_001")
        with pytest.raises(CameraConnectionError):
            await cam.export_config(str(tmp_path / "camera.json"))

    @pytest.mark.asyncio
    async def test_export_config_writes_expected_json(self, tmp_path):
        config_path = tmp_path / "nested" / "camera.json"
        cam = make_camera("MOCK_KEYENCE_001", vendor="KEYENCE")
        await cam.initialize()
        await cam.set_gain(4.0)
        await cam.set_exposure(1500)
        await cam.set_triggermode("trigger")
        await cam.set_ROI(1, 1, 4, 4)

        with patch("mindtrace.hardware.cameras.backends.genicam.mock_genicam_camera_backend.time.time", return_value=123.0):
            await cam.export_config(str(config_path))

        config_data = json.loads(config_path.read_text())
        assert config_data["camera_type"] == "mock_genicam"
        assert config_data["camera_name"] == "MOCK_KEYENCE_001"
        assert config_data["vendor"] == "KEYENCE"
        assert config_data["timestamp"] == 123.0
        assert config_data["exposure_time"] == 1500.0
        assert config_data["gain"] == 4.0
        assert config_data["trigger_mode"] == "trigger"
        assert config_data["roi"] == {"x": 1, "y": 1, "width": 4, "height": 4}

    @pytest.mark.asyncio
    async def test_export_config_wraps_write_errors(self, tmp_path):
        config_path = tmp_path / "camera.json"
        cam = make_camera("MOCK_KEYENCE_001")
        await cam.initialize()

        with patch("builtins.open", side_effect=OSError("disk full")):
            with pytest.raises(CameraConfigurationError, match="Failed to export configuration"):
                await cam.export_config(str(config_path))
