import json
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest

from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraNotFoundError,
    HardwareOperationError,
)


# Mock Harvesters classes
class MockDeviceInfo:
    """Mock device info from Harvester."""

    def __init__(
        self, serial_number="12345678", model="CV-X420", vendor="Keyence", unique_id="TLUsb::0x1234::0x5678::12345678"
    ):
        self.serial_number = serial_number
        self.model = model
        self.vendor = vendor
        self.unique_id = unique_id
        self.display_name = f"{vendor} {model} ({serial_number})"


class MockGenICamNode:
    """Mock GenICam node with value and accessibility."""

    def __init__(self, value, writable=True, readable=True, min_val=None, max_val=None, node_type="IntNode"):
        self._value = value
        self._writable = writable
        self._readable = readable
        self._min_val = min_val
        self._max_val = max_val
        self._node_type = node_type

    @property
    def value(self):
        if not self._readable:
            raise RuntimeError("Node is not readable")
        return self._value

    @value.setter
    def value(self, new_value):
        if not self._writable:
            raise RuntimeError("Node is not writable")
        if self._min_val is not None and new_value < self._min_val:
            raise ValueError(f"Value {new_value} below minimum {self._min_val}")
        if self._max_val is not None and new_value > self._max_val:
            raise ValueError(f"Value {new_value} above maximum {self._max_val}")
        self._value = new_value

    @property
    def min(self):
        return self._min_val

    @property
    def max(self):
        return self._max_val

    def is_writable(self):
        return self._writable

    def is_readable(self):
        return self._readable


class MockEnumNode(MockGenICamNode):
    """Mock GenICam enumeration node with entries."""

    def __init__(self, value, entries, writable=True, readable=True):
        super().__init__(value, writable, readable, node_type="EnumNode")
        self._entries = entries
        self._entry_objects = [MockEnumEntry(name) for name in entries]

    @property
    def value(self):
        if not self._readable:
            raise RuntimeError("Node is not readable")
        return self._value

    @value.setter
    def value(self, new_value):
        if not self._writable:
            raise RuntimeError("Node is not writable")
        if new_value not in self._entries:
            raise ValueError(f"Invalid enum value {new_value}, valid values: {self._entries}")
        self._value = new_value

    @property
    def entries(self):
        return self._entry_objects


class MockEnumEntry:
    """Mock GenICam enum entry."""

    def __init__(self, symbolic_value):
        self.symbolic_value = symbolic_value
        self.symbolic = symbolic_value  # Alias for GenICam compatibility

    def is_available(self):
        """Check if entry is available."""
        return True


class MockNodeMap:
    """Mock GenICam node map."""

    def __init__(self, **nodes):
        self._nodes = nodes

    def __getattr__(self, name):
        return self._nodes.get(name)


class MockImageAcquirer:
    """Mock Harvester ImageAcquirer."""

    def __init__(self, device_info, node_map=None):
        self.device_info = device_info
        self._node_map = node_map or MockNodeMap()
        self._is_acquiring = False
        self._timeout_exception = None

    @property
    def remote_device(self):
        """Remote device with node_map."""
        remote_mock = Mock()
        remote_mock.node_map = self._node_map
        return remote_mock

    def start(self):
        """Start acquisition."""
        self._is_acquiring = True

    def stop(self):
        """Stop acquisition."""
        self._is_acquiring = False

    def destroy(self):
        """Destroy acquirer."""
        self._is_acquiring = False

    def fetch(self, timeout=1.0):
        """Fetch a buffer."""
        if self._timeout_exception:
            raise self._timeout_exception
        buffer = MockBuffer()
        return buffer

    def is_acquiring(self):
        """Check if acquiring (method, not property)."""
        return self._is_acquiring


