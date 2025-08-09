import asyncio
import os
import pathlib
import pytest


@pytest.fixture(autouse=True)
def fast_camera_sleep_and_imwrite(monkeypatch):
    """Pytest fixture to speed up camera unit tests.

    - Skip the 0.1s settle sleep used only in HDR capture
    - Replace cv2.imwrite with a fast placeholder write
    - Replace mock camera image generation/enhancement with lightweight ops

    This avoids affecting retry timing assertions elsewhere.
    """
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

    # Patch mock camera image generation to be lightweight
    try:
        import numpy as np  # noqa: F401
        from mindtrace.hardware.cameras.backends.basler.mock_basler import MockBaslerCamera

        def _fast_generate_basler(self):  # type: ignore[no-redef]
            return np.zeros((480, 640, 3), dtype=np.uint8)

        def _no_enhance_b(self, img):  # type: ignore[no-redef]
            return img

        monkeypatch.setattr(MockBaslerCamera, "_generate_synthetic_image", _fast_generate_basler, raising=False)
        monkeypatch.setattr(MockBaslerCamera, "_enhance_image", _no_enhance_b, raising=False)
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
            from mindtrace.hardware.cameras.backends.basler.mock_basler import MockBaslerCamera

            original_capture = MockBaslerCamera.capture

            async def _slightly_slow_capture(self, *args, **kwargs):  # type: ignore[no-redef]
                # Add ~0.08s so 3 sequential captures >= 0.24s
                await asyncio.sleep(0.08)
                return await original_capture(self, *args, **kwargs)

            monkeypatch.setattr(MockBaslerCamera, "capture", _slightly_slow_capture, raising=False)
        except Exception:
            pass
    yield 
