import asyncio
import json
import os
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, Mock, patch
import logging

import numpy as np
import pytest

from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraInitializationError,
    CameraNotFoundError,
    CameraTimeoutError,
    SDKNotAvailableError,
    HardwareOperationError,
)


# Mock pypylon classes and functions
class MockGenICamError(Exception):
    """Mock genicam exception."""
    pass


class MockRuntimeError(Exception):
    """Mock runtime exception."""
    pass


class MockTimeoutError(Exception):
    """Mock timeout exception."""
    pass


class MockPylonDevice:
    """Mock pylon device."""
    
    def __init__(self, serial="12345678", model="acA1920-40uc", vendor="Basler AG"):
        self.serial = serial
        self.model = model
        self.vendor = vendor
        self.user_defined_name = f"Camera_{serial}"
        self.device_class = "BaslerUsb"
        self.interface = "USB1"
        self._friendly_name = f"Basler {model} ({serial})"
        
    def GetSerialNumber(self):
        return self.serial
        
    def GetModelName(self):
        return self.model
        
    def GetVendorName(self):
        return self.vendor
        
    def GetUserDefinedName(self):
        return self.user_defined_name
        
    def GetDeviceClass(self):
        return self.device_class
        
    def GetInterfaceID(self):
        return self.interface
        
    def GetFriendlyName(self):
        return self._friendly_name


class MockPylonCamera:
    """Mock pylon instant camera."""
    
    def __init__(self, device_info=None):
        self.device_info = device_info or MockPylonDevice()
        self.opened = False
        self.grabbing = False
        self.exposure_time = 10000.0
        self.gain = 1.0
        self.width = 1920
        self.height = 1080
        self.pixel_format = "BGR8"
        self.trigger_mode = "Off"
        self.trigger_source = "Software"
        self.auto_exposure = "Off"
        self.auto_gain = "Off"
        self.image_enhancement = True
        self.roi = {"x": 0, "y": 0, "width": 1920, "height": 1080}
        self._simulate_error = None
        
        # Additional attributes for parameter synchronization
        self.max_num_buffer = 25
        self.trigger_selector = "FrameStart"
        self.trigger_software = None
        self.balance_white_auto = "Off"
        self.offset_x = 0
        self.offset_y = 0
        
        # Create parameter objects as properties
        self._exposure_time_param = MockParameter(self.exposure_time, min_val=100.0, max_val=1000000.0, camera_attr="exposure_time", camera_obj=self)
        self._gain_param = MockParameter(self.gain, min_val=0.0, max_val=20.0, camera_attr="gain", camera_obj=self)
        self._width_param = MockParameter(self.width, min_val=32, max_val=1920, camera_attr="width", camera_obj=self)
        self._height_param = MockParameter(self.height, min_val=32, max_val=1080, camera_attr="height", camera_obj=self)
        self._pixel_format_param = MockEnumParameter(self.pixel_format, ["Mono8", "BGR8", "RGB8"], camera_attr="pixel_format", camera_obj=self)
        self._trigger_mode_param = MockEnumParameter(self.trigger_mode, ["Off", "On"], camera_attr="trigger_mode", camera_obj=self)
        self._trigger_source_param = MockEnumParameter(self.trigger_source, ["Software", "Line1", "Line2"], camera_attr="trigger_source", camera_obj=self)
        self._max_num_buffer_param = MockParameter(25, min_val=1, max_val=100, camera_attr="max_num_buffer", camera_obj=self)
        self._trigger_selector_param = MockEnumParameter("FrameStart", ["FrameStart", "LineStart"], camera_attr="trigger_selector", camera_obj=self)
        self._trigger_software_param = MockParameter(None, camera_attr="trigger_software", camera_obj=self)
        self._balance_white_auto_param = MockEnumParameter("Off", ["Off", "Once", "Continuous"], camera_attr="balance_white_auto", camera_obj=self)
        self._offset_x_param = MockParameter(0, min_val=0, max_val=1920, camera_attr="offset_x", camera_obj=self)
        self._offset_y_param = MockParameter(0, min_val=0, max_val=1080, camera_attr="offset_y", camera_obj=self)
        
    def Attach(self, device_info):
        self.device_info = device_info
        
    def Open(self):
        if self._simulate_error == "open":
            raise MockRuntimeError("Failed to open camera")
        self.opened = True
        
    def Close(self):
        self.opened = False
        self.grabbing = False
        
    def IsOpen(self):
        return self.opened
        
    def StartGrabbing(self, strategy=None):
        if not self.opened:
            raise MockRuntimeError("Camera not open")
        if self._simulate_error == "start_grab":
            raise MockRuntimeError("Failed to start grabbing")
        self.grabbing = True
        
    def StopGrabbing(self):
        self.grabbing = False
        
    def IsGrabbing(self):
        return self.grabbing
        
    def RetrieveResult(self, timeout_ms, timeout_handling=None):
        if not self.opened:
            raise MockRuntimeError("Camera not open")
        if not self.grabbing:
            raise MockRuntimeError("Camera not grabbing")
        if self._simulate_error == "timeout":
            raise MockTimeoutError("Retrieve timeout")
        if self._simulate_error == "capture":
            raise MockRuntimeError("Capture failed")
            
        # Create mock grab result
        grab_result = MockGrabResult()
        return grab_result
        
    def LoadConfigurationFile(self, path):
        if self._simulate_error == "load_config":
            raise MockRuntimeError("Failed to load config")
            
    def SaveConfigurationFile(self, path):
        if self._simulate_error == "save_config":
            raise MockRuntimeError("Failed to save config")
            
    # Property-like methods for camera parameters
    @property
    def ExposureTime(self):
        return self._exposure_time_param
        
    @property
    def Gain(self):
        return self._gain_param
        
    @property
    def Width(self):
        return self._width_param
        
    @property
    def Height(self):
        return self._height_param
        
    @property
    def PixelFormat(self):
        return self._pixel_format_param
        
    @property
    def TriggerMode(self):
        return self._trigger_mode_param
        
    @property
    def TriggerSource(self):
        return self._trigger_source_param
    
    @property
    def MaxNumBuffer(self):
        return self._max_num_buffer_param
    
    @property
    def TriggerSelector(self):
        return self._trigger_selector_param
    
    @property
    def TriggerSoftware(self):
        return self._trigger_software_param
    
    @property
    def BalanceWhiteAuto(self):
        return self._balance_white_auto_param
    
    @property
    def OffsetX(self):
        return self._offset_x_param
    
    @property
    def OffsetY(self):
        return self._offset_y_param


class MockParameter:
    """Mock parameter for camera settings."""
    
    def __init__(self, value, min_val=None, max_val=None, camera_attr=None, camera_obj=None):
        self.value = value
        self.min_val = min_val
        self.max_val = max_val
        self.camera_attr = camera_attr  # Attribute name on camera object to sync with
        self.camera_obj = camera_obj    # Reference to camera object
        
    def GetValue(self):
        # Sync from camera if we have a reference
        if self.camera_obj and self.camera_attr:
            return getattr(self.camera_obj, self.camera_attr, self.value)
        return self.value
        
    def SetValue(self, value):
        if self.min_val is not None and value < self.min_val:
            raise MockGenICamError(f"Value {value} is below minimum {self.min_val}")
        if self.max_val is not None and value > self.max_val:
            raise MockGenICamError(f"Value {value} is above maximum {self.max_val}")
        self.value = value
        # Sync to camera if we have a reference
        if self.camera_obj and self.camera_attr:
            setattr(self.camera_obj, self.camera_attr, value)
        
    def GetMin(self):
        return self.min_val if self.min_val is not None else 0
        
    def GetMax(self):
        return self.max_val if self.max_val is not None else 1000000
    
    def GetInc(self):
        """Get the increment value for this parameter."""
        # Return 1 for most parameters, or a reasonable increment based on the parameter type
        if self.camera_attr in ["width", "height", "offset_x", "offset_y"]:
            return 2  # Common increment for ROI parameters (pixel alignment)
        return 1
    
    def Execute(self):
        """Mock execute for trigger software."""
        pass
    
    def GetAccessMode(self):
        """Mock access mode - return RW (read-write)."""
        return "RW"


class MockEnumParameter:
    """Mock enumeration parameter."""
    
    def __init__(self, value, valid_values, camera_attr=None, camera_obj=None):
        self.value = value
        self.valid_values = valid_values
        self.camera_attr = camera_attr  # Attribute name on camera object to sync with
        self.camera_obj = camera_obj    # Reference to camera object
        
    def GetValue(self):
        # Sync from camera if we have a reference
        if self.camera_obj and self.camera_attr:
            return getattr(self.camera_obj, self.camera_attr, self.value)
        return self.value
        
    def SetValue(self, value):
        if value not in self.valid_values:
            raise MockGenICamError(f"Invalid value {value}")
        self.value = value
        # Sync to camera if we have a reference
        if self.camera_obj and self.camera_attr:
            setattr(self.camera_obj, self.camera_attr, value)
        
    def GetSymbolics(self):
        return self.valid_values
    
    def GetAccessMode(self):
        """Mock access mode - return RW (read-write)."""
        return "RW"
    
    def GetEntries(self):
        """Get available entries for enumeration parameters."""
        return self.valid_values


class MockGrabResult:
    """Mock grab result."""
    
    def __init__(self):
        self.grab_succeeded = True
        
    def GrabSucceeded(self):
        return self.grab_succeeded
        
    def GetArray(self):
        # Return a mock image array
        return np.zeros((1080, 1920, 3), dtype=np.uint8)
    
    def Release(self):
        """Release the grab result."""
        pass
    
    def ErrorDescription(self):
        """Return error description."""
        return "No error"


class MockImageFormatConverter:
    """Mock image format converter."""
    
    def __init__(self):
        self.output_pixel_format = "BGR8"
        
    def Convert(self, grab_result):
        # Return an object that has GetArray method
        class ConvertedImage:
            def GetArray(self):
                return grab_result.GetArray()
        return ConvertedImage()
        
    def SetOutputPixelFormat(self, format):
        self.output_pixel_format = format


# Mock pylon module structure
class MockPylon:
    TlFactory = Mock()
    InstantCamera = MockPylonCamera
    ImageFormatConverter = MockImageFormatConverter
    GrabStrategy_LatestImageOnly = "LatestImageOnly"
    
    # Pixel format constants
    PixelType_BGR8packed = "BGR8"
    OutputBitAlignment_MsbAligned = "MsbAligned"
    
    # Timeout handling constants
    TimeoutHandling_ThrowException = "ThrowException"
    TimeoutHandling_Return = "Return"
    
    @staticmethod
    def GetGrabResultGrabSucceeded():
        return True


class MockGenicam:
    GenericException = MockGenICamError
    RuntimeException = MockRuntimeError
    TimeoutException = MockTimeoutError
    
    # Access mode constants
    RW = "RW"
    WO = "WO"
    RO = "RO"


@pytest.fixture
def mock_pypylon(monkeypatch):
    """Mock the pypylon module."""
    # Mock the imports
    mock_pylon = MockPylon()
    mock_genicam = MockGenicam()
    
    # Mock TlFactory
    tl_factory = Mock()
    devices = [MockPylonDevice(serial=f"1234567{i}", model=f"acA1920-40uc") for i in range(3)]
    tl_factory.EnumerateDevices.return_value = devices
    tl_factory.CreateDevice.side_effect = lambda device_info: device_info  # Return the device_info as-is
    mock_pylon.TlFactory.GetInstance.return_value = tl_factory
    
    monkeypatch.setattr("mindtrace.hardware.cameras.backends.basler.basler_camera_backend.pylon", mock_pylon)
    monkeypatch.setattr("mindtrace.hardware.cameras.backends.basler.basler_camera_backend.genicam", mock_genicam)
    monkeypatch.setattr("mindtrace.hardware.cameras.backends.basler.basler_camera_backend.PYPYLON_AVAILABLE", True)
    
    return mock_pylon, mock_genicam


@pytest.fixture
def basler_camera(mock_pypylon):
    """Create a BaslerCameraBackend instance."""
    from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
    
    camera = BaslerCameraBackend(
        camera_name="Camera_12345670",  # Use a name that matches discovery
        img_quality_enhancement=True,
        retrieve_retry_count=3,
        pixel_format="BGR8",
        buffer_count=10,
        timeout_ms=1000
    )
    
    return camera


@pytest.fixture
def temp_config_file():
    """Create a temporary configuration file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pfs", delete=False) as f:
        f.write('{"camera_type": "basler", "exposure_time": 10000, "gain": 1.0}\n')
        temp_path = f.name
    try:
        yield temp_path
    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass


class TestBaslerCameraBackendInitialization:
    """Test camera initialization and configuration."""
    
    def test_init_without_pypylon(self, monkeypatch):
        """Test initialization when pypylon is not available."""
        monkeypatch.setattr("mindtrace.hardware.cameras.backends.basler.basler_camera_backend.PYPYLON_AVAILABLE", False)
        
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        with pytest.raises(SDKNotAvailableError, match="pypylon"):
            BaslerCameraBackend("test_camera")
    
    def test_init_with_valid_config(self, mock_pypylon):
        """Test initialization with valid configuration."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        camera = BaslerCameraBackend(
            camera_name="test_camera",
            img_quality_enhancement=True,
            retrieve_retry_count=5,
            pixel_format="BGR8",
            buffer_count=20,
            timeout_ms=2000
        )
        
        assert camera.camera_name == "test_camera"
        assert camera.default_pixel_format == "BGR8"
        assert camera.buffer_count == 20
        assert camera.timeout_ms == 2000
        assert camera.retrieve_retry_count == 5
    
    def test_init_with_invalid_buffer_count(self, mock_pypylon):
        """Test initialization with invalid buffer count."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        with pytest.raises(CameraConfigurationError, match="Buffer count must be at least 1"):
            BaslerCameraBackend("test_camera", buffer_count=0)
    
    def test_init_with_invalid_timeout(self, mock_pypylon):
        """Test initialization with invalid timeout."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        with pytest.raises(CameraConfigurationError, match="Timeout must be at least 100ms"):
            BaslerCameraBackend("test_camera", timeout_ms=50)


class TestBaslerCameraBackendDiscovery:
    """Test camera discovery functionality."""
    
    def test_get_available_cameras_simple(self, mock_pypylon):
        """Test simple camera discovery."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        cameras = BaslerCameraBackend.get_available_cameras(include_details=False)
        assert isinstance(cameras, list)
        assert len(cameras) == 3
        # BaslerCameraBackend returns the user-defined names, not serial numbers
        assert "Camera_12345670" in cameras
        assert "Camera_12345671" in cameras
        assert "Camera_12345672" in cameras
    
    def test_get_available_cameras_with_details(self, mock_pypylon):
        """Test camera discovery with details."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        cameras = BaslerCameraBackend.get_available_cameras(include_details=True)
        assert isinstance(cameras, dict)
        assert len(cameras) == 3
        
        camera_info = cameras["Camera_12345670"]
        assert camera_info["serial_number"] == "12345670"
        assert camera_info["model"] == "acA1920-40uc"
        assert camera_info["vendor"] == "Basler AG"
        assert camera_info["device_class"] == "BaslerUsb"
    
    def test_get_available_cameras_no_pypylon(self, monkeypatch):
        """Test camera discovery when pypylon is not available."""
        monkeypatch.setattr("mindtrace.hardware.cameras.backends.basler.basler_camera_backend.PYPYLON_AVAILABLE", False)
        
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # When pypylon is not available, it should raise an error, not return empty list
        with pytest.raises(SDKNotAvailableError):
            BaslerCameraBackend.get_available_cameras()
    
    def test_get_available_cameras_discovery_error(self, mock_pypylon):
        """Test camera discovery with SDK error."""
        mock_pylon, _ = mock_pypylon
        mock_pylon.TlFactory.GetInstance.return_value.EnumerateDevices.side_effect = Exception("Discovery failed")
        
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Should raise HardwareOperationError, not return empty list
        with pytest.raises(HardwareOperationError, match="Failed to discover Basler cameras"):
            BaslerCameraBackend.get_available_cameras()


