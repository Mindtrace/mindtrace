"""Tests for Daheng Camera Backend.

Tests the DahengCameraBackend implementation using a mocked gxipy SDK,
covering initialization, capture, configuration, discovery, and lifecycle.
"""

import asyncio
import sys
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import pytest_asyncio

from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraInitializationError,
    CameraNotFoundError,
    CameraTimeoutError,
    HardwareOperationError,
    SDKNotAvailableError,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Mock gxipy SDK
# ═══════════════════════════════════════════════════════════════════════════════


class MockGxFeature:
    """Mock gxipy feature (ExposureTime, Gain, etc.)."""

    def __init__(self, value=0.0, min_val=0.0, max_val=100000.0, implemented=True):
        self._value = value
        self._min = min_val
        self._max = max_val
        self._implemented = implemented

    def get(self):
        return self._value

    def set(self, value):
        self._value = value

    def get_min(self):
        return self._min

    def get_max(self):
        return self._max

    def is_implemented(self):
        return self._implemented

    def get_range(self):
        return ["Mono8", "BGR8", "RGB8"]

    def send_command(self):
        pass


class MockDataStream:
    """Mock gxipy data stream."""

    def __init__(self, width=1920, height=1080):
        self._width = width
        self._height = height

    def get_image(self, timeout=1000):
        raw = MagicMock()
        raw.get_numpy_array.return_value = np.random.randint(
            0, 255, (self._height, self._width, 3), dtype=np.uint8
        )
        return raw


class MockDahengDevice:
    """Mock gxipy Device (camera object)."""

    def __init__(self, width=1920, height=1080):
        self.ExposureTime = MockGxFeature(10000.0, 20.0, 1000000.0)
        self.ExposureAuto = MockGxFeature(0)
        self.Gain = MockGxFeature(0.0, 0.0, 24.0)
        self.GainAuto = MockGxFeature(0)
        self.TriggerMode = MockGxFeature(0)
        self.TriggerSource = MockGxFeature(0)
        self.TriggerSoftware = MockGxFeature()
        self.AcquisitionMode = MockGxFeature(0)
        self.PixelFormat = MockGxFeature("BGR8")
        self.BalanceWhiteAuto = MockGxFeature(0)
        self.OffsetX = MockGxFeature(0, 0, width)
        self.OffsetY = MockGxFeature(0, 0, height)
        self.Width = MockGxFeature(width, 1, width)
        self.Height = MockGxFeature(height, 1, height)
        self.WidthMax = MockGxFeature(width)
        self.HeightMax = MockGxFeature(height)
        self.data_stream = [MockDataStream(width, height)]
        self._open = True

    def stream_on(self):
        pass

    def stream_off(self):
        pass

    def close_device(self):
        self._open = False


class MockGxDeviceManager:
    """Mock gxipy DeviceManager."""

    def __init__(self):
        self._devices = [
            {"sn": "DH000001", "model_name": "MER2-G-P", "vendor_name": "Daheng Imaging",
             "ip": "192.168.1.100", "user_id": "cam1", "display_name": "Daheng MER2-G-P"},
            {"sn": "DH000002", "model_name": "MARS-G-P", "vendor_name": "Daheng Imaging",
             "ip": "", "user_id": "", "display_name": "Daheng MARS-G-P"},
        ]

    def update_device_list(self):
        return len(self._devices), self._devices

    # The real gxipy API exposes ``update_all_device_list``; the backend uses
    # that name, so the stub mirrors both for forward/back compatibility.
    def update_all_device_list(self):
        return len(self._devices), self._devices

    def open_device_by_sn(self, sn):
        for d in self._devices:
            if d["sn"] == sn:
                return MockDahengDevice()
        raise Exception(f"Device with SN {sn} not found")

    def open_device_by_ip(self, ip):
        for d in self._devices:
            if d.get("ip") == ip:
                return MockDahengDevice()
        raise Exception(f"Device with IP {ip} not found")

    def open_device_by_user_id(self, user_id):
        for d in self._devices:
            if d.get("user_id") == user_id:
                return MockDahengDevice()
        raise Exception(f"Device with user_id {user_id} not found")

    def open_device_by_index(self, index):
        if 1 <= index <= len(self._devices):
            return MockDahengDevice()
        raise Exception(f"Device with index {index} not found")


