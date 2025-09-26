"""Comprehensive pypylon mock for Basler camera testing."""

import time
import types

import numpy as np


def create_fake_pypylon():
    """Create a complete fake pypylon module for testing."""

    # Create the module
    pypylon = types.ModuleType("pypylon")

    # Sub-modules
    pylon = types.ModuleType("pylon")
    genicam = types.ModuleType("genicam")

    # Exception classes
    class GenericException(Exception):
        """Base pypylon exception."""

        pass

    class TimeoutException(GenericException):
        """Timeout during camera operations."""

        pass

    class RuntimeException(GenericException):
        """Runtime error in camera operations."""

        pass

    class AccessException(GenericException):
        """Access denied to camera resource."""

        pass

    # Parameter classes
    class Parameter:
        """Mock camera parameter."""

        def __init__(self, value, min_val=None, max_val=None, access_mode="RW"):
            self._value = value
            self._min = min_val
            self._max = max_val
            self._access_mode = access_mode

        def GetValue(self):
            return self._value

        def SetValue(self, value):
            if self._access_mode not in ["RW", "WO"]:
                raise AccessException("Parameter is read-only")
            if self._min is not None and value < self._min:
                raise RuntimeException(f"Value {value} below minimum {self._min}")
            if self._max is not None and value > self._max:
                raise RuntimeException(f"Value {value} above maximum {self._max}")
            self._value = value

        def GetMin(self):
            return self._min or 0

        def GetMax(self):
            return self._max or 100

        def GetAccessMode(self):
            return self._access_mode

        def IsWritable(self):
            return self._access_mode in ["RW", "WO"]

        def IsReadable(self):
            return self._access_mode in ["RW", "RO"]

    class EnumParameter(Parameter):
        """Mock enumeration parameter."""

        def __init__(self, value, entries, access_mode="RW"):
            super().__init__(value, access_mode=access_mode)
            self._entries = entries

        def GetSymbolics(self):
            return self._entries

        def SetValue(self, value):
            if value not in self._entries:
                raise RuntimeException(f"Invalid enum value: {value}")
            super().SetValue(value)

        def GetIntValue(self):
            return self._entries.index(self._value) if self._value in self._entries else 0

        def SetIntValue(self, index):
            if 0 <= index < len(self._entries):
                self._value = self._entries[index]
            else:
                raise RuntimeException(f"Invalid enum index: {index}")

    # Device info class
    class DeviceInfo:
        """Mock device information."""

        def __init__(
            self, serial="12345678", model="acA1920-40uc", friendly_name=None, vendor="Basler", device_class="BaslerUsb"
        ):
            self.serial = serial
            self.model = model
            self.vendor = vendor
            self.device_class = device_class
            self.user_defined_name = f"Camera_{serial}"
            self.friendly_name = friendly_name or f"{vendor} {model} ({serial})"

        def GetSerialNumber(self):
            return self.serial

        def GetModelName(self):
            return self.model

        def GetVendorName(self):
            return self.vendor

        def GetDeviceClass(self):
            return self.device_class

        def GetUserDefinedName(self):
            return self.user_defined_name

        def GetFriendlyName(self):
            return self.friendly_name

    # Grab result class
    class GrabResult:
        """Mock image grab result."""

        def __init__(self, success=True, image_array=None, error_code=None, error_desc=None):
            self._success = success
            self._image_array = (
                image_array if image_array is not None else np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
            )
            self._error_code = error_code
            self._error_desc = error_desc
            self._timestamp = time.time()

        def GrabSucceeded(self):
            return self._success

        def GetArray(self):
            if not self._success:
                raise RuntimeException(f"Grab failed: {self._error_desc}")
            return self._image_array

        def GetErrorCode(self):
            return self._error_code or 0

        def GetErrorDescription(self):
            return self._error_desc or ""

        def GetTimeStamp(self):
            return self._timestamp

        def Release(self):
            pass

    # Camera class
    class InstantCamera:
        """Mock Basler camera."""

        def __init__(self, device=None):
            self.device_info = device or DeviceInfo()
            self._is_open = False
            self._is_grabbing = False
            self._parameters = self._create_parameters()
            self._simulate_error = None
            self._grab_timeout = 5000
            self._exposure_auto = "Off"
            self._gain_auto = "Off"

        def _create_parameters(self):
            """Create camera parameters."""
            return {
                "ExposureTime": Parameter(10000.0, 100.0, 1000000.0),
                "ExposureTimeAbs": Parameter(10000.0, 100.0, 1000000.0),
                "ExposureAuto": EnumParameter("Off", ["Off", "Once", "Continuous"]),
                "Gain": Parameter(1.0, 0.0, 20.0),
                "GainRaw": Parameter(100, 0, 1000),
                "GainAuto": EnumParameter("Off", ["Off", "Once", "Continuous"]),
                "Width": Parameter(1920, 32, 1920),
                "Height": Parameter(1080, 32, 1080),
                "OffsetX": Parameter(0, 0, 1920),
                "OffsetY": Parameter(0, 0, 1080),
                "PixelFormat": EnumParameter("BGR8", ["Mono8", "BGR8", "RGB8", "BayerRG8"]),
                "TriggerMode": EnumParameter("Off", ["Off", "On"]),
                "TriggerSource": EnumParameter("Software", ["Software", "Line1", "Line2", "Line3"]),
                "TriggerSelector": EnumParameter("FrameStart", ["FrameStart", "LineStart", "FrameActive"]),
                "TriggerSoftware": Parameter(None),
                "AcquisitionMode": EnumParameter("Continuous", ["SingleFrame", "Continuous", "MultiFrame"]),
                "AcquisitionFrameRateEnable": Parameter(True),
                "AcquisitionFrameRate": Parameter(30.0, 1.0, 100.0),
                "AcquisitionFrameRateAbs": Parameter(30.0, 1.0, 100.0),
                "MaxNumBuffer": Parameter(10, 1, 100),
                "OutputQueueSize": Parameter(10, 1, 100),
                "BalanceWhiteAuto": EnumParameter("Off", ["Off", "Once", "Continuous"]),
                "BalanceRatioSelector": EnumParameter("Red", ["Red", "Green", "Blue"]),
                "BalanceRatio": Parameter(1.0, 0.0, 10.0),
                "BlackLevel": Parameter(0.0, 0.0, 100.0),
                "Gamma": Parameter(1.0, 0.0, 2.0),
                "LightSourcePreset": EnumParameter("Off", ["Off", "Daylight5000K", "Tungsten2800K"]),
            }

        def Attach(self, device):
            """Attach to a device."""
            self.device_info = device

        def Open(self):
            """Open the camera."""
            if self._simulate_error == "open_error":
                raise RuntimeException("Failed to open camera")
            self._is_open = True

        def Close(self):
            """Close the camera."""
            self.StopGrabbing()
            self._is_open = False

        def IsOpen(self):
            """Check if camera is open."""
            return self._is_open

        def StartGrabbing(self, grab_strategy=None):
            """Start image acquisition."""
            if not self._is_open:
                raise RuntimeException("Camera not open")
            if self._simulate_error == "grab_error":
                raise RuntimeException("Failed to start grabbing")
            self._is_grabbing = True

        def StopGrabbing(self):
            """Stop image acquisition."""
            self._is_grabbing = False

        def IsGrabbing(self):
            """Check if camera is grabbing."""
            return self._is_grabbing

        def RetrieveResult(self, timeout_ms, timeout_handling=None):
            """Retrieve an image."""
            if not self._is_open:
                raise RuntimeException("Camera not open")
            if not self._is_grabbing:
                raise RuntimeException("Camera not grabbing")

            if self._simulate_error == "timeout":
                raise TimeoutException("Image retrieval timeout")
            elif self._simulate_error == "grab_failed":
                return GrabResult(success=False, error_code=1, error_desc="Grab failed")

            # Simulate successful grab
            width = self._parameters["Width"].GetValue()
            height = self._parameters["Height"].GetValue()
            pixel_format = self._parameters["PixelFormat"].GetValue()

            if pixel_format == "Mono8":
                shape = (height, width)
            else:
                shape = (height, width, 3)

            image = np.random.randint(0, 255, shape, dtype=np.uint8)
            return GrabResult(success=True, image_array=image)

        def ExecuteSoftwareTrigger(self):
            """Execute software trigger."""
            if self._parameters["TriggerMode"].GetValue() != "On":
                raise RuntimeException("Trigger mode not enabled")
            if self._parameters["TriggerSource"].GetValue() != "Software":
                raise RuntimeException("Trigger source not set to Software")

        def GetDeviceInfo(self):
            """Get device information."""
            return self.device_info

        def __getattr__(self, name):
            """Access camera parameters dynamically."""
            if name in self._parameters:
                return self._parameters[name]
            raise AttributeError(f"Camera has no parameter '{name}'")

        def simulate_error(self, error_type):
            """Simulate specific error conditions for testing."""
            self._simulate_error = error_type

        def clear_error(self):
            """Clear simulated error."""
            self._simulate_error = None

    # Transport layer factory
    class TlFactory:
        """Mock transport layer factory."""

        def __init__(self):
            self._devices = [
                DeviceInfo("12345678", "acA1920-40uc"),
                DeviceInfo("87654321", "acA2040-90um"),
                DeviceInfo("11111111", "acA1300-60gc"),
            ]

        @classmethod
        def GetInstance(cls):
            return cls()

        def EnumerateDevices(self):
            return self._devices

        def CreateDevice(self, device_info):
            return InstantCamera(device_info)

    # Configuration event handler
    class ConfigurationEventHandler:
        """Base configuration event handler."""

        def OnOpened(self, camera):
            pass

        def OnClosed(self, camera):
            pass

        def OnGrabStarted(self, camera):
            pass

        def OnGrabStopped(self, camera):
            pass

    class AcquireContinuousConfiguration(ConfigurationEventHandler):
        """Continuous acquisition configuration."""

        def OnOpened(self, camera):
            camera.MaxNumBuffer.SetValue(5)

    class AcquireSingleFrameConfiguration(ConfigurationEventHandler):
        """Single frame acquisition configuration."""

        def OnOpened(self, camera):
            camera.MaxNumBuffer.SetValue(1)

    # Image format converter and result
    class PylonImage:
        """Mock pypylon image result."""

        def __init__(self, image_array):
            self._array = image_array

        def GetArray(self):
            """Return the numpy array."""
            return self._array

    class ImageFormatConverter:
        """Mock image format converter."""

        def __init__(self):
            self.OutputPixelFormat = None
            self.OutputBitAlignment = None

        def Convert(self, grab_result):
            """Convert grab result to image."""
            # Return a PylonImage object that has GetArray() method
            # Generate a simple test image
            image_array = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)
            return PylonImage(image_array)

    # Grab strategies
    class GrabStrategy:
        """Base grab strategy."""

        pass

    class OneByOneStrategy(GrabStrategy):
        """One by one grab strategy."""

        pass

    class LatestImageOnlyStrategy(GrabStrategy):
        """Latest image only strategy."""

        pass

    # Timeout handling
    class TimeoutHandling:
        """Timeout handling options."""

        ThrowException = "ThrowException"
        Return = "Return"

    # Pixel type enum
    class PixelType:
        """Pixel format types."""

        Mono8 = "Mono8"
        BGR8 = "BGR8"
        RGB8 = "RGB8"
        BayerRG8 = "BayerRG8"

    # EGrabStrategy enum
    class EGrabStrategy:
        """Grab strategy enumeration."""

        OneByOne = OneByOneStrategy()
        LatestImageOnly = LatestImageOnlyStrategy()

    # Assign classes to modules
    pylon.TlFactory = TlFactory
    pylon.InstantCamera = InstantCamera
    pylon.DeviceInfo = DeviceInfo
    pylon.ImageFormatConverter = ImageFormatConverter
    pylon.ConfigurationEventHandler = ConfigurationEventHandler
    pylon.AcquireContinuousConfiguration = AcquireContinuousConfiguration
    pylon.AcquireSingleFrameConfiguration = AcquireSingleFrameConfiguration
    pylon.GrabStrategy = GrabStrategy
    pylon.OneByOneStrategy = OneByOneStrategy
    pylon.LatestImageOnlyStrategy = LatestImageOnlyStrategy
    pylon.TimeoutHandling = TimeoutHandling
    pylon.PixelType = PixelType
    pylon.EGrabStrategy = EGrabStrategy

    # Add missing attributes for compatibility
    pylon.GrabStrategy_LatestImageOnly = LatestImageOnlyStrategy()
    pylon.GrabStrategy_OneByOne = OneByOneStrategy()
    pylon.TimeoutHandling_ThrowException = "ThrowException"
    pylon.TimeoutHandling_Return = "Return"

    # Pixel type constants
    pylon.PixelType_BGR8packed = "BGR8packed"
    pylon.PixelType_RGB8packed = "RGB8packed"
    pylon.PixelType_Mono8 = "Mono8"

    # Output bit alignment constants
    pylon.OutputBitAlignment_MsbAligned = "MsbAligned"
    pylon.OutputBitAlignment_LsbAligned = "LsbAligned"

    genicam.GenericException = GenericException
    genicam.TimeoutException = TimeoutException
    genicam.RuntimeException = RuntimeException
    genicam.AccessException = AccessException

    # Assign sub-modules
    pypylon.pylon = pylon
    pypylon.genicam = genicam

    return pypylon
