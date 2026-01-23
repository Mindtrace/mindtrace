"""Tests for Photoneo 3D scanner backend."""

import sys
import types
from unittest.mock import patch

import numpy as np


def create_mock_harvesters():
    """Create a mock harvesters module for testing."""
    harvesters = types.ModuleType("harvesters")
    harvesters_core = types.ModuleType("harvesters.core")

    class MockHarvester:
        """Mock Harvester class."""

        def __init__(self):
            self._cti_files = []
            self._devices = []
            self._updated = False

        def add_file(self, path):
            self._cti_files.append(path)

        def update(self):
            self._updated = True
            # Simulate found devices
            self._devices = [
                MockDeviceInfo("Photoneo:DVJ-104", "MotionCam-3D Color"),
            ]

        @property
        def device_info_list(self):
            return self._devices

        def create(self, search_key=None):
            return MockImageAcquirer()

        def reset(self):
            self._devices = []
            self._updated = False

    class MockDeviceInfo:
        """Mock device info."""

        def __init__(self, id_str, model):
            self.id_ = id_str
            self.model = model
            self.vendor = "Photoneo"
            self.serial_number = id_str.split(":")[-1] if ":" in id_str else id_str

    class MockNodeMap:
        """Mock GenICam node map."""

        def __init__(self):
            self._nodes = {
                "OperationMode": MockEnumNode(["Camera", "Scanner", "Mode_2D"], "Camera"),
                "CodingStrategy": MockEnumNode(["Normal", "Interreflections", "HighFrequency"], "Normal"),
                "CodingQuality": MockEnumNode(["Ultra", "High", "Fast"], "High"),
                "ExposureTime": MockFloatNode(10.24, 10.24, 100.352),
                "ShutterMultiplier": MockIntNode(1, 1, 10),
                "ScanMultiplier": MockIntNode(1, 1, 10),
                "LEDPower": MockIntNode(4095, 0, 4095),
                "LaserPower": MockIntNode(4095, 1, 4095),
                "TextureSource": MockEnumNode(["LED", "Computed", "Laser", "Focus", "Color"], "LED"),
                "OutputTopology": MockEnumNode(["Raw", "RegularGrid", "FullGrid"], "Raw"),
                "NormalsEstimationRadius": MockIntNode(0, 0, 4),
                "MaxInaccuracy": MockFloatNode(10.0, 0.0, 100.0),
                "CalibrationVolumeOnly": MockBoolNode(False),
                "HoleFilling": MockBoolNode(False),
                "TriggerMode": MockEnumNode(["Software", "Hardware", "Continuous"], "Software"),
                "HardwareTrigger": MockBoolNode(False),
                "HardwareTriggerSignal": MockEnumNode(["Falling", "Rising", "Both"], "Falling"),
                "ComponentSelector": MockEnumNode(
                    ["Range", "Intensity", "Confidence", "Normal", "ColorCamera"], "Range"
                ),
                "ComponentEnable": MockBoolNode(True),
                "Width": MockIntNode(640, 1, 2048),
                "Height": MockIntNode(480, 1, 1536),
            }

        def __getattr__(self, name):
            if name in self._nodes:
                return self._nodes[name]
            raise AttributeError(f"Node {name} not found")

    class MockEnumNode:
        """Mock enum node."""

        def __init__(self, symbolics, value):
            self.symbolics = symbolics
            self.value = value

        def set(self, value):
            if value in self.symbolics:
                self.value = value

    class MockFloatNode:
        """Mock float node."""

        def __init__(self, value, min_val, max_val):
            self.value = value
            self.min = min_val
            self.max = max_val

        def set(self, value):
            self.value = max(self.min, min(self.max, value))

    class MockIntNode:
        """Mock int node."""

        def __init__(self, value, min_val, max_val):
            self.value = value
            self.min = min_val
            self.max = max_val

        def set(self, value):
            self.value = max(self.min, min(self.max, int(value)))

    class MockBoolNode:
        """Mock bool node."""

        def __init__(self, value):
            self.value = value

        def set(self, value):
            self.value = bool(value)

    class MockRemoteDevice:
        """Mock remote device."""

        def __init__(self):
            self.node_map = MockNodeMap()

    class MockImageAcquirer:
        """Mock image acquirer."""

        def __init__(self):
            self._is_open = False
            self._is_acquiring = False
            self.remote_device = MockRemoteDevice()
            self.device = MockDevice()
            self.num_buffers = 5

        def start(self):
            self._is_acquiring = True

        def stop(self):
            self._is_acquiring = False

        def destroy(self):
            self._is_open = False
            self._is_acquiring = False

        def fetch(self, timeout=None):
            """Return a mock buffer."""
            return MockBuffer()

    class MockDevice:
        """Mock device."""

        def __init__(self):
            self.node_map = MockNodeMap()

    class MockBuffer:
        """Mock buffer with payload."""

        def __init__(self):
            self.payload = MockPayload()

        def queue(self):
            pass

    class MockPayload:
        """Mock payload containing components."""

        def __init__(self):
            self.components = [
                MockComponent("Coord3D_ABC32f", (480, 640, 3), np.float32),  # Range
                MockComponent("RGB8", (480, 640, 3), np.uint8),  # Intensity
                MockComponent("Mono8", (480, 640), np.uint8),  # Confidence
            ]

    class MockComponent:
        """Mock data component."""

        def __init__(self, data_format, shape, dtype):
            self.data_format = data_format
            self._shape = shape
            self._dtype = dtype

        @property
        def data(self):
            if self.data_format == "Coord3D_ABC32f":
                # Range map with values in mm range
                return np.random.rand(*self._shape).astype(self._dtype) * 1000
            elif self.data_format == "RGB8":
                return np.random.randint(0, 255, self._shape, dtype=np.uint8)
            elif self.data_format == "Mono8":
                return np.random.randint(0, 255, self._shape, dtype=np.uint8)
            return np.zeros(self._shape, dtype=self._dtype)

    harvesters_core.Harvester = MockHarvester
    harvesters.core = harvesters_core

    return harvesters


