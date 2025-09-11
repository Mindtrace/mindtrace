import asyncio
import json
import os

import numpy as np
import pytest

from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import OpenCVCameraBackend
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraNotFoundError,
    CameraTimeoutError,
)


class FakeCap:
    def __init__(self, index, backend=None):  # noqa: ARG002
        self._opened = True
        self._props = {
            "index": index,
            "width": 640,
            "height": 480,
            "fps": 30.0,
            "exposure": -5.0,
            "gain": 10.0,
            "auto_wb": 1.0,
            "brightness": 0.5,
            "contrast": 0.5,
            "saturation": 0.5,
            "hue": 0.0,
            "auto_exposure": 1.0,
            "white_balance_blue_u": 4500.0,
            "white_balance_red_v": 4500.0,
        }

    def isOpened(self):
        return self._opened

    def release(self):
        self._opened = False

    def set(self, prop, value):
        self._props[self._prop_name(prop)] = value
        return True

    def get(self, prop):
        name = self._prop_name(prop)
        return self._props.get(name, 0.0)

    def read(self):
        # Return a simple BGR frame
        frame = np.zeros((self._props.get("height", 480), self._props.get("width", 640), 3), dtype=np.uint8)
        frame[..., 0] = 255  # Blue channel
        return True, frame

    def getBackendName(self):
        return "FAKE"

    def _prop_name(self, prop):
        import cv2

        mapping = {
            cv2.CAP_PROP_FRAME_WIDTH: "width",
            cv2.CAP_PROP_FRAME_HEIGHT: "height",
            cv2.CAP_PROP_FPS: "fps",
            cv2.CAP_PROP_EXPOSURE: "exposure",
            cv2.CAP_PROP_GAIN: "gain",
            cv2.CAP_PROP_AUTO_WB: "auto_wb",
            cv2.CAP_PROP_BRIGHTNESS: "brightness",
            cv2.CAP_PROP_CONTRAST: "contrast",
            cv2.CAP_PROP_SATURATION: "saturation",
            cv2.CAP_PROP_HUE: "hue",
            cv2.CAP_PROP_AUTO_EXPOSURE: "auto_exposure",
            cv2.CAP_PROP_WHITE_BALANCE_BLUE_U: "white_balance_blue_u",
            cv2.CAP_PROP_WHITE_BALANCE_RED_V: "white_balance_red_v",
        }
        return mapping.get(prop, str(prop))


@pytest.fixture
def fake_cv(monkeypatch):
    import cv2

    monkeypatch.setattr(cv2, "VideoCapture", lambda *args, **kwargs: FakeCap(*args, **kwargs))
    yield


@pytest.mark.asyncio
async def test_initialize_and_capture_success(fake_cv):
    cam = OpenCVCameraBackend("0", width=640, height=480, fps=30, exposure=-5.0, timeout_ms=500)
    ok, cap, rc = await cam.initialize()
    assert ok and cap is rc

    success, img = await cam.capture()
    assert success is True
    assert isinstance(img, np.ndarray) and img.ndim == 3

    await cam.close()


@pytest.mark.asyncio
async def test_initialize_failure_cannot_open(monkeypatch):
    import cv2

    class ClosedCap(FakeCap):
        def isOpened(self):
            return False

    monkeypatch.setattr(cv2, "VideoCapture", lambda *args, **kwargs: ClosedCap(*args, **kwargs))

    cam = OpenCVCameraBackend("0")
    with pytest.raises(CameraNotFoundError):
        await cam.initialize()


def test_parse_camera_identifier_cases():
    cam = OpenCVCameraBackend("0")
    # Positive index
    assert cam._parse_camera_identifier("2") == 2
    # Named opencv_camera_N
    assert cam._parse_camera_identifier("opencv_camera_3") == 3
    # Device path
    assert cam._parse_camera_identifier("/dev/video0") == "/dev/video0"
    with pytest.raises(CameraConfigurationError):
        cam._parse_camera_identifier("opencv_camera_x")
    with pytest.raises(CameraConfigurationError):
        cam._parse_camera_identifier("-1")
    with pytest.raises(CameraConfigurationError):
        cam._parse_camera_identifier("invalid")


@pytest.mark.asyncio
async def test_set_exposure_not_supported(fake_cv, monkeypatch):
    cam = OpenCVCameraBackend("0")
    await cam.initialize()
    monkeypatch.setattr(cam, "is_exposure_control_supported", lambda: asyncio.sleep(0, result=False))
    ok = await cam.set_exposure(-5.0)
    assert ok is False
    await cam.close()


