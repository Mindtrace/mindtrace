"""Integration tests for OpenCV camera backend.

These tests require a working webcam/camera accessible via OpenCV.
Skip with: pytest -m "not hardware" or set SKIP_HARDWARE_TESTS=1
"""

import os

import pytest

# Skip if SKIP_HARDWARE_TESTS is set
if os.environ.get("SKIP_HARDWARE_TESTS", "0") == "1":
    pytest.skip("Hardware tests disabled via SKIP_HARDWARE_TESTS env var", allow_module_level=True)

from mindtrace.hardware.cameras.core.async_camera import AsyncCamera
from mindtrace.hardware.core.exceptions import (
    CameraConnectionError,
    CameraInitializationError,
    CameraNotFoundError,
)


@pytest.mark.hardware
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
    except (CameraNotFoundError, CameraConnectionError, CameraInitializationError):
        # If no OpenCV cameras available, skip
        pytest.skip("No OpenCV cameras available for default open.")
    except Exception as e:
        # Check for common "no camera" error messages
        error_str = str(e).lower()
        if any(
            msg in error_str for msg in ["no camera", "not found", "cannot open", "no device", "failed to discover"]
        ):
            pytest.skip(f"No OpenCV cameras available: {e}")
        raise