class TestPhotoneoBackendImport:
    """Test Photoneo backend import."""

    def test_backend_importable(self):
        """Test that backend can be imported."""
        with patch.dict(
            sys.modules, {"harvesters": create_mock_harvesters(), "harvesters.core": create_mock_harvesters().core}
        ):
            from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
                PhotoneoBackend,
            )

            assert PhotoneoBackend is not None

    def test_backend_has_required_methods(self):
        """Test that backend has all required abstract methods."""
        with patch.dict(
            sys.modules, {"harvesters": create_mock_harvesters(), "harvesters.core": create_mock_harvesters().core}
        ):
            from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
                PhotoneoBackend,
            )

            # Check required methods exist
            assert hasattr(PhotoneoBackend, "initialize")
            assert hasattr(PhotoneoBackend, "close")
            assert hasattr(PhotoneoBackend, "capture")
            assert hasattr(PhotoneoBackend, "capture_point_cloud")
            assert hasattr(PhotoneoBackend, "get_capabilities")
            assert hasattr(PhotoneoBackend, "get_configuration")
            assert hasattr(PhotoneoBackend, "set_configuration")


class TestPhotoneoBackendCreation:
    """Test Photoneo backend creation."""

    def test_create_with_serial_number(self):
        """Test creating backend with serial number."""
        with patch.dict(
            sys.modules, {"harvesters": create_mock_harvesters(), "harvesters.core": create_mock_harvesters().core}
        ):
            from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
                PhotoneoBackend,
            )

            backend = PhotoneoBackend(serial_number="DVJ-104")
            assert backend.serial_number == "DVJ-104"

    def test_create_without_serial_number(self):
        """Test creating backend without serial number."""
        with patch.dict(
            sys.modules, {"harvesters": create_mock_harvesters(), "harvesters.core": create_mock_harvesters().core}
        ):
            from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
                PhotoneoBackend,
            )

            backend = PhotoneoBackend()
            assert backend.serial_number is None