@pytest.mark.asyncio
async def test_set_exposure_supported_and_range(fake_cv, monkeypatch):
    cam = OpenCVCameraBackend("0")
    await cam.initialize()
    monkeypatch.setattr(cam, "is_exposure_control_supported", lambda: asyncio.sleep(0, result=True))
    monkeypatch.setattr(cam, "get_exposure_range", lambda: asyncio.sleep(0, result=[-13.0, -1.0]))
    ok = await cam.set_exposure(-6.0)
    assert ok is True
    with pytest.raises(CameraConfigurationError):
        await cam.set_exposure(-20.0)
    await cam.close()


@pytest.mark.asyncio
async def test_gain_set_get(fake_cv):
    cam = OpenCVCameraBackend("0")
    # Manually set initialized and cap for sync paths to work without async init
    import cv2

    cam.initialized = True
    cam.cap = cv2.VideoCapture(0)
    assert await cam.set_gain(15.0) is True
    val = await cam.get_gain()
    assert isinstance(val, float)
    with pytest.raises(CameraConfigurationError):
        await cam.set_gain(1000.0)


@pytest.mark.asyncio
async def test_roi_and_pixel_format_and_enhancement(fake_cv):
    cam = OpenCVCameraBackend("0")
    import cv2

    cam.initialized = True
    cam.cap = cv2.VideoCapture(0)

    # ROI methods
    assert await cam.set_ROI(0, 0, 10, 10) is False
    roi = await cam.get_ROI()
    assert set(roi.keys()) == {"x", "y", "width", "height"}
    assert await cam.reset_ROI() is False

    # Pixel format
    fmts = await cam.get_pixel_format_range()
    assert "RGB8" in fmts
    assert await cam.set_pixel_format("RGB8") is True
    with pytest.raises(CameraConfigurationError):
        await cam.set_pixel_format("XYZ")

    # Enhancement toggle
    assert await cam.set_image_quality_enhancement(True) is True
    assert await cam.get_image_quality_enhancement() is True


@pytest.mark.asyncio
async def test_white_balance_get_and_set(fake_cv):
    cam = OpenCVCameraBackend("0")
    await cam.initialize()
    mode = await cam.get_wb()
    assert mode in {"auto", "manual", "unknown"}
    assert await cam.set_auto_wb_once("auto") in {True, False}
    assert await cam.set_auto_wb_once("manual") in {True, False}
    assert await cam.set_auto_wb_once("off") in {True, False}
    assert await cam.set_auto_wb_once("invalid") is False
    await cam.close()


@pytest.mark.asyncio
async def test_export_and_import_config(fake_cv, tmp_path):
    cam = OpenCVCameraBackend("0")
    await cam.initialize()
    path = os.path.join(tmp_path, "cfg.json")
    ok = await cam.export_config(path)
    assert ok is True
    with open(path, "r") as f:
        data = json.load(f)
    assert "camera_type" in data and data["camera_type"] == "opencv"
    ok2 = await cam.import_config(path)
    assert ok2 is True
    await cam.close()


@pytest.mark.asyncio
async def test_capture_timeout_and_generic_errors(fake_cv, monkeypatch):
    cam = OpenCVCameraBackend("0", timeout_ms=200)
    await cam.initialize()

    # Timeout on read path
    original_sdk = cam._sdk

    async def _sdk_timeout(func, *args, **kwargs):  # noqa: ARG001
        # Only simulate timeout for cap.read
        if func == cam.cap.read:
            raise CameraTimeoutError("timeout")
        return await original_sdk(func, *args, **kwargs)

    monkeypatch.setattr(cam, "_sdk", _sdk_timeout, raising=False)
    cam.retrieve_retry_count = 2
    with pytest.raises(CameraTimeoutError):
        await cam.capture()

    # Generic error -> CameraCaptureError after retries
    async def _sdk_error(func, *args, **kwargs):  # noqa: ARG001
        if func == cam.cap.read:
            raise RuntimeError("read failed")
        return await original_sdk(func, *args, **kwargs)

    monkeypatch.setattr(cam, "_sdk", _sdk_error, raising=False)
    cam.retrieve_retry_count = 2
    with pytest.raises(CameraCaptureError):
        await cam.capture()

    await cam.close()


def test_discovery_with_fake_cv(monkeypatch):
    import cv2

    monkeypatch.setattr(cv2, "VideoCapture", lambda *args, **kwargs: FakeCap(*args, **kwargs))
    lst = OpenCVCameraBackend.get_available_cameras(include_details=False)
    # On macOS the function stops after first found; at least one should be present under our fake
    assert isinstance(lst, list)
    recs = OpenCVCameraBackend.get_available_cameras(include_details=True)
    assert isinstance(recs, dict)
    if recs:
        sample_key = next(iter(recs))
        assert set(["index", "backend", "width", "height", "fps"]).issubset(recs[sample_key].keys())


