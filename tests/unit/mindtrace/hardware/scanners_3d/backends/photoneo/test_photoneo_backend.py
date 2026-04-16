"""Tests for Photoneo 3D scanner backend."""

import asyncio
import sys
import time
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest

from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraNotFoundError,
    CameraTimeoutError,
    HardwareOperationError,
    SDKNotAvailableError,
)
from mindtrace.hardware.scanners_3d.backends.photoneo import photoneo_backend as photoneo_module
from mindtrace.hardware.scanners_3d.core.models import (
    CameraSpace,
    CodingQuality,
    CodingStrategy,
    HardwareTriggerSignal,
    OperationMode,
    OutputTopology,
    ScannerConfiguration,
    ScanResult,
    TextureSource,
    TriggerMode,
)


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

            with (
                patch("mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend.HARVESTERS_AVAILABLE", True),
                patch("os.path.exists", return_value=True),
            ):
                backend = PhotoneoBackend(serial_number="DVJ-104", cti_path="/mock/producer.cti")
                assert backend.serial_number == "DVJ-104"

    def test_create_without_serial_number(self):
        """Test creating backend without serial number."""
        with patch.dict(
            sys.modules, {"harvesters": create_mock_harvesters(), "harvesters.core": create_mock_harvesters().core}
        ):
            from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
                PhotoneoBackend,
            )

            with (
                patch("mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend.HARVESTERS_AVAILABLE", True),
                patch("os.path.exists", return_value=True),
            ):
                backend = PhotoneoBackend(cti_path="/mock/producer.cti")
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

            with (
                patch("mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend.HARVESTERS_AVAILABLE", True),
                patch("os.path.exists", return_value=True),
            ):
                backend = PhotoneoBackend(serial_number="DVJ-104", cti_path="/mock/producer.cti")
                assert backend.name == "Photoneo:DVJ-104"

    def test_is_open_property_initially_false(self):
        """Test is_open property is initially False."""
        with patch.dict(
            sys.modules, {"harvesters": create_mock_harvesters(), "harvesters.core": create_mock_harvesters().core}
        ):
            from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
                PhotoneoBackend,
            )

            with (
                patch("mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend.HARVESTERS_AVAILABLE", True),
                patch("os.path.exists", return_value=True),
            ):
                backend = PhotoneoBackend(cti_path="/mock/producer.cti")
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

                with (
                    patch(
                        "mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend.HARVESTERS_AVAILABLE",
                        True,
                    ),
                    patch("os.path.exists", return_value=True),
                ):
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

                with patch(
                    "mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend.HARVESTERS_AVAILABLE",
                    True,
                ):
                    backend = PhotoneoBackend(cti_path="/custom/mvGenTLProducer.cti")
                    assert backend._cti_path == "/custom/mvGenTLProducer.cti"


def _make_backend(**kwargs):
    """Create a backend instance with SDK and CTI checks mocked."""
    with (
        patch.object(photoneo_module, "HARVESTERS_AVAILABLE", True),
        patch("os.path.exists", return_value=True),
    ):
        return photoneo_module.PhotoneoBackend(cti_path="/mock/producer.cti", **kwargs)


async def _run_immediately(func, *args, **kwargs):
    """Run a blocking callback inline for async tests."""
    kwargs.pop("timeout", None)
    return func(*args, **kwargs)


class _ValueNode:
    """Simple GenICam-like node for value access."""

    def __init__(self, value=None, *, min_value=None, max_value=None, symbolics=None, fail_on_set=False):
        self._value = value
        self.min = min_value
        self.max = max_value
        self.symbolics = symbolics or []
        self.fail_on_set = fail_on_set

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        if self.fail_on_set:
            raise RuntimeError("set failed")
        self._value = new_value


