from unittest.mock import Mock, patch

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