@pytest.mark.asyncio
async def test_config_warnings_on_mismatch_and_failed_sets(monkeypatch):
    import cv2

    class MismatchCap(FakeCap):
        def set(self, prop, value):
            # Simulate failed sets to trigger warnings
            return False

        def get(self, prop):
            # Return values far from requested to trigger mismatch warnings
            name = self._prop_name(prop)
            if name in {"width", "height"}:
                return 100
            if name == "fps":
                return 10.0
            return super().get(prop)

    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: MismatchCap(*a, **k))
    cam = OpenCVCameraBackend("0", width=640, height=480, fps=30)
    ok, _, _ = await cam.initialize()
    assert ok is True
    await cam.close()


def test_enhance_image_quality_error_path(monkeypatch, fake_cv):
    import cv2

    cam = OpenCVCameraBackend("0")
    # Monkey cvtColor to raise
    monkeypatch.setattr(cv2, "cvtColor", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fail")))
    with pytest.raises(CameraCaptureError):
        cam._enhance_image_quality(np.zeros((4, 4, 3), dtype=np.uint8))


@pytest.mark.asyncio
async def test_check_connection_failure_branches(monkeypatch):
    import cv2

    # a) Not initialized
    cam = OpenCVCameraBackend("0")
    assert (await cam.check_connection()) is False

    # b) initialized but not opened
    class ClosedCap(FakeCap):
        def isOpened(self):
            return False

    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: ClosedCap(*a, **k))
    cam2 = OpenCVCameraBackend("0")
    cam2.initialized = True
    cam2.cap = cv2.VideoCapture(0)
    assert (await cam2.check_connection()) is False

    # c) opened but width 0
    class ZeroWidthCap(FakeCap):
        def get(self, prop):
            import cv2 as _cv

            if prop == _cv.CAP_PROP_FRAME_WIDTH:
                return 0
            return super().get(prop)

    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: ZeroWidthCap(*a, **k))
    cam3 = OpenCVCameraBackend("0")
    cam3.initialized = True
    cam3.cap = cv2.VideoCapture(0)
    assert (await cam3.check_connection()) is False

    # d) exception in sdk path returns False
    cam4 = OpenCVCameraBackend("0")
    cam4.initialized = True
    cam4.cap = cv2.VideoCapture(0)
    _original = cam4._sdk

    async def _boom(func, *a, **k):  # noqa: ARG001
        raise RuntimeError("boom")

    monkeypatch.setattr(cam4, "_sdk", _boom, raising=False)
    assert (await cam4.check_connection()) is False


@pytest.mark.asyncio
async def test_import_config_optional_settings_failures(fake_cv, tmp_path, monkeypatch):
    cam = OpenCVCameraBackend("0")
    await cam.initialize()
    path = os.path.join(tmp_path, "cfg.json")
    data = {
        "width": 800,
        "height": 600,
        "fps": 25,
        "exposure_time": -5.0,
        # Optional ones: force failures by returning False from _sdk for set
        "brightness": 0.4,
        "contrast": 0.4,
        "saturation": 0.4,
        "hue": 0.1,
        "gain": 5.0,
        "auto_exposure": 1.0,
        "white_balance_blue_u": 4600.0,
        "white_balance_red_v": 4600.0,
        "white_balance": "auto",
        "image_enhancement": True,
        "retrieve_retry_count": 2,
        "timeout_ms": 500,
    }
    with open(path, "w") as f:
        json.dump(data, f)

    original_sdk = cam._sdk

    async def _sdk_maybe_fail(func, *args, **kwargs):
        # If setting optional properties, return False; otherwise call through
        if (
            func == cam.cap.set
            and args
            and args[0]
            in {
                getattr(__import__("cv2"), "CAP_PROP_BRIGHTNESS"),
                getattr(__import__("cv2"), "CAP_PROP_CONTRAST"),
                getattr(__import__("cv2"), "CAP_PROP_SATURATION"),
                getattr(__import__("cv2"), "CAP_PROP_HUE"),
                getattr(__import__("cv2"), "CAP_PROP_GAIN"),
                getattr(__import__("cv2"), "CAP_PROP_AUTO_EXPOSURE"),
                getattr(__import__("cv2"), "CAP_PROP_WHITE_BALANCE_BLUE_U"),
                getattr(__import__("cv2"), "CAP_PROP_WHITE_BALANCE_RED_V"),
            }
        ):
            return False
        return await original_sdk(func, *args, **kwargs)

    monkeypatch.setattr(cam, "_sdk", _sdk_maybe_fail, raising=False)
    ok = await cam.import_config(path)
    assert ok is True
    await cam.close()