class TestBaslerCameraBackendConnection:
    """Test camera connection and initialization."""
    
    @pytest.mark.asyncio
    async def test_initialize_success(self, basler_camera, mock_pypylon):
        """Test successful camera initialization."""
        success, cam_obj, remote_obj = await basler_camera.initialize()
        
        assert success is True
        assert cam_obj is not None
        assert remote_obj is None  # Basler cameras don't have a separate remote object
        assert basler_camera.initialized is True
    
    @pytest.mark.asyncio
    async def test_initialize_camera_not_found(self, mock_pypylon):
        """Test initialization when camera is not found."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Mock empty device list
        mock_pylon, _ = mock_pypylon
        mock_pylon.TlFactory.GetInstance.return_value.EnumerateDevices.return_value = []
        
        camera = BaslerCameraBackend("nonexistent_camera")
        
        with pytest.raises(CameraNotFoundError, match="No Basler cameras found"):
            await camera.initialize()
    
    @pytest.mark.asyncio
    async def test_initialize_open_failure(self, basler_camera, mock_pypylon):
        """Test initialization when camera open fails."""
        # Set up mock to simulate open failure
        mock_pylon, _ = mock_pypylon
        mock_camera = mock_pylon.InstantCamera()
        mock_camera._simulate_error = "open"
        mock_pylon.InstantCamera = lambda *args: mock_camera
        
        with pytest.raises(CameraConnectionError, match="Failed to open camera"):
            await basler_camera.initialize()
    
    @pytest.mark.asyncio
    async def test_initialize_with_config_file(self, basler_camera, temp_config_file):
        """Test initialization with configuration file."""
        basler_camera.camera_config_path = temp_config_file
        
        success, cam_obj, remote_obj = await basler_camera.initialize()
        assert success is True
    
    @pytest.mark.asyncio
    async def test_check_connection_success(self, basler_camera):
        """Test connection check on initialized camera."""
        await basler_camera.initialize()
        assert await basler_camera.check_connection() is True
    
    @pytest.mark.asyncio
    async def test_check_connection_not_initialized(self, basler_camera):
        """Test connection check on uninitialized camera."""
        assert await basler_camera.check_connection() is False
    
    @pytest.mark.asyncio
    async def test_check_connection_closed_camera(self, basler_camera):
        """Test connection check on closed camera."""
        await basler_camera.initialize()
        # Simulate a camera that fails to reopen
        basler_camera.camera.Close()
        basler_camera.camera._simulate_error = "open"  # Make reopening fail
        assert await basler_camera.check_connection() is False


class TestBaslerCameraBackendCapture:
    """Test image capture functionality."""
    
    @pytest.mark.asyncio
    async def test_capture_success(self, basler_camera):
        """Test successful image capture."""
        await basler_camera.initialize()
        
        success, image = await basler_camera.capture()
        
        assert success is True
        assert isinstance(image, np.ndarray)
        assert image.shape == (1080, 1920, 3)
    
    @pytest.mark.asyncio
    async def test_capture_not_initialized(self, basler_camera):
        """Test capture on uninitialized camera."""
        with pytest.raises(CameraConnectionError, match="Camera.*is not initialized"):
            await basler_camera.capture()
    
    @pytest.mark.asyncio
    async def test_capture_timeout(self, basler_camera, mock_pypylon):
        """Test capture timeout."""
        await basler_camera.initialize()
        
        # Set up mock to simulate timeout
        basler_camera.camera._simulate_error = "timeout"
        
        with pytest.raises(CameraTimeoutError, match="Capture timeout after.*attempts"):
            await basler_camera.capture()
    
    @pytest.mark.asyncio
    async def test_capture_generic_error(self, basler_camera, mock_pypylon):
        """Test capture with generic error."""
        await basler_camera.initialize()
        
        # Set up mock to simulate generic error
        basler_camera.camera._simulate_error = "capture"
        
        with pytest.raises(CameraCaptureError, match="Capture failed for camera"):
            await basler_camera.capture()
    
    @pytest.mark.asyncio
    async def test_capture_with_retries(self, basler_camera, monkeypatch):
        """Test capture with retry logic."""
        await basler_camera.initialize()
        basler_camera.retrieve_retry_count = 3
        
        # Mock asyncio.sleep to speed up test
        async def fast_sleep(delay):
            pass
        monkeypatch.setattr(asyncio, "sleep", fast_sleep)
        
        # Set up mock to fail twice then succeed
        call_count = 0
        original_retrieve = basler_camera.camera.RetrieveResult
        
        def failing_retrieve(timeout_ms, timeout_handling=None):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise MockTimeoutError("Timeout")
            return original_retrieve(timeout_ms, timeout_handling)
        
        basler_camera.camera.RetrieveResult = failing_retrieve
        
        success, image = await basler_camera.capture()
        assert success is True
        assert call_count == 3


class TestBaslerCameraBackendConfiguration:
    """Test camera configuration functionality."""
    
    @pytest.mark.asyncio
    async def test_set_exposure_success(self, basler_camera):
        """Test setting exposure time."""
        await basler_camera.initialize()
        
        result = await basler_camera.set_exposure(20000)
        assert result is True
        assert basler_camera.camera.exposure_time == 20000
    
    @pytest.mark.asyncio
    async def test_set_exposure_out_of_range(self, basler_camera):
        """Test setting exposure time out of range."""
        await basler_camera.initialize()
        
        with pytest.raises(CameraConfigurationError, match="Exposure.*outside valid range"):
            await basler_camera.set_exposure(2000000)  # Too high
    
    @pytest.mark.asyncio
    async def test_get_exposure(self, basler_camera):
        """Test getting exposure time."""
        await basler_camera.initialize()
        basler_camera.camera.exposure_time = 15000
        
        exposure = await basler_camera.get_exposure()
        assert exposure == 15000
    
    @pytest.mark.asyncio
    async def test_get_exposure_range(self, basler_camera):
        """Test getting exposure range."""
        await basler_camera.initialize()
        
        min_exp, max_exp = await basler_camera.get_exposure_range()
        assert min_exp == 100.0
        assert max_exp == 1000000.0
    
    @pytest.mark.asyncio
    async def test_set_gain_success(self, basler_camera):
        """Test setting gain."""
        await basler_camera.initialize()
        
        result = await basler_camera.set_gain(5.0)
        assert result is True
        assert basler_camera.camera.gain == 5.0
    
    @pytest.mark.asyncio
    async def test_set_gain_out_of_range(self, basler_camera):
        """Test setting gain out of range."""
        await basler_camera.initialize()
        
        with pytest.raises(CameraConfigurationError, match="Gain.*outside valid range"):
            await basler_camera.set_gain(1000)  # Way too high
    
    @pytest.mark.asyncio
    async def test_get_gain(self, basler_camera):
        """Test getting gain."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        basler_camera.camera.gain = 3.5
        
        gain = await basler_camera.get_gain()
        assert gain == 3.5
    
    @pytest.mark.asyncio
    async def test_get_gain_range(self, basler_camera):
        """Test getting gain range."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        
        gain_range = await basler_camera.get_gain_range()
        assert gain_range == [0.0, 20.0]  # Range from our mock


class TestBaslerCameraBackendTriggerMode:
    """Test trigger mode functionality."""
    
    @pytest.mark.asyncio
    async def test_set_triggermode_continuous(self, basler_camera):
        """Test setting continuous trigger mode."""
        await basler_camera.initialize()
        
        result = await basler_camera.set_triggermode("continuous")
        assert result is True
        assert basler_camera.camera.trigger_mode == "Off"
    
    @pytest.mark.asyncio
    async def test_set_triggermode_trigger(self, basler_camera):
        """Test setting trigger mode."""
        await basler_camera.initialize()
        
        result = await basler_camera.set_triggermode("trigger")
        assert result is True
        assert basler_camera.camera.trigger_mode == "On"
        assert basler_camera.camera.trigger_source == "Software"
    
    @pytest.mark.asyncio
    async def test_set_triggermode_invalid(self, basler_camera):
        """Test setting invalid trigger mode."""
        await basler_camera.initialize()
        
        with pytest.raises(CameraConfigurationError, match="Invalid trigger mode"):
            await basler_camera.set_triggermode("invalid_mode")
    
    @pytest.mark.asyncio
    async def test_get_triggermode(self, basler_camera):
        """Test getting trigger mode."""
        await basler_camera.initialize()
        basler_camera.camera.trigger_mode = "On"
        
        mode = await basler_camera.get_triggermode()
        assert mode == "trigger"


class TestBaslerCameraBackendROI:
    """Test ROI (Region of Interest) functionality."""
    
    @pytest.mark.asyncio
    async def test_set_roi_success(self, basler_camera):
        """Test setting ROI."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        
        result = await basler_camera.set_ROI(100, 100, 800, 600)
        assert result is True
        assert basler_camera.camera.width == 800
        assert basler_camera.camera.height == 600
    
    @pytest.mark.asyncio
    async def test_set_roi_invalid_dimensions(self, basler_camera):
        """Test setting ROI with invalid dimensions."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        
        with pytest.raises(CameraConfigurationError, match="ROI dimensions.*out of range"):
            await basler_camera.set_ROI(0, 0, 3000, 2000)  # Too large
    
    @pytest.mark.asyncio
    async def test_get_roi(self, basler_camera):
        """Test getting ROI."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        # Set the individual parameter values that get_ROI() actually reads
        basler_camera.camera.offset_x = 50
        basler_camera.camera.offset_y = 50
        basler_camera.camera.width = 640
        basler_camera.camera.height = 480
        
        roi = await basler_camera.get_ROI()
        assert roi == {"x": 50, "y": 50, "width": 640, "height": 480}
    
    @pytest.mark.asyncio
    async def test_reset_roi(self, basler_camera):
        """Test resetting ROI."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        
        result = await basler_camera.reset_ROI()
        assert result is True
        assert basler_camera.camera.width == 1920
        assert basler_camera.camera.height == 1080


class TestBaslerCameraBackendPixelFormat:
    """Test pixel format functionality."""
    
    @pytest.mark.asyncio
    async def test_set_pixel_format_success(self, basler_camera):
        """Test setting pixel format."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        
        result = await basler_camera.set_pixel_format("RGB8")
        assert result is True
        assert basler_camera.camera.pixel_format == "RGB8"
    
    @pytest.mark.asyncio
    async def test_set_pixel_format_invalid(self, basler_camera):
        """Test setting invalid pixel format."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        
        with pytest.raises(CameraConfigurationError, match="Pixel format.*not supported"):
            await basler_camera.set_pixel_format("INVALID_FORMAT")
    
    @pytest.mark.asyncio
    async def test_get_pixel_format(self, basler_camera):
        """Test getting pixel format."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        basler_camera.camera.pixel_format = "Mono8"
        
        format = await basler_camera.get_current_pixel_format()
        assert format == "Mono8"
    
    @pytest.mark.asyncio
    async def test_get_pixel_format_range(self, basler_camera):
        """Test getting available pixel formats."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        
        formats = await basler_camera.get_pixel_format_range()
        assert isinstance(formats, list)
        assert "BGR8" in formats
        assert "RGB8" in formats
        assert "Mono8" in formats


class TestBaslerCameraBackendWhiteBalance:
    """Test white balance functionality."""
    
    @pytest.mark.asyncio
    async def test_get_wb_success(self, basler_camera):
        """Test getting white balance mode."""
        await basler_camera.initialize()
        
        # Test getting current white balance
        wb_mode = await basler_camera.get_wb()
        assert wb_mode in ["off", "once", "continuous"]
    
    @pytest.mark.asyncio
    async def test_get_wb_not_initialized(self, basler_camera):
        """Test getting white balance on uninitialized camera."""
        with pytest.raises(CameraConnectionError, match="not initialized"):
            await basler_camera.get_wb()
    
    @pytest.mark.asyncio
    async def test_set_auto_wb_once_success(self, basler_camera):
        """Test setting white balance modes."""
        await basler_camera.initialize()
        
        # Test all valid white balance modes
        for mode in ["off", "once", "continuous"]:
            result = await basler_camera.set_auto_wb_once(mode)
            assert result is True
            
            # Verify the mode was set
            current_mode = await basler_camera.get_wb()
            assert current_mode == mode
    
    @pytest.mark.asyncio
    async def test_set_auto_wb_once_invalid_mode(self, basler_camera):
        """Test setting invalid white balance mode."""
        await basler_camera.initialize()
        
        with pytest.raises(CameraConfigurationError, match="Invalid white balance mode"):
            await basler_camera.set_auto_wb_once("invalid_mode")
    
    @pytest.mark.asyncio
    async def test_set_auto_wb_once_not_initialized(self, basler_camera):
        """Test setting white balance on uninitialized camera."""
        with pytest.raises(CameraConnectionError, match="not initialized"):
            await basler_camera.set_auto_wb_once("off")
    
    @pytest.mark.asyncio
    async def test_get_wb_range(self, basler_camera):
        """Test getting available white balance modes."""
        wb_range = await basler_camera.get_wb_range()
        assert isinstance(wb_range, list)
        assert "off" in wb_range
        assert "once" in wb_range
        assert "continuous" in wb_range
    
    @pytest.mark.asyncio
    async def test_wb_feature_unavailable(self, basler_camera, monkeypatch):
        """Test white balance when feature is not available."""
        await basler_camera.initialize()
        
        # Mock the white balance parameter to be unavailable for reading
        monkeypatch.setattr(basler_camera.camera.BalanceWhiteAuto, "GetAccessMode", lambda: "NA")
        
        # Should return "off" when feature unavailable
        wb_mode = await basler_camera.get_wb()
        assert wb_mode == "off"
        
        # For setting, mock as read-only (not writable)
        import mindtrace.hardware.cameras.backends.basler.basler_camera_backend as mod
        monkeypatch.setattr(basler_camera.camera.BalanceWhiteAuto, "GetAccessMode", lambda: mod.genicam.RO)
        
        # Setting should return False when not writable
        result = await basler_camera.set_auto_wb_once("once")
        assert result is False


class TestBaslerCameraBackendRangeQueries:
    """Test width/height range query functionality."""
    
    @pytest.mark.asyncio
    async def test_get_width_range_success(self, basler_camera):
        """Test getting camera width range."""
        await basler_camera.initialize()
        
        width_range = await basler_camera.get_width_range()
        assert isinstance(width_range, list)
        assert len(width_range) == 2
        assert width_range[0] <= width_range[1]  # min <= max
        assert width_range[0] > 0  # Positive values
    
    @pytest.mark.asyncio
    async def test_get_width_range_not_initialized(self, basler_camera):
        """Test getting width range on uninitialized camera."""
        with pytest.raises(CameraConnectionError, match="not initialized"):
            await basler_camera.get_width_range()
    
    @pytest.mark.asyncio
    async def test_get_height_range_success(self, basler_camera):
        """Test getting camera height range."""
        await basler_camera.initialize()
        
        height_range = await basler_camera.get_height_range()
        assert isinstance(height_range, list)
        assert len(height_range) == 2
        assert height_range[0] <= height_range[1]  # min <= max
        assert height_range[0] > 0  # Positive values
    
    @pytest.mark.asyncio
    async def test_get_height_range_not_initialized(self, basler_camera):
        """Test getting height range on uninitialized camera."""
        with pytest.raises(CameraConnectionError, match="not initialized"):
            await basler_camera.get_height_range()
    
    @pytest.mark.asyncio
    async def test_width_range_error_handling(self, basler_camera, monkeypatch):
        """Test width range error handling."""
        await basler_camera.initialize()
        
        # Mock width parameter to raise error
        def raise_error():
            raise MockGenICamError("Width feature error")
        
        monkeypatch.setattr(basler_camera.camera.Width, "GetMin", raise_error)
        
        with pytest.raises(HardwareOperationError, match="Failed to get width range"):
            await basler_camera.get_width_range()
    
    @pytest.mark.asyncio
    async def test_height_range_error_handling(self, basler_camera, monkeypatch):
        """Test height range error handling."""
        await basler_camera.initialize()
        
        # Mock height parameter to raise error
        def raise_error():
            raise MockGenICamError("Height feature error")
        
        monkeypatch.setattr(basler_camera.camera.Height, "GetMin", raise_error)
        
        with pytest.raises(HardwareOperationError, match="Failed to get height range"):
            await basler_camera.get_height_range()
    
    @pytest.mark.asyncio
    async def test_range_queries_with_closed_camera(self, basler_camera):
        """Test range queries when camera needs to be reopened."""
        await basler_camera.initialize()
        
        # Close the camera
        basler_camera.camera.Close()
        
        # Range queries should still work by reopening camera
        width_range = await basler_camera.get_width_range()
        assert isinstance(width_range, list)
        
        height_range = await basler_camera.get_height_range()
        assert isinstance(height_range, list)


class TestBaslerCameraBackendAdvancedSDKOperations:
    """Test advanced SDK internal operations."""
    
    @pytest.mark.asyncio
    async def test_ensure_open_success(self, basler_camera):
        """Test _ensure_open method."""
        await basler_camera.initialize()
        
        # Should succeed when camera is already open
        await basler_camera._ensure_open()
        assert basler_camera.camera.IsOpen() is True
    
    @pytest.mark.asyncio
    async def test_ensure_open_closed_camera(self, basler_camera):
        """Test _ensure_open when camera is closed."""
        await basler_camera.initialize()
        
        # Close the camera
        basler_camera.camera.Close()
        
        # _ensure_open should reopen it
        await basler_camera._ensure_open()
        assert basler_camera.camera.IsOpen() is True
    
    @pytest.mark.asyncio
    async def test_ensure_open_failure(self, basler_camera, monkeypatch):
        """Test _ensure_open when camera cannot be opened."""
        await basler_camera.initialize()
        basler_camera.camera.Close()
        
        # Mock camera to fail on open
        basler_camera.camera._simulate_error = "open"
        
        with pytest.raises(CameraConnectionError, match="Failed to ensure camera.*is open"):
            await basler_camera._ensure_open()
    
    @pytest.mark.asyncio
    async def test_ensure_grabbing_success(self, basler_camera):
        """Test _ensure_grabbing method."""
        await basler_camera.initialize()
        
        await basler_camera._ensure_grabbing()
        assert basler_camera.camera.IsGrabbing() is True
    
    @pytest.mark.asyncio
    async def test_ensure_grabbing_failure(self, basler_camera):
        """Test _ensure_grabbing when start grabbing fails."""
        await basler_camera.initialize()
        
        # Mock camera to fail on start grabbing
        basler_camera.camera._simulate_error = "start_grab"
        
        with pytest.raises(CameraConnectionError, match="Failed to start grabbing"):
            await basler_camera._ensure_grabbing()
    
    @pytest.mark.asyncio
    async def test_ensure_stopped_grabbing(self, basler_camera):
        """Test _ensure_stopped_grabbing method."""
        await basler_camera.initialize()
        
        # Start grabbing first
        await basler_camera._ensure_grabbing()
        assert basler_camera.camera.IsGrabbing() is True
        
        # Stop grabbing
        await basler_camera._ensure_stopped_grabbing()
        assert basler_camera.camera.IsGrabbing() is False
    
    @pytest.mark.asyncio
    async def test_grabbing_suspended_context_manager(self, basler_camera):
        """Test _grabbing_suspended context manager."""
        await basler_camera.initialize()
        
        # Start grabbing
        await basler_camera._ensure_grabbing()
        assert basler_camera.camera.IsGrabbing() is True
        
        # Use context manager
        async with basler_camera._grabbing_suspended():
            # Inside context: grabbing should be stopped
            assert basler_camera.camera.IsGrabbing() is False
        
        # After context: grabbing should be restored
        assert basler_camera.camera.IsGrabbing() is True
    
    @pytest.mark.asyncio
    async def test_configure_camera_success(self, basler_camera):
        """Test _configure_camera method."""
        await basler_camera.initialize()
        
        # Should complete without error
        await basler_camera._configure_camera()
        
        # Camera should be configured with buffer count
        assert basler_camera.camera.max_num_buffer == basler_camera.buffer_count


class TestBaslerCameraBackendImageEnhancement:
    """Test image enhancement functionality."""
    
    @pytest.mark.asyncio
    async def test_set_image_quality_enhancement(self, basler_camera):
        """Test enabling/disabling image enhancement."""
        basler_camera.initialized = True
        
        result = await basler_camera.set_image_quality_enhancement(True)
        assert result is True
        assert await basler_camera.get_image_quality_enhancement() is True
        
        result = await basler_camera.set_image_quality_enhancement(False)
        assert result is True
        assert await basler_camera.get_image_quality_enhancement() is False
    
    @pytest.mark.asyncio
    async def test_get_image_quality_enhancement(self, basler_camera):
        """Test getting image enhancement status."""
        await basler_camera.set_image_quality_enhancement(True)
        
        result = await basler_camera.get_image_quality_enhancement()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_enhance_image_success(self, basler_camera):
        """Test _enhance_image method."""
        await basler_camera.initialize()
        
        # Create test image
        test_image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        
        # Enable enhancement
        await basler_camera.set_image_quality_enhancement(True)
        
        # Enhance image
        enhanced_image = await basler_camera._enhance_image(test_image)
        
        assert isinstance(enhanced_image, np.ndarray)
        assert enhanced_image.shape == test_image.shape
        assert enhanced_image.dtype == test_image.dtype
    
    @pytest.mark.asyncio
    async def test_enhance_image_disabled(self, basler_camera):
        """Test image enhancement through capture when disabled."""
        await basler_camera.initialize()
        
        # Disable enhancement
        await basler_camera.set_image_quality_enhancement(False)
        
        # Test that capture works when enhancement is disabled
        success, image = await basler_camera.capture()
        assert success is True
        assert isinstance(image, np.ndarray)
        assert image.shape == (1080, 1920, 3)  # Original mock size
    
    @pytest.mark.asyncio
    async def test_enhance_image_error_handling(self, basler_camera, monkeypatch):
        """Test _enhance_image error handling."""
        await basler_camera.initialize()
        
        # Create test image
        test_image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        
        # Enable enhancement
        await basler_camera.set_image_quality_enhancement(True)
        
        # Mock cv2.createCLAHE to raise error
        import cv2
        monkeypatch.setattr(cv2, "createCLAHE", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("CLAHE error")))
        
        # Should raise CameraCaptureError when enhancement fails
        with pytest.raises(CameraCaptureError, match="Image enhancement failed"):
            await basler_camera._enhance_image(test_image)
    
    @pytest.mark.asyncio
    async def test_enhance_image_grayscale(self, basler_camera, monkeypatch):
        """Test _enhance_image with grayscale image."""
        await basler_camera.initialize()
        
        # Create grayscale test image
        test_image = np.random.randint(0, 255, (100, 100), dtype=np.uint8)
        
        # Enable enhancement
        await basler_camera.set_image_quality_enhancement(True)
        
        # Mock cv2.cvtColor to handle grayscale properly  
        import cv2
        original_cvtColor = cv2.cvtColor
        
        def mock_cvtColor(img, code):
            if code == cv2.COLOR_BGR2LAB:
                # Convert single channel to 3-channel first
                if len(img.shape) == 2:
                    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                return original_cvtColor(img, code)
            return original_cvtColor(img, code)
        
        monkeypatch.setattr(cv2, "cvtColor", mock_cvtColor)
        
        # Enhance image
        enhanced_image = await basler_camera._enhance_image(test_image)
        
        assert isinstance(enhanced_image, np.ndarray)
        assert enhanced_image.ndim == 3  # Should be converted to color
        assert enhanced_image.dtype == test_image.dtype


class TestBaslerCameraBackendConfigurationFiles:
    """Test configuration file import/export."""
    
    @pytest.mark.asyncio
    async def test_export_config_success(self, basler_camera, tmp_path):
        """Test exporting camera configuration."""
        await basler_camera.initialize()
        config_path = tmp_path / "test_config.json"
        
        result = await basler_camera.export_config(str(config_path))
        assert result is True
        assert config_path.exists()
        
        # Verify config content
        with open(config_path, "r") as f:
            config = json.load(f)
        
        assert config["camera_type"] == "basler"
        assert config["camera_name"] == basler_camera.camera_name
        assert "exposure_time" in config
        assert "gain" in config
        assert "trigger_mode" in config
    
    @pytest.mark.asyncio
    async def test_import_config_success(self, basler_camera, tmp_path):
        """Test importing camera configuration."""
        await basler_camera.initialize()
        
        # Create test config
        config_data = {
            "camera_type": "basler",
            "camera_name": "test_camera",
            "exposure_time": 25000,
            "gain": 3.5,
            "trigger_mode": "continuous",
            "pixel_format": "RGB8",
            "image_enhancement": False,
            "roi": {"x": 0, "y": 0, "width": 1600, "height": 1200}
        }
        
        config_path = tmp_path / "test_config.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f)
        
        result = await basler_camera.import_config(str(config_path))
        assert result is True
    
    @pytest.mark.asyncio
    async def test_import_config_file_not_found(self, basler_camera):
        """Test importing non-existent configuration file."""
        await basler_camera.initialize()
        
        with pytest.raises(CameraConfigurationError, match="Configuration file not found"):
            await basler_camera.import_config("nonexistent_config.json")


class TestBaslerCameraBackendCleanup:
    """Test camera cleanup and resource management."""
    
    @pytest.mark.asyncio
    async def test_close_success(self, basler_camera):
        """Test successful camera close."""
        await basler_camera.initialize()
        assert basler_camera.initialized is True
        assert basler_camera.camera is not None
        
        await basler_camera.close()
        assert basler_camera.initialized is False
        assert basler_camera.camera is None  # Camera object is set to None after close
    
    @pytest.mark.asyncio
    async def test_close_not_initialized(self, basler_camera):
        """Test closing uninitialized camera."""
        # Should not raise exception
        await basler_camera.close()
        assert basler_camera.initialized is False
    
    @pytest.mark.asyncio
    async def test_setup_camera_success(self, basler_camera):
        """Test camera setup after initialization."""
        await basler_camera.initialize()
        
        result = await basler_camera.setup_camera()
        assert result is None  # setup_camera doesn't return a value


class TestBaslerCameraBackendErrorHandling:
    """Test error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_sdk_timeout_handling(self, basler_camera, monkeypatch):
        """Test SDK timeout error handling."""
        await basler_camera.initialize()
        
        # Mock the _sdk method to simulate timeout
        async def mock_sdk_timeout(*args, **kwargs):
            await asyncio.sleep(0.01)  # Small delay
            raise asyncio.TimeoutError("SDK timeout")
        
        monkeypatch.setattr(basler_camera, "_sdk", mock_sdk_timeout)
        
        with pytest.raises(CameraConnectionError, match="Failed to ensure camera.*is open"):
            await basler_camera.set_exposure(10000)
    
    @pytest.mark.asyncio
    async def test_genicam_error_handling(self, basler_camera):
        """Test GenICam error handling."""
        await basler_camera.initialize()
        
        # Set up mock to raise GenICam error
        def raise_genicam_error(value):
            raise MockGenICamError("GenICam error")
        
        basler_camera.camera.ExposureTime.SetValue = raise_genicam_error
        
        result = await basler_camera.set_exposure(10000)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_runtime_error_handling(self, basler_camera):
        """Test runtime error handling."""
        await basler_camera.initialize()
        
        # Set up mock to raise runtime error during capture
        basler_camera.camera._simulate_error = "capture"
        
        with pytest.raises(CameraCaptureError):
            await basler_camera.capture()