def _create_mock_gx_module():
    """Create a mock gxipy module."""
    mock_gx = MagicMock()
    mock_gx.DeviceManager = MockGxDeviceManager
    mock_gx.GxTriggerModeEntry.ON = 1
    mock_gx.GxTriggerModeEntry.OFF = 0
    mock_gx.GxTriggerSourceEntry.SOFTWARE = 0
    mock_gx.GxAcquisitionModeEntry.CONTINUOUS = 0
    mock_gx.GxAutoEntry.OFF = 0
    mock_gx.GxAutoEntry.ONCE = 1
    mock_gx.GxAutoEntry.CONTINUOUS = 2
    mock_gx.GxPixelFormatEntry.MONO8 = 0x01080001
    mock_gx.GxPixelFormatEntry.BGR8 = 0x02180015
    mock_gx.GxPixelFormatEntry.RGB8 = 0x02180014
    mock_gx.GxPixelFormatEntry.BAYER_RG8 = 0x01080009
    return mock_gx


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def mock_gxipy(monkeypatch):
    """Inject mock gxipy module into sys.modules and patch the backend module."""
    mock_gx = _create_mock_gx_module()

    # Inject into sys.modules so import gxipy works
    monkeypatch.setitem(sys.modules, "gxipy", mock_gx)

    # Patch the backend module's gx reference and availability flag
    import mindtrace.hardware.cameras.backends.daheng.daheng_camera_backend as backend_mod

    monkeypatch.setattr(backend_mod, "gx", mock_gx)
    monkeypatch.setattr(backend_mod, "GXIPY_AVAILABLE", True)

    return mock_gx


@pytest_asyncio.fixture
async def daheng_camera():
    """Create a DahengCameraBackend instance with mocked SDK."""
    from mindtrace.hardware.cameras.backends.daheng.daheng_camera_backend import DahengCameraBackend

    camera = DahengCameraBackend("DH000001")
    try:
        yield camera
    finally:
        if camera.initialized:
            await camera.close()


@pytest_asyncio.fixture
async def initialized_daheng():
    """Create and initialize a DahengCameraBackend."""
    from mindtrace.hardware.cameras.backends.daheng.daheng_camera_backend import DahengCameraBackend

    camera = DahengCameraBackend("DH000001")
    await camera.initialize()
    try:
        yield camera
    finally:
        if camera.initialized:
            await camera.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Initialization Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDahengInitialization:
    """Test DahengCameraBackend initialization."""

    @pytest.mark.asyncio
    async def test_initialization_by_serial(self, daheng_camera):
        """Test initialization using serial number."""
        success, cam_obj, _ = await daheng_camera.initialize()
        assert success is True
        assert cam_obj is not None
        assert daheng_camera.initialized is True

    @pytest.mark.asyncio
    async def test_initialization_by_ip(self, mock_gxipy):
        """Test initialization using IP address."""
        from mindtrace.hardware.cameras.backends.daheng.daheng_camera_backend import DahengCameraBackend

        camera = DahengCameraBackend("192.168.1.100")
        success, cam_obj, _ = await camera.initialize()
        assert success is True
        await camera.close()

    @pytest.mark.asyncio
    async def test_initialization_by_user_id(self, mock_gxipy):
        """Test initialization using user-defined name."""
        from mindtrace.hardware.cameras.backends.daheng.daheng_camera_backend import DahengCameraBackend

        camera = DahengCameraBackend("cam1")
        success, cam_obj, _ = await camera.initialize()
        assert success is True
        await camera.close()

    @pytest.mark.asyncio
    async def test_initialization_by_index(self, mock_gxipy):
        """Test initialization using index."""
        from mindtrace.hardware.cameras.backends.daheng.daheng_camera_backend import DahengCameraBackend

        camera = DahengCameraBackend("1")
        success, cam_obj, _ = await camera.initialize()
        assert success is True
        await camera.close()

    @pytest.mark.asyncio
    async def test_initialization_camera_not_found(self, mock_gxipy):
        """Test initialization with nonexistent camera."""
        from mindtrace.hardware.cameras.backends.daheng.daheng_camera_backend import DahengCameraBackend

        camera = DahengCameraBackend("NONEXISTENT_SN")
        with pytest.raises((CameraNotFoundError, CameraInitializationError)):
            await camera.initialize()

    @pytest.mark.asyncio
    async def test_re_initialization_skipped(self, initialized_daheng):
        """Test that re-initialization is skipped when already initialized."""
        success, cam_obj, _ = await initialized_daheng.initialize()
        assert success is True

    @pytest.mark.asyncio
    async def test_sdk_not_available(self, monkeypatch):
        """Test that SDKNotAvailableError is raised when gxipy is not available."""
        import mindtrace.hardware.cameras.backends.daheng.daheng_camera_backend as backend_mod

        monkeypatch.setattr(backend_mod, "GXIPY_AVAILABLE", False)

        with pytest.raises(SDKNotAvailableError):
            backend_mod.DahengCameraBackend("test")


