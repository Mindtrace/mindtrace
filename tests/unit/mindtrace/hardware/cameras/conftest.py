import asyncio
import os
import pathlib
import pytest
import pytest_asyncio


@pytest.fixture(autouse=True)
def fast_camera_sleep_and_imwrite(monkeypatch, request):
    """Pytest fixture to speed up camera unit tests.

    - Skip the 0.1s settle sleep used only in HDR capture
    - Replace cv2.imwrite with a fast placeholder write
    - Replace mock camera image generation/enhancement with lightweight ops
      (but skip this for tests that specifically need to test image generation)

    This avoids affecting retry timing assertions elsewhere.
    """
    # Check if this is a test that needs real image generation
    test_name = getattr(request.node, 'name', '')
    needs_real_image_generation = any(pattern in test_name for pattern in [
        'test_different_image_patterns',
        'test_auto_pattern_rotation', 
        'test_exposure_and_gain_effects_on_image',
        'test_roi_get_set_cycle',
        'test_extreme_roi_values',
        'test_checkerboard_size_parameter'
    ])
    
    # Patch camera_manager asyncio.sleep: skip only the 0.1s settle used in HDR
    try:
        import mindtrace.hardware.cameras.core.camera_manager as cm

        _orig_sleep = cm.asyncio.sleep

        async def _fast_sleep(delay: float, *args, **kwargs):
            # Skip only the small settle delay used by HDR capture
            if abs(delay - 0.1) < 1e-6:
                return None
            return await _orig_sleep(delay, *args, **kwargs)

        monkeypatch.setattr(cm.asyncio, "sleep", _fast_sleep, raising=False)
    except Exception:
        pass

    # Patch cv2.imwrite to create an empty file quickly
    try:
        import cv2  # noqa: F401

        def _fast_imwrite(path, img):  # type: ignore[no-redef]
            p = pathlib.Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "wb") as f:
                f.write(b"")
            return True

        monkeypatch.setattr("cv2.imwrite", _fast_imwrite, raising=False)
    except Exception:
        pass

    # Patch mock camera image generation to be lightweight (but skip for image generation tests)
    if not needs_real_image_generation:
        try:
            import numpy as np  # noqa: F401
            from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend

            def _fast_generate_basler(self):  # type: ignore[no-redef]
                return np.zeros((480, 640, 3), dtype=np.uint8)

            def _no_enhance_b(self, img):  # type: ignore[no-redef]
                return img

            monkeypatch.setattr(MockBaslerCameraBackend, "_generate_synthetic_image", _fast_generate_basler, raising=False)
            monkeypatch.setattr(MockBaslerCameraBackend, "_enhance_image", _no_enhance_b, raising=False)
        except Exception:
            pass

    yield


@pytest.fixture(autouse=True)
def enforce_timing_for_concurrency_test(monkeypatch, request):
    """Enforce timing for the sequential concurrency timing test.
    
    Only for the sequential concurrency timing test, ensure each capture has a small delay so the measured time 
    reflects sequential execution without significantly slowing the suite.
    """
    if request.node and request.node.name == "test_concurrent_capture_limiting":
        try:
            from mindtrace.hardware.cameras.backends.basler.mock_basler_camera_backend import MockBaslerCameraBackend
 
            original_capture = MockBaslerCameraBackend.capture

            async def _slightly_slow_capture(self, *args, **kwargs):  # type: ignore[no-redef]
                # Add ~0.08s so 3 sequential captures >= 0.24s
                await asyncio.sleep(0.08)
                return await original_capture(self, *args, **kwargs)

            monkeypatch.setattr(MockBaslerCameraBackend, "capture", _slightly_slow_capture, raising=False)
        except Exception:
            pass
    yield 


# ===== Moved fixtures from test_cameras.py =====


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def camera_manager():
    """Async camera manager with mocks enabled."""
    from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager as CameraManager

    manager = CameraManager(include_mocks=True)
    yield manager
    try:
        await manager.close(None)
    except Exception:
        pass


@pytest_asyncio.fixture
async def mock_basler_camera():
    """Mock Basler backend instance."""
    from mindtrace.hardware.cameras.backends.basler import MockBaslerCameraBackend

    camera = MockBaslerCameraBackend(camera_name="mock_basler_1", camera_config=None)
    yield camera
    try:
        await camera.close()
    except Exception:
        pass


@pytest_asyncio.fixture
async def temp_config_file():
    """Temporary configuration file for camera tests."""
    import json
    import tempfile

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
    try:
        os.unlink(temp_path)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _disable_real_opencv_camera_discovery(monkeypatch):
    try:
        from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import OpenCVCameraBackend

        def _fake_get_available_cameras(include_details: bool = False):
            return {} if include_details else []

        monkeypatch.setattr(OpenCVCameraBackend, "get_available_cameras", staticmethod(_fake_get_available_cameras))
    except Exception:
        pass 