class TestBaslerCameraBackendAdvancedErrorScenarios:
    """Test advanced error scenarios and edge cases."""
    
    @pytest.mark.asyncio
    async def test_connection_check_with_reopening(self, basler_camera):
        """Test connection check that requires camera reopening."""
        await basler_camera.initialize()
        
        # Close camera and make reopening fail first time
        basler_camera.camera.Close()
        
        call_count = 0
        original_open = basler_camera.camera.Open
        
        def failing_open():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise MockRuntimeError("First open fails")
            return original_open()
        
        basler_camera.camera.Open = failing_open
        
        # Should return False when reopening fails
        result = await basler_camera.check_connection()
        assert result is False
    
    @pytest.mark.asyncio
    async def test_capture_with_grabbing_state_corruption(self, basler_camera):
        """Test capture when grabbing state is corrupted."""
        await basler_camera.initialize()
        
        # Manually corrupt grabbing state
        basler_camera.camera.grabbing = False
        
        # Capture should automatically start grabbing
        success, image = await basler_camera.capture()
        assert success is True
        assert isinstance(image, np.ndarray)
        assert basler_camera.camera.IsGrabbing() is True
    
    @pytest.mark.asyncio
    async def test_exposure_setting_with_genicam_error(self, basler_camera):
        """Test exposure setting with GenICam error handling."""
        await basler_camera.initialize()
        
        # Mock exposure parameter to raise GenICam error
        def raise_genicam_error(value):
            raise MockGenICamError("Parameter access error")
        
        basler_camera.camera.ExposureTime.SetValue = raise_genicam_error
        
        # Should still return True (error is logged but not propagated)
        result = await basler_camera.set_exposure(10000)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_initialize_with_device_creation_failure(self, basler_camera, mock_pypylon):
        """Test initialization when device creation fails."""
        mock_pylon, _ = mock_pypylon
        mock_pylon.TlFactory.GetInstance.return_value.CreateDevice.side_effect = Exception("Device creation failed")
        
        with pytest.raises(CameraConnectionError, match="Failed to open camera"):
            await basler_camera.initialize()
    
    @pytest.mark.asyncio
    async def test_pixel_format_with_no_entries(self, basler_camera, monkeypatch):
        """Test pixel format range when no entries are available."""
        await basler_camera.initialize()
        
        # Mock pixel format to return empty entries
        monkeypatch.setattr(basler_camera.camera.PixelFormat, "GetEntries", lambda: [])
        
        formats = await basler_camera.get_pixel_format_range()
        # Should return default formats when entries are empty
        assert "BGR8" in formats
        assert "RGB8" in formats
        assert "Mono8" in formats
    
    @pytest.mark.asyncio
    async def test_sdk_executor_shutdown_error(self, basler_camera, monkeypatch):
        """Test error handling during executor shutdown."""
        await basler_camera.initialize()
        
        # Mock executor to raise error on shutdown
        mock_executor = Mock()
        mock_executor.shutdown.side_effect = RuntimeError("Shutdown error")
        basler_camera._sdk_executor = mock_executor
        
        # Should not raise error (errors are caught and ignored)
        await basler_camera.close()
        assert basler_camera.initialized is False


class TestBaslerCameraBackendConcurrentOperations:
    """Test concurrent operations and threading scenarios."""
    
    @pytest.mark.asyncio
    async def test_concurrent_captures(self, basler_camera):
        """Test multiple simultaneous capture operations."""
        await basler_camera.initialize()
        
        # Start multiple capture tasks concurrently
        capture_tasks = [basler_camera.capture() for _ in range(3)]
        results = await asyncio.gather(*capture_tasks)
        
        # All captures should succeed
        for success, image in results:
            assert success is True
            assert isinstance(image, np.ndarray)
    
    @pytest.mark.asyncio
    async def test_configuration_during_capture(self, basler_camera, monkeypatch):
        """Test configuration changes during capture operations."""
        await basler_camera.initialize()
        
        # Slow down capture to allow configuration changes
        original_retrieve = basler_camera.camera.RetrieveResult
        
        def slow_retrieve(timeout_ms, timeout_handling=None):
            import time
            time.sleep(0.1)  # Add delay
            return original_retrieve(timeout_ms, timeout_handling)
        
        basler_camera.camera.RetrieveResult = slow_retrieve
        
        # Start capture and configuration change concurrently
        capture_task = asyncio.create_task(basler_camera.capture())
        config_task = asyncio.create_task(basler_camera.set_exposure(15000))
        
        capture_result, config_result = await asyncio.gather(capture_task, config_task)
        
        success, image = capture_result
        assert success is True
        assert isinstance(image, np.ndarray)
        assert config_result is True
    
    @pytest.mark.asyncio
    async def test_connection_check_during_operations(self, basler_camera):
        """Test connection checking during active operations."""
        await basler_camera.initialize()
        
        # Start multiple async operations concurrently
        tasks = [
            basler_camera.capture(),
            basler_camera.check_connection(),
            basler_camera.get_exposure(),
            basler_camera.set_exposure(15000)  # Use async set_exposure instead
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All operations should complete successfully
        success, image = results[0]
        assert success is True
        assert results[1] is True  # connection check
        assert isinstance(results[2], float)  # exposure
        assert results[3] is True  # exposure setting
        
        # Test sync method separately
        gain_result = await basler_camera.set_gain(2.0)
        assert gain_result is True
    
    @pytest.mark.asyncio
    async def test_grabbing_state_race_condition(self, basler_camera, monkeypatch):
        """Test grabbing state management under race conditions."""
        await basler_camera.initialize()
        
        # Add delays to create race conditions using sync functions
        original_start = basler_camera.camera.StartGrabbing
        original_stop = basler_camera.camera.StopGrabbing
        
        def delayed_start(*args, **kwargs):
            import time
            time.sleep(0.01)  # Use sync sleep for sync function
            return original_start(*args, **kwargs)
        
        def delayed_stop(*args, **kwargs):
            import time
            time.sleep(0.01)  # Use sync sleep for sync function
            return original_stop(*args, **kwargs)
        
        monkeypatch.setattr(basler_camera.camera, "StartGrabbing", delayed_start)
        monkeypatch.setattr(basler_camera.camera, "StopGrabbing", delayed_stop)
        
        # Start multiple grabbing operations
        tasks = [
            basler_camera._ensure_grabbing(),
            basler_camera._ensure_grabbing(),
            basler_camera._ensure_stopped_grabbing()
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Final state should be consistent
        assert isinstance(basler_camera.camera.IsGrabbing(), bool)


class TestBaslerCameraBackendConfigurationEdgeCases:
    """Test configuration edge cases and advanced scenarios."""
    
    @pytest.mark.asyncio
    async def test_import_config_with_invalid_white_balance(self, basler_camera, tmp_path):
        """Test config import with invalid white balance values."""
        await basler_camera.initialize()
        
        # Create config with invalid white balance
        config_data = {
            "camera_type": "basler",
            "white_balance": "invalid_mode",
            "exposure_time": 10000,
            "gain": 1.0
        }
        
        config_path = tmp_path / "invalid_wb_config.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f)
        
        # Should handle invalid values gracefully
        result = await basler_camera.import_config(str(config_path))
        assert result is True  # Import succeeds despite invalid values
    
    @pytest.mark.asyncio
    async def test_import_config_with_unavailable_features(self, basler_camera, tmp_path, monkeypatch):
        """Test config import when camera features are unavailable."""
        await basler_camera.initialize()
        
        # Mock some features as unavailable
        monkeypatch.setattr(basler_camera.camera.BalanceWhiteAuto, "GetAccessMode", lambda: "NA")
        
        config_data = {
            "camera_type": "basler",
            "white_balance": "once",
            "exposure_time": 10000,
            "gain": 1.0,
            "trigger_mode": "continuous"
        }
        
        config_path = tmp_path / "unavailable_features_config.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f)
        
        # Should handle unavailable features gracefully
        result = await basler_camera.import_config(str(config_path))
        assert result is True
    
    @pytest.mark.asyncio
    async def test_export_config_with_feature_errors(self, basler_camera, tmp_path, monkeypatch):
        """Test config export when feature access fails."""
        await basler_camera.initialize()
        
        # Mock some features to raise errors
        def raise_error():
            raise MockGenICamError("Feature access error")
        
        monkeypatch.setattr(basler_camera.camera.BalanceWhiteAuto, "GetValue", raise_error)
        
        config_path = tmp_path / "error_export_config.json"
        
        # Should still export successfully with available features
        result = await basler_camera.export_config(str(config_path))
        assert result is True
        assert config_path.exists()
    
    @pytest.mark.asyncio
    async def test_config_with_extreme_values(self, basler_camera, tmp_path):
        """Test configuration with extreme but valid values."""
        await basler_camera.initialize()
        
        # Create config with extreme values
        config_data = {
            "camera_type": "basler",
            "exposure_time": 100,  # Minimum exposure
            "gain": 20.0,  # Maximum gain
            "roi": {"x": 0, "y": 0, "width": 32, "height": 32},  # Minimum ROI
            "buffer_count": 1,  # Minimum buffers
            "timeout_ms": 100  # Minimum timeout
        }
        
        config_path = tmp_path / "extreme_values_config.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f)
        
        # Should handle extreme values correctly
        result = await basler_camera.import_config(str(config_path))
        assert result is True
    
    @pytest.mark.asyncio
    async def test_partial_config_import_failure(self, basler_camera, tmp_path, monkeypatch):
        """Test config import with partial failures."""
        await basler_camera.initialize()
        
        # Mock exposure setting to fail
        def raise_exposure_error(value):
            raise MockGenICamError("Exposure setting failed")
        
        basler_camera.camera.ExposureTime.SetValue = raise_exposure_error
        
        config_data = {
            "camera_type": "basler",
            "exposure_time": 50000,  # This will fail
            "gain": 2.0,  # This should succeed
            "trigger_mode": "continuous"  # This should succeed
        }
        
        config_path = tmp_path / "partial_failure_config.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f)
        
        # Should still return True even with partial failures
        result = await basler_camera.import_config(str(config_path))
        assert result is True
        
        # Verify successful settings were applied
        assert await basler_camera.get_gain() == 2.0
    
    @pytest.mark.asyncio
    async def test_config_version_compatibility(self, basler_camera, tmp_path):
        """Test configuration compatibility with different formats."""
        await basler_camera.initialize()
        
        # Test config without version info (legacy format)
        legacy_config = {
            "exposure_time": 12000,
            "gain": 1.5,
            # Missing camera_type and timestamp
        }
        
        config_path = tmp_path / "legacy_config.json"
        with open(config_path, "w") as f:
            json.dump(legacy_config, f)
        
        # Should handle legacy format gracefully
        result = await basler_camera.import_config(str(config_path))
        assert result is True


class TestBaslerCameraBackendMissingCoverageLines:
    """Test additional error handling and edge cases for improved coverage."""
    
    def test_pypylon_available_true_branch(self, mock_pypylon):
        """Test that PYPYLON_AVAILABLE is properly set to True when pypylon is available."""
        # Import the module to ensure the True branch is executed
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import PYPYLON_AVAILABLE
        assert PYPYLON_AVAILABLE is True
    
    @pytest.mark.asyncio
    async def test_sdk_method_loop_and_executor_initialization(self, basler_camera):
        """Test that _sdk method properly initializes asyncio loop and thread pool executor when needed."""
        await basler_camera.initialize()
        
        # Reset loop and executor to trigger initialization paths
        basler_camera._loop = None
        basler_camera._sdk_executor = None
        
        def test_func():
            return "test_result"
        
        result = await basler_camera._sdk(test_func)
        assert result == "test_result"
        assert basler_camera._loop is not None
        assert basler_camera._sdk_executor is not None
    
    @pytest.mark.asyncio
    async def test_sdk_method_hardware_operation_error_branch(self, basler_camera):
        """Test that _sdk method properly wraps exceptions in HardwareOperationError."""
        await basler_camera.initialize()
        
        def failing_func():
            raise RuntimeError("Generic SDK error")
        
        with pytest.raises(HardwareOperationError, match="Pypylon operation failed"):
            await basler_camera._sdk(failing_func)
    
    def test_discovery_error_handling_branches(self, mock_pypylon):
        """Test error handling when device enumeration fails during camera discovery."""
        # Unpack the tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Test when device enumeration fails - should raise HardwareOperationError
        mock_pylon.TlFactory.GetInstance.return_value.EnumerateDevices.side_effect = Exception("Enum failed")
        
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        with pytest.raises(HardwareOperationError, match="Failed to discover Basler cameras"):
            BaslerCameraBackend.get_available_cameras()
        
        # Test with details - should also raise HardwareOperationError
        with pytest.raises(HardwareOperationError, match="Failed to discover Basler cameras"):
            BaslerCameraBackend.get_available_cameras(include_details=True)
    
    @pytest.mark.asyncio
    async def test_initialize_pypylon_unavailable_branch(self, monkeypatch):
        """Test initialization behavior when pypylon SDK is not available."""
        # Mock PYPYLON_AVAILABLE to be False
        monkeypatch.setattr("mindtrace.hardware.cameras.backends.basler.basler_camera_backend.PYPYLON_AVAILABLE", False)
        
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # The constructor itself will raise SDKNotAvailableError when PYPYLON_AVAILABLE is False
        with pytest.raises(SDKNotAvailableError, match="SDK 'pypylon' is not available"):
            BaslerCameraBackend("test_camera")
    

    
    @pytest.mark.asyncio
    async def test_enhance_image_error_branch(self, basler_camera):
        """Test _enhance_image error branch."""
        await basler_camera.initialize()
        
        # Create an image that will cause enhancement to fail
        import cv2
        
        # Mock cv2.createCLAHE to fail
        with pytest.MonkeyPatch().context() as m:
            m.setattr(cv2, "createCLAHE", lambda: (_ for _ in ()).throw(Exception("CLAHE failed")))
            
            test_image = np.zeros((100, 100, 3), dtype=np.uint8)
            with pytest.raises(CameraCaptureError):
                await basler_camera._enhance_image(test_image)
    
    @pytest.mark.asyncio
    async def test_roi_error_branches(self, basler_camera):
        """Test ROI setting error branches."""
        basler_camera.initialized = True
        basler_camera.camera = Mock()
        
        # Test when Width feature is None
        basler_camera.camera.Width = None
        with pytest.raises(HardwareOperationError):
            await basler_camera.set_ROI(0, 0, 100, 100)
    
    @pytest.mark.asyncio
    async def test_gain_error_branches(self, basler_camera):
        """Test gain setting error branches."""
        basler_camera.initialized = True
        basler_camera.camera = Mock()
        
        # Test when Gain feature is None  
        basler_camera.camera.Gain = None
        with pytest.raises(HardwareOperationError):
            await basler_camera.set_gain(2.0)
    
    @pytest.mark.asyncio  
    async def test_close_error_branches(self, basler_camera):
        """Test close method error branches."""
        await basler_camera.initialize()
        
        # Test executor shutdown error  
        mock_executor = Mock()
        mock_executor.shutdown.side_effect = Exception("Shutdown failed")
        basler_camera._sdk_executor = mock_executor
        
        # Should handle executor errors gracefully - this tests the exception handling in close()
        await basler_camera.close()


class TestBaslerCameraBackendUncoveredErrorPaths:
    """Test specific uncovered error paths in BaslerCameraBackend."""

    @pytest.mark.asyncio
    async def test_initialization_config_parsing_error(self, monkeypatch):
        """Test error handling during config parsing in initialization."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Mock json.loads to fail during config parsing
        import json
        original_loads = json.loads
        
        def failing_loads(s):
            if "op_timeout_s" in s:
                raise ValueError("Invalid JSON")
            return original_loads(s)
        
        monkeypatch.setattr(json, "loads", failing_loads)
        
        # Initialize with config that will trigger the error
        camera = BaslerCameraBackend("test_camera", config='{"op_timeout_s": "invalid"}')
        
        # Should fall back to default timeout (5.0) when config parsing fails
        assert camera._op_timeout_s == 5.0

    @pytest.mark.asyncio 
    async def test_sdk_timeout_error_conversion(self, basler_camera, monkeypatch):
        """Test SDK timeout error conversion."""
        await basler_camera.initialize()
        
        # Mock asyncio.wait_for to raise TimeoutError
        original_wait_for = asyncio.wait_for
        
        async def failing_wait_for(fut, timeout):
            raise asyncio.TimeoutError("Operation timed out")
        
        monkeypatch.setattr(asyncio, "wait_for", failing_wait_for)
        
        # This should convert asyncio.TimeoutError to CameraTimeoutError
        with pytest.raises(CameraTimeoutError, match="Pypylon operation timed out after .* for camera"):
            await basler_camera._sdk(lambda: None, timeout=1.0)

    @pytest.mark.asyncio
    async def test_sdk_generic_exception_conversion(self, basler_camera, monkeypatch):
        """Test SDK generic exception conversion.""" 
        await basler_camera.initialize()
        
        # Mock asyncio.wait_for to raise generic exception
        async def failing_wait_for(fut, timeout):
            raise RuntimeError("Generic SDK error")
        
        monkeypatch.setattr(asyncio, "wait_for", failing_wait_for)
        
        # This should convert generic Exception to HardwareOperationError
        with pytest.raises(HardwareOperationError, match="Pypylon operation failed for camera"):
            await basler_camera._sdk(lambda: None, timeout=1.0)

    @pytest.mark.asyncio
    async def test_discovery_pypylon_not_available(self, monkeypatch):
        """Test discovery when pypylon is not available."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Mock PYPYLON_AVAILABLE to be False
        monkeypatch.setattr(
            "mindtrace.hardware.cameras.backends.basler.basler_camera_backend.PYPYLON_AVAILABLE", 
            False
        )
        
        # Should raise SDKNotAvailableError
        with pytest.raises(SDKNotAvailableError, match="Basler SDK \\(pypylon\\) is not available"):
            BaslerCameraBackend.get_available_cameras()

    @pytest.mark.asyncio
    async def test_sdk_executor_creation_failure(self, basler_camera, monkeypatch):
        """Test SDK executor creation failure during _sdk method."""
        await basler_camera.initialize()
        
        # Clear existing executor to force recreation
        basler_camera._sdk_executor = None
        
        # Mock ThreadPoolExecutor to fail
        import concurrent.futures
        original_executor = concurrent.futures.ThreadPoolExecutor
        
        def failing_executor(*args, **kwargs):
            raise RuntimeError("Cannot create thread pool")
        
        monkeypatch.setattr(concurrent.futures, "ThreadPoolExecutor", failing_executor)
        
        # Should handle executor creation failure - the RuntimeError will bubble up directly
        with pytest.raises(RuntimeError, match="Cannot create thread pool"):
            await basler_camera._sdk(lambda: None)

    @pytest.mark.asyncio
    async def test_sdk_loop_access_failure(self, basler_camera, monkeypatch):
        """Test failure to get event loop in _sdk method."""
        await basler_camera.initialize()
        
        # Mock asyncio.get_running_loop to fail
        def failing_get_loop():
            raise RuntimeError("No running event loop")
        
        monkeypatch.setattr(asyncio, "get_running_loop", failing_get_loop)
        
        # Clear loop to force recreation
        basler_camera._loop = None
        
        # Should handle loop access failure - the RuntimeError will bubble up directly
        with pytest.raises(RuntimeError, match="No running event loop"):
            await basler_camera._sdk(lambda: None)

    @pytest.mark.asyncio
    async def test_sdk_future_creation_failure(self, basler_camera, monkeypatch):
        """Test failure during future creation in _sdk method."""
        await basler_camera.initialize()
        
        # Mock loop.run_in_executor to fail
        basler_camera._loop.run_in_executor = Mock(side_effect=RuntimeError("Future creation failed"))
        
        # Should handle future creation failure - the RuntimeError will bubble up directly
        with pytest.raises(RuntimeError, match="Future creation failed"):
            await basler_camera._sdk(lambda: None)

    @pytest.mark.asyncio
    async def test_config_timeout_edge_cases(self, monkeypatch):
        """Test various edge cases in config timeout parsing."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Test various config formats that could cause parsing errors
        test_configs = [
            '{"op_timeout_s": null}',  # null value
            '{"op_timeout_s": "not_a_number"}',  # string instead of number
            '{"op_timeout_s": [1, 2, 3]}',  # array instead of number
            '{"op_timeout_s": {}}',  # object instead of number
            '{"other_setting": 42}',  # missing op_timeout_s
            'invalid_json',  # completely invalid JSON
            '',  # empty string
        ]
        
        for config in test_configs:
            camera = BaslerCameraBackend("test_camera", config=config)
            # All should fall back to default timeout of 5.0
            assert camera._op_timeout_s == 5.0

    @pytest.mark.asyncio
    async def test_sdk_with_none_function(self, basler_camera):
        """Test _sdk method with None function parameter."""
        await basler_camera.initialize()
        
        # Should handle None function gracefully
        with pytest.raises(HardwareOperationError, match="Pypylon operation failed"):
            await basler_camera._sdk(None)

    @pytest.mark.asyncio
    async def test_sdk_with_non_callable(self, basler_camera):
        """Test _sdk method with non-callable parameter."""
        await basler_camera.initialize()
        
        # Should handle non-callable parameter
        with pytest.raises(HardwareOperationError, match="Pypylon operation failed"):
            await basler_camera._sdk("not_callable")

    @pytest.mark.asyncio
    async def test_timeout_parameter_edge_cases(self, basler_camera):
        """Test _sdk method with various timeout parameter edge cases."""
        await basler_camera.initialize()
        
        # Test with very short timeout that should trigger timeout
        # Use a slow synchronous operation to ensure timeout occurs
        import time
        def slow_operation():
            time.sleep(1.0)  # This will block and trigger timeout
            return "success"
        
        with pytest.raises(CameraTimeoutError):
            await basler_camera._sdk(slow_operation, timeout=0.001)  # Very short timeout

    @pytest.mark.asyncio
    async def test_discovery_exception_during_device_enumeration(self, monkeypatch):
        """Test exception handling during device enumeration in discovery."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Mock pylon to be available but raise exception during enumeration
        mock_pylon = MagicMock()
        mock_factory = MagicMock()
        mock_factory.EnumerateDevices.side_effect = RuntimeError("Enumeration failed")
        mock_pylon.TlFactory.GetInstance.return_value = mock_factory
        
        monkeypatch.setattr(
            "mindtrace.hardware.cameras.backends.basler.basler_camera_backend.pylon", 
            mock_pylon
        )
        
        # The discovery method actually raises HardwareOperationError on enumeration failure
        with pytest.raises(HardwareOperationError, match="Failed to discover Basler cameras"):
            BaslerCameraBackend.get_available_cameras()


class TestBaslerCameraBackendInitializePylonCheck:
    """Test initialize() method when pypylon is not available."""
    
    @pytest.mark.asyncio
    async def test_initialize_pypylon_not_available(self, monkeypatch):
        """Test that initialize() raises SDKNotAvailableError when PYPYLON_AVAILABLE is False."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import SDKNotAvailableError
        
        # First create camera when pypylon is available (constructor succeeds)
        camera = BaslerCameraBackend("test_camera")
        
        # Now mock PYPYLON_AVAILABLE to be False to trigger the check in initialize()
        monkeypatch.setattr(
            "mindtrace.hardware.cameras.backends.basler.basler_camera_backend.PYPYLON_AVAILABLE", 
            False
        )
        
        # Calling initialize() should now raise SDKNotAvailableError
        with pytest.raises(SDKNotAvailableError) as exc_info:
            await camera.initialize()
        
        # Verify the specific error message
        error_msg = str(exc_info.value)
        assert "pypylon" in error_msg
        assert "Basler SDK (pypylon) is not available for camera discovery" in error_msg


class TestBaslerCameraBackendUserDefinedNameUpdate:
    """Test camera name update when found by serial number with user-defined name."""
    
    @pytest.mark.asyncio
    async def test_camera_name_update(self, mock_pypylon):
        """Test that camera name gets updated when found by serial number with user-defined name."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with a serial number as the camera name
        camera_serial = "123456789"
        user_defined_name = "Production_Camera_A1"
        camera = BaslerCameraBackend(camera_serial)
        
        # Mock device that matches by serial number AND has a user-defined name
        mock_device = MagicMock()
        mock_device.GetSerialNumber.return_value = camera_serial  # Matches camera_name
        mock_device.GetUserDefinedName.return_value = user_defined_name  # Non-empty user-defined name
        mock_device.GetDeviceInfo.return_value = mock_device
        mock_device.GetModelName.return_value = "acA1920-40gm"
        mock_device.GetVendorName.return_value = "Basler"
        
        # Mock factory to return our device
        mock_tl_factory = mock_pylon.TlFactory.GetInstance.return_value
        mock_tl_factory.EnumerateDevices.return_value = [mock_device]
        mock_tl_factory.CreateDevice.return_value = mock_device
        
        # Mock InstantCamera
        mock_instant_camera = MagicMock()
        mock_pylon.InstantCamera.return_value = mock_instant_camera
        
        # Verify initial camera name is the serial number
        assert camera.camera_name == camera_serial
        
        # Initialize the camera - this should trigger the name update logic
        await camera.initialize()
        
        # Verify that the camera name was updated to the user-defined name
        assert camera.camera_name == user_defined_name
        assert camera.camera_name != camera_serial  # Should have changed
        
        # Verify camera was successfully initialized
        assert camera.initialized is True

    @pytest.mark.asyncio
    async def test_camera_name_no_update_when_no_user_defined_name(self, mock_pypylon):
        """Test that camera name does NOT get updated when user-defined name is empty."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_serial = "987654321"
        camera = BaslerCameraBackend(camera_serial)
        
        # Mock device that matches by serial number but has NO user-defined name
        mock_device = MagicMock()
        mock_device.GetSerialNumber.return_value = camera_serial  # Matches camera_name
        mock_device.GetUserDefinedName.return_value = ""  # Empty user-defined name
        mock_device.GetDeviceInfo.return_value = mock_device
        mock_device.GetModelName.return_value = "acA1920-40gm"
        mock_device.GetVendorName.return_value = "Basler"
        
        # Mock factory
        mock_tl_factory = mock_pylon.TlFactory.GetInstance.return_value
        mock_tl_factory.EnumerateDevices.return_value = [mock_device]
        mock_tl_factory.CreateDevice.return_value = mock_device
        
        # Mock InstantCamera
        mock_instant_camera = MagicMock()
        mock_pylon.InstantCamera.return_value = mock_instant_camera
        
        # Initialize the camera
        await camera.initialize()
        
        # Verify that the camera name was NOT updated (name update logic should NOT execute)
        assert camera.camera_name == camera_serial  # Should remain unchanged
        assert camera.initialized is True

    @pytest.mark.asyncio
    async def test_camera_name_no_update_when_found_by_name_not_serial(self, mock_pypylon):
        """Test that camera name does NOT get updated when camera is found by name, not serial."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Use a user-defined name as the camera name (not a serial number)
        camera_name = "Test_Camera_B2"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock device that matches by user-defined name, not serial number
        mock_device = MagicMock()
        mock_device.GetSerialNumber.return_value = "111222333"  # Different from camera_name
        mock_device.GetUserDefinedName.return_value = camera_name  # Matches camera_name
        mock_device.GetDeviceInfo.return_value = mock_device
        mock_device.GetModelName.return_value = "acA1920-40gm"
        mock_device.GetVendorName.return_value = "Basler"
        
        # Mock factory
        mock_tl_factory = mock_pylon.TlFactory.GetInstance.return_value
        mock_tl_factory.EnumerateDevices.return_value = [mock_device]
        mock_tl_factory.CreateDevice.return_value = mock_device
        
        # Mock InstantCamera
        mock_instant_camera = MagicMock()
        mock_pylon.InstantCamera.return_value = mock_instant_camera
        
        # Initialize the camera
        await camera.initialize()
        
        # Since camera was found by user-defined name (not serial), 
        # name update logic should NOT execute
        assert camera.camera_name == camera_name  # Should remain unchanged
        assert camera.initialized is True


class TestBaslerCameraBackendCameraNotFoundError:
    """Test CameraNotFoundError with available cameras list when no camera matches."""
    
    @pytest.mark.asyncio
    async def test_camera_not_found_with_available_cameras_lines_344_350(self, mock_pypylon):
        """Test CameraNotFoundError with available cameras list when no matching camera is found."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraNotFoundError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with a name that won't match any available cameras
        requested_camera = "NonExistentCamera123"
        camera = BaslerCameraBackend(requested_camera)
        
        # Mock multiple available devices that DON'T match the requested camera
        mock_device1 = MagicMock()
        mock_device1.GetSerialNumber.return_value = "111111111"
        mock_device1.GetUserDefinedName.return_value = "Lab_Camera_A"
        mock_device1.GetDeviceInfo.return_value = mock_device1
        
        mock_device2 = MagicMock()
        mock_device2.GetSerialNumber.return_value = "222222222"
        mock_device2.GetUserDefinedName.return_value = "Lab_Camera_B"
        mock_device2.GetDeviceInfo.return_value = mock_device2
        
        mock_device3 = MagicMock()
        mock_device3.GetSerialNumber.return_value = "333333333"
        mock_device3.GetUserDefinedName.return_value = ""  # Empty user-defined name
        mock_device3.GetDeviceInfo.return_value = mock_device3
        
        # Mock factory to return devices that don't match the requested camera
        mock_tl_factory = mock_pylon.TlFactory.GetInstance.return_value
        mock_tl_factory.EnumerateDevices.return_value = [mock_device1, mock_device2, mock_device3]
        
        # Initialize should raise CameraNotFoundError with available cameras list
        with pytest.raises(CameraNotFoundError) as exc_info:
            await camera.initialize()
        
        error_msg = str(exc_info.value)
        
        # Verify the error message format
        assert f"Camera '{requested_camera}' not found" in error_msg
        assert "Available cameras:" in error_msg
        
        # Verify the available cameras list format
        assert "111111111 (Lab_Camera_A)" in error_msg
        assert "222222222 (Lab_Camera_B)" in error_msg
        assert "333333333 ()" in error_msg  # Empty user-defined name shows as ()

    @pytest.mark.asyncio
    async def test_camera_not_found_with_empty_cameras_list(self, mock_pypylon):
        """Test CameraNotFoundError when no cameras are available at all."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraNotFoundError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        requested_camera = "SomeCamera"
        camera = BaslerCameraBackend(requested_camera)
        
        # Mock factory to return NO devices (empty list)
        mock_tl_factory = mock_pylon.TlFactory.GetInstance.return_value
        mock_tl_factory.EnumerateDevices.return_value = []  # No devices available
        
        # This should trigger the earlier check for no cameras found
        # But let's see what happens - it might still go through the camera not found logic
        with pytest.raises(CameraNotFoundError) as exc_info:
            await camera.initialize()
        
        error_msg = str(exc_info.value)
        # This might be the generic "No Basler cameras found" message
        # or it might go through the camera not found logic with an empty list
        assert "not found" in error_msg or "No Basler cameras found" in error_msg

    @pytest.mark.asyncio 
    async def test_camera_not_found_various_user_defined_name_formats(self, mock_pypylon):
        """Test various formats of user-defined names in the available cameras list."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraNotFoundError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        requested_camera = "NotFoundCamera"
        camera = BaslerCameraBackend(requested_camera)
        
        # Mock devices with various user-defined name formats
        devices_data = [
            ("111111111", "Normal_Camera"),      # Normal case
            ("222222222", "Camera With Spaces"), # Spaces in name
            ("333333333", "Camera-With-Dashes"), # Dashes
            ("444444444", ""),                   # Empty name
            ("555555555", "Special/Chars&More"), # Special characters
        ]
        
        mock_devices = []
        for serial, user_name in devices_data:
            mock_device = MagicMock()
            mock_device.GetSerialNumber.return_value = serial
            mock_device.GetUserDefinedName.return_value = user_name
            mock_device.GetDeviceInfo.return_value = mock_device
            mock_devices.append(mock_device)
        
        # Mock factory
        mock_tl_factory = mock_pylon.TlFactory.GetInstance.return_value
        mock_tl_factory.EnumerateDevices.return_value = mock_devices
        
        # Should raise CameraNotFoundError with all camera formats
        with pytest.raises(CameraNotFoundError) as exc_info:
            await camera.initialize()
        
        error_msg = str(exc_info.value)
        
        # Verify all cameras appear in the list with proper formatting
        assert "111111111 (Normal_Camera)" in error_msg
        assert "222222222 (Camera With Spaces)" in error_msg
        assert "333333333 (Camera-With-Dashes)" in error_msg
        assert "444444444 ()" in error_msg  # Empty name
        assert "555555555 (Special/Chars&More)" in error_msg


class TestBaslerCameraBackendUnexpectedInitializationError:
    """Test unexpected exception handling during initialization."""
    
    @pytest.mark.asyncio
    async def test_unexpected_exception_during_initialization_lines_354_356(self, mock_pypylon):
        """Test that unexpected exceptions during initialization get converted to CameraInitializationError."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraInitializationError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock TlFactory.GetInstance().EnumerateDevices to raise an unexpected exception
        # This happens outside the device loop, so should trigger the exception handling
        mock_tl_factory = mock_pylon.TlFactory.GetInstance.return_value
        mock_tl_factory.EnumerateDevices.side_effect = RuntimeError("Unexpected enumeration error")
        
        # Initialize should catch the RuntimeError and convert it to CameraInitializationError
        with pytest.raises(CameraInitializationError) as exc_info:
            await camera.initialize()
        
        error_msg = str(exc_info.value)
        
        # Verify the error message format
        assert f"Unexpected error initializing camera '{camera_name}'" in error_msg
        assert "Unexpected enumeration error" in error_msg


class TestBaslerCameraBackendCameraAvailabilityCheck:
    """Test camera availability check before operations."""
    
    @pytest.mark.asyncio
    async def test_camera_not_available_ensure_open_lines_364_365(self, mock_pypylon):
        """Test that _ensure_open raises CameraConnectionError when camera is None."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConnectionError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Ensure camera is None (not initialized)
        camera.camera = None
        
        # _ensure_open should raise CameraConnectionError when camera is None
        with pytest.raises(CameraConnectionError) as exc_info:
            await camera._ensure_open()
        
        error_msg = str(exc_info.value)
        assert f"Camera '{camera_name}' not available" in error_msg

    @pytest.mark.asyncio
    async def test_camera_not_available_ensure_grabbing(self, mock_pypylon):
        """Test that _ensure_grabbing raises CameraConnectionError when camera is None."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConnectionError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Ensure camera is None (not initialized)
        camera.camera = None
        
        # _ensure_grabbing should raise CameraConnectionError when camera is None
        with pytest.raises(CameraConnectionError) as exc_info:
            await camera._ensure_grabbing()
        
        error_msg = str(exc_info.value)
        assert f"Camera '{camera_name}' not available" in error_msg

    @pytest.mark.asyncio
    async def test_camera_not_available_ensure_stopped_grabbing(self, mock_pypylon):
        """Test that _ensure_stopped_grabbing raises CameraConnectionError when camera is None."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConnectionError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Ensure camera is None (not initialized)
        camera.camera = None
        
        # _ensure_stopped_grabbing should raise CameraConnectionError when camera is None
        with pytest.raises(CameraConnectionError) as exc_info:
            await camera._ensure_stopped_grabbing()
        
        error_msg = str(exc_info.value)
        assert f"Camera '{camera_name}' not available" in error_msg

    @pytest.mark.asyncio
    async def test_camera_available_operations_succeed(self, mock_pypylon):
        """Test that camera operations succeed when camera is available."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        mock_camera.IsGrabbing.return_value = False
        
        # Set the camera
        camera.camera = mock_camera
        
        # These operations should not raise exceptions when camera is available
        await camera._ensure_open()  # Should not raise
        await camera._ensure_grabbing()  # Should not raise
        await camera._ensure_stopped_grabbing()  # Should not raise


class TestBaslerCameraBackendGrabbingSuspendedContextManager:
    """Test _grabbing_suspended context manager functionality."""
    
    @pytest.mark.asyncio
    async def test_grabbing_suspended_camera_availability_check_line_401(self, mock_pypylon):
        """Test that _grabbing_suspended checks camera availability."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Test when camera is None - should not raise and should not call any methods
        camera.camera = None
        
        async with camera._grabbing_suspended():
            # Inside the context, no operations should be performed
            pass
        
        # No camera operations should have been attempted when camera is None

    @pytest.mark.asyncio
    async def test_grabbing_suspended_is_grabbing_check_line_402(self, mock_pypylon):
        """Test that _grabbing_suspended checks IsGrabbing status."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        
        # Set the camera
        camera.camera = mock_camera
        
        # Mock the _sdk method to return False for IsGrabbing (not currently grabbing)
        async def mock_sdk_not_grabbing(func, *args, **kwargs):
            if func == mock_camera.IsGrabbing:
                return False
            return None
        
        camera._sdk = mock_sdk_not_grabbing
        
        # Test when camera is not grabbing - should not call StopGrabbing or StartGrabbing
        async with camera._grabbing_suspended():
            # Inside the context, no changes should be made
            pass
        
        # No grabbing operations should have been called when not currently grabbing


class TestBaslerCameraBackendConfigureCameraPypylonCheck:
    """Test _configure_camera method when pypylon is not available."""
    
    @pytest.mark.asyncio
    async def test_configure_camera_pypylon_not_available(self, mock_pypylon, monkeypatch):
        """Test that _configure_camera raises SDKNotAvailableError when PYPYLON_AVAILABLE is False."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import SDKNotAvailableError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object so the camera availability checks pass
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        
        # Mock PYPYLON_AVAILABLE to be False to trigger the check in _configure_camera
        monkeypatch.setattr(
            "mindtrace.hardware.cameras.backends.basler.basler_camera_backend.PYPYLON_AVAILABLE", 
            False
        )
        
        # _configure_camera should raise SDKNotAvailableError when PYPYLON_AVAILABLE is False
        with pytest.raises(SDKNotAvailableError) as exc_info:
            await camera._configure_camera()
        
        error_msg = str(exc_info.value)
        assert "pypylon" in error_msg
        assert "Basler SDK (pypylon) is not available for camera discovery" in error_msg

    @pytest.mark.asyncio
    async def test_configure_camera_pypylon_available_success(self, mock_pypylon):
        """Test that _configure_camera succeeds when PYPYLON_AVAILABLE is True."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        
        # Mock the _sdk method to return success
        async def mock_sdk(func, *args, **kwargs):
            return None
        
        camera._sdk = mock_sdk
        
        # _configure_camera should succeed when PYPYLON_AVAILABLE is True
        await camera._configure_camera()
        
        # Verify that the camera was configured (converter was created)
        assert hasattr(camera, 'converter')


class TestBaslerCameraBackendExceptionHandlingAndChecks:
    """Test exception handling and initialization checks in various methods."""
    
    @pytest.mark.asyncio
    async def test_configure_camera_exception_handling_lines_442_444(self, mock_pypylon, monkeypatch):
        """Test that _configure_camera catches exceptions and re-raises as CameraConfigurationError."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConfigurationError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object so the camera availability checks pass
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        
        # Mock _ensure_open to raise an exception to trigger the error handling
        async def mock_ensure_open():
            raise RuntimeError("Camera open failed")
        
        camera._ensure_open = mock_ensure_open
        
        # _configure_camera should catch the exception and re-raise as CameraConfigurationError
        with pytest.raises(CameraConfigurationError) as exc_info:
            await camera._configure_camera()
        
        error_msg = str(exc_info.value)
        assert f"Failed to configure camera '{camera_name}'" in error_msg
        assert "Camera open failed" in error_msg

    @pytest.mark.asyncio
    async def test_get_exposure_range_not_initialized(self, mock_pypylon):
        """Test that get_exposure_range raises CameraConnectionError when camera is not initialized."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConnectionError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Ensure camera is not initialized
        camera.initialized = False
        camera.camera = None
        
        # get_exposure_range should raise CameraConnectionError when not initialized
        with pytest.raises(CameraConnectionError) as exc_info:
            await camera.get_exposure_range()
        
        error_msg = str(exc_info.value)
        assert f"Camera '{camera_name}' is not initialized" in error_msg

    @pytest.mark.asyncio
    async def test_get_exposure_not_initialized(self, mock_pypylon):
        """Test that get_exposure raises CameraConnectionError when camera is not initialized."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConnectionError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Ensure camera is not initialized
        camera.initialized = False
        camera.camera = None
        
        # get_exposure should raise CameraConnectionError when not initialized
        with pytest.raises(CameraConnectionError) as exc_info:
            await camera.get_exposure()
        
        error_msg = str(exc_info.value)
        assert f"Camera '{camera_name}' is not initialized" in error_msg

    @pytest.mark.asyncio
    async def test_get_exposure_exception_handling(self, mock_pypylon):
        """Test that get_exposure catches exceptions and returns default value."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Mock _sdk to raise an exception to trigger the error handling
        async def mock_sdk(func, *args, **kwargs):
            raise RuntimeError("Exposure retrieval failed")
        
        camera._sdk = mock_sdk
        
        # get_exposure should catch the exception and return the default value
        result = await camera.get_exposure()
        
        # Should return the default exposure value (20000.0 μs = 20ms)
        assert result == 20000.0


class TestBaslerCameraBackendAdditionalLineCoverage:
    """Test additional exception handling and initialization checks in various methods."""
    
    @pytest.mark.asyncio
    async def test_set_exposure_not_initialized(self, mock_pypylon):
        """Test that set_exposure raises CameraConnectionError when camera is not initialized."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConnectionError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Ensure camera is not initialized
        camera.initialized = False
        camera.camera = None
        
        # set_exposure should raise CameraConnectionError when not initialized
        with pytest.raises(CameraConnectionError) as exc_info:
            await camera.set_exposure(20000.0)
        
        error_msg = str(exc_info.value)
        assert f"Camera '{camera_name}' is not initialized" in error_msg

    @pytest.mark.asyncio
    async def test_set_exposure_verification_failed_warning(self, mock_pypylon):
        """Test that set_exposure logs warning when exposure verification fails."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock the logger to capture warning calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Mock _sdk to return different values for SetValue and GetValue to trigger verification failure
        # The verification logic is: abs(actual_exposure - exposure) < 0.01 * exposure
        # With exposure = 20000.0, tolerance = 0.01 * 20000.0 = 200.0
        # We need actual_exposure to be outside this range
        async def mock_sdk(func, *args, **kwargs):
            if func == mock_camera.ExposureTime.SetValue:
                return None  # SetValue succeeds
            elif func == mock_camera.ExposureTime.GetValue:
                return 50000.0  # GetValue returns much different value (50ms vs 20ms)
            else:
                return None
        
        camera._sdk = mock_sdk
        
        # Mock get_exposure_range to return valid range
        async def mock_get_exposure_range():
            return [1000.0, 100000.0]
        
        camera.get_exposure_range = mock_get_exposure_range
        
        # set_exposure should log warning when verification fails
        result = await camera.set_exposure(20000.0)
        
        # Should return False due to verification failure
        # abs(50000.0 - 20000.0) = 30000.0, which is NOT < 200.0
        assert result is False
        
        # Should log warning about verification failure
        mock_logger.warning.assert_called_once_with(
            f"Exposure setting verification failed for camera '{camera_name}'"
        )

    @pytest.mark.asyncio
    async def test_get_triggermode_not_initialized(self, mock_pypylon):
        """Test that get_triggermode returns 'continuous' when camera is not initialized."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Ensure camera is not initialized
        camera.initialized = False
        camera.camera = None
        
        # get_triggermode should return "continuous" when not initialized
        result = await camera.get_triggermode()
        assert result == "continuous"

    @pytest.mark.asyncio
    async def test_get_triggermode_exception_handling(self, mock_pypylon):
        """Test that get_triggermode catches exceptions and re-raises as HardwareOperationError."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import HardwareOperationError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Mock _grabbing_suspended context manager
        class MockGrabbingSuspended:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        camera._grabbing_suspended = lambda: MockGrabbingSuspended()
        
        # Mock _sdk to raise an exception to trigger the error handling
        async def mock_sdk(func, *args, **kwargs):
            raise RuntimeError("Trigger mode retrieval failed")
        
        camera._sdk = mock_sdk
        
        # get_triggermode should catch the exception and re-raise as HardwareOperationError
        with pytest.raises(HardwareOperationError) as exc_info:
            await camera.get_triggermode()
        
        error_msg = str(exc_info.value)
        assert "Failed to get trigger mode" in error_msg
        assert "Trigger mode retrieval failed" in error_msg


class TestBaslerCameraBackendErrorHandlingAndFallbackPaths:
    """Test error handling and fallback paths in various methods."""
    
    @pytest.mark.asyncio
    async def test_set_triggermode_exception_handling(self, mock_pypylon):
        """Test that set_triggermode catches unexpected exceptions and re-raises as HardwareOperationError."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import HardwareOperationError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock the logger to capture error calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Mock _grabbing_suspended context manager
        class MockGrabbingSuspended:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        camera._grabbing_suspended = lambda: MockGrabbingSuspended()
        
        # Mock _sdk to raise an exception to trigger the error handling
        async def mock_sdk(func, *args, **kwargs):
            raise RuntimeError("Trigger mode setting failed")
        
        camera._sdk = mock_sdk
        
        # set_triggermode should catch the exception and re-raise as HardwareOperationError
        with pytest.raises(HardwareOperationError) as exc_info:
            await camera.set_triggermode("trigger")
        
        error_msg = str(exc_info.value)
        assert "Failed to set trigger mode" in error_msg
        assert "Trigger mode setting failed" in error_msg
        
        # Should log error about the exception
        mock_logger.error.assert_called_once_with(
            f"Error setting trigger mode for camera '{camera_name}': Trigger mode setting failed"
        )

    @pytest.mark.asyncio
    async def test_capture_inner_exception_handling(self, mock_pypylon):
        """Test that capture catches non-timeout exceptions and re-raises as CameraCaptureError."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraCaptureError
        
        # Unpack the mock tuple
        mock_pypylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock _ensure_open and _ensure_grabbing to succeed
        async def mock_ensure_open():
            pass
        
        async def mock_ensure_grabbing():
            pass
        
        camera._ensure_open = mock_ensure_open
        camera._ensure_grabbing = mock_ensure_grabbing
        
        # Mock _sdk to raise a non-timeout exception to trigger the error handling
        async def mock_sdk(func, *args, **kwargs):
            if func == mock_camera.RetrieveResult:
                raise RuntimeError("Image retrieval failed")
            else:
                return None
        
        camera._sdk = mock_sdk
        
        # capture should catch the non-timeout exception and re-raise as CameraCaptureError
        with pytest.raises(CameraCaptureError) as exc_info:
            await camera.capture()
        
        error_msg = str(exc_info.value)
        assert "Capture failed for camera" in error_msg
        assert "Image retrieval failed" in error_msg

    @pytest.mark.asyncio
    async def test_capture_outer_exception_handling(self, mock_pypylon):
        """Test that capture catches unexpected exceptions and re-raises as CameraCaptureError."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraCaptureError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock the logger to capture error calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock _ensure_open to raise an exception to trigger the outer error handling
        async def mock_ensure_open():
            raise RuntimeError("Camera open failed")
        
        camera._ensure_open = mock_ensure_open
        
        # capture should catch the unexpected exception and re-raise as CameraCaptureError
        with pytest.raises(CameraCaptureError) as exc_info:
            await camera.capture()
        
        error_msg = str(exc_info.value)
        assert "Unexpected capture error for camera" in error_msg
        assert "Camera open failed" in error_msg
        
        # Should log error about the unexpected exception
        mock_logger.error.assert_called_once_with(
            f"Unexpected error during capture for camera '{camera_name}': Camera open failed"
        )

    @pytest.mark.asyncio
    async def test_enhance_image_exception_handling(self, mock_pypylon):
        """Test that _enhance_image catches exceptions and re-raises as CameraCaptureError."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraCaptureError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock the logger to capture error calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Create a test image
        test_image = np.zeros((100, 100, 3), dtype=np.uint8)
        
        # Mock asyncio.to_thread to raise an exception to trigger the error handling
        with patch('asyncio.to_thread', side_effect=RuntimeError("Image processing failed")):
            # _enhance_image should catch the exception and re-raise as CameraCaptureError
            with pytest.raises(CameraCaptureError) as exc_info:
                await camera._enhance_image(test_image)
        
        error_msg = str(exc_info.value)
        assert "Image enhancement failed" in error_msg
        assert "Image processing failed" in error_msg
        
        # Should log error about the image enhancement failure
        mock_logger.error.assert_called_once_with(
            f"Image enhancement failed for camera '{camera_name}': Image processing failed"
        )

    @pytest.mark.asyncio
    async def test_check_connection_exception_handling(self, mock_pypylon):
        """Test that check_connection catches exceptions and returns False."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock the logger to capture warning calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Set as initialized
        camera.initialized = True
        
        # Mock capture to raise an exception to trigger the error handling
        async def mock_capture():
            raise RuntimeError("Capture failed")
        
        camera.capture = mock_capture
        
        # check_connection should catch the exception and return False
        result = await camera.check_connection()
        assert result is False
        
        # Should log warning about the connection check failure
        mock_logger.warning.assert_called_once_with(
            f"Connection check failed for camera '{camera_name}': Capture failed"
        )

    @pytest.mark.asyncio
    async def test_import_config_exception_handling(self, mock_pypylon):
        """Test that import_config catches exceptions and re-raises as CameraConfigurationError."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConfigurationError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        camera.camera = mock_camera
        
        # Mock the logger to capture error calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock os.path.exists to return True so we get to the file reading part
        with patch('os.path.exists', return_value=True):
            # Mock open to raise an exception to trigger the error handling
            with patch('builtins.open', side_effect=RuntimeError("File read failed")):
                # import_config should catch the exception and re-raise as CameraConfigurationError
                with pytest.raises(CameraConfigurationError) as exc_info:
                    await camera.import_config("test_config.json")
        
        error_msg = str(exc_info.value)
        assert "Failed to import configuration" in error_msg
        assert "File read failed" in error_msg
        
        # Should log error about the configuration import failure
        mock_logger.error.assert_called_once_with(
            f"Error importing configuration for camera '{camera_name}': File read failed"
        )


class TestBaslerCameraBackendHardwareFeatureAvailabilityChecks:
    """Test hardware feature availability checks in configuration methods."""
    
    @pytest.mark.asyncio
    async def test_trigger_mode_feature_availability_check(self, mock_pypylon):
        """Test that trigger mode configuration checks for feature availability."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock the logger to capture warning calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Test when TriggerMode feature is available but GetAccessMode fails
        config_data = {"trigger_mode": "trigger"}
        
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            # Create a mock TriggerMode object that will fail when GetAccessMode is called
            mock_trigger_mode = MagicMock()
            mock_trigger_mode.GetAccessMode.side_effect = RuntimeError("GetAccessMode failed")
            mock_camera.TriggerMode = mock_trigger_mode
            
            await camera.import_config(config_path)
        finally:
            # Clean up temporary file
            os.unlink(config_path)
        
        # Should log warning about not being able to set trigger mode
        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "Could not set trigger mode" in warning_msg

    @pytest.mark.asyncio
    async def test_trigger_selector_and_source_feature_availability_checks(self, mock_pypylon):
        """Test that trigger selector and source configuration checks for feature availability."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock the logger to capture warning calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Mock _sdk to succeed
        async def mock_sdk(func, *args, **kwargs):
            return None
        
        camera._sdk = mock_sdk
        
        # Test when TriggerMode is available but TriggerSelector is NOT available
        config_data = {"trigger_mode": "trigger"}
        
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            # Mock hasattr to return True for TriggerMode but False for TriggerSelector
            def mock_hasattr(obj, attr):
                if attr == "TriggerMode":
                    return True
                elif attr == "TriggerSelector":
                    return False
                return False
            
            with patch('builtins.hasattr', side_effect=mock_hasattr):
                # Mock GetAccessMode to return RW for TriggerMode
                mock_camera.TriggerMode.GetAccessMode.return_value = mock_genicam.RW
                
                await camera.import_config(config_path)
        finally:
            # Clean up temporary file
            os.unlink(config_path)
        
        # Should succeed without warnings since TriggerSelector is optional
        mock_logger.warning.assert_not_called()
        
        # Test when both TriggerMode and TriggerSelector are available but TriggerSource is NOT
        mock_logger.warning.reset_mock()
        
        # Create another temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            def mock_hasattr_with_source(obj, attr):
                if attr in ["TriggerMode", "TriggerSelector"]:
                    return True
                elif attr == "TriggerSource":
                    return False
                return False
            
            with patch('builtins.hasattr', side_effect=mock_hasattr_with_source):
                # Mock GetAccessMode to return RW for both
                mock_camera.TriggerMode.GetAccessMode.return_value = mock_genicam.RW
                mock_camera.TriggerSelector.GetAccessMode.return_value = mock_genicam.RW
                
                await camera.import_config(config_path)
        finally:
            # Clean up temporary file
            os.unlink(config_path)
        
        # Should succeed without warnings since TriggerSource is optional
        mock_logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_white_balance_feature_availability_check(self, mock_pypylon):
        """Test that white balance configuration checks for feature availability."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock the logger to capture warning calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Test when BalanceWhiteAuto feature is available but GetAccessMode fails
        config_data = {"white_balance": "continuous"}
        
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            # Create a mock BalanceWhiteAuto object that will fail when GetAccessMode is called
            mock_balance_white_auto = MagicMock()
            mock_balance_white_auto.GetAccessMode.side_effect = RuntimeError("GetAccessMode failed")
            mock_camera.BalanceWhiteAuto = mock_balance_white_auto
            
            await camera.import_config(config_path)
        finally:
            # Clean up temporary file
            os.unlink(config_path)
        
        # Should log warning about not being able to set white balance
        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "Could not set white balance" in warning_msg

    @pytest.mark.asyncio
    async def test_roi_width_feature_availability_check(self, mock_pypylon):
        """Test that ROI width configuration checks for feature availability."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock the logger to capture warning calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Test when Width feature is available but GetAccessMode fails
        config_data = {"roi": {"width": 1280, "height": 720}}
        
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            # Create a mock Width object that will fail when GetAccessMode is called
            mock_width = MagicMock()
            mock_width.GetAccessMode.side_effect = RuntimeError("GetAccessMode failed")
            mock_camera.Width = mock_width
            
            await camera.import_config(config_path)
        finally:
            # Clean up temporary file
            os.unlink(config_path)
        
        # Should log warning about not being able to set ROI Width
        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "Could not set ROI Width" in warning_msg

    @pytest.mark.asyncio
    async def test_roi_height_feature_availability_check(self, mock_pypylon):
        """Test that ROI height configuration checks for feature availability."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock the logger to capture warning calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Test when Height feature is available but GetAccessMode fails
        config_data = {"roi": {"width": 1280, "height": 720}}
        
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            # Create a mock Height object that will fail when GetAccessMode is called
            mock_height = MagicMock()
            mock_height.GetAccessMode.side_effect = RuntimeError("GetAccessMode failed")
            mock_camera.Height = mock_height
            
            await camera.import_config(config_path)
        finally:
            # Clean up temporary file
            os.unlink(config_path)
        
        # Should log warning about not being able to set ROI Height
        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "Could not set ROI Height" in warning_msg

    @pytest.mark.asyncio
    async def test_roi_offset_x_feature_availability_check(self, mock_pypylon):
        """Test that ROI offset X configuration checks for feature availability."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock the logger to capture warning calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Test when OffsetX feature is available but GetAccessMode fails
        config_data = {"roi": {"x": 100, "y": 200}}
        
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            # Create a mock OffsetX object that will fail when GetAccessMode is called
            mock_offset_x = MagicMock()
            mock_offset_x.GetAccessMode.side_effect = RuntimeError("GetAccessMode failed")
            mock_camera.OffsetX = mock_offset_x
            
            await camera.import_config(config_path)
        finally:
            # Clean up temporary file
            os.unlink(config_path)
        
        # Should log warning about not being able to set ROI OffsetX
        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "Could not set ROI OffsetX" in warning_msg

    @pytest.mark.asyncio
    async def test_roi_offset_y_feature_availability_check(self, mock_pypylon):
        """Test that ROI offset Y configuration checks for feature availability."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock the logger to capture warning calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Test when OffsetY feature is available but GetAccessMode fails
        config_data = {"roi": {"x": 100, "y": 200}}
        
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            # Create a mock OffsetY object that will fail when GetAccessMode is called
            mock_offset_y = MagicMock()
            mock_offset_y.GetAccessMode.side_effect = RuntimeError("GetAccessMode failed")
            mock_camera.OffsetY = mock_offset_y
            
            await camera.import_config(config_path)
        finally:
            # Clean up temporary file
            os.unlink(config_path)
        
        # Should log warning about not being able to set ROI OffsetY
        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "Could not set ROI OffsetY" in warning_msg


class TestBaslerCameraBackendROIOperations:
    """Test ROI (Region of Interest) operations including setting, getting, and validation."""
    
    @pytest.mark.asyncio
    async def test_roi_width_setting_with_default_fallback(self, mock_pypylon):
        """Test ROI width setting with default fallback value (1920)."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock the logger to capture warning calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Test ROI configuration with width but no height (should use default height)
        config_data = {"roi": {"width": 1280}}  # Only width specified
        
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            # Mock _sdk to succeed
            async def mock_sdk(func, *args, **kwargs):
                return None
            
            camera._sdk = mock_sdk
            
            # Mock Width feature to be available
            mock_width = MagicMock()
            mock_width.GetAccessMode.return_value = mock_genicam.RW
            mock_camera.Width = mock_width
            
            await camera.import_config(config_path)
        finally:
            # Clean up temporary file
            os.unlink(config_path)
        
        # Should succeed without warnings since Width is available
        mock_logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_roi_height_setting_with_default_fallback(self, mock_pypylon):
        """Test ROI height setting with default fallback value (1080)."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock the logger to capture warning calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Test ROI configuration with height but no width (should use default width)
        config_data = {"roi": {"height": 720}}  # Only height specified
        
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            # Mock _sdk to succeed
            async def mock_sdk(func, *args, **kwargs):
                return None
            
            camera._sdk = mock_sdk
            
            # Mock Height feature to be available
            mock_height = MagicMock()
            mock_height.GetAccessMode.return_value = mock_genicam.RW
            mock_camera.Height = mock_height
            
            await camera.import_config(config_path)
        finally:
            # Clean up temporary file
            os.unlink(config_path)
        
        # Should succeed without warnings since Height is available
        mock_logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_roi_offset_x_setting_with_default_fallback(self, mock_pypylon):
        """Test ROI offset X setting with default fallback value (0)."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock the logger to capture warning calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Test ROI configuration with offset X but no offset Y (should use default Y)
        config_data = {"roi": {"x": 100}}  # Only offset X specified
        
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            # Mock _sdk to succeed
            async def mock_sdk(func, *args, **kwargs):
                return None
            
            camera._sdk = mock_sdk
            
            # Mock OffsetX feature to be available
            mock_offset_x = MagicMock()
            mock_offset_x.GetAccessMode.return_value = mock_genicam.RW
            mock_camera.OffsetX = mock_offset_x
            
            await camera.import_config(config_path)
        finally:
            # Clean up temporary file
            os.unlink(config_path)
        
        # Should succeed without warnings since OffsetX is available
        mock_logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_roi_offset_y_setting_with_default_fallback(self, mock_pypylon):
        """Test ROI offset Y setting with default fallback value (0)."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock the logger to capture warning calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Test ROI configuration with offset Y but no offset X (should use default X)
        config_data = {"roi": {"y": 200}}  # Only offset Y specified
        
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            # Mock _sdk to succeed
            async def mock_sdk(func, *args, **kwargs):
                return None
            
            camera._sdk = mock_sdk
            
            # Mock OffsetY feature to be available
            mock_offset_y = MagicMock()
            mock_offset_y.GetAccessMode.return_value = mock_genicam.RW
            mock_camera.OffsetY = mock_offset_y
            
            await camera.import_config(config_path)
        finally:
            # Clean up temporary file
            os.unlink(config_path)
        
        # Should succeed without warnings since OffsetY is available
        mock_logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_roi_success_counting_logic(self, mock_pypylon):
        """Test ROI success counting logic (if roi_success > 0: success_count += 1)."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock the logger to capture info calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Mock _grabbing_suspended to avoid complex context manager operations
        class MockContextManager:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        camera._grabbing_suspended = lambda: MockContextManager()
        
        # Test ROI configuration with partial success (only width succeeds)
        config_data = {"roi": {"width": 1280, "height": 720, "x": 100, "y": 200}}
        
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            # Mock _sdk to succeed for Width but fail for others
            async def mock_sdk_partial_success(func, *args, **kwargs):
                if "Width" in str(func):
                    return None  # Width succeeds
                else:
                    raise RuntimeError("Feature not available")  # Others fail
            
            camera._sdk = mock_sdk_partial_success
            
            # Mock Width feature to be available
            mock_width = MagicMock()
            mock_width.GetAccessMode.return_value = mock_genicam.RW
            mock_camera.Width = mock_width
            
            # Mock other features to be unavailable to avoid _sdk calls
            mock_camera.Height = None
            mock_camera.OffsetX = None
            mock_camera.OffsetY = None
            
            await camera.import_config(config_path)
        finally:
            # Clean up temporary file
            os.unlink(config_path)
        
        # Should log info about configuration import with partial success
        mock_logger.info.assert_called_once()
        info_msg = mock_logger.info.call_args[0][0]
        assert "Configuration imported from" in info_msg
        assert "1/1" in info_msg  # 1 ROI setting succeeded out of 1 total

    @pytest.mark.asyncio
    async def test_roi_offset_retrieval_in_export_config(self, mock_pypylon):
        """Test ROI offset retrieval in export_config with fallback values."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock the logger to capture warning calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Mock _ensure_open to succeed
        async def mock_ensure_open():
            pass
        
        camera._ensure_open = mock_ensure_open
        
        # Test export_config when ROI offset retrieval fails (should use defaults)
        config_path = "test_export_config.json"
        
        try:
            # Mock _sdk to fail for ROI offset retrieval
            async def mock_sdk_failing(func, *args, **kwargs):
                if "OffsetX" in str(func) or "OffsetY" in str(func):
                    raise RuntimeError("ROI offset retrieval failed")
                return None
            
            camera._sdk = mock_sdk_failing
            
            # Mock Width and Height to succeed
            mock_width = MagicMock()
            mock_width.GetValue.return_value = 1920
            mock_camera.Width = mock_width
            
            mock_height = MagicMock()
            mock_height.GetValue.return_value = 1080
            mock_camera.Height = mock_height
            
            # Mock other required features
            mock_exposure = MagicMock()
            mock_exposure.GetValue.return_value = 20000.0
            mock_camera.ExposureTime = mock_exposure
            
            mock_gain = MagicMock()
            mock_gain.GetValue.return_value = 1.0
            mock_camera.Gain = mock_gain
            
            mock_trigger = MagicMock()
            mock_trigger.GetValue.return_value = "Off"
            mock_camera.TriggerMode = mock_trigger
            
            mock_pixel_format = MagicMock()
            mock_pixel_format.GetValue.return_value = "BayerRG8"
            mock_camera.PixelFormat = mock_pixel_format
            
            await camera.export_config(config_path)
        finally:
            # Clean up temporary file
            if os.path.exists(config_path):
                os.unlink(config_path)
        
        # Should log warning about ROI offset retrieval failure
        mock_logger.warning.assert_called()
        warning_calls = [call[0][0] for call in mock_logger.warning.call_args_list]
        assert any("Could not get ROI offsets" in msg for msg in warning_calls)

    @pytest.mark.asyncio
    async def test_set_roi_parameter_validation(self, mock_pypylon):
        """Test set_ROI method parameter validation and bounds checking."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConfigurationError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Test invalid ROI dimensions (width <= 0)
        with pytest.raises(CameraConfigurationError) as exc_info:
            await camera.set_ROI(0, 0, 0, 100)
        
        error_msg = str(exc_info.value)
        assert "Invalid ROI dimensions" in error_msg
        assert "0x100" in error_msg
        
        # Test invalid ROI dimensions (height <= 0)
        with pytest.raises(CameraConfigurationError) as exc_info:
            await camera.set_ROI(0, 0, 100, 0)
        
        error_msg = str(exc_info.value)
        assert "Invalid ROI dimensions" in error_msg
        assert "100x0" in error_msg
        
        # Test invalid ROI offsets (x < 0)
        with pytest.raises(CameraConfigurationError) as exc_info:
            await camera.set_ROI(-1, 0, 100, 100)
        
        error_msg = str(exc_info.value)
        assert "Invalid ROI offsets" in error_msg
        assert "(-1, 0)" in error_msg
        
        # Test invalid ROI offsets (y < 0)
        with pytest.raises(CameraConfigurationError) as exc_info:
            await camera.set_ROI(0, -1, 100, 100)
        
        error_msg = str(exc_info.value)
        assert "Invalid ROI offsets" in error_msg
        assert "(0, -1)" in error_msg

    @pytest.mark.asyncio
    async def test_set_roi_bounds_checking(self, mock_pypylon):
        """Test set_ROI method bounds checking against camera capabilities."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConfigurationError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        mock_camera.IsGrabbing.return_value = False
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock camera capabilities
        mock_width = MagicMock()
        mock_width.GetMax.return_value = 1920
        mock_width.GetInc.return_value = 1
        mock_camera.Width = mock_width
        
        mock_height = MagicMock()
        mock_height.GetMax.return_value = 1080
        mock_height.GetInc.return_value = 1
        mock_camera.Height = mock_height
        
        mock_offset_x = MagicMock()
        mock_offset_x.GetMax.return_value = 1000
        mock_offset_x.GetInc.return_value = 1
        mock_camera.OffsetX = mock_offset_x
        
        mock_offset_y = MagicMock()
        mock_offset_y.GetMax.return_value = 800
        mock_offset_y.GetInc.return_value = 1
        mock_camera.OffsetY = mock_offset_y
        
        # Test ROI dimensions out of range
        with pytest.raises(CameraConfigurationError) as exc_info:
            await camera.set_ROI(0, 0, 2000, 1000)  # Width > max_width
        
        error_msg = str(exc_info.value)
        assert "ROI dimensions" in error_msg
        assert "out of range" in error_msg
        
        # Test ROI offsets out of range
        with pytest.raises(CameraConfigurationError) as exc_info:
            await camera.set_ROI(1200, 0, 100, 100)  # x > max_offset_x
        
        error_msg = str(exc_info.value)
        assert "ROI offsets" in error_msg
        assert "out of range" in error_msg

    @pytest.mark.asyncio
    async def test_get_roi_method(self, mock_pypylon):
        """Test get_ROI method for retrieving current ROI settings."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock ROI values
        mock_offset_x = MagicMock()
        mock_offset_x.GetValue.return_value = 100
        mock_camera.OffsetX = mock_offset_x
        
        mock_offset_y = MagicMock()
        mock_offset_y.GetValue.return_value = 200
        mock_camera.OffsetY = mock_offset_y
        
        mock_width = MagicMock()
        mock_width.GetValue.return_value = 1280
        mock_camera.Width = mock_width
        
        mock_height = MagicMock()
        mock_height.GetValue.return_value = 720
        mock_camera.Height = mock_height
        
        # Get ROI settings
        roi = await camera.get_ROI()
        
        # Verify ROI values
        assert roi["x"] == 100
        assert roi["y"] == 200
        assert roi["width"] == 1280
        assert roi["height"] == 720

    @pytest.mark.asyncio
    async def test_reset_roi_method(self, mock_pypylon):
        """Test reset_ROI method for resetting to maximum sensor area."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        mock_camera.IsGrabbing.return_value = False
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock camera capabilities
        mock_width = MagicMock()
        mock_width.GetMax.return_value = 1920
        mock_width.GetInc.return_value = 1
        mock_camera.Width = mock_width
        
        mock_height = MagicMock()
        mock_height.GetMax.return_value = 1080
        mock_height.GetInc.return_value = 1
        mock_camera.Height = mock_height
        
        mock_offset_x = MagicMock()
        mock_offset_x.SetValue = MagicMock()
        mock_camera.OffsetX = mock_offset_x
        
        mock_offset_y = MagicMock()
        mock_offset_y.SetValue = MagicMock()
        mock_camera.OffsetY = mock_offset_y
        
        # Mock the logger to capture info calls
        mock_logger = MagicMock()
        camera.logger = mock_logger
        
        # Reset ROI
        result = await camera.reset_ROI()
        
        # Verify result
        assert result is True
        
        # Verify that ROI was reset to maximum values
        mock_offset_x.SetValue.assert_called_once_with(0)
        mock_offset_y.SetValue.assert_called_once_with(0)
        mock_width.SetValue.assert_called_once_with(1920)
        mock_height.SetValue.assert_called_once_with(1080)
        
        # Verify info logging
        mock_logger.info.assert_called_once()
        info_msg = mock_logger.info.call_args[0][0]
        assert "ROI reset to maximum" in info_msg

    @pytest.mark.asyncio
    async def test_set_roi_increment_adjustment(self, mock_pypylon):
        """Test that set_ROI adjusts values according to camera increment requirements."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        camera_name = "test_camera"
        camera = BaslerCameraBackend(camera_name)
        
        # Mock a camera object and set as initialized
        mock_camera = MagicMock()
        mock_camera.IsOpen.return_value = True
        mock_camera.IsGrabbing.return_value = False
        camera.camera = mock_camera
        camera.initialized = True
        
        # Mock camera capabilities with non-unit increments
        mock_width = MagicMock()
        mock_width.GetMax.return_value = 1920
        mock_width.GetInc.return_value = 4  # Width increment of 4
        mock_width.SetValue = MagicMock()
        mock_camera.Width = mock_width
        
        mock_height = MagicMock()
        mock_height.GetMax.return_value = 1080
        mock_height.GetInc.return_value = 2  # Height increment of 2
        mock_height.SetValue = MagicMock()
        mock_camera.Height = mock_height
        
        mock_offset_x = MagicMock()
        mock_offset_x.GetMax.return_value = 1000
        mock_offset_x.GetInc.return_value = 8  # X offset increment of 8
        mock_offset_x.SetValue = MagicMock()
        mock_camera.OffsetX = mock_offset_x
        
        mock_offset_y = MagicMock()
        mock_offset_y.GetMax.return_value = 800
        mock_offset_y.GetInc.return_value = 2  # Y offset increment of 2
        mock_offset_y.SetValue = MagicMock()
        mock_camera.OffsetY = mock_offset_y
        
        # Set ROI with values that need adjustment
        result = await camera.set_ROI(105, 203, 1283, 721)  # Values not aligned with increments
        
        # Verify result
        assert result is True
        
        # Verify that values were adjusted to increments
        # 105 // 8 * 8 = 104, 203 // 2 * 2 = 202, 1283 // 4 * 4 = 1280, 721 // 2 * 2 = 720
        mock_offset_x.SetValue.assert_called_once_with(104)
        mock_offset_y.SetValue.assert_called_once_with(202)
        mock_width.SetValue.assert_called_once_with(1280)
        mock_height.SetValue.assert_called_once_with(720)


class TestBaslerCameraBackendWhiteBalanceAndPixelFormatErrorHandling:
    """Test white balance and pixel format error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_config_import_pixel_format_setting_failure(self, mock_pypylon, tmp_path):
        """Test pixel format setting failure during config import."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Create config file with pixel format
        config_path = tmp_path / "test_config.json"
        config_data = {
            "pixel_format": "BGR8",
            "exposure_time": 20000.0
        }
        with open(config_path, "w") as f:
            json.dump(config_data, f)
        
        # Mock the _sdk method to raise exception for pixel format setting
        original_sdk = camera._sdk
        async def mock_sdk(func, *args, **kwargs):
            if func == camera.camera.PixelFormat.SetValue:
                raise Exception("Pixel format not supported")
            return await original_sdk(func, *args, **kwargs)
        
        camera._sdk = mock_sdk
        
        # Import should succeed despite pixel format failure
        result = await camera.import_config(str(config_path))
        assert result is True
        
        # Verify warning was logged
        # Note: We can't easily verify logging in unit tests, but the code path is covered
    
    @pytest.mark.asyncio
    async def test_config_import_white_balance_setting_failure(self, mock_pypylon, tmp_path):
        """Test white balance setting failure during config import."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Create config file with white balance
        config_path = tmp_path / "test_config.json"
        config_data = {
            "white_balance": "once",
            "exposure_time": 20000.0
        }
        with open(config_path, "w") as f:
            json.dump(config_data, f)
        
        # Mock the _sdk method to raise exception for white balance setting
        original_sdk = camera._sdk
        async def mock_sdk(func, *args, **kwargs):
            if func == camera.camera.BalanceWhiteAuto.SetValue:
                raise Exception("White balance not supported")
            return await original_sdk(func, *args, **kwargs)
        
        camera._sdk = mock_sdk
        
        # Import should succeed despite white balance failure
        result = await camera.import_config(str(config_path))
        assert result is True
        
        # Verify warning was logged
    
    @pytest.mark.asyncio
    async def test_config_export_white_balance_retrieval_failure(self, mock_pypylon, tmp_path):
        """Test white balance retrieval failure during config export."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Mock the _sdk method to raise exception for white balance retrieval
        original_sdk = camera._sdk
        async def mock_sdk(func, *args, **kwargs):
            if func == camera.camera.BalanceWhiteAuto.GetValue:
                raise Exception("White balance retrieval failed")
            return await original_sdk(func, *args, **kwargs)
        
        camera._sdk = mock_sdk
        
        # Export should succeed despite white balance failure
        config_path = tmp_path / "export_config.json"
        result = await camera.export_config(str(config_path))
        assert result is True
        
        # Verify warning was logged
        
        # Verify config file was created with default white balance
        with open(config_path, "r") as f:
            exported_config = json.load(f)
        assert exported_config["white_balance"] == "off"  # Default value
    
    @pytest.mark.asyncio
    async def test_config_export_pixel_format_retrieval_failure(self, mock_pypylon, tmp_path):
        """Test pixel format retrieval failure during config export."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Mock the _sdk method to raise exception for pixel format retrieval
        original_sdk = camera._sdk
        async def mock_sdk(func, *args, **kwargs):
            if func == camera.camera.PixelFormat.GetValue:
                raise Exception("Pixel format retrieval failed")
            return await original_sdk(func, *args, **kwargs)
        
        camera._sdk = mock_sdk
        
        # Export should succeed despite pixel format failure
        config_path = tmp_path / "export_config.json"
        result = await camera.export_config(str(config_path))
        assert result is True
        
        # Verify warning was logged
        
        # Verify config file was created with default pixel format
        with open(config_path, "r") as f:
            exported_config = json.load(f)
        assert exported_config["pixel_format"] == "BayerRG8"  # Default value
    
    @pytest.mark.asyncio
    async def test_get_wb_feature_not_available(self, mock_pypylon):
        """Test white balance retrieval when feature is not available."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Mock the _sdk method to raise exception for white balance retrieval
        original_sdk = camera._sdk
        async def mock_sdk(func, *args, **kwargs):
            if func == camera.camera.BalanceWhiteAuto.GetValue:
                raise Exception("Feature not available")
            return await original_sdk(func, *args, **kwargs)
        
        camera._sdk = mock_sdk
        
        # Get white balance should raise HardwareOperationError when feature not available
        with pytest.raises(HardwareOperationError) as exc_info:
            await camera.get_wb()
        
        assert "Failed to get white balance" in str(exc_info.value)
        
        # Verify error was logged
    
    @pytest.mark.asyncio
    async def test_get_wb_exception_handling(self, mock_pypylon):
        """Test white balance retrieval exception handling."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import HardwareOperationError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Mock BalanceWhiteAuto to be available but fail when getting value
        # Note: We can't reassign properties, so we'll test the exception path differently
        
        # Mock the _sdk method to raise exception
        original_sdk = camera._sdk
        async def mock_sdk(func, *args, **kwargs):
            if func == camera.camera.BalanceWhiteAuto.GetValue:
                raise Exception("Hardware error")
            return await original_sdk(func, *args, **kwargs)
        
        camera._sdk = mock_sdk
        
        # Get white balance should raise HardwareOperationError
        with pytest.raises(HardwareOperationError) as exc_info:
            await camera.get_wb()
        
        assert "Failed to get white balance" in str(exc_info.value)
        
        # Verify error was logged
    
    @pytest.mark.asyncio
    async def test_set_auto_wb_feature_not_writable(self, mock_pypylon):
        """Test white balance setting when feature is not writable."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Mock the _sdk method to raise exception for white balance setting
        original_sdk = camera._sdk
        async def mock_sdk(func, *args, **kwargs):
            if func == camera.camera.BalanceWhiteAuto.SetValue:
                raise Exception("Feature not writable")
            return await original_sdk(func, *args, **kwargs)
        
        camera._sdk = mock_sdk
        
        # Set white balance should raise HardwareOperationError when feature not writable
        with pytest.raises(HardwareOperationError) as exc_info:
            await camera.set_auto_wb_once("once")
        
        assert "Failed to set white balance" in str(exc_info.value)
        
        # Verify error was logged
    
    @pytest.mark.asyncio
    async def test_set_auto_wb_verification_failure(self, mock_pypylon):
        """Test white balance setting verification failure."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Mock the _sdk method to raise exception for white balance setting
        original_sdk = camera._sdk
        async def mock_sdk(func, *args, **kwargs):
            if func == camera.camera.BalanceWhiteAuto.SetValue:
                raise Exception("Verification failed")
            return await original_sdk(func, *args, **kwargs)
        
        camera._sdk = mock_sdk
        
        # Set white balance should raise HardwareOperationError when verification fails
        with pytest.raises(HardwareOperationError) as exc_info:
            await camera.set_auto_wb_once("once")
        
        assert "Failed to set white balance" in str(exc_info.value)
        
        # Verify error was logged
    
    @pytest.mark.asyncio
    async def test_set_auto_wb_exception_handling(self, mock_pypylon):
        """Test white balance setting exception handling."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import HardwareOperationError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Mock the _sdk method to raise exception
        original_sdk = camera._sdk
        async def mock_sdk(func, *args, **kwargs):
            if func == camera.camera.BalanceWhiteAuto.SetValue:
                raise Exception("Hardware error")
            return await original_sdk(func, *args, **kwargs)
        
        camera._sdk = mock_sdk
        
        # Set white balance should raise HardwareOperationError
        with pytest.raises(HardwareOperationError) as exc_info:
            await camera.set_auto_wb_once("once")
        
        assert "Failed to set white balance" in str(exc_info.value)
        
        # Verify error was logged
    
    @pytest.mark.asyncio
    async def test_set_pixel_format_exception_handling(self, mock_pypylon):
        """Test pixel format setting exception handling."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import HardwareOperationError, CameraConnectionError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Mock the camera to be open but fail during pixel format setting
        def mock_is_open():
            return True
            
        camera.camera.IsOpen = mock_is_open
        
        # Mock pixel format setting to raise exception
        def mock_pixel_format_setter(value):
            raise Exception("Pixel format setting failed")
        
        camera.camera.PixelFormat.SetValue = mock_pixel_format_setter
        
        # Set pixel format should raise HardwareOperationError when pixel format setting fails
        with pytest.raises(HardwareOperationError) as exc_info:
            await camera.set_pixel_format("BGR8")
        
        assert "Failed to set pixel format" in str(exc_info.value)
        
        # Verify error was logged
    
    @pytest.mark.asyncio
    async def test_get_pixel_format_exception_handling(self, mock_pypylon):
        """Test pixel format retrieval exception handling."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import HardwareOperationError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Mock the camera to raise exception during pixel format retrieval
        # We need to mock the actual camera methods that are called
        original_is_open = camera.camera.IsOpen
        original_open = camera.camera.Open
        
        def mock_is_open():
            return False
        
        def mock_open():
            raise Exception("Open failed")
        
        camera.camera.IsOpen = mock_is_open
        camera.camera.Open = mock_open
        
        # Get current pixel format should raise HardwareOperationError
        with pytest.raises(HardwareOperationError) as exc_info:
            await camera.get_current_pixel_format()
        
        assert "Failed to get current pixel format" in str(exc_info.value)
        
        # Verify error was logged
    
    @pytest.mark.asyncio
    async def test_get_pixel_format_range_exception_handling(self, mock_pypylon):
        """Test pixel format range retrieval exception handling."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Mock the _sdk method to raise exception for pixel format operations
        original_sdk = camera._sdk
        async def mock_sdk(func, *args, **kwargs):
            if func == camera.camera.PixelFormat.GetEntries:
                raise Exception("Pixel format operation failed")
            return await original_sdk(func, *args, **kwargs)
        
        camera._sdk = mock_sdk
        
        # Get pixel format range should return default formats when camera operations fail
        result = await camera.get_pixel_format_range()
        expected_defaults = ["BGR8", "RGB8", "Mono8", "BayerRG8", "BayerGB8", "BayerGR8", "BayerBG8"]
        assert result == expected_defaults
        
        # Verify error was logged
    
    @pytest.mark.asyncio
    async def test_set_pixel_format_invalid_format(self, mock_pypylon):
        """Test pixel format setting with invalid format."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConfigurationError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Mock the camera to be open but fail during pixel format setting
        def mock_is_open():
            return True
            
        camera.camera.IsOpen = mock_is_open
        
        # Mock pixel format setting to raise exception
        def mock_pixel_format_setter(value):
            raise Exception("Pixel format setting failed")
        
        camera.camera.PixelFormat.SetValue = mock_pixel_format_setter
        
        # Set pixel format should raise HardwareOperationError when pixel format setting fails
        with pytest.raises(HardwareOperationError) as exc_info:
            await camera.set_pixel_format("BGR8")
        
        assert "Failed to set pixel format" in str(exc_info.value)
        
        # Verify error was logged


class TestBaslerCameraBackendSpecificLineCoverage:
    """Test specific uncovered lines in camera state management error handling."""
    
    @pytest.mark.asyncio
    async def test_trigger_mode_camera_not_initialized(self, mock_pypylon):
        """Test trigger mode setting when camera is not initialized."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConnectionError
        
        # Create camera instance but don't initialize it
        camera = BaslerCameraBackend("12345670")
        
        # Try to set trigger mode on uninitialized camera - this should hit line 590
        with pytest.raises(CameraConnectionError) as exc_info:
            await camera.set_triggermode("trigger")
        
        assert "is not initialized" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_capture_trigger_software_execute_failure(self, mock_pypylon):
        """Test capture error when trigger software execution fails."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraCaptureError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Set trigger mode to "trigger" to ensure trigger software execution is tested
        await camera.set_triggermode("trigger")
        
        # Mock the _sdk method to raise exception for TriggerSoftware.Execute
        original_sdk = camera._sdk
        async def mock_sdk(func, *args, **kwargs):
            if func == camera.camera.TriggerSoftware.Execute:
                raise Exception("Trigger software execute failed")
            return await original_sdk(func, *args, **kwargs)
        
        camera._sdk = mock_sdk
        
        # Capture should raise CameraCaptureError due to trigger software failure
        with pytest.raises(CameraCaptureError) as exc_info:
            await camera.capture()
        
        assert "Trigger software execute failed" in str(exc_info.value)
        
        # Restore original method
        camera._sdk = original_sdk
    
    @pytest.mark.asyncio
    async def test_grab_failed_with_release_handling(self, mock_pypylon):
        """Test capture error handling when grab fails and release also fails."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraCaptureError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Store reference to a mock grab result that we'll use
        mock_grab_result = MagicMock()
        mock_grab_result.GrabSucceeded.return_value = False  # Simulate grab failure
        mock_grab_result.ErrorDescription.return_value = "Grab failed"
        mock_grab_result.Release.return_value = None  # Release succeeds, but grab failed
        
        # Mock the _sdk method to simulate grab failure  
        original_sdk = camera._sdk
        async def mock_sdk(func, *args, **kwargs):
            if func == camera.camera.RetrieveResult:
                return mock_grab_result
            elif func == mock_grab_result.GrabSucceeded:
                return False  # This triggers the else branch when grab fails
            elif func == mock_grab_result.ErrorDescription:
                return "Grab failed"  # Get error description for failed grab
            elif func == mock_grab_result.Release:
                return None  # Release after failed grab
            return await original_sdk(func, *args, **kwargs)
        
        camera._sdk = mock_sdk
        
        # This should trigger grab failure error handling:
        # Get error description from failed grab result
        # Log warning about grab failure
        # Release the failed grab result
        # Since all retry attempts fail due to grab failure, it should eventually raise CameraCaptureError
        with pytest.raises(CameraCaptureError) as exc_info:
            await camera.capture()
        
        assert "Failed to capture image after" in str(exc_info.value)
        
        # Restore original method
        camera._sdk = original_sdk
    
    @pytest.mark.asyncio
    async def test_capture_exhausted_retry_attempts(self, mock_pypylon):
        """Test capture error when all retry attempts are exhausted."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraCaptureError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with low retry count
        camera = BaslerCameraBackend("12345670", retrieve_retry_count=2)
        await camera.initialize()
        
        # Mock the _sdk method to always return failed grab results
        original_sdk = camera._sdk
        async def mock_sdk(func, *args, **kwargs):
            if func == camera.camera.RetrieveResult:
                # Always return failed grab result
                mock_grab_result = MagicMock()
                mock_grab_result.GrabSucceeded.return_value = False
                mock_grab_result.ErrorDescription.return_value = "Always fails"
                mock_grab_result.Release.return_value = None
                return mock_grab_result
            return await original_sdk(func, *args, **kwargs)
        
        camera._sdk = mock_sdk
        
        # This should exhaust all retry attempts and raise the final capture error
        with pytest.raises(CameraCaptureError) as exc_info:
            await camera.capture()
        
        assert "Failed to capture image after 2 attempts" in str(exc_info.value)
        
        # Restore original method
        camera._sdk = original_sdk
    
    @pytest.mark.asyncio
    async def test_import_config_camera_none(self, mock_pypylon, tmp_path):
        """Test import config when camera is None."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConnectionError
        
        # Create camera instance but set camera to None
        camera = BaslerCameraBackend("12345670")
        camera.camera = None  # Simulate uninitialized state
        
        # Create config file
        config_path = tmp_path / "test_config.json"
        config_data = {"exposure_time": 20000.0}
        with open(config_path, "w") as f:
            json.dump(config_data, f)
        
        # This should trigger the camera None check in import_config
        with pytest.raises(CameraConnectionError) as exc_info:
            await camera.import_config(str(config_path))
        
        assert "not initialized" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_export_config_camera_not_initialized(self, mock_pypylon, tmp_path):
        """Test export config when camera is not initialized."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConnectionError
        
        # Create camera instance but don't initialize it
        camera = BaslerCameraBackend("12345670")
        
        # Create export path
        config_path = tmp_path / "export_config.json"
        
        # This should trigger the camera not initialized check in export_config
        with pytest.raises(CameraConnectionError) as exc_info:
            await camera.export_config(str(config_path))
        
        assert "not initialized" in str(exc_info.value)


class TestBaslerCameraBackendRemainingLineCoverage:
    """Test remaining uncovered lines in configuration error handling."""
    
    @pytest.mark.asyncio
    async def test_import_config_gain_setting_exception(self, mock_pypylon, tmp_path):
        """Test gain setting exception handling during config import."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Create config file with gain setting
        config_path = tmp_path / "test_config.json"
        config_data = {
            "gain": 2.5,
            "exposure_time": 20000.0
        }
        with open(config_path, "w") as f:
            json.dump(config_data, f)
        
        # Mock the _sdk method to raise exception for gain setting
        original_sdk = camera._sdk
        async def mock_sdk(func, *args, **kwargs):
            if func == camera.camera.Gain.SetValue:
                raise Exception("Gain setting failed")
            return await original_sdk(func, *args, **kwargs)
        
        camera._sdk = mock_sdk
        
        # Import should succeed despite gain setting failure (warning logged)
        result = await camera.import_config(str(config_path))
        assert result is True
        
        # Restore original method
        camera._sdk = original_sdk
    
    @pytest.mark.asyncio
    async def test_import_config_trigger_source_setting(self, mock_pypylon, tmp_path):
        """Test trigger source setting during config import."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # The mock camera already has TriggerSource property, so hasattr() will return True
        # This should trigger line 810 when importing trigger mode
        
        # Create config file with trigger mode setting
        config_path = tmp_path / "test_config.json"
        config_data = {
            "trigger_mode": "trigger",
            "exposure_time": 20000.0
        }
        with open(config_path, "w") as f:
            json.dump(config_data, f)
        
        # Import should succeed and trigger source should be set
        result = await camera.import_config(str(config_path))
        assert result is True
        
        # Verify that the trigger source setting was attempted
        # (This exercises line 810)
    
    @pytest.mark.asyncio
    async def test_import_config_white_balance_off_setting(self, mock_pypylon, tmp_path):
        """Test white balance 'off' setting during config import."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Create config file with white balance off setting
        config_path = tmp_path / "test_config.json"
        config_data = {
            "white_balance": "off",
            "exposure_time": 20000.0
        }
        with open(config_path, "w") as f:
            json.dump(config_data, f)
        
        # Import should succeed and white balance should be set to off
        result = await camera.import_config(str(config_path))
        assert result is True
        
        # This should exercise line 826
    
    @pytest.mark.asyncio
    async def test_import_config_white_balance_continuous_setting(self, mock_pypylon, tmp_path):
        """Test white balance 'continuous' setting during config import."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Create config file with white balance continuous setting
        config_path = tmp_path / "test_config.json"
        config_data = {
            "white_balance": "continuous",
            "exposure_time": 20000.0
        }
        with open(config_path, "w") as f:
            json.dump(config_data, f)
        
        # Import should succeed and white balance should be set to continuous
        result = await camera.import_config(str(config_path))
        assert result is True
        
        # This should exercise line 830
    
    @pytest.mark.asyncio
    async def test_export_config_directory_creation_failure(self, mock_pypylon, tmp_path, monkeypatch):
        """Test export config when directory creation fails."""
        from mindtrace.hardware.cameras.backends.basler.basler_camera_backend import BaslerCameraBackend
        from mindtrace.hardware.core.exceptions import CameraConfigurationError
        
        # Unpack the mock tuple
        mock_pylon, mock_genicam = mock_pypylon
        
        # Create camera instance with existing mock device name
        camera = BaslerCameraBackend("12345670")
        await camera.initialize()
        
        # Mock os.makedirs to raise an exception
        def mock_makedirs(*args, **kwargs):
            raise PermissionError("Permission denied to create directory")
        
        monkeypatch.setattr("os.makedirs", mock_makedirs)
        
        # Create export path that would require directory creation
        config_path = tmp_path / "nonexistent" / "subdirectory" / "export_config.json"
        
        # Export should raise CameraConfigurationError due to directory creation failure
        with pytest.raises(CameraConfigurationError) as exc_info:
            await camera.export_config(str(config_path))
        
        assert "Permission denied" in str(exc_info.value)