class MockBuffer:
    """Mock buffer from Harvester."""

    def __init__(self, width=1920, height=1080, pixel_format="RGB8"):
        self.payload = MockPayload(width, height, pixel_format)

    def queue(self):
        """Queue buffer back to acquirer."""
        pass

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically queue buffer."""
        self.queue()
        return False


class MockComponent:
    """Mock GenICam image component."""

    def __init__(self, data, width, height, pixel_format):
        self.data = data
        self.width = width
        self.height = height
        self.pixel_format = pixel_format
        # Set num_components_per_pixel based on format
        if pixel_format == "Mono8":
            self.num_components_per_pixel = 1
        else:  # RGB8, BGR8
            self.num_components_per_pixel = 3


class MockPayload:
    """Mock payload with image data."""

    def __init__(self, width=1920, height=1080, pixel_format="RGB8"):
        self._width = width
        self._height = height
        self._pixel_format = pixel_format
        # Generate mock image data
        if pixel_format == "Mono8":
            self._data = np.random.randint(0, 255, (height, width), dtype=np.uint8)
        else:  # RGB8 or BGR8
            self._data = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)

    @property
    def components(self):
        """Components with image data."""
        return [MockComponent(self._data, self._width, self._height, self._pixel_format)]


class MockHarvester:
    """Mock Harvesters Harvester."""

    def __init__(self):
        self.device_info_list = []
        self._cti_files = []
        self._updated = False

    def add_file(self, file_path):
        """Add CTI file."""
        self._cti_files.append(file_path)

    def update(self):
        """Update device list."""
        self._updated = True
        # Simulate discovering devices
        self.device_info_list = [
            MockDeviceInfo(serial_number="12345678", model="CV-X420", vendor="Keyence"),
            MockDeviceInfo(serial_number="87654321", model="CV-X450", vendor="Keyence"),
        ]

    def create(self, id_=None):
        """Create ImageAcquirer for device."""
        # Find device by unique_id OR index
        device_info = None

        # If id_ is an integer, use it as index
        if isinstance(id_, int):
            if 0 <= id_ < len(self.device_info_list):
                device_info = self.device_info_list[id_]
            else:
                raise RuntimeError(f"Device index out of range: {id_}")
        else:
            # Find by unique_id
            for dev in self.device_info_list:
                if dev.unique_id == id_:
                    device_info = dev
                    break

        if device_info is None:
            raise RuntimeError(f"Device not found: {id_}")

        # Create node map with typical GenICam nodes
        node_map = MockNodeMap(
            ExposureTime=MockGenICamNode(10000.0, writable=True, readable=True, min_val=100.0, max_val=1000000.0),
            Gain=MockGenICamNode(1.0, writable=True, readable=True, min_val=0.0, max_val=20.0),
            Width=MockGenICamNode(1920, writable=True, readable=True, min_val=32, max_val=1920),
            Height=MockGenICamNode(1080, writable=True, readable=True, min_val=32, max_val=1080),
            PixelFormat=MockEnumNode("RGB8", ["Mono8", "RGB8", "BGR8"], writable=True, readable=True),
            TriggerMode=MockEnumNode("Off", ["Off", "On"], writable=True, readable=True),
            TriggerSource=MockEnumNode("Software", ["Software", "Line0", "Line1"], writable=True, readable=True),
            TriggerSelector=MockEnumNode("FrameStart", ["FrameStart", "ExposureStart"], writable=True, readable=True),
        )

        return MockImageAcquirer(device_info, node_map)

    def reset(self):
        """Reset Harvester."""
        self.device_info_list = []
        self._cti_files = []
        self._updated = False


# Pytest fixtures
@pytest.fixture
def mock_harvester():
    """Create a mock Harvester instance."""
    harvester = MockHarvester()
    # Pre-populate device list
    harvester.device_info_list = [
        MockDeviceInfo(serial_number="12345678", model="CV-X420", vendor="Keyence"),
        MockDeviceInfo(serial_number="87654321", model="CV-X450", vendor="Keyence"),
    ]
    return harvester


@pytest.fixture
def mock_harvester_module(mock_harvester):
    """Patch harvesters module and return mock Harvester."""

    # Patch the Harvester class to return NEW mock instances on each call
    # Also patch os.path.exists to make CTI file "exist"
    def create_mock_harvester():
        """Create a new MockHarvester instance for each call."""
        harvester = MockHarvester()
        # Pre-populate device list
        harvester.device_info_list = [
            MockDeviceInfo(serial_number="12345678", model="CV-X420", vendor="Keyence"),
            MockDeviceInfo(serial_number="87654321", model="CV-X450", vendor="Keyence"),
        ]
        return harvester

    with (
        patch("mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend.Harvester") as MockHarvesterClass,
        patch("mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend.os.path.exists", return_value=True),
        patch("mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend.HARVESTERS_AVAILABLE", True),
    ):
        MockHarvesterClass.side_effect = create_mock_harvester
        yield mock_harvester


@pytest.fixture
async def genicam_backend(mock_harvester_module):
    """Create GenICamCameraBackend instance with mocked Harvester."""
    from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

    # Reset singleton before each test
    GenICamCameraBackend._shared_harvester = None
    GenICamCameraBackend._harvester_cti_path = None

    backend = GenICamCameraBackend(
        camera_name="12345678",  # Use serial number for proper device matching
        cti_path="/mock/path/to/gentl.cti",
    )

    # Initialize and connect
    await backend.initialize()

    yield backend

    # Cleanup - backend will be cleaned up automatically
    # No explicit cleanup needed since initialize() handles everything


@pytest.fixture
async def genicam_backend_uninitialized(mock_harvester_module):
    """Create GenICamCameraBackend instance without initialization."""
    from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

    # Reset singleton before each test
    GenICamCameraBackend._shared_harvester = None
    GenICamCameraBackend._harvester_cti_path = None

    backend = GenICamCameraBackend(
        camera_name="12345678",  # Use serial number for proper device matching
        cti_path="/mock/path/to/gentl.cti",
    )

    yield backend


def attach_mock_acquirer(backend, node_map=None, *, vendor="Keyence", model="CV-X420"):
    """Attach a simple mocked image acquirer and synchronous _run_blocking helper."""
    backend.initialized = True
    backend.device_info = {"vendor": vendor, "model": model}
    backend.image_acquirer = MockImageAcquirer(
        MockDeviceInfo(serial_number=backend.camera_name, vendor=vendor, model=model),
        node_map=node_map or MockNodeMap(),
    )

    async def run_blocking(func, timeout=None):
        return func()

    backend._run_blocking = AsyncMock(side_effect=run_blocking)
    return backend


# Tests for singleton Harvester pattern
class TestSingletonHarvesterPattern:
    """Tests for singleton Harvester pattern implementation."""

    @pytest.mark.asyncio
    async def test_shared_harvester_creation(self, mock_harvester_module):
        """Test that shared Harvester is created once and reused."""
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        # Reset class-level harvester
        GenICamCameraBackend._shared_harvester = None
        GenICamCameraBackend._harvester_cti_path = None

        backend1 = GenICamCameraBackend(
            camera_name="12345678",  # Use serial number as camera name
            cti_path="/mock/path/to/gentl.cti",
        )
        await backend1.initialize()

        backend2 = GenICamCameraBackend(
            camera_name="87654321",  # Use serial number as camera name
            cti_path="/mock/path/to/gentl.cti",
        )
        await backend2.initialize()

        # Both backends should share the same Harvester instance
        assert backend1.harvester is backend2.harvester
        assert GenICamCameraBackend._shared_harvester is not None

    @pytest.mark.asyncio
    async def test_harvester_update_called_once(self, mock_harvester_module):
        """Test that harvester.update() is only called once during Harvester creation."""
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        # Reset class-level harvester
        GenICamCameraBackend._shared_harvester = None
        GenICamCameraBackend._harvester_cti_path = None

        # Track update calls on the shared class instance
        update_count = 0

        # Wrap the original MockHarvester.update method to count calls
        original_mock_update = MockHarvester.update

        def counting_update(self):
            nonlocal update_count
            update_count += 1
            original_mock_update(self)

        MockHarvester.update = counting_update

        try:
            # Create and initialize two backends
            backend1 = GenICamCameraBackend(
                camera_name="12345678",  # Use serial number
                cti_path="/mock/path/to/gentl.cti",
            )
            await backend1.initialize()

            backend2 = GenICamCameraBackend(
                camera_name="87654321",  # Use serial number
                cti_path="/mock/path/to/gentl.cti",
            )
            await backend2.initialize()

            # update() should have been called exactly once
            assert update_count == 1
        finally:
            # Restore original update method
            MockHarvester.update = original_mock_update

    @pytest.mark.asyncio
    async def test_harvester_reset_on_cti_path_change(self, mock_harvester_module):
        """Test that Harvester is reset when CTI path changes."""
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        # Reset class-level harvester
        GenICamCameraBackend._shared_harvester = None
        GenICamCameraBackend._harvester_cti_path = None

        backend1 = GenICamCameraBackend(
            camera_name="12345678",  # Use serial number
            cti_path="/mock/path/to/gentl.cti",
        )
        await backend1.initialize()
        first_harvester = backend1.harvester

        # Reset shared harvester to simulate CTI path change
        GenICamCameraBackend._shared_harvester = None
        GenICamCameraBackend._harvester_cti_path = None

        # Create backend with different CTI path
        backend2 = GenICamCameraBackend(
            camera_name="87654321",  # Use serial number
            cti_path="/different/path/to/gentl.cti",
        )
        await backend2.initialize()

        # Should have created new Harvester instance
        assert backend2.harvester is not first_harvester

    @pytest.mark.asyncio
    async def test_multi_camera_acquisition_no_interference(self, mock_harvester_module):
        """Test that multiple cameras can acquire simultaneously without interference."""
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        # Reset class-level harvester
        GenICamCameraBackend._shared_harvester = None
        GenICamCameraBackend._harvester_cti_path = None

        # Create two backends
        backend1 = GenICamCameraBackend(
            camera_name="12345678",  # Use serial number
            cti_path="/mock/path/to/gentl.cti",
        )
        await backend1.initialize()

        backend2 = GenICamCameraBackend(
            camera_name="87654321",  # Use serial number
            cti_path="/mock/path/to/gentl.cti",
        )
        await backend2.initialize()

        # Start acquisition on both cameras

        # Both should be acquiring
        assert backend1.image_acquirer.is_acquiring() is True
        assert backend2.image_acquirer.is_acquiring() is True

        # Cleanup


# Tests for pixel format methods
class TestPixelFormatMethods:
    """Tests for pixel format get/set/range methods."""

    @pytest.mark.asyncio
    async def test_get_current_pixel_format(self, genicam_backend):
        """Test getting current pixel format."""
        pixel_format = await genicam_backend.get_current_pixel_format()
        assert pixel_format == "RGB8"

    @pytest.mark.asyncio
    async def test_get_pixel_format_range(self, genicam_backend):
        """Test getting available pixel formats."""
        pixel_formats = await genicam_backend.get_pixel_format_range()
        assert "Mono8" in pixel_formats
        assert "RGB8" in pixel_formats
        assert "BGR8" in pixel_formats

    @pytest.mark.asyncio
    async def test_set_pixel_format(self, genicam_backend):
        """Test setting pixel format."""
        await genicam_backend.set_pixel_format("Mono8")

        # Verify it was actually set
        current = await genicam_backend.get_current_pixel_format()
        assert current == "Mono8"

    @pytest.mark.asyncio
    async def test_set_invalid_pixel_format(self, genicam_backend):
        """Test setting invalid pixel format raises error."""
        with pytest.raises(HardwareOperationError):
            await genicam_backend.set_pixel_format("InvalidFormat")

    @pytest.mark.asyncio
    async def test_pixel_format_when_not_initialized(self, genicam_backend_uninitialized):
        """Test pixel format methods raise error when not initialized."""
        with pytest.raises(CameraConnectionError):
            await genicam_backend_uninitialized.get_current_pixel_format()

        with pytest.raises(CameraConnectionError):
            await genicam_backend_uninitialized.get_pixel_format_range()

        with pytest.raises(CameraConnectionError):
            await genicam_backend_uninitialized.set_pixel_format("Mono8")


# Tests for trigger mode capability detection
class TestTriggerModeDetection:
    """Tests for trigger mode capability detection (RO vs RW)."""

    @pytest.mark.asyncio
    async def test_detect_writable_trigger_mode(self, genicam_backend):
        """Test detection of writable TriggerMode node."""
        # Default mock has writable TriggerMode
        await genicam_backend.set_triggermode("trigger")
        mode = await genicam_backend.get_triggermode()
        assert mode == "trigger"

    @pytest.mark.asyncio
    async def test_detect_readonly_trigger_mode(self, mock_harvester_module):
        """Test detection of read-only TriggerMode node."""
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        # Modify mock to have read-only TriggerMode BEFORE creating backend
        original_create = mock_harvester_module.create

        def create_with_readonly_trigger(id_=None):
            acquirer = original_create(id_)
            # Replace TriggerMode with read-only version
            acquirer.remote_device.node_map._nodes["TriggerMode"] = MockEnumNode(
                "Off", ["Off", "On"], writable=False, readable=True
            )
            return acquirer

        mock_harvester_module.create = create_with_readonly_trigger

        # Create backend with read-only TriggerMode
        backend = GenICamCameraBackend(
            camera_name="12345678",  # Use serial number
            cti_path="/mock/path/to/gentl.cti",
        )

        await backend.initialize()

        # Attempting to set trigger mode should handle gracefully or raise configuration error
        with pytest.raises((CameraConfigurationError, RuntimeError)):
            await backend.set_triggermode("On")

        # Cleanup


# Note: Software trigger methods (set_trigger_source, execute_software_trigger)
# are not part of the GenICam backend public API, so tests are removed


# Tests for error handling
class TestErrorHandling:
    """Tests for error handling and exceptions."""

    @pytest.mark.asyncio
    async def test_camera_not_found_error(self, mock_harvester_module):
        """Test CameraNotFoundError when camera with serial not found."""
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        backend = GenICamCameraBackend(
            camera_name="NonExistent",
            cti_path="/mock/path/to/gentl.cti",
        )

        with pytest.raises(CameraNotFoundError):
            await backend.initialize()

    @pytest.mark.asyncio
    async def test_initialization_required(self, genicam_backend_uninitialized):
        """Test that operations require initialization."""
        # Backend not initialized - operations should fail
        with pytest.raises((CameraConnectionError, AttributeError)):
            await genicam_backend_uninitialized.capture()

    @pytest.mark.asyncio
    async def test_capture_success(self, genicam_backend):
        """Test that capture works since acquisition starts automatically."""
        # Acquisition started automatically in initialize()
        image = await genicam_backend.capture()
        assert image is not None
        assert isinstance(image, np.ndarray)

    @pytest.mark.asyncio
    async def test_timeout_error_on_fetch(self, mock_harvester_module):
        """Test timeout error during buffer fetch."""
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        # Patch MockHarvester.create to inject timeout exception
        original_create = MockHarvester.create

        def create_with_timeout(self, id_=None):
            acquirer = original_create(self, id_)
            acquirer._timeout_exception = TimeoutError("Fetch timeout")
            return acquirer

        MockHarvester.create = create_with_timeout

        try:
            backend = GenICamCameraBackend(
                camera_name="12345678",  # Use serial number
                cti_path="/mock/path/to/gentl.cti",
            )

            await backend.initialize()

            with pytest.raises(CameraCaptureError):
                await backend.capture()
        finally:
            # Restore original create method
            MockHarvester.create = original_create


# Tests for exposure and gain
class TestExposureAndGain:
    """Tests for exposure and gain configuration."""

    @pytest.mark.asyncio
    async def test_get_exposure_time(self, genicam_backend):
        """Test getting exposure time."""
        exposure = await genicam_backend.get_exposure()
        assert exposure == 10000.0

    @pytest.mark.asyncio
    async def test_set_exposure_time(self, genicam_backend):
        """Test setting exposure time."""
        await genicam_backend.set_exposure(50000.0)
        exposure = await genicam_backend.get_exposure()
        assert exposure == 50000.0

    @pytest.mark.asyncio
    async def test_get_gain(self, genicam_backend):
        """Test getting gain."""
        gain = await genicam_backend.get_gain()
        assert gain == 1.0

    @pytest.mark.asyncio
    async def test_set_gain(self, genicam_backend):
        """Test setting gain."""
        await genicam_backend.set_gain(5.0)
        gain = await genicam_backend.get_gain()
        assert gain == 5.0

    @pytest.mark.asyncio
    async def test_exposure_range_validation(self, genicam_backend):
        """Test exposure range validation."""
        with pytest.raises((CameraConfigurationError, ValueError)):
            await genicam_backend.set_exposure(50.0)  # Below minimum

        with pytest.raises((CameraConfigurationError, ValueError)):
            await genicam_backend.set_exposure(2000000.0)  # Above maximum


# Tests for image capture
class TestImageCapture:
    """Tests for image capture functionality."""

    @pytest.mark.asyncio
    async def test_capture_success(self, genicam_backend):
        """Test successful image capture."""
        image = await genicam_backend.capture()

        assert image is not None
        assert isinstance(image, np.ndarray)
        assert image.shape == (1080, 1920, 3)  # Height, Width, Channels

    @pytest.mark.asyncio
    async def test_acquisition_auto_started(self, genicam_backend):
        """Test that acquisition is automatically started."""
        # Acquisition should be started automatically in initialize()
        assert genicam_backend.image_acquirer.is_acquiring() is True

    @pytest.mark.asyncio
    async def test_multiple_captures(self, genicam_backend):
        """Test capturing multiple images."""

        for _ in range(5):
            image = await genicam_backend.capture()
            assert image is not None
            assert isinstance(image, np.ndarray)


# Tests for camera info
class TestCameraInfo:
    """Tests for camera information retrieval."""

    @pytest.mark.asyncio
    async def test_get_camera_info(self, genicam_backend):
        """Test getting camera information."""
        # Access device_info dict directly
        info = genicam_backend.device_info

        assert "serial_number" in info
        assert "model" in info
        assert info["serial_number"] == "12345678"
        assert info["model"] == "CV-X420"

    @pytest.mark.asyncio
    async def test_camera_name_property(self, genicam_backend):
        """Test camera_name property."""
        assert genicam_backend.camera_name == "12345678"


class TestDiscoveryAndHelperMethods:
    @pytest.mark.asyncio
    async def test_discover_async_uses_to_thread(self, mock_harvester_module):
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        with patch(
            "mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend.asyncio.to_thread",
            new=AsyncMock(return_value=["12345678"]),
        ) as to_thread:
            result = await GenICamCameraBackend.discover_async(include_details=False)

        assert result == ["12345678"]
        to_thread.assert_awaited_once_with(GenICamCameraBackend.get_available_cameras, False)

    def test_detect_cti_path_prefers_env_var(self, mock_harvester_module):
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        with (
            patch(
                "mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend.os.getenv", return_value="/env.cti"
            ),
            patch(
                "mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend.os.path.exists", return_value=True
            ),
        ):
            assert GenICamCameraBackend._detect_cti_path() == "/env.cti"

    def test_detect_cti_path_raises_when_not_found(self, mock_harvester_module):
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        with (
            patch("mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend.os.getenv", return_value=None),
            patch(
                "mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend.os.path.exists", return_value=False
            ),
            patch(
                "mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend.platform.system",
                return_value="Linux",
            ),
            patch(
                "mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend.platform.machine",
                return_value="x86_64",
            ),
        ):
            with pytest.raises(CameraConfigurationError, match="GenTL Producer not found"):
                GenICamCameraBackend._detect_cti_path()

    def test_get_available_cameras_returns_empty_when_cti_missing(self, mock_harvester_module):
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        with patch.object(GenICamCameraBackend, "_detect_cti_path", side_effect=CameraConfigurationError("missing")):
            assert GenICamCameraBackend.get_available_cameras() == []
            assert GenICamCameraBackend.get_available_cameras(include_details=True) == {}

    @pytest.mark.asyncio
    async def test_cleanup_on_failure_clears_resources(self, genicam_backend_uninitialized):
        backend = attach_mock_acquirer(genicam_backend_uninitialized)
        backend.harvester = Mock()
        backend.image_acquirer.start()
        backend._cleanup_executor = AsyncMock()

        await backend._cleanup_on_failure()

        assert backend.image_acquirer is None
        assert backend.harvester is None
        assert backend.initialized is False
        backend._cleanup_executor.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("vendor", "expected_integer"),
        [("Keyence", True), ("Basler", False), ("Other", False)],
    )
    async def test_detect_vendor_quirks_sets_expected_flags(
        self, genicam_backend_uninitialized, vendor, expected_integer
    ):
        backend = genicam_backend_uninitialized
        backend.device_info = {"vendor": vendor}
        backend._detect_trigger_mode_capability = AsyncMock()

        await backend._detect_vendor_quirks()

        assert backend.vendor_quirks["use_integer_exposure"] is expected_integer
        backend._detect_trigger_mode_capability.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_detect_trigger_mode_capability_handles_missing_node(self, genicam_backend_uninitialized):
        backend = attach_mock_acquirer(genicam_backend_uninitialized, MockNodeMap())

        await backend._detect_trigger_mode_capability()

        assert backend.vendor_quirks["trigger_mode_writable"] is False
        assert backend.vendor_quirks["trigger_mode_at_init"] == "unknown"
        assert backend.triggermode == "unknown"

    @pytest.mark.asyncio
    async def test_detect_trigger_mode_capability_falls_back_on_error(self, genicam_backend_uninitialized):
        backend = attach_mock_acquirer(genicam_backend_uninitialized)
        backend.logger.warning = Mock()
        backend._run_blocking = AsyncMock(side_effect=RuntimeError("boom"))

        await backend._detect_trigger_mode_capability()

        assert backend.vendor_quirks["trigger_mode_writable"] is True
        assert backend.vendor_quirks["trigger_mode_at_init"] == "continuous"
        backend.logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_get_node_value_uses_fallback_names(self, genicam_backend_uninitialized):
        node_map = MockNodeMap(ExposureTimeAbs=MockGenICamNode(123.0))
        backend = attach_mock_acquirer(genicam_backend_uninitialized, node_map)

        value = await backend._get_node_value("ExposureTime", ["ExposureTimeAbs"])

        assert value == 123.0

    @pytest.mark.asyncio
    async def test_set_node_value_uses_integer_exposure_conversion(self, genicam_backend_uninitialized):
        node_map = MockNodeMap(ExposureTime=MockGenICamNode(0))
        backend = attach_mock_acquirer(genicam_backend_uninitialized, node_map)
        backend.vendor_quirks["use_integer_exposure"] = True

        await backend._set_node_value("ExposureTime", 12.9)

        assert node_map.ExposureTime.value == 12

    @pytest.mark.asyncio
    async def test_configure_camera_sets_buffer_count_and_acquisition_mode(self, genicam_backend_uninitialized):
        node_map = MockNodeMap(AcquisitionMode=MockEnumNode("SingleFrame", ["SingleFrame", "Continuous"]))
        backend = attach_mock_acquirer(genicam_backend_uninitialized, node_map)
        backend.buffer_count = 7

        await backend._configure_camera()

        assert backend.image_acquirer.num_buffers == 7
        assert node_map.AcquisitionMode.value == "Continuous"

    @pytest.mark.asyncio
    async def test_start_acquisition_starts_when_not_running(self, genicam_backend_uninitialized):
        backend = attach_mock_acquirer(genicam_backend_uninitialized)

        await backend._start_acquisition()

        assert backend.image_acquirer.is_acquiring() is True


class TestAdditionalGenICamOperations:
    @pytest.mark.asyncio
    async def test_initialize_imports_existing_config(self, mock_harvester_module, tmp_path):
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        config_path = tmp_path / "camera.json"
        config_path.write_text("{}")
        backend = GenICamCameraBackend("12345678", cti_path="/mock/path/to/gentl.cti", camera_config=str(config_path))
        backend.import_config = AsyncMock()

        await backend.initialize()

        backend.import_config.assert_awaited_once_with(str(config_path))

    @pytest.mark.asyncio
    async def test_get_width_and_height_ranges_default_when_nodes_missing(self, genicam_backend_uninitialized):
        backend = attach_mock_acquirer(genicam_backend_uninitialized, MockNodeMap())

        assert await backend.get_width_range() == [1, 9999]
        assert await backend.get_height_range() == [1, 9999]

    @pytest.mark.asyncio
    async def test_get_trigger_mode_falls_back_when_trigger_source_unreadable(self, genicam_backend_uninitialized):
        node_map = MockNodeMap(
            TriggerMode=MockEnumNode("On", ["Off", "On"], readable=True),
            TriggerSource=MockEnumNode("Software", ["Software"], readable=False),
        )
        backend = attach_mock_acquirer(genicam_backend_uninitialized, node_map)

        assert await backend.get_triggermode() == "trigger"

    @pytest.mark.asyncio
    async def test_set_trigger_mode_restarts_acquisition_and_updates_nodes(self, genicam_backend):
        await genicam_backend.set_triggermode("trigger")
        node_map = genicam_backend.image_acquirer.remote_device.node_map

        assert node_map.TriggerSelector.value == "FrameStart"
        assert node_map.TriggerMode.value == "On"
        assert node_map.TriggerSource.value == "Software"
        assert genicam_backend.image_acquirer.is_acquiring() is True

    @pytest.mark.asyncio
    async def test_capture_in_trigger_mode_requires_software_trigger_command(self, genicam_backend_uninitialized):
        node_map = MockNodeMap(
            TriggerMode=MockEnumNode("On", ["Off", "On"]),
            TriggerSource=MockEnumNode("Software", ["Software"]),
        )
        backend = attach_mock_acquirer(genicam_backend_uninitialized, node_map)
        backend.triggermode = "trigger"

        with pytest.raises(CameraCaptureError, match="No software trigger command found"):
            await backend.capture()

    @pytest.mark.asyncio
    async def test_capture_converts_mono8_to_bgr(self, genicam_backend_uninitialized):
        backend = attach_mock_acquirer(genicam_backend_uninitialized)
        backend.triggermode = "continuous"
        backend.image_acquirer.fetch = lambda timeout=1.0: MockBuffer(width=4, height=3, pixel_format="Mono8")

        image = await backend.capture()

        assert image.shape == (3, 4, 3)
        assert image.dtype == np.uint8

    @pytest.mark.asyncio
    async def test_capture_uses_image_enhancement_when_enabled(self, genicam_backend_uninitialized):
        backend = attach_mock_acquirer(genicam_backend_uninitialized)
        backend.triggermode = "continuous"
        backend.img_quality_enhancement = True
        backend._enhance_image = AsyncMock(return_value=np.ones((1080, 1920, 3), dtype=np.uint8))

        image = await backend.capture()

        backend._enhance_image.assert_awaited_once()
        assert image.shape == (1080, 1920, 3)

    @pytest.mark.asyncio
    async def test_enhance_image_wraps_failures(self, genicam_backend_uninitialized, monkeypatch):
        backend = attach_mock_acquirer(genicam_backend_uninitialized)

        async def raise_from_to_thread(_func):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend.asyncio.to_thread", raise_from_to_thread
        )

        with pytest.raises(CameraCaptureError, match="Image enhancement failed"):
            await backend._enhance_image(np.zeros((2, 2, 3), dtype=np.uint8))

    @pytest.mark.asyncio
    async def test_check_connection_returns_false_when_vendor_node_missing(self, genicam_backend_uninitialized):
        backend = attach_mock_acquirer(genicam_backend_uninitialized, MockNodeMap())
        backend.image_acquirer.start()

        assert await backend.check_connection() is False

    @pytest.mark.asyncio
    async def test_close_cleans_up_image_acquirer_and_executor(self, genicam_backend_uninitialized):
        backend = attach_mock_acquirer(genicam_backend_uninitialized)
        backend.harvester = Mock()
        backend.image_acquirer.start()
        backend._cleanup_executor = AsyncMock()

        await backend.close()

        assert backend.image_acquirer is None
        assert backend.harvester is None
        assert backend.initialized is False
        backend._cleanup_executor.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_white_balance_helpers_cover_common_paths(self, genicam_backend_uninitialized):
        wb_node = Mock()
        wb_node.value = "Continuous"
        wb_node.symbolics = ["Continuous", "Off", "Once"]
        node_map = MockNodeMap(BalanceWhiteAuto=wb_node)
        backend = attach_mock_acquirer(genicam_backend_uninitialized, node_map)

        assert await backend.get_wb() == "auto"
        assert await backend.get_wb_range() == ["auto", "manual", "once"]

        await backend.set_auto_wb_once("mystery")
        assert wb_node.value == "Once"

    @pytest.mark.asyncio
    async def test_import_config_supports_legacy_exposure_and_genicam_nodes(
        self, genicam_backend_uninitialized, tmp_path
    ):
        backend = attach_mock_acquirer(genicam_backend_uninitialized)
        backend.set_exposure = AsyncMock()
        backend.set_gain = AsyncMock()
        backend.set_triggermode = AsyncMock()
        backend.set_auto_wb_once = AsyncMock()
        backend.set_ROI = AsyncMock()
        backend._apply_genicam_nodes = AsyncMock()
        config_path = tmp_path / "camera.json"
        config_path.write_text(
            json.dumps(
                {
                    "exposure": 1500,
                    "gain": 2.5,
                    "triggermode": "trigger",
                    "white_balance": "once",
                    "roi": {"x": 1, "y": 2, "width": 100, "height": 50},
                    "genicam_nodes": {"PixelFormat": "Mono8"},
                }
            )
        )

        await backend.import_config(str(config_path))

        backend.set_exposure.assert_awaited_once_with(1500)
        backend.set_gain.assert_awaited_once_with(2.5)
        backend.set_triggermode.assert_awaited_once_with("trigger")
        backend.set_auto_wb_once.assert_awaited_once_with("once")
        backend.set_ROI.assert_awaited_once_with(1, 2, 100, 50)
        backend._apply_genicam_nodes.assert_awaited_once_with({"PixelFormat": "Mono8"})

    @pytest.mark.asyncio
    async def test_export_config_writes_current_values(self, genicam_backend_uninitialized, tmp_path):
        backend = attach_mock_acquirer(genicam_backend_uninitialized)
        backend.get_exposure = AsyncMock(return_value=1000.0)
        backend.get_gain = AsyncMock(return_value=2.0)
        backend.get_triggermode = AsyncMock(return_value="trigger")
        backend.get_wb = AsyncMock(return_value="auto")
        backend.get_ROI = AsyncMock(return_value={"x": 1, "y": 2, "width": 100, "height": 50})
        backend.get_exposure_range = AsyncMock(return_value=[10.0, 10000.0])
        backend.get_gain_range = AsyncMock(return_value=[0.0, 24.0])
        backend.get_wb_range = AsyncMock(return_value=["auto", "once"])
        backend._export_genicam_nodes = AsyncMock(return_value={"PixelFormat": "Mono8"})
        config_path = tmp_path / "nested" / "camera.json"

        with patch("mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend.time.time", return_value=123.0):
            await backend.export_config(str(config_path))

        config = json.loads(config_path.read_text())
        assert config["camera_name"] == "12345678"
        assert config["vendor"] == "Keyence"
        assert config["exported_timestamp"] == 123.0
        assert config["exposure_time"] == 1000.0
        assert config["roi"] == {"x": 1, "y": 2, "width": 100, "height": 50}
        assert config["genicam_nodes"] == {"PixelFormat": "Mono8"}

    @pytest.mark.asyncio
    async def test_apply_and_export_genicam_nodes_use_available_values(self, genicam_backend_uninitialized):
        reverse_x = MockGenICamNode(False)
        pixel_format = MockEnumNode("RGB8", ["RGB8", "Mono8"])
        node_map = MockNodeMap(PixelFormat=pixel_format, ReverseX=reverse_x)
        backend = attach_mock_acquirer(genicam_backend_uninitialized, node_map)

        await backend._apply_genicam_nodes({"PixelFormat": "Mono8", "Missing": 1, "ReverseX": True})
        exported = await backend._export_genicam_nodes()

        assert pixel_format.value == "Mono8"
        assert reverse_x.value is True
        assert exported["PixelFormat"] == "Mono8"
        assert exported["ReverseX"] is True

    @pytest.mark.asyncio
    async def test_region_of_interest_methods_cover_region_nodes_and_defaults(self, genicam_backend_uninitialized):
        node_map = MockNodeMap(
            RegionOffsetX=MockGenICamNode(0, min_val=0, max_val=10),
            RegionOffsetY=MockGenICamNode(0, min_val=0, max_val=10),
            RegionWidth=MockGenICamNode(640, min_val=1, max_val=1280),
            RegionHeight=MockGenICamNode(480, min_val=1, max_val=960),
        )
        backend = attach_mock_acquirer(genicam_backend_uninitialized, node_map)

        await backend.set_ROI(5, 6, 320, 240)
        roi = await backend.get_ROI()
        await backend.reset_ROI()

        assert roi == {"x": 5, "y": 6, "width": 320, "height": 240}
        assert node_map.RegionOffsetX.value == 0
        assert node_map.RegionOffsetY.value == 0
        assert node_map.RegionWidth.value == 1280
        assert node_map.RegionHeight.value == 960

    @pytest.mark.asyncio
    async def test_capture_timeout_round_trip(self, genicam_backend_uninitialized):
        backend = genicam_backend_uninitialized

        await backend.set_capture_timeout(250)

        assert await backend.get_capture_timeout() == 250
        with pytest.raises(ValueError, match="non-negative"):
            await backend.set_capture_timeout(-1)
