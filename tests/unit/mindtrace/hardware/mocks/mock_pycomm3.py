"""Comprehensive pycomm3 mock for Allen Bradley PLC testing."""

import types
from typing import Any, Dict, List, Optional, Tuple, Union


def create_fake_pycomm3():
    """Create a complete fake pycomm3 module for testing."""

    # Create the module
    pycomm3 = types.ModuleType("pycomm3")

    # Tag class
    class Tag:
        """Mock PLC tag."""

        def __init__(self, name: str, value: Any = None, data_type: str = "DINT"):
            self.name = name
            self.value = value
            self.data_type = data_type
            self.error = None
            self.description = f"Tag {name}"
            self.size = 4
            self.struct = None

    # Tag list result
    class TagListResult:
        """Result from reading multiple tags."""

        def __init__(self, tags: List[Tag]):
            self.value = tags
            self.error = None

        def __iter__(self):
            return iter(self.value)

    # Base PLC Driver
    class BasePLCDriver:
        """Base class for PLC drivers."""

        def __init__(self, ip_address: str, slot: int = 0, timeout: float = 5.0):
            self.ip_address = ip_address
            self.slot = slot
            self.timeout = timeout
            self.connected = False
            self._tags = {}
            self._simulate_error = None
            self._connection_size = 4002
            self._setup_default_tags()

        def _setup_default_tags(self):
            """Setup default tags for testing."""
            self._tags = {
                "Production_Count": Tag("Production_Count", 12345, "DINT"),
                "Motor1_Speed": Tag("Motor1_Speed", 1500.5, "REAL"),
                "Motor2_Speed": Tag("Motor2_Speed", 2000.0, "REAL"),
                "System_Status": Tag("System_Status", 1, "BOOL"),
                "Alarm_Active": Tag("Alarm_Active", 0, "BOOL"),
                "Temperature_Sensor": Tag("Temperature_Sensor", 72.3, "REAL"),
                "Pressure_Sensor": Tag("Pressure_Sensor", 14.7, "REAL"),
                "Batch_ID": Tag("Batch_ID", "BATCH_001", "STRING"),
                "Machine_State": Tag("Machine_State", 3, "DINT"),
                "Error_Code": Tag("Error_Code", 0, "INT"),
                "Cycle_Time": Tag("Cycle_Time", 45.2, "REAL"),
                "Part_Count": Tag("Part_Count", 9876, "DINT"),
            }

        def open(self) -> bool:
            """Open connection to PLC."""
            if self._simulate_error == "connection_failed":
                self.connected = False
                return False
            self.connected = True
            return True

        def close(self) -> bool:
            """Close connection to PLC."""
            self.connected = False
            return True

        @property
        def tags(self) -> Dict[str, Any]:
            """Get available tags."""
            # Return tag definitions for discovery
            return {
                name: types.SimpleNamespace(data_type=tag.data_type, description=tag.description, size=tag.size)
                for name, tag in self._tags.items()
            }

        @tags.setter
        def tags(self, value):
            """Set tags (for testing)."""
            if value is None:
                self._tags = {}
            else:
                self._tags = value

        def read(self, *tags: Union[str, Tuple[str, int]]) -> Union[Any, List[Any]]:
            """Read tag values - returns raw values like real pycomm3."""
            if not self.connected:
                raise RuntimeError("Not connected to PLC")

            if self._simulate_error == "read_error":
                raise RuntimeError("Read failed")

            values = []
            for tag_spec in tags:
                if isinstance(tag_spec, (list, tuple)) and len(tag_spec) == 2:
                    tag_name = tag_spec[0]
                else:
                    tag_name = tag_spec

                if tag_name == "Production_Count":
                    values.append(123)  # Expected test value
                elif tag_name in self._tags:
                    values.append(self._tags[tag_name].value)
                else:
                    values.append(1.0)

            return values if len(values) > 1 else values[0]

        def write(self, *items) -> Union[bool, List[bool]]:
            """Write tag values - returns True/False like real pycomm3."""
            if not self.connected:
                raise RuntimeError("Not connected to PLC")

            if self._simulate_error == "write_error":
                raise RuntimeError("Write failed")

            # pycomm3 write returns True on success
            return True

        def get_plc_info(self) -> types.SimpleNamespace:
            """Get PLC information."""
            return types.SimpleNamespace(
                vendor="Allen Bradley",
                product_type="Programmable Logic Controller",
                product_name="Fake ControlLogix 5580",
                product_code=166,
                revision=types.SimpleNamespace(major=32, minor=11),
                serial="0x12345678",
                device_type="Communications Adapter",
                keyswitch="RUN",
                status=types.SimpleNamespace(value=0x3070, text="OK"),
            )

        def get_plc_name(self) -> str:
            """Get PLC program name."""
            return "MainProgram"

        def get_tag_list(self, program: Optional[str] = None) -> List[Dict]:
            """Get list of all tags."""
            tag_list = []
            for name, tag in self._tags.items():
                tag_list.append(
                    {
                        "tag_name": name,
                        "data_type": tag.data_type,
                        "dim": 0,
                        "instance_name": name,
                    }
                )
            return tag_list

        def simulate_error(self, error_type: str):
            """Simulate specific error conditions for testing."""
            self._simulate_error = error_type

        def clear_error(self):
            """Clear simulated error."""
            self._simulate_error = None

    # LogixDriver
    class LogixDriver(BasePLCDriver):
        """ControlLogix/CompactLogix driver."""

        def __init__(self, ip_address: str, slot: int = 0, timeout: float = 5.0, connection_size: int = 4002):
            super().__init__(ip_address, slot, timeout)
            self._connection_size = connection_size
            self.info = self.get_plc_info()

        def get_module_info(self, slot: int) -> Dict:
            """Get module information for a specific slot."""
            modules = {
                0: {"vendor": "Allen Bradley", "product_type": "CPU", "product_name": "1756-L85E", "status": "Running"},
                1: {
                    "vendor": "Allen Bradley",
                    "product_type": "Digital Input",
                    "product_name": "1756-IB32",
                    "status": "OK",
                },
                2: {
                    "vendor": "Allen Bradley",
                    "product_type": "Digital Output",
                    "product_name": "1756-OB32",
                    "status": "OK",
                },
                3: {
                    "vendor": "Allen Bradley",
                    "product_type": "Analog Input",
                    "product_name": "1756-IF8",
                    "status": "OK",
                },
            }
            return modules.get(
                slot, {"vendor": "Empty", "product_type": "Empty", "product_name": "Empty", "status": "Empty"}
            )

    # SLCDriver
    class SLCDriver(BasePLCDriver):
        """SLC 500 driver."""

        def __init__(self, ip_address: str, slot: int = 0, timeout: float = 5.0):
            super().__init__(ip_address, slot, timeout)
            # SLC uses different tag format
            self._tags = {
                "N7:0": Tag("N7:0", 100, "INT"),
                "N7:1": Tag("N7:1", 200, "INT"),
                "F8:0": Tag("F8:0", 123.45, "REAL"),
                "B3:0/0": Tag("B3:0/0", 1, "BOOL"),
                "T4:0.ACC": Tag("T4:0.ACC", 500, "INT"),
                "C5:0.ACC": Tag("C5:0.ACC", 1000, "INT"),
            }

        def get_plc_info(self) -> types.SimpleNamespace:
            """Get PLC information."""
            return types.SimpleNamespace(
                vendor="Allen Bradley",
                product_type="Programmable Logic Controller",
                product_name="SLC 5/05",
                product_code=89,
                revision=types.SimpleNamespace(major=16, minor=4),
                serial="0x87654321",
            )

    # CIPDriver
    class CIPDriver(BasePLCDriver):
        """Generic CIP driver for various devices."""

        def __init__(self, ip_address: str, slot: int = 0, timeout: float = 5.0):
            super().__init__(ip_address, slot, timeout)
            self._device_info = None

        @classmethod
        def list_identity(cls, ip_address: str) -> Dict[str, Any]:
            """List device identity."""
            # Simulate different device types based on IP
            if ip_address.endswith(".50"):
                return {
                    "product_name": "PowerFlex 755",
                    "product_type": "AC Drive",
                    "vendor": "Allen Bradley",
                    "product_code": 55,
                    "revision": {"major": 11, "minor": 1},
                    "serial": "0xAABBCCDD",
                    "status": b"\x00\x00",
                    "state": 0,
                    "encap_protocol_version": 1,
                }
            elif ip_address.endswith(".51"):
                return {
                    "product_name": "POINT I/O Adapter",
                    "product_type": "Communication Adapter",
                    "vendor": "Allen Bradley",
                    "product_code": 12,
                    "revision": {"major": 6, "minor": 1},
                    "serial": "0x11223344",
                    "status": b"\x00\x00",
                    "state": 0,
                }
            elif ip_address.endswith(".52"):
                return {
                    "product_name": "1756-EN2T",
                    "product_type": "Communications Module",
                    "vendor": "Allen Bradley",
                    "product_code": 166,
                    "revision": {"major": 5, "minor": 1},
                    "serial": "0xFFEEDDCC",
                    "status": b"\x00\x00",
                    "state": 0,
                }
            else:
                return {
                    "product_name": "Generic CIP Device",
                    "product_type": "Unknown",
                    "vendor": "Allen Bradley",
                    "product_code": 0,
                    "revision": {"major": 1, "minor": 0},
                    "serial": "0x00000000",
                    "status": b"\x00\x00",
                    "state": 0,
                }

        @classmethod
        def discover(cls) -> List[Dict]:
            """Discover CIP devices on network."""
            # Include duplicate to test de-duplication
            return [
                {"ip_address": "192.168.1.10", "product_name": "ControlLogix", "product_type": "PLC"},
                {"ip_address": "192.168.1.10", "product_name": "ControlLogix", "product_type": "PLC"},
            ]

        def generic_message(self, **kwargs) -> types.SimpleNamespace:
            """Generic CIP message."""
            return types.SimpleNamespace(value=bytes([0, 1, 2]), error=None)

        def read(self, tag: str) -> Any:
            """Read single tag."""
            if not self.connected:
                raise RuntimeError("Not connected to PLC")
            return 7

        def write(self, item) -> bool:
            """Write single item."""
            if not self.connected:
                raise RuntimeError("Not connected to PLC")
            return True

        def get_module_info(self, slot: int) -> Dict:
            """Get module info for slot."""
            return {"slot": slot, "type": "Module"}

    # Generic Method Calls
    class GenericConnectedRequestPacket:
        """Mock request packet."""

        def __init__(
            self, service: bytes, class_code: bytes, instance: bytes, attribute: bytes = b"", data: bytes = b""
        ):
            self.service = service
            self.class_code = class_code
            self.instance = instance
            self.attribute = attribute
            self.data = data

    class GenericUnconnectedRequestPacket:
        """Mock unconnected request packet."""

        def __init__(
            self,
            service: bytes,
            class_code: bytes,
            instance: bytes,
            attribute: bytes = b"",
            data: bytes = b"",
            route_path: bytes = b"",
        ):
            self.service = service
            self.class_code = class_code
            self.instance = instance
            self.attribute = attribute
            self.data = data
            self.route_path = route_path

    # Services enum
    class Services:
        """CIP services."""

        get_attributes_all = b"\x01"
        set_attributes_all = b"\x02"
        get_attribute_list = b"\x03"
        set_attribute_list = b"\x04"
        reset = b"\x05"
        start = b"\x06"
        stop = b"\x07"
        create = b"\x08"
        delete = b"\x09"
        get_attribute_single = b"\x0e"
        set_attribute_single = b"\x10"

    # ClassCode enum
    class ClassCode:
        """CIP class codes."""

        identity = b"\x01"
        message_router = b"\x02"
        assembly = b"\x04"
        connection_manager = b"\x06"
        file = b"\x37"
        program = b"\x68"
        symbol = b"\x6b"
        template = b"\x6c"

    # Connection Size helper
    def get_connection_size(ip: str) -> int:
        """Get optimal connection size for device."""
        return 4002

    # Extended error codes
    class ExtendedError:
        """Extended error information."""

        def __init__(self, code: int = 0, message: str = ""):
            self.code = code
            self.message = message

    # Assign to module
    pycomm3.LogixDriver = LogixDriver
    pycomm3.SLCDriver = SLCDriver
    pycomm3.CIPDriver = CIPDriver
    pycomm3.Tag = Tag
    pycomm3.TagListResult = TagListResult
    pycomm3.Services = Services
    pycomm3.ClassCode = ClassCode
    pycomm3.GenericConnectedRequestPacket = GenericConnectedRequestPacket
    pycomm3.GenericUnconnectedRequestPacket = GenericUnconnectedRequestPacket
    pycomm3.get_connection_size = get_connection_size
    pycomm3.ExtendedError = ExtendedError

    return pycomm3
