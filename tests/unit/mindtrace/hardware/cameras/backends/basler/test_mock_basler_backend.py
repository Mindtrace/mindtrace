import json
import os
import tempfile

import pytest
import pytest_asyncio

from mindtrace.hardware.cameras.backends.basler import MockBaslerCameraBackend


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
    gain_range = camera.get_gain_range()
    assert isinstance(gain_range, list) and len(gain_range) == 2
    pixel_formats = camera.get_pixel_format_range()
    assert isinstance(pixel_formats, list) and "BGR8" in pixel_formats


@pytest.mark.asyncio
async def test_configuration_compatibility(mock_basler_camera, temp_config_file):
    camera = mock_basler_camera
    await camera.initialize()
    success = await camera.import_config(temp_config_file)
    assert success is True
    assert await camera.get_exposure() == 15000.0
    assert camera.get_gain() == 2.5


@pytest.mark.asyncio
async def test_common_format_export(mock_basler_camera):
    camera = mock_basler_camera
    await camera.initialize()
    await camera.set_exposure(30000)
    camera.set_gain(4.0)
    await camera.set_triggermode("trigger")
    camera.set_image_quality_enhancement(True)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        export_path = f.name

    try:
        success = await camera.export_config(export_path)
        assert success is True
        with open(export_path, "r") as f:
            config = json.load(f)
        assert config["exposure_time"] == 30000
        assert config["gain"] == 4.0
        assert config["trigger_mode"] == "trigger"
        assert config["image_enhancement"] is True
    finally:
        os.unlink(export_path) 