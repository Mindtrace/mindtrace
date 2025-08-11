import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, Mock, patch

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
        
        result = basler_camera.set_gain(5.0)
        assert result is True
        assert basler_camera.camera.gain == 5.0
    
    @pytest.mark.asyncio
    async def test_set_gain_out_of_range(self, basler_camera):
        """Test setting gain out of range."""
        await basler_camera.initialize()
        
        with pytest.raises(CameraConfigurationError, match="Gain.*outside valid range"):
            basler_camera.set_gain(1000)  # Way too high
    
    def test_get_gain(self, basler_camera):
        """Test getting gain."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        basler_camera.camera.gain = 3.5
        
        gain = basler_camera.get_gain()
        assert gain == 3.5
    
    def test_get_gain_range(self, basler_camera):
        """Test getting gain range."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        
        gain_range = basler_camera.get_gain_range()
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
    
    def test_set_roi_success(self, basler_camera):
        """Test setting ROI."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        
        result = basler_camera.set_ROI(100, 100, 800, 600)
        assert result is True
        assert basler_camera.camera.width == 800
        assert basler_camera.camera.height == 600
    
    def test_set_roi_invalid_dimensions(self, basler_camera):
        """Test setting ROI with invalid dimensions."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        
        with pytest.raises(CameraConfigurationError, match="ROI dimensions.*out of range"):
            basler_camera.set_ROI(0, 0, 3000, 2000)  # Too large
    
    def test_get_roi(self, basler_camera):
        """Test getting ROI."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        # Set the individual parameter values that get_ROI() actually reads
        basler_camera.camera.offset_x = 50
        basler_camera.camera.offset_y = 50
        basler_camera.camera.width = 640
        basler_camera.camera.height = 480
        
        roi = basler_camera.get_ROI()
        assert roi == {"x": 50, "y": 50, "width": 640, "height": 480}
    
    def test_reset_roi(self, basler_camera):
        """Test resetting ROI."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        
        result = basler_camera.reset_ROI()
        assert result is True
        assert basler_camera.camera.width == 1920
        assert basler_camera.camera.height == 1080


class TestBaslerCameraBackendPixelFormat:
    """Test pixel format functionality."""
    
    def test_set_pixel_format_success(self, basler_camera):
        """Test setting pixel format."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        
        result = basler_camera.set_pixel_format("RGB8")
        assert result is True
        assert basler_camera.camera.pixel_format == "RGB8"
    
    def test_set_pixel_format_invalid(self, basler_camera):
        """Test setting invalid pixel format."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        
        with pytest.raises(CameraConfigurationError, match="Pixel format.*not supported"):
            basler_camera.set_pixel_format("INVALID_FORMAT")
    
    def test_get_pixel_format(self, basler_camera):
        """Test getting pixel format."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        basler_camera.camera.pixel_format = "Mono8"
        
        format = basler_camera.get_current_pixel_format()
        assert format == "Mono8"
    
    def test_get_pixel_format_range(self, basler_camera):
        """Test getting available pixel formats."""
        basler_camera.initialized = True
        basler_camera.camera = MockPylonCamera()
        
        formats = basler_camera.get_pixel_format_range()
        assert isinstance(formats, list)
        assert "BGR8" in formats
        assert "RGB8" in formats
        assert "Mono8" in formats


class TestBaslerCameraBackendImageEnhancement:
    """Test image enhancement functionality."""
    
    def test_set_image_quality_enhancement(self, basler_camera):
        """Test enabling/disabling image enhancement."""
        basler_camera.initialized = True
        
        result = basler_camera.set_image_quality_enhancement(True)
        assert result is True
        assert basler_camera.get_image_quality_enhancement() is True
        
        result = basler_camera.set_image_quality_enhancement(False)
        assert result is True
        assert basler_camera.get_image_quality_enhancement() is False
    
    def test_get_image_quality_enhancement(self, basler_camera):
        """Test getting image enhancement status."""
        basler_camera.set_image_quality_enhancement(True)
        
        result = basler_camera.get_image_quality_enhancement()
        assert result is True


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 
