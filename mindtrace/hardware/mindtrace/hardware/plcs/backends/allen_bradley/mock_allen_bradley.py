"""
Mock Allen Bradley PLC Implementation

This module provides a mock implementation of Allen Bradley PLCs for testing and development
without requiring actual hardware or the pycomm3 SDK.

Features:
    - Complete simulation of all three driver types (Logix, SLC, CIP)
    - Realistic tag data generation and management
    - Configurable number of mock PLCs
    - Error simulation capabilities for testing
    - No hardware dependencies

Components:
    - MockAllenBradleyPLC: Mock PLC implementation

Usage:
    from mindtrace.hardware.plcs.backends.allen_bradley import MockAllenBradleyPLC

    # Initialize mock PLC
    plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")

    # Use exactly like real PLC
    await plc.connect()
    tags = await plc.read_tag(["Motor1_Speed", "Conveyor_Status"])
    await plc.write_tag([("Pump1_Command", True)])
    await plc.disconnect()
"""

import asyncio
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from mindtrace.hardware.core.exceptions import (
    PLCCommunicationError,
    PLCConnectionError,
    PLCInitializationError,
    PLCTagError,
    PLCTagNotFoundError,
    PLCTagReadError,
    PLCTagWriteError,
    PLCTimeoutError,
)
from mindtrace.hardware.plcs.backends.base import BasePLC