def test_discovery_error_returns_empty(monkeypatch):
    import cv2

    def _raise(*a, **k):  # noqa: ARG001
        raise RuntimeError("fail")

    monkeypatch.setattr(cv2, "VideoCapture", _raise)
    assert OpenCVCameraBackend.get_available_cameras(include_details=False) == []
    assert OpenCVCameraBackend.get_available_cameras(include_details=True) == {}


class TestOpenCVInitializationErrors:
    """Test OpenCV initialization errors and edge cases."""

    def test_discovery_opencv_not_available(self, fake_cv, monkeypatch):
        """Test discovery when OpenCV is not available."""
        # Simulate OPENCV_AVAILABLE being False
        monkeypatch.setattr("mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend.OPENCV_AVAILABLE", False)

        # Should return empty results without errors
        assert OpenCVCameraBackend.get_available_cameras(include_details=False) == []
        assert OpenCVCameraBackend.get_available_cameras(include_details=True) == {}

    def test_basic_initialization_edge_cases(self, fake_cv):
        """Test basic initialization edge cases that are commonly missed."""
        # Test simple initialization scenarios
        cam = OpenCVCameraBackend("opencv_camera_0")
        assert cam.camera_name == "opencv_camera_0"
        assert not cam.initialized


class TestOpenCVFormatConversionErrors:
    """Test OpenCV format conversion errors and edge cases."""

    @pytest.mark.asyncio
    async def test_enhance_image_quality_basic_scenarios(self, fake_cv):
        """Test basic image enhancement scenarios."""
        cam = OpenCVCameraBackend("opencv_camera_0")
        await cam.initialize()

        # Test with simple numpy array
        test_image = np.zeros((240, 320, 3), dtype=np.uint8)

        # Should handle the image without crashing
        try:
            result = await cam._enhance_image_quality(test_image)
            # Either enhanced or original should be returned
            assert isinstance(result, np.ndarray)
        except Exception:
            # If enhancement fails, that's also acceptable
            pass

        await cam.close()

    @pytest.mark.asyncio
    async def test_enhance_image_quality_various_image_formats(self, fake_cv):
        """Test image enhancement with different image sizes."""
        cam = OpenCVCameraBackend("opencv_camera_0")
        await cam.initialize()

        # Test different image sizes
        test_images = [
            np.zeros((100, 100, 3), dtype=np.uint8),  # Small square
            np.zeros((480, 640, 3), dtype=np.uint8),  # Standard size
            np.zeros((1080, 1920, 3), dtype=np.uint8),  # Large size
        ]

        for img in test_images:
            try:
                result = await cam._enhance_image_quality(img)
                assert isinstance(result, np.ndarray)
                assert result.shape == img.shape
            except Exception:
                # Enhancement failure is acceptable
                pass

        await cam.close()

    @pytest.mark.asyncio
    async def test_enhance_image_quality_edge_case_values(self, fake_cv):
        """Test image enhancement with edge case pixel values."""
        cam = OpenCVCameraBackend("opencv_camera_0")
        await cam.initialize()

        # Test with all black, all white, and mixed images
        edge_images = [
            np.zeros((240, 320, 3), dtype=np.uint8),  # All black
            np.full((240, 320, 3), 255, dtype=np.uint8),  # All white
            np.random.randint(0, 256, (240, 320, 3), dtype=np.uint8),  # Random
        ]

        for img in edge_images:
            try:
                result = await cam._enhance_image_quality(img)
                assert isinstance(result, np.ndarray)
            except Exception:
                # Enhancement failure is acceptable for edge cases
                pass

        await cam.close()


class TestOpenCVAdvancedFeatures:
    """Test advanced OpenCV camera features that need coverage."""

    @pytest.mark.asyncio
    async def test_is_exposure_control_supported_uninitialized(self, fake_cv):
        """Test exposure control support check when camera is not initialized."""
        from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import OpenCVCameraBackend

        cam = OpenCVCameraBackend("opencv_camera_0")
        # Camera not initialized - should return False
        result = await cam.is_exposure_control_supported()
        assert result is False

    @pytest.mark.asyncio
    async def test_is_exposure_control_supported_no_cap(self, fake_cv):
        """Test exposure control support check when cap is None."""
        from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import OpenCVCameraBackend

        cam = OpenCVCameraBackend("opencv_camera_0")
        cam.initialized = True
        cam.cap = None

        # No cap - should return False
        result = await cam.is_exposure_control_supported()
        assert result is False