# ═══════════════════════════════════════════════════════════════════════════════
# Discovery Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDahengDiscovery:
    """Test DahengCameraBackend discovery."""

    def test_get_available_cameras(self):
        """Test listing available cameras."""
        from mindtrace.hardware.cameras.backends.daheng.daheng_camera_backend import DahengCameraBackend

        cameras = DahengCameraBackend.get_available_cameras()
        assert len(cameras) == 2
        assert "DH000001" in cameras
        assert "DH000002" in cameras

    def test_get_available_cameras_with_details(self):
        """Test listing cameras with detailed info."""
        from mindtrace.hardware.cameras.backends.daheng.daheng_camera_backend import DahengCameraBackend

        details = DahengCameraBackend.get_available_cameras(include_details=True)
        assert "DH000001" in details
        assert details["DH000001"]["model"] == "MER2-G-P"
        assert details["DH000001"]["vendor"] == "Daheng Imaging"
        assert details["DH000001"]["interface"] == "GigE"

    @pytest.mark.asyncio
    async def test_discover_async(self):
        """Test async discovery."""
        from mindtrace.hardware.cameras.backends.daheng.daheng_camera_backend import DahengCameraBackend

        cameras = await DahengCameraBackend.discover_async()
        assert len(cameras) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Capture Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDahengCapture:
    """Test DahengCameraBackend capture."""

    @pytest.mark.asyncio
    async def test_basic_capture(self, initialized_daheng):
        """Test capturing a single image."""
        image = await initialized_daheng.capture()
        assert image is not None
        assert isinstance(image, np.ndarray)
        assert len(image.shape) == 3

    @pytest.mark.asyncio
    async def test_capture_without_initialization(self, daheng_camera):
        """Test capture fails when not initialized."""
        with pytest.raises(CameraConnectionError):
            await daheng_camera.capture()


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDahengConfiguration:
    """Test DahengCameraBackend configuration."""

    @pytest.mark.asyncio
    async def test_exposure_control(self, initialized_daheng):
        """Test exposure get/set."""
        await initialized_daheng.set_exposure(50000)
        exposure = await initialized_daheng.get_exposure()
        assert exposure == 50000.0

    @pytest.mark.asyncio
    async def test_exposure_range(self, initialized_daheng):
        """Test getting exposure range."""
        exp_range = await initialized_daheng.get_exposure_range()
        assert len(exp_range) == 2
        assert exp_range[0] < exp_range[1]

    @pytest.mark.asyncio
    async def test_gain_control(self, initialized_daheng):
        """Test gain get/set."""
        await initialized_daheng.set_gain(10.0)
        gain = await initialized_daheng.get_gain()
        assert gain == 10.0

    @pytest.mark.asyncio
    async def test_gain_range(self, initialized_daheng):
        """Test getting gain range."""
        gain_range = await initialized_daheng.get_gain_range()
        assert len(gain_range) == 2

    @pytest.mark.asyncio
    async def test_trigger_mode(self, initialized_daheng):
        """Test trigger mode control."""
        await initialized_daheng.set_triggermode("continuous")
        mode = await initialized_daheng.get_triggermode()
        assert mode == "continuous"

        await initialized_daheng.set_triggermode("trigger")
        mode = await initialized_daheng.get_triggermode()
        assert mode == "trigger"

    @pytest.mark.asyncio
    async def test_invalid_trigger_mode(self, initialized_daheng):
        """Test setting invalid trigger mode."""
        with pytest.raises(CameraConfigurationError):
            await initialized_daheng.set_triggermode("invalid_mode")

    @pytest.mark.asyncio
    async def test_roi_control(self, initialized_daheng):
        """Test ROI get/set."""
        await initialized_daheng.set_ROI(100, 100, 800, 600)
        roi = await initialized_daheng.get_ROI()
        assert roi["x"] == 100
        assert roi["y"] == 100

    @pytest.mark.asyncio
    async def test_roi_invalid(self, initialized_daheng):
        """Test setting invalid ROI."""
        with pytest.raises(CameraConfigurationError):
            await initialized_daheng.set_ROI(0, 0, -1, 100)

    @pytest.mark.asyncio
    async def test_reset_roi(self, initialized_daheng):
        """Test resetting ROI."""
        await initialized_daheng.set_ROI(100, 100, 800, 600)
        await initialized_daheng.reset_ROI()
        roi = await initialized_daheng.get_ROI()
        assert roi["x"] == 0
        assert roi["y"] == 0

    @pytest.mark.asyncio
    async def test_white_balance(self, initialized_daheng):
        """Test white balance control."""
        wb = await initialized_daheng.get_wb()
        assert isinstance(wb, str)

        wb_range = await initialized_daheng.get_wb_range()
        assert len(wb_range) > 0

    @pytest.mark.asyncio
    async def test_pixel_format(self, initialized_daheng):
        """Test pixel format control."""
        fmt = await initialized_daheng.get_current_pixel_format()
        assert isinstance(fmt, str)

        formats = await initialized_daheng.get_pixel_format_range()
        assert len(formats) > 0

    @pytest.mark.asyncio
    async def test_capture_timeout(self, initialized_daheng):
        """Test capture timeout control."""
        await initialized_daheng.set_capture_timeout(10000)
        timeout = await initialized_daheng.get_capture_timeout()
        assert timeout == 10000

    @pytest.mark.asyncio
    async def test_negative_capture_timeout(self, initialized_daheng):
        """Test setting negative capture timeout."""
        with pytest.raises(ValueError):
            await initialized_daheng.set_capture_timeout(-1)