class MockAllenBradleyPLC(BasePLC):
    """
    Mock implementation of Allen Bradley PLC for testing and development.

    This class provides a complete simulation of the Allen Bradley PLC API without
    requiring actual hardware. It simulates all three driver types and provides
    realistic tag behavior for comprehensive testing.

    Attributes:
        plc_name: User-defined PLC identifier
        ip_address: Simulated IP address
        plc_type: PLC type ("logix", "slc", "cip", or "auto")
        driver_type: Detected/simulated driver type
        _is_connected: Connection status simulation
        _tag_values: Simulated tag values storage
        _tag_types: Tag type mapping for different driver types
        _cache_ttl: Tag cache time-to-live
        _tags_cache: Cached list of available tags
        _cache_timestamp: Timestamp of last cache update
    """

    def __init__(
        self,
        plc_name: str,
        ip_address: str,
        plc_type: Optional[str] = None,
        plc_config_file: Optional[str] = None,
        connection_timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
        write_timeout: Optional[float] = None,
        retry_count: Optional[int] = None,
        retry_delay: Optional[float] = None,
    ):
        """
        Initialize mock Allen Bradley PLC.

        Args:
            plc_name: Unique identifier for the PLC
            ip_address: Simulated IP address
            plc_type: PLC type ('logix', 'slc', 'cip', or 'auto' for auto-detection)
            plc_config_file: Path to configuration file (simulated)
            connection_timeout: Connection timeout in seconds
            read_timeout: Tag read timeout in seconds
            write_timeout: Tag write timeout in seconds
            retry_count: Number of retry attempts
            retry_delay: Delay between retries in seconds
        """
        super().__init__(
            plc_name=plc_name,
            ip_address=ip_address,
            plc_config_file=plc_config_file,
            connection_timeout=connection_timeout,
            read_timeout=read_timeout,
            write_timeout=write_timeout,
            retry_count=retry_count,
            retry_delay=retry_delay,
        )

        self.plc_type = plc_type or "auto"
        self.driver_type = None
        self._is_connected = False
        self._tag_values: Dict[str, Any] = {}
        self._tag_types: Dict[str, str] = {}
        self._cache_ttl = 300  # 5 minutes
        self._tags_cache: Optional[List[str]] = None
        self._cache_timestamp: float = 0

        # Error simulation flags
        self.fail_connect = os.getenv("MOCK_AB_FAIL_CONNECT", "false").lower() == "true"
        self.fail_read = os.getenv("MOCK_AB_FAIL_READ", "false").lower() == "true"
        self.fail_write = os.getenv("MOCK_AB_FAIL_WRITE", "false").lower() == "true"
        self.simulate_timeout = os.getenv("MOCK_AB_TIMEOUT", "false").lower() == "true"

        # Initialize simulated tag data
        self._initialize_mock_data()

        self.logger.info(f"Mock Allen Bradley PLC initialized: plc_type={self.plc_type}, ip_address={self.ip_address}")

    def _initialize_mock_data(self):
        """Initialize realistic mock tag data based on PLC type."""
        # Common Logix tags
        logix_tags = {
            # Motor control tags
            "Motor1_Speed": 1500.0,
            "Motor1_Command": False,
            "Motor1_Status": True,
            "Motor1_Fault": False,
            "Motor2_Speed": 2200.5,
            "Motor2_Command": True,
            "Motor2_Status": True,
            "Motor2_Fault": False,
            # Conveyor system tags
            "Conveyor_Speed": 850.0,
            "Conveyor_Status": True,
            "Conveyor_Emergency_Stop": False,
            "Conveyor_Direction": 1,
            # Sensor tags
            "Temperature_Tank1": 75.2,
            "Temperature_Tank2": 68.8,
            "Pressure_Line1": 125.6,
            "Pressure_Line2": 89.3,
            "Level_Tank1": 67.5,
            "Level_Tank2": 45.2,
            # Digital I/O
            "Pump1_Command": False,
            "Pump1_Status": True,
            "Pump2_Command": True,
            "Pump2_Status": False,
            "Valve1_Open": True,
            "Valve1_Closed": False,
            "Valve2_Open": False,
            "Valve2_Closed": True,
            # Production counters
            "Production_Count": 12567,
            "Good_Parts": 12450,
            "Bad_Parts": 117,
            "Cycle_Time": 45.8,
            # Alarm tags
            "Alarm_Active": False,
            "Warning_Active": True,
            "Emergency_Stop": False,
            "System_Ready": True,
        }

        # SLC-style data file addressing
        slc_tags = {
            # Integer files
            "N7:0": 1500,
            "N7:1": 2200,
            "N7:2": 850,
            "N7:10": 12567,
            "N9:0": 255,
            "N9:1": 128,
            # Binary files
            "B3:0": True,
            "B3:1": False,
            "B3:2": True,
            "B10:0": False,
            # Timer files
            "T4:0": 5000,
            "T4:0.PRE": 10000,
            "T4:0.ACC": 5000,
            "T4:0.EN": True,
            "T4:0.TT": True,
            "T4:0.DN": False,
            # Counter files
            "C5:0": 250,
            "C5:0.PRE": 1000,
            "C5:0.ACC": 250,
            "C5:0.CU": True,
            "C5:0.DN": False,
            # Float files
            "F8:0": 75.2,
            "F8:1": 125.6,
            # Input/Output files
            "I:0.0": 170,  # Binary: 10101010
            "O:0.0": 85,  # Binary: 01010101
            "I:0.0/0": True,
            "I:0.0/1": False,
            "O:0.0/0": False,
            "O:0.0/1": True,
        }

        # CIP object addressing
        cip_tags = {
            # Identity Object
            "Identity": {"vendor_id": 1, "device_type": 14, "product_code": 55},
            "DeviceInfo": {"name": "Mock PowerFlex 755", "revision": "1.001"},
            # Assembly Objects (typical for drives/I/O)
            "Assembly:20": [1500, 0, 255, 0],  # Input assembly
            "Assembly:21": [100, 1, 0],  # Output assembly
            "Assembly:100": [170, 85, 255, 0],  # I/O input data
            "Assembly:101": [85, 170, 0],  # I/O output data
            # Parameter Objects (drive parameters)
            "Parameter:1": 1500.0,  # Speed Reference
            "Parameter:2": 1485.2,  # Speed Feedback
            "Parameter:3": 75.5,  # Torque Reference
            "Parameter:4": 76.1,  # Torque Feedback
            "Parameter:5": 12.8,  # Motor Current
            "Parameter:6": 480.2,  # DC Bus Voltage
            "Parameter:7": 45.6,  # Drive Temperature
            "Parameter:8": 0,  # Fault Code
            "Parameter:9": 0,  # Warning Code
            "Parameter:10": 1,  # Drive Status (running)
            # Module information (for I/O modules)
            "Module:0": {"type": "Digital Input", "status": "OK"},
            "Module:1": {"type": "Analog Input", "status": "OK"},
            # Connection status
            "Connection": {"status": "connected", "timeout": 0},
            # Standard CIP objects
            "0x01:1:1": 1,  # Vendor ID
            "0x01:1:2": 14,  # Device Type
            "0x01:1:3": 55,  # Product Code
            "0x01:1:7": "Mock AB Device",  # Product Name
        }

        # Combine all tag data
        self._tag_values.update(logix_tags)
        self._tag_values.update(slc_tags)
        self._tag_values.update(cip_tags)

        # Set tag types for proper handling
        for tag in logix_tags:
            if isinstance(logix_tags[tag], bool):
                self._tag_types[tag] = "BOOL"
            elif isinstance(logix_tags[tag], int):
                self._tag_types[tag] = "DINT"
            elif isinstance(logix_tags[tag], float):
                self._tag_types[tag] = "REAL"
            else:
                self._tag_types[tag] = "STRING"

    async def initialize(self) -> Tuple[bool, Any, Any]:
        """
        Initialize the mock Allen Bradley PLC connection.

        Returns:
            Tuple of (success, mock_plc_object, mock_device_manager)
        """
        try:
            success = await self.connect()
            if success:
                self.initialized = True
                mock_plc = {
                    "name": self.plc_name,
                    "ip": self.ip_address,
                    "type": self.plc_type,
                    "driver": self.driver_type,
                    "connected": True,
                }
                return True, mock_plc, None
            else:
                return False, None, None
        except Exception as e:
            self.logger.error(f"Mock PLC initialization failed: {e}")
            raise PLCInitializationError(f"Failed to initialize mock Allen Bradley PLC: {e}")

    async def _detect_plc_type(self) -> str:
        """
        Simulate PLC type detection.

        Returns:
            Detected PLC type based on IP pattern or random selection
        """
        self.logger.info(f"Mock auto-detecting PLC type for {self.ip_address}")

        # Simulate detection based on IP pattern for deterministic testing
        last_octet = int(self.ip_address.split(".")[-1])

        if last_octet % 3 == 0:
            detected_type = "logix"
            self.logger.info("Mock detected Logix-compatible PLC")
        elif last_octet % 3 == 1:
            detected_type = "slc"
            self.logger.info("Mock detected SLC/MicroLogix PLC")
        else:
            detected_type = "cip"
            self.logger.info("Mock detected generic CIP device")

        # Add small delay to simulate detection time
        await asyncio.sleep(0.1)
        return detected_type

    async def connect(self) -> bool:
        """
        Simulate connection to the Allen Bradley PLC.

        Returns:
            True if connection successful, False otherwise
        """
        if self.fail_connect:
            raise PLCConnectionError("Simulated connection failure")

        self.logger.info(f"Mock connecting to Allen Bradley PLC at {self.ip_address}")

        # Determine driver type
        if self.plc_type == "auto":
            detected_type = await self._detect_plc_type()
            self.plc_type = detected_type

        for attempt in range(self.retry_count):
            try:
                # Simulate connection delay
                await asyncio.sleep(0.05 * (attempt + 1))

                # Set driver type based on PLC type
                if self.plc_type == "logix":
                    self.driver_type = "LogixDriver"
                elif self.plc_type == "slc":
                    self.driver_type = "SLCDriver"
                else:  # cip or fallback
                    self.driver_type = "CIPDriver"

                # Simulate successful connection
                self._is_connected = True
                self.logger.info(f"Mock successfully connected to Allen Bradley PLC using {self.driver_type}")
                return True

            except Exception as e:
                self.logger.warning(f"Mock connection attempt {attempt + 1} failed: {e}")
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    raise PLCConnectionError(
                        f"Mock failed to connect to Allen Bradley PLC at {self.ip_address} after {self.retry_count} attempts"
                    )

        return False

    async def disconnect(self) -> bool:
        """
        Simulate disconnection from the Allen Bradley PLC.

        Returns:
            True if disconnection successful, False otherwise
        """
        try:
            await asyncio.sleep(0.01)  # Simulate disconnect delay
            self._is_connected = False
            self.initialized = False
            self.logger.info(f"Mock disconnected from Allen Bradley PLC at {self.ip_address}")
            return True
        except Exception as e:
            self.logger.error(f"Mock disconnection error: {e}")
            return False

    async def is_connected(self) -> bool:
        """
        Check if mock Allen Bradley PLC is currently connected.

        Returns:
            True if connected, False otherwise
        """
        return self._is_connected

    async def read_tag(self, tags: Union[str, List[str]]) -> Dict[str, Any]:
        """
        Simulate reading values from Allen Bradley PLC tags.

        Args:
            tags: Single tag name or list of tag names

        Returns:
            Dictionary mapping tag names to their values
        """
        if self.fail_read:
            raise PLCTagReadError("Simulated tag read failure")

        if self.simulate_timeout:
            await asyncio.sleep(10)  # Simulate timeout
            raise PLCTimeoutError("Simulated read timeout")

        if not self._is_connected:
            raise PLCCommunicationError(f"Mock not connected to Allen Bradley PLC at {self.ip_address}")

        try:
            if isinstance(tags, str):
                tag_list = [tags]
            else:
                tag_list = tags

            # Simulate read delay
            await asyncio.sleep(0.01 * len(tag_list))

            # Prepare results
            tag_values = {}

            for tag_name in tag_list:
                if tag_name in self._tag_values:
                    value = self._tag_values[tag_name]

                    # Add some realistic variation to certain tags
                    if isinstance(value, (int, float)) and any(
                        keyword in tag_name.lower() for keyword in ["temp", "pressure", "speed", "level"]
                    ):
                        # Add ±2% random variation to simulate real sensor data
                        variation = value * 0.02 * (random.random() - 0.5)
                        value = value + variation
                        if isinstance(self._tag_values[tag_name], int):
                            value = int(value)
                        # Update stored value for consistency
                        self._tag_values[tag_name] = value

                    tag_values[tag_name] = value
                else:
                    # Tag not found - different behavior per driver type
                    if self.driver_type == "LogixDriver":
                        self.logger.warning(f"Mock tag '{tag_name}' not found in Logix PLC")
                        tag_values[tag_name] = None
                    elif self.driver_type == "SLCDriver":
                        # SLC might return 0 for non-existent addresses
                        self.logger.warning(f"Mock SLC address '{tag_name}' not configured, returning 0")
                        tag_values[tag_name] = 0
                    else:  # CIP
                        self.logger.warning(f"Mock CIP object '{tag_name}' not available")
                        tag_values[tag_name] = None

            return tag_values

        except Exception as e:
            self.logger.error(f"Mock failed to read tags: {e}")
            raise PLCTagReadError(f"Mock failed to read tags from Allen Bradley PLC: {e}")

    async def write_tag(self, tags: Union[Tuple[str, Any], List[Tuple[str, Any]]]) -> Dict[str, bool]:
        """
        Simulate writing values to Allen Bradley PLC tags.

        Args:
            tags: Single (tag_name, value) tuple or list of tuples

        Returns:
            Dictionary mapping tag names to write success status
        """
        if self.fail_write:
            raise PLCTagWriteError("Simulated tag write failure")

        if not self._is_connected:
            raise PLCCommunicationError(f"Mock not connected to Allen Bradley PLC at {self.ip_address}")

        try:
            if isinstance(tags, tuple):
                tag_list = [tags]
            else:
                tag_list = tags

            # Simulate write delay
            await asyncio.sleep(0.01 * len(tag_list))

            # Prepare results
            write_status = {}

            for tag_name, value in tag_list:
                if tag_name in self._tag_values:
                    # Validate value type based on tag type
                    expected_type = self._tag_types.get(tag_name, "UNKNOWN")

                    try:
                        # Type validation and conversion
                        if expected_type == "BOOL":
                            value = bool(value)
                        elif expected_type == "DINT":
                            value = int(value)
                        elif expected_type == "REAL":
                            value = float(value)

                        # Update stored value
                        self._tag_values[tag_name] = value
                        write_status[tag_name] = True

                        self.logger.debug(f"Mock wrote {tag_name} = {value}")

                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"Mock type conversion failed for {tag_name}: {e}")
                        write_status[tag_name] = False

                else:
                    # Tag doesn't exist
                    self.logger.warning(f"Mock tag '{tag_name}' not found for writing")
                    write_status[tag_name] = False

            return write_status

        except Exception as e:
            self.logger.error(f"Mock failed to write tags: {e}")
            raise PLCTagWriteError(f"Mock failed to write tags to Allen Bradley PLC: {e}")

    async def get_all_tags(self) -> List[str]:
        """
        Get list of all available mock tags.

        Returns:
            List of tag names
        """
        current_time = time.time()

        # Check if cache is still valid
        if self._tags_cache is not None and current_time - self._cache_timestamp < self._cache_ttl:
            return self._tags_cache

        if not self._is_connected:
            raise PLCCommunicationError(f"Mock not connected to Allen Bradley PLC at {self.ip_address}")

        # Return available tags based on driver type
        try:
            if self.driver_type == "LogixDriver":
                # Return Logix-style tags
                self._tags_cache = [
                    tag for tag in self._tag_values.keys() if not any(char in tag for char in [":", ".", "/"])
                ]
            elif self.driver_type == "SLCDriver":
                # Return SLC-style data file addresses
                self._tags_cache = [
                    tag
                    for tag in self._tag_values.keys()
                    if any(tag.startswith(prefix) for prefix in ["N", "B", "T", "C", "F", "R", "S", "I:", "O:"])
                ]
            else:  # CIPDriver
                # Return CIP object addresses and assembly objects
                self._tags_cache = [
                    tag
                    for tag in self._tag_values.keys()
                    if any(
                        tag.startswith(prefix)
                        for prefix in [
                            "Assembly:",
                            "Parameter:",
                            "Module:",
                            "Connection",
                            "0x",
                            "Identity",
                            "DeviceInfo",
                        ]
                    )
                ]

            self._cache_timestamp = current_time
            return self._tags_cache

        except Exception as e:
            self.logger.error(f"Mock failed to get tags: {e}")
            raise PLCTagError(f"Mock failed to get tags from Allen Bradley PLC: {e}")

    async def get_tag_info(self, tag_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a mock tag.

        Args:
            tag_name: Name of the tag

        Returns:
            Dictionary with tag information
        """
        if not self._is_connected:
            raise PLCCommunicationError(f"Mock not connected to Allen Bradley PLC at {self.ip_address}")

        try:
            if tag_name not in self._tag_values:
                raise PLCTagNotFoundError(f"Mock tag '{tag_name}' not found on Allen Bradley PLC")

            value = self._tag_values[tag_name]
            tag_type = self._tag_types.get(tag_name, "UNKNOWN")

            return {
                "name": tag_name,
                "type": tag_type,
                "value": value,
                "description": f"Mock {self.driver_type} tag: {tag_name}",
                "driver": self.driver_type,
                "size": len(str(value)) if isinstance(value, str) else 4,
            }

        except PLCTagNotFoundError:
            raise
        except Exception as e:
            self.logger.error(f"Mock failed to get tag info: {e}")
            raise PLCTagError(f"Mock failed to get tag info from Allen Bradley PLC: {e}")

    async def get_plc_info(self) -> Dict[str, Any]:
        """
        Get detailed information about the mock PLC.

        Returns:
            Dictionary with PLC information
        """
        if not self._is_connected:
            raise PLCCommunicationError(f"Mock not connected to Allen Bradley PLC at {self.ip_address}")

        try:
            base_info = {
                "name": self.plc_name,
                "ip_address": self.ip_address,
                "driver_type": self.driver_type,
                "plc_type": self.plc_type,
                "connected": self._is_connected,
                "mock": True,
            }

            # Add driver-specific info
            if self.driver_type == "LogixDriver":
                base_info.update(
                    {
                        "product_name": "Mock ControlLogix 5580",
                        "product_type": "Programmable Logic Controller",
                        "vendor": "Mock Allen Bradley",
                        "revision": "32.011",
                        "serial": f"MOCK{hash(self.plc_name) % 10000:04d}",
                        "program_name": "MockProgram",
                    }
                )
            elif self.driver_type == "SLCDriver":
                base_info.update(
                    {
                        "product_type": "Mock SLC 5/05 PLC",
                        "vendor": "Mock Allen Bradley",
                        "description": "Mock SLC500 series PLC",
                        "processor": "SLC 5/05",
                    }
                )
            elif self.driver_type == "CIPDriver":
                base_info.update(
                    {
                        "product_name": "Mock PowerFlex 755",
                        "product_type": "AC Drive",
                        "vendor": "Mock Allen Bradley",
                        "product_code": 55,
                        "revision": {"major": 1, "minor": 1},
                        "serial": f"MOCK{hash(self.ip_address) % 10000:04d}",
                        "status": b"\x20\x00",  # Mock status word
                    }
                )

            return base_info

        except Exception as e:
            self.logger.error(f"Mock failed to get PLC info: {e}")
            return {
                "name": self.plc_name,
                "ip_address": self.ip_address,
                "driver_type": self.driver_type,
                "plc_type": self.plc_type,
                "connected": False,
                "error": str(e),
                "mock": True,
            }

    @staticmethod
    def get_available_plcs() -> List[str]:
        """
        Discover available mock Allen Bradley PLCs.

        Returns:
            List of PLC identifiers in format "AllenBradley:IP:Type"
        """
        try:
            mock_plcs = []

            # Generate deterministic mock PLCs
            base_ips = ["192.168.1.100", "192.168.1.101", "192.168.1.102", "10.0.0.50", "10.0.0.51", "10.0.0.52"]

            for i, ip in enumerate(base_ips):
                if i % 3 == 0:
                    device_type = "Logix"
                elif i % 3 == 1:
                    device_type = "SLC"
                else:
                    device_type = "CIP"

                mock_plcs.append(f"AllenBradley:{ip}:{device_type}")

            return mock_plcs

        except Exception:
            return []

    @staticmethod
    def get_backend_info() -> Dict[str, Any]:
        """
        Get information about the mock Allen Bradley PLC backend.

        Returns:
            Dictionary with backend information
        """
        return {
            "name": "MockAllenBradley",
            "description": "Mock Allen Bradley PLC backend for testing without hardware",
            "sdk_name": "mock",
            "sdk_available": True,
            "mock": True,
            "drivers": [
                {
                    "name": "MockLogixDriver",
                    "description": "Mock ControlLogix/CompactLogix simulation",
                    "supported_models": ["Mock ControlLogix", "Mock CompactLogix"],
                    "capabilities": ["Tag simulation", "Type validation", "Error simulation"],
                    "fully_implemented": True,
                },
                {
                    "name": "MockSLCDriver",
                    "description": "Mock SLC500/MicroLogix simulation",
                    "supported_models": ["Mock SLC500", "Mock MicroLogix"],
                    "capabilities": ["Data file simulation", "Bit addressing", "Timer/Counter simulation"],
                    "fully_implemented": True,
                },
                {
                    "name": "MockCIPDriver",
                    "description": "Mock generic Ethernet/IP device simulation",
                    "supported_models": ["Mock PowerFlex", "Mock I/O Modules"],
                    "capabilities": ["CIP object simulation", "Assembly objects", "Parameter objects"],
                    "fully_implemented": True,
                },
            ],
            "features": [
                "Complete PLC simulation without hardware",
                "Realistic tag data with variation",
                "Multi-driver type support",
                "Error simulation capabilities",
                "Deterministic behavior for testing",
                "Type validation and conversion",
                "Connection state management",
                "Comprehensive logging",
            ],
        }