class _ExecuteNode:
    """Simple executable node."""

    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = 0

    def execute(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("execute failed")


def _make_node_map(**overrides):
    """Build a node map with the subset needed by the unit tests."""
    nodes = {
        "OperationMode": _ValueNode(
            OperationMode.CAMERA.value,
            symbolics=[OperationMode.CAMERA.value, OperationMode.SCANNER.value],
        ),
        "CodingStrategy": _ValueNode(
            CodingStrategy.INTERREFLECTIONS.value,
            symbolics=[CodingStrategy.NORMAL.value, CodingStrategy.INTERREFLECTIONS.value],
        ),
        "CodingQuality": _ValueNode(
            CodingQuality.ULTRA.value,
            symbolics=[CodingQuality.ULTRA.value, CodingQuality.FAST.value],
        ),
        "MaximumFPS": _ValueNode(12.5, min_value=1.0, max_value=30.0),
        "ExposureTime": _ValueNode(20.0, min_value=10.0, max_value=100.0),
        "SinglePatternExposure": _ValueNode(11.0),
        "ShutterMultiplier": _ValueNode(2),
        "ScanMultiplier": _ValueNode(3),
        "ColorSettings_Exposure": _ValueNode(8.0),
        "LEDPower": _ValueNode(50, min_value=0, max_value=100),
        "LaserPower": _ValueNode(60, min_value=1, max_value=100),
        "TextureSource": _ValueNode(
            TextureSource.LED.value,
            symbolics=[TextureSource.LED.value, TextureSource.COLOR.value],
        ),
        "CameraTextureSource": _ValueNode(TextureSource.COLOR.value),
        "OutputTopology": _ValueNode(
            OutputTopology.RAW.value,
            symbolics=[OutputTopology.RAW.value, OutputTopology.FULL_GRID.value],
        ),
        "CameraSpace": _ValueNode(CameraSpace.PRIMARY_CAMERA.value),
        "NormalsEstimationRadius": _ValueNode(4),
        "MaxInaccuracy": _ValueNode(1.5),
        "CalibrationVolumeOnly": _ValueNode(True),
        "HoleFilling": _ValueNode(False),
        "TriggerSelector": _ValueNode("FrameStart"),
        "TriggerMode": _ValueNode("Off"),
        "TriggerSource": _ValueNode("Software"),
        "TriggerSoftware": _ExecuteNode(),
        "HardwareTrigger": _ValueNode(True),
        "HardwareTriggerSignal": _ValueNode(HardwareTriggerSignal.RISING.value),
        "ComponentSelector": _ValueNode("Range"),
        "ComponentEnable": _ValueNode(True),
    }
    nodes.update(overrides)
    return SimpleNamespace(**nodes)


def _make_open_backend(node_map=None, **kwargs):
    """Create an initialized backend with a fake image acquirer."""
    backend = _make_backend(**kwargs)
    backend._is_open = True
    backend._device_info = {"serial_number": "DVJ-104", "model": "MotionCam-3D Color", "vendor": "Photoneo"}
    backend._image_acquirer = SimpleNamespace(remote_device=SimpleNamespace(node_map=node_map or _make_node_map()))
    backend._run_blocking = _run_immediately
    return backend


class _FakeComponent:
    """Minimal Harvesters-like component."""

    def __init__(self, data_format, array):
        self.data_format = data_format
        self._array = np.asarray(array)
        self.height = self._array.shape[0]
        self.width = self._array.shape[1]

    @property
    def data(self):
        return self._array.reshape(-1)


class _FakeBuffer:
    """Context manager wrapper around fake payload data."""

    def __init__(self, components, timestamp_ns=None):
        self.payload = SimpleNamespace(components=components)
        if timestamp_ns is not None:
            self.timestamp_ns = timestamp_ns

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestPhotoneoBackendHighValueUnitPaths:
    """High-value unit-testable paths for the backend."""

    def test_init_raises_when_sdk_is_unavailable(self):
        """The backend should fail fast when Harvesters is missing."""
        with patch.object(photoneo_module, "HARVESTERS_AVAILABLE", False):
            with pytest.raises(SDKNotAvailableError):
                photoneo_module.PhotoneoBackend(cti_path="/mock/producer.cti")

    def test_init_raises_when_cti_file_is_missing(self):
        """An explicit missing CTI path should raise configuration error."""
        with patch.object(photoneo_module, "HARVESTERS_AVAILABLE", True):
            with patch("os.path.exists", return_value=False):
                with pytest.raises(CameraConfigurationError, match="GenTL Producer file not found"):
                    photoneo_module.PhotoneoBackend(cti_path="/missing/producer.cti")

    @pytest.mark.asyncio
    async def test_run_blocking_returns_result(self):
        """Blocking calls should return their result through the async wrapper."""
        backend = _make_backend()

        result = await backend._run_blocking(lambda value: value + 1, 41, timeout=0.1)

        assert result == 42

    @pytest.mark.asyncio
    async def test_run_blocking_converts_timeouts(self):
        """Slow blocking calls should become camera timeout errors."""
        backend = _make_backend(op_timeout_s=0.01)

        with pytest.raises(CameraTimeoutError, match="timed out"):
            await backend._run_blocking(lambda: time.sleep(0.05))

    @pytest.mark.asyncio
    async def test_run_blocking_wraps_unexpected_errors(self):
        """Unexpected blocking failures should be wrapped consistently."""
        backend = _make_backend()

        def _explode():
            raise RuntimeError("boom")

        with pytest.raises(HardwareOperationError, match="Photoneo operation failed: boom"):
            await backend._run_blocking(_explode)

    def test_detect_cti_path_prefers_environment_file(self):
        """A direct file path from GENICAM_GENTL64_PATH should be returned."""
        with (
            patch.dict("os.environ", {"GENICAM_GENTL64_PATH": "/env/producer.cti"}, clear=True),
            patch("os.path.isfile", return_value=True),
        ):
            assert photoneo_module.PhotoneoBackend._detect_cti_path() == "/env/producer.cti"

    def test_detect_cti_path_checks_environment_directory_candidates(self):
        """A directory in GENICAM_GENTL64_PATH should resolve the producer file."""
        with (
            patch.dict("os.environ", {"GENICAM_GENTL64_PATH": "/opt/mvimpact"}, clear=True),
            patch("os.path.isfile", return_value=False),
            patch(
                "os.path.exists",
                side_effect=lambda path: path == "/opt/mvimpact/mvGenTLProducer.cti",
            ),
        ):
            assert photoneo_module.PhotoneoBackend._detect_cti_path() == "/opt/mvimpact/mvGenTLProducer.cti"

    def test_get_shared_harvester_reuses_instance_until_cti_changes(self, monkeypatch):
        """Shared Harvester state should be reused and reset on CTI changes."""
        created = []

        class DummyHarvester:
            def __init__(self):
                self.add_file = Mock()
                self.update = Mock()
                self.reset = Mock()
                self.device_info_list = []
                created.append(self)

        monkeypatch.setattr(photoneo_module, "Harvester", DummyHarvester)
        monkeypatch.setattr(photoneo_module.PhotoneoBackend, "_shared_harvester", None)
        monkeypatch.setattr(photoneo_module.PhotoneoBackend, "_harvester_cti_path", None)
        monkeypatch.setattr(photoneo_module.PhotoneoBackend, "_harvester_lock", None)

        first = photoneo_module.PhotoneoBackend._get_shared_harvester("/one.cti")
        second = photoneo_module.PhotoneoBackend._get_shared_harvester("/one.cti")
        third = photoneo_module.PhotoneoBackend._get_shared_harvester("/two.cti")

        assert first is second
        assert third is not first
        first.add_file.assert_called_once_with("/one.cti")
        first.update.assert_called_once_with()
        first.reset.assert_called_once_with()
        third.add_file.assert_called_once_with("/two.cti")
        third.update.assert_called_once_with()
        assert len(created) == 2

    def test_discover_filters_for_photoneo_devices(self):
        """Discovery should return only Photoneo/PhoXi serial numbers."""
        devices = [
            SimpleNamespace(vendor="Photoneo", model="MotionCam-3D Color", serial_number="SN-1"),
            SimpleNamespace(vendor="Other", model="Unrelated", serial_number="SN-2"),
            SimpleNamespace(vendor="", model="PhoXi XL", serial_number="SN-3"),
        ]

        with (
            patch.object(photoneo_module, "HARVESTERS_AVAILABLE", True),
            patch.object(photoneo_module.PhotoneoBackend, "_detect_cti_path", return_value="/mock/producer.cti"),
            patch.object(
                photoneo_module.PhotoneoBackend,
                "_get_shared_harvester",
                return_value=SimpleNamespace(device_info_list=devices),
            ),
        ):
            assert photoneo_module.PhotoneoBackend.discover() == ["SN-1", "SN-3"]

    def test_discover_detailed_returns_empty_when_cti_is_missing(self):
        """Discovery should degrade cleanly when CTI detection fails."""
        with (
            patch.object(photoneo_module, "HARVESTERS_AVAILABLE", True),
            patch.object(
                photoneo_module.PhotoneoBackend,
                "_detect_cti_path",
                side_effect=CameraConfigurationError("missing"),
            ),
        ):
            assert photoneo_module.PhotoneoBackend.discover_detailed() == []

    @pytest.mark.asyncio
    async def test_initialize_sets_state_and_applies_default_config(self):
        """Initialization should pick a matching device and mark the backend open."""
        backend = _make_backend(serial_number="SN-123", buffer_count=7)
        image_acquirer = SimpleNamespace(num_buffers=0)
        harvester = SimpleNamespace(
            device_info_list=[
                SimpleNamespace(serial_number="SN-123", vendor="Photoneo", model="MotionCam-3D Color"),
            ],
            create=Mock(return_value=image_acquirer),
        )
        backend._run_blocking = _run_immediately
        backend._set_default_config = AsyncMock()

        with patch.object(photoneo_module.PhotoneoBackend, "_get_shared_harvester", return_value=harvester):
            result = await backend.initialize()

        assert result is True
        assert backend.is_open is True
        assert backend.device_info["serial_number"] == "SN-123"
        assert image_acquirer.num_buffers == 7
        harvester.create.assert_called_once_with({"serial_number": "SN-123"})
        backend._set_default_config.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_initialize_raises_when_requested_serial_is_missing(self):
        """Initialization should raise when the requested device is absent."""
        backend = _make_backend(serial_number="missing")
        harvester = SimpleNamespace(
            device_info_list=[SimpleNamespace(serial_number="SN-123", vendor="Photoneo", model="MotionCam-3D Color")]
        )
        backend._run_blocking = _run_immediately

        with patch.object(photoneo_module.PhotoneoBackend, "_get_shared_harvester", return_value=harvester):
            with pytest.raises(CameraNotFoundError, match="missing"):
                await backend.initialize()

    @pytest.mark.asyncio
    async def test_close_stops_acquisition_and_clears_state(self):
        """Closing should stop acquisition, destroy the acquirer, and clear state."""
        image_acquirer = SimpleNamespace(
            is_acquiring=Mock(return_value=True),
            stop=Mock(),
            destroy=Mock(),
        )
        backend = _make_backend()
        backend._is_open = True
        backend._image_acquirer = image_acquirer
        backend._run_blocking = _run_immediately

        await backend.close()

        image_acquirer.stop.assert_called_once_with()
        image_acquirer.destroy.assert_called_once_with()
        assert backend.is_open is False
        assert backend._image_acquirer is None

    @pytest.mark.asyncio
    async def test_capture_parses_components_and_tracks_enabled_flags(self):
        """Capture should disambiguate range, normals, intensity, color, and confidence."""
        range_map = np.array(
            [
                [[10.0, 20.0, 30.0], [40.0, 50.0, 60.0]],
                [[70.0, 80.0, 90.0], [100.0, 110.0, 120.0]],
            ],
            dtype=np.float32,
        )
        normal_map = np.array(
            [
                [[0.0, 0.0, 1.0], [0.1, 0.2, 0.3]],
                [[-0.2, 0.4, 0.5], [0.6, -0.6, 0.2]],
            ],
            dtype=np.float32,
        )
        intensity = np.array([[1, 2], [3, 4]], dtype=np.uint8)
        confidence = np.array([[8, 9], [10, 11]], dtype=np.uint16)
        color = np.full((3, 3, 3), 200, dtype=np.uint8)
        node_map = _make_node_map()
        buffer = _FakeBuffer(
            components=[
                _FakeComponent("Mono8", intensity),
                _FakeComponent("Coord3D_ABC32f", range_map),
                _FakeComponent("Confidence16", confidence),
                _FakeComponent("Coord3D_ABC32f", normal_map),
                _FakeComponent("RGB8", color),
            ],
            timestamp_ns=2_500_000_000,
        )
        image_acquirer = SimpleNamespace(
            remote_device=SimpleNamespace(node_map=node_map),
            is_acquiring=Mock(return_value=False),
            start=Mock(),
            fetch=Mock(return_value=buffer),
        )
        backend = _make_backend()
        backend._is_open = True
        backend._image_acquirer = image_acquirer
        backend._run_blocking = _run_immediately

        result = await backend.capture(
            timeout_ms=250,
            enable_range=True,
            enable_intensity=True,
            enable_confidence=True,
            enable_normal=True,
            enable_color=True,
        )

        image_acquirer.start.assert_called_once_with()
        image_acquirer.fetch.assert_called_once_with(timeout=0.25)
        assert node_map.ComponentSelector.value == "ColorCamera"
        assert node_map.ComponentEnable.value is True
        assert node_map.TriggerSoftware.calls == 1
        np.testing.assert_array_equal(result.range_map, range_map)
        np.testing.assert_array_equal(result.normal_map, normal_map)
        np.testing.assert_array_equal(result.intensity, intensity[..., None])
        np.testing.assert_array_equal(result.confidence, confidence)
        np.testing.assert_array_equal(result.color, color)
        assert result.timestamp == pytest.approx(2.5)
        assert result.frame_number == 1
        assert result.components_enabled[photoneo_module.ScanComponent.COLOR] is True
        assert result.components_enabled[photoneo_module.ScanComponent.NORMAL] is True

    @pytest.mark.asyncio
    async def test_capture_raises_when_backend_is_not_open(self):
        """Capture should fail fast if the backend has not been opened."""
        backend = _make_backend()

        with pytest.raises(CameraConnectionError, match="Scanner not opened"):
            await backend.capture()

    @pytest.mark.asyncio
    async def test_capture_uses_time_fallback_and_wraps_timeout(self, monkeypatch):
        """Capture should fall back to wall-clock time and wrap timeouts consistently."""
        node_map = _make_node_map(TriggerSoftware=_ExecuteNode(fail=True))
        image_acquirer = SimpleNamespace(
            remote_device=SimpleNamespace(node_map=node_map),
            is_acquiring=Mock(return_value=True),
            start=Mock(),
            fetch=Mock(return_value=_FakeBuffer(components=[_FakeComponent("Mono8", np.array([[1]], dtype=np.uint8))])),
        )
        backend = _make_backend()
        backend._is_open = True
        backend._image_acquirer = image_acquirer
        backend._run_blocking = _run_immediately
        monkeypatch.setattr(time, "time", lambda: 123.456)

        result = await backend.capture(timeout_ms=100, enable_range=False, enable_intensity=True)

        image_acquirer.start.assert_not_called()
        assert result.timestamp == pytest.approx(123.456)
        assert result.color is not None

        backend._run_blocking = AsyncMock(side_effect=asyncio.TimeoutError())
        with pytest.raises(CameraTimeoutError, match="100ms"):
            await backend.capture(timeout_ms=100)

    @pytest.mark.asyncio
    async def test_capture_passes_through_and_wraps_capture_errors(self):
        """Capture should preserve capture errors and wrap unrelated failures."""
        backend = _make_backend()
        backend._is_open = True
        backend._image_acquirer = SimpleNamespace()

        backend._run_blocking = AsyncMock(side_effect=CameraCaptureError("device failed"))
        with pytest.raises(CameraCaptureError, match="device failed"):
            await backend.capture()

        backend._run_blocking = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(CameraCaptureError, match="Capture failed: boom"):
            await backend.capture()

    @pytest.mark.asyncio
    async def test_capture_ignores_component_toggle_failures_and_handles_bgr(self):
        """Capture should tolerate component-toggle errors and parse BGR payloads."""
        failing_selector = _ValueNode("Range", fail_on_set=True)
        node_map = _make_node_map(ComponentSelector=failing_selector)
        range_map = np.array([[[1.0, 2.0, 3.0]]], dtype=np.float32)
        bgr_texture = np.array([[[5, 6, 7]]], dtype=np.uint8)
        image_acquirer = SimpleNamespace(
            remote_device=SimpleNamespace(node_map=node_map),
            is_acquiring=Mock(return_value=False),
            start=Mock(),
            fetch=Mock(
                return_value=_FakeBuffer(
                    components=[
                        _FakeComponent("Coord3D_ABC32f", range_map),
                        _FakeComponent("BGR8", bgr_texture),
                    ],
                    timestamp_ns=1_000_000_000,
                )
            ),
        )
        backend = _make_backend()
        backend._is_open = True
        backend._image_acquirer = image_acquirer
        backend._run_blocking = _run_immediately

        result = await backend.capture(enable_range=True, enable_intensity=True, enable_color=False)

        image_acquirer.start.assert_called_once_with()
        np.testing.assert_array_equal(result.range_map, range_map)
        np.testing.assert_array_equal(result.intensity, bgr_texture)
        assert result.color is None

    @pytest.mark.asyncio
    async def test_capture_point_cloud_uses_xyz_intensity_and_confidence(self):
        """XYZ range maps should preserve coordinates and map intensity/confidence."""
        backend = _make_backend()
        backend.capture = AsyncMock(
            return_value=ScanResult(
                range_map=np.array(
                    [
                        [[0.0, 0.0, 0.0], [10.0, 20.0, 30.0]],
                        [[1.0, 1.0, 1.0], [0.0, 0.0, 0.0]],
                    ],
                    dtype=np.float32,
                ),
                intensity=np.array([[0, 255], [128, 64]], dtype=np.uint8),
                confidence=np.array([[10, 200], [255, 1]], dtype=np.uint8),
            )
        )

        point_cloud = await backend.capture_point_cloud(include_colors=True, include_confidence=True)

        np.testing.assert_allclose(point_cloud.points, np.array([[10.0, 20.0, 30.0], [1.0, 1.0, 1.0]]))
        np.testing.assert_allclose(
            point_cloud.colors,
            np.array([[1.0, 1.0, 1.0], [128.0 / 255.0, 128.0 / 255.0, 128.0 / 255.0]]),
        )
        np.testing.assert_allclose(point_cloud.confidence, np.array([200.0 / 255.0, 1.0]))
        assert point_cloud.num_points == 2
        assert point_cloud.has_colors is True

    @pytest.mark.asyncio
    async def test_capture_point_cloud_reconstructs_xyz_from_depth_map(self):
        """Depth-only range maps should be converted into XYZ coordinates."""
        backend = _make_backend()
        backend.capture = AsyncMock(return_value=ScanResult(range_map=np.array([[0.0, 1000.0], [2000.0, 0.0]])))

        point_cloud = await backend.capture_point_cloud(include_colors=False, include_confidence=False)

        np.testing.assert_allclose(
            point_cloud.points,
            np.array(
                [
                    [0.0, -1.0, 1000.0],
                    [-2.0, 0.0, 2000.0],
                ]
            ),
        )
        assert point_cloud.colors is None
        assert point_cloud.confidence is None

    @pytest.mark.asyncio
    async def test_get_capabilities_reads_symbolics_ranges_and_device_info(self):
        """Capabilities should be translated from the scanner node map."""
        backend = _make_open_backend()

        capabilities = await backend.get_capabilities()

        assert capabilities.operation_modes == [OperationMode.CAMERA.value, OperationMode.SCANNER.value]
        assert capabilities.coding_strategies == [CodingStrategy.NORMAL.value, CodingStrategy.INTERREFLECTIONS.value]
        assert capabilities.exposure_range == (10.0, 100.0)
        assert capabilities.led_power_range == (0, 100)
        assert capabilities.fps_range == (1.0, 30.0)
        assert capabilities.model == "MotionCam-3D Color"
        assert capabilities.serial_number == "DVJ-104"

    @pytest.mark.asyncio
    async def test_get_configuration_translates_node_values(self):
        """Configuration reads should map node values into domain enums."""
        backend = _make_open_backend()

        config = await backend.get_configuration()

        assert config.operation_mode == OperationMode.CAMERA
        assert config.coding_strategy == CodingStrategy.INTERREFLECTIONS
        assert config.coding_quality == CodingQuality.ULTRA
        assert config.maximum_fps == 12.5
        assert config.texture_source == TextureSource.LED
        assert config.output_topology == OutputTopology.RAW
        assert config.camera_space == CameraSpace.PRIMARY_CAMERA
        assert config.trigger_mode == TriggerMode.CONTINUOUS
        assert config.hardware_trigger is True
        assert config.hardware_trigger_signal == HardwareTriggerSignal.RISING

    @pytest.mark.asyncio
    async def test_set_configuration_applies_values_and_logs_failures(self):
        """Configuration writes should update nodes and warn on individual failures."""
        node_map = _make_node_map(
            OperationMode=_ValueNode(OperationMode.CAMERA.value),
            LEDPower=_ValueNode(50, fail_on_set=True),
        )
        backend = _make_open_backend(node_map=node_map)
        backend.logger.warning = Mock()

        await backend.set_configuration(
            ScannerConfiguration(
                operation_mode=OperationMode.SCANNER,
                texture_source=TextureSource.COLOR,
                trigger_mode=TriggerMode.CONTINUOUS,
                hardware_trigger=True,
                hardware_trigger_signal=HardwareTriggerSignal.RISING,
                led_power=80,
            )
        )

        assert node_map.OperationMode.value == OperationMode.SCANNER.value
        assert node_map.TextureSource.value == TextureSource.COLOR.value
        assert node_map.TriggerSelector.value == "FrameStart"
        assert node_map.TriggerMode.value == "Off"
        assert node_map.HardwareTrigger.value is True
        assert node_map.HardwareTriggerSignal.value == HardwareTriggerSignal.RISING.value
        backend.logger.warning.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("set_method", "get_method", "node_name", "value"),
        [
            ("set_exposure_time", "get_exposure_time", "ExposureTime", 33.5),
            ("set_operation_mode", "get_operation_mode", "OperationMode", OperationMode.SCANNER.value),
            ("set_coding_strategy", "get_coding_strategy", "CodingStrategy", CodingStrategy.HIGH_FREQUENCY.value),
            ("set_coding_quality", "get_coding_quality", "CodingQuality", CodingQuality.FAST.value),
            ("set_led_power", "get_led_power", "LEDPower", 77),
            ("set_laser_power", "get_laser_power", "LaserPower", 88),
            ("set_texture_source", "get_texture_source", "TextureSource", TextureSource.COLOR.value),
            ("set_output_topology", "get_output_topology", "OutputTopology", OutputTopology.FULL_GRID.value),
            ("set_camera_space", "get_camera_space", "CameraSpace", CameraSpace.COLOR_CAMERA.value),
            ("set_normals_estimation_radius", "get_normals_estimation_radius", "NormalsEstimationRadius", 3),
            ("set_max_inaccuracy", "get_max_inaccuracy", "MaxInaccuracy", 2.75),
            ("set_hole_filling", "get_hole_filling", "HoleFilling", True),
            ("set_calibration_volume_only", "get_calibration_volume_only", "CalibrationVolumeOnly", False),
            ("set_hardware_trigger", "get_hardware_trigger", "HardwareTrigger", False),
            ("set_maximum_fps", "get_maximum_fps", "MaximumFPS", 21.0),
            ("set_shutter_multiplier", "get_shutter_multiplier", "ShutterMultiplier", 4),
        ],
    )
    async def test_simple_configuration_accessors_round_trip(self, set_method, get_method, node_name, value):
        """Thin get/set wrappers should delegate directly to the expected node."""
        backend = _make_open_backend()

        await getattr(backend, set_method)(value)

        assert getattr(backend._image_acquirer.remote_device.node_map, node_name).value == value
        assert await getattr(backend, get_method)() == value

    @pytest.mark.asyncio
    async def test_trigger_mode_accessors_translate_continuous_and_software(self):
        """Trigger mode helpers should map between user-facing and node values."""
        backend = _make_open_backend()
        node_map = backend._image_acquirer.remote_device.node_map

        await backend.set_trigger_mode("continuous")
        assert node_map.TriggerSelector.value == "FrameStart"
        assert node_map.TriggerMode.value == "Off"

        await backend.set_trigger_mode("software")
        assert node_map.TriggerMode.value == "On"
        assert node_map.TriggerSource.value == "Software"

        node_map.TriggerMode.value = "Off"
        assert await backend.get_trigger_mode() == "Continuous"
        node_map.TriggerMode.value = "On"
        assert await backend.get_trigger_mode() == "Software"