# ═══════════════════════════════════════════════════════════════════════════════
# Connection & Lifecycle Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDahengLifecycle:
    """Test DahengCameraBackend lifecycle."""

    @pytest.mark.asyncio
    async def test_check_connection(self, initialized_daheng):
        """Test connection check."""
        result = await initialized_daheng.check_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_connection_not_initialized(self, daheng_camera):
        """Test connection check when not initialized."""
        result = await daheng_camera.check_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_close(self, initialized_daheng):
        """Test closing the camera."""
        await initialized_daheng.close()
        assert initialized_daheng.initialized is False
        assert initialized_daheng.camera is None

    @pytest.mark.asyncio
    async def test_image_quality_enhancement(self, initialized_daheng):
        """Test image quality enhancement."""
        assert initialized_daheng.get_image_quality_enhancement() is False
        initialized_daheng.set_image_quality_enhancement(True)
        assert initialized_daheng.get_image_quality_enhancement() is True

    @pytest.mark.asyncio
    async def test_constructor_validation(self, mock_gxipy):
        """Test constructor parameter validation."""
        from mindtrace.hardware.cameras.backends.daheng.daheng_camera_backend import DahengCameraBackend

        with pytest.raises(CameraConfigurationError):
            DahengCameraBackend("test", buffer_count=0)

        with pytest.raises(CameraConfigurationError):
            DahengCameraBackend("test", timeout_ms=50)

    @pytest.mark.asyncio
    async def test_thread_affinity(self, mock_gxipy):
        """Test that REQUIRES_THREAD_AFFINITY is True."""
        from mindtrace.hardware.cameras.backends.daheng.daheng_camera_backend import DahengCameraBackend

        assert DahengCameraBackend.REQUIRES_THREAD_AFFINITY is True

    @pytest.mark.asyncio
    async def test_is_ip_address(self, mock_gxipy):
        """Test IP address detection."""
        from mindtrace.hardware.cameras.backends.daheng.daheng_camera_backend import DahengCameraBackend

        assert DahengCameraBackend._is_ip_address("192.168.1.100") is True
        assert DahengCameraBackend._is_ip_address("10.0.0.1") is True
        assert DahengCameraBackend._is_ip_address("DH000001") is False
        assert DahengCameraBackend._is_ip_address("not_an_ip") is False
        assert DahengCameraBackend._is_ip_address("999.999.999.999") is False
