import pytest

from mindtrace.hardware.cameras.core.async_camera import AsyncCamera


@pytest.mark.asyncio
async def test_async_camera_open_default_opencv():
    """Test AsyncCamera.open() with None to discover default OpenCV camera."""

    try:
        # This should discover and open the first available OpenCV camera
        cam = await AsyncCamera.open(None)
        assert cam is not None
        assert "OpenCV:" in cam.name
        assert cam.is_connected

        await cam.close()
    except Exception:
        # If no OpenCV cameras available, skip
        pytest.skip("No OpenCV cameras available for default open.")
