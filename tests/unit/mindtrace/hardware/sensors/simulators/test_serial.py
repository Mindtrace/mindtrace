"""
Unit tests for Serial sensor simulator backend.

Tests cover Serial simulator initialization, connection, publishing, and error scenarios.
Currently tests placeholder implementation that raises NotImplementedError.
"""

import pytest

from mindtrace.hardware.sensors.simulators.serial import SerialSensorSimulator


class TestSerialSensorSimulator:
    """Test cases for SerialSensorSimulator class."""

    def test_serial_simulator_initialization_basic(self):
        """Test basic Serial simulator initialization."""
        simulator = SerialSensorSimulator("/dev/ttyUSB0")

        assert simulator.port == "/dev/ttyUSB0"
        assert simulator.baudrate == 9600
        assert simulator.timeout == 5.0
        assert simulator.kwargs == {}
        assert not simulator.is_connected()

    def test_serial_simulator_initialization_full_config(self):
        """Test Serial simulator initialization with all parameters."""
        simulator = SerialSensorSimulator(
            "COM3",
            baudrate=115200,
            timeout=10.0,
            parity="E",
            stopbits=2,
        )

        assert simulator.port == "COM3"
        assert simulator.baudrate == 115200
        assert simulator.timeout == 10.0
        assert simulator.kwargs == {"parity": "E", "stopbits": 2}
        assert not simulator.is_connected()

    def test_serial_simulator_initialization_different_ports(self):
        """Test initialization with different port formats."""
        # Test Linux-style port
        simulator1 = SerialSensorSimulator("/dev/ttyUSB0")
        assert simulator1.port == "/dev/ttyUSB0"

        # Test Windows-style port
        simulator2 = SerialSensorSimulator("COM3")
        assert simulator2.port == "COM3"

        # Test custom port name
        simulator3 = SerialSensorSimulator("/dev/cu.usbserial-1420")
        assert simulator3.port == "/dev/cu.usbserial-1420"

    def test_serial_simulator_initialization_different_baudrates(self):
        """Test initialization with different baudrates."""
        # Test common baudrates
        simulator1 = SerialSensorSimulator("/dev/ttyUSB0", baudrate=9600)
        assert simulator1.baudrate == 9600

        simulator2 = SerialSensorSimulator("/dev/ttyUSB0", baudrate=115200)
        assert simulator2.baudrate == 115200

        simulator3 = SerialSensorSimulator("/dev/ttyUSB0", baudrate=57600)
        assert simulator3.baudrate == 57600

    def test_serial_simulator_initialization_kwargs(self):
        """Test that additional kwargs are properly stored."""
        extra_kwargs = {"parity": "N", "stopbits": 1, "bytesize": 8}
        simulator = SerialSensorSimulator("/dev/ttyUSB0", **extra_kwargs)

        assert simulator.kwargs == extra_kwargs

    @pytest.mark.asyncio
    async def test_connect_not_implemented(self):
        """Test that connect raises NotImplementedError."""
        simulator = SerialSensorSimulator("/dev/ttyUSB0")

        with pytest.raises(NotImplementedError, match="Serial simulator backend not yet implemented"):
            await simulator.connect()

    @pytest.mark.asyncio
    async def test_disconnect_sets_connected_false(self):
        """Test that disconnect sets _is_connected to False."""
        simulator = SerialSensorSimulator("/dev/ttyUSB0")

        # Manually set connected state
        simulator._is_connected = True
        assert simulator._is_connected is True

        # Disconnect should set it to False
        await simulator.disconnect()
        assert simulator._is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_safe_to_call_multiple_times(self):
        """Test that disconnect can be called multiple times safely."""
        simulator = SerialSensorSimulator("/dev/ttyUSB0")

        # Call disconnect multiple times
        await simulator.disconnect()
        await simulator.disconnect()
        await simulator.disconnect()

        # Should still be False
        assert simulator._is_connected is False

    @pytest.mark.asyncio
    async def test_publish_data_not_implemented(self):
        """Test that publish_data raises NotImplementedError."""
        simulator = SerialSensorSimulator("/dev/ttyUSB0")

        with pytest.raises(NotImplementedError, match="Serial simulator backend not yet implemented"):
            await simulator.publish_data("TEMP_DATA", {"temperature": 25.5})

    def test_is_connected_always_false(self):
        """Test that is_connected always returns False."""
        simulator = SerialSensorSimulator("/dev/ttyUSB0")

        # Should return False initially
        assert simulator.is_connected() is False

        # Even if we manually set _is_connected, the method should still return False
        # (though this tests the current implementation behavior)
        simulator._is_connected = True
        # Note: The current implementation returns False, so this tests that behavior
        assert simulator.is_connected() is False