class TestPhotoneoBackendProperties:
    """Test Photoneo backend properties."""

    def test_name_property(self):
        """Test name property."""
        with patch.dict(
            sys.modules, {"harvesters": create_mock_harvesters(), "harvesters.core": create_mock_harvesters().core}
        ):
            from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
                PhotoneoBackend,
            )

            backend = PhotoneoBackend(serial_number="DVJ-104")
            assert backend.name == "Photoneo:DVJ-104"

    def test_is_open_property_initially_false(self):
        """Test is_open property is initially False."""
        with patch.dict(
            sys.modules, {"harvesters": create_mock_harvesters(), "harvesters.core": create_mock_harvesters().core}
        ):
            from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
                PhotoneoBackend,
            )

            backend = PhotoneoBackend()
            assert backend.is_open is False


class TestPhotoneoBackendDiscovery:
    """Test Photoneo backend device discovery."""

    def test_discover_classmethod_exists(self):
        """Test discover class method exists."""
        with patch.dict(
            sys.modules, {"harvesters": create_mock_harvesters(), "harvesters.core": create_mock_harvesters().core}
        ):
            from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
                PhotoneoBackend,
            )

            assert hasattr(PhotoneoBackend, "discover")
            assert callable(getattr(PhotoneoBackend, "discover"))

    def test_discover_detailed_classmethod_exists(self):
        """Test discover_detailed class method exists."""
        with patch.dict(
            sys.modules, {"harvesters": create_mock_harvesters(), "harvesters.core": create_mock_harvesters().core}
        ):
            from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
                PhotoneoBackend,
            )

            assert hasattr(PhotoneoBackend, "discover_detailed")
            assert callable(getattr(PhotoneoBackend, "discover_detailed"))


class TestPhotoneoBackendConfiguration:
    """Test Photoneo backend configuration methods."""

    def test_configuration_dataclass_compatible(self):
        """Test that ScannerConfiguration is properly used."""
        from mindtrace.hardware.scanners_3d.core.models import (
            CodingQuality,
            CodingStrategy,
            OperationMode,
            ScannerConfiguration,
        )

        config = ScannerConfiguration(
            operation_mode=OperationMode.CAMERA,
            coding_strategy=CodingStrategy.INTERREFLECTIONS,
            coding_quality=CodingQuality.ULTRA,
            exposure_time=20.0,
            led_power=4095,
            laser_power=4095,
        )

        assert config.operation_mode == OperationMode.CAMERA
        assert config.coding_strategy == CodingStrategy.INTERREFLECTIONS
        assert config.coding_quality == CodingQuality.ULTRA

    def test_capabilities_dataclass_compatible(self):
        """Test that ScannerCapabilities is properly used."""
        from mindtrace.hardware.scanners_3d.core.models import ScannerCapabilities

        caps = ScannerCapabilities(
            has_range=True,
            has_intensity=True,
            has_confidence=True,
            has_normal=True,
            has_color=True,
            operation_modes=["Camera", "Scanner", "Mode_2D"],
            coding_strategies=["Normal", "Interreflections", "HighFrequency"],
            coding_qualities=["Ultra", "High", "Fast"],
            exposure_range=(10.24, 100.352),
            led_power_range=(0, 4095),
            laser_power_range=(1, 4095),
            model="MotionCam-3D Color",
            serial_number="DVJ-104",
        )

        assert caps.has_color is True
        assert caps.model == "MotionCam-3D Color"


class TestPhotoneoBackendCTIPath:
    """Test CTI path detection."""

    def test_cti_path_environment_variable(self):
        """Test CTI path from environment variable."""
        with patch.dict(
            sys.modules, {"harvesters": create_mock_harvesters(), "harvesters.core": create_mock_harvesters().core}
        ):
            with patch.dict("os.environ", {"GENICAM_GENTL64_PATH": "/custom/path:/other/path"}):
                from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
                    PhotoneoBackend,
                )

                # The backend should be able to look for CTI files in env paths
                backend = PhotoneoBackend()
                assert backend is not None

    def test_cti_path_explicit(self):
        """Test explicit CTI path with mocked file existence."""
        with patch.dict(
            sys.modules, {"harvesters": create_mock_harvesters(), "harvesters.core": create_mock_harvesters().core}
        ):
            # Need to patch os.path.exists to return True for the custom path
            with patch("os.path.exists") as mock_exists:
                mock_exists.return_value = True

                from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
                    PhotoneoBackend,
                )

                backend = PhotoneoBackend(cti_path="/custom/mvGenTLProducer.cti")
                assert backend._cti_path == "/custom/mvGenTLProducer.cti"
