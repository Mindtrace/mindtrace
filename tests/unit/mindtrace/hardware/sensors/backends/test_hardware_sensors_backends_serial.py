"""
Unit tests for Serial sensor backend.

Tests cover Serial backend initialization, connection, reading, and error scenarios.
Currently tests placeholder implementation that raises NotImplementedError.
"""

import pytest

from mindtrace.hardware.sensors.backends.serial import SerialSensorBackend


class TestSerialSensorBackend:
    """Test cases for SerialSensorBackend class."""

    def test_serial_backend_initialization_basic(self):
        """Test basic Serial backend initialization."""
        backend = SerialSensorBackend("/dev/ttyUSB0")

        assert backend.port == "/dev/ttyUSB0"
        assert backend.baudrate == 9600
        assert backend.timeout == 5.0
        assert backend.kwargs == {}
        assert not backend.is_connected()

    def test_serial_backend_initialization_full_config(self):
        """Test Serial backend initialization with all parameters."""
        backend = SerialSensorBackend(
            "COM3",
            baudrate=115200,
            timeout=10.0,
            parity="E",
            stopbits=2,
        )

        assert backend.port == "COM3"
        assert backend.baudrate == 115200
        assert backend.timeout == 10.0
        assert backend.kwargs == {"parity": "E", "stopbits": 2}
        assert not backend.is_connected()

    def test_serial_backend_initialization_different_ports(self):
        """Test initialization with different port formats."""
        # Test Linux-style port
        backend1 = SerialSensorBackend("/dev/ttyUSB0")
        assert backend1.port == "/dev/ttyUSB0"

        # Test Windows-style port
        backend2 = SerialSensorBackend("COM3")
        assert backend2.port == "COM3"

        # Test custom port name
        backend3 = SerialSensorBackend("/dev/cu.usbserial-1420")
        assert backend3.port == "/dev/cu.usbserial-1420"

    def test_serial_backend_initialization_different_baudrates(self):
        """Test initialization with different baudrates."""
        # Test common baudrates
        backend1 = SerialSensorBackend("/dev/ttyUSB0", baudrate=9600)
        assert backend1.baudrate == 9600

        backend2 = SerialSensorBackend("/dev/ttyUSB0", baudrate=115200)
        assert backend2.baudrate == 115200

        backend3 = SerialSensorBackend("/dev/ttyUSB0", baudrate=57600)
        assert backend3.baudrate == 57600

    def test_serial_backend_initialization_kwargs(self):
        """Test that additional kwargs are properly stored."""
        extra_kwargs = {"parity": "N", "stopbits": 1, "bytesize": 8}
        backend = SerialSensorBackend("/dev/ttyUSB0", **extra_kwargs)

        assert backend.kwargs == extra_kwargs

    @pytest.mark.asyncio
    async def test_connect_not_implemented(self):
        """Test that connect raises NotImplementedError."""
        backend = SerialSensorBackend("/dev/ttyUSB0")

        with pytest.raises(NotImplementedError, match="Serial backend not yet implemented"):
            await backend.connect()

    @pytest.mark.asyncio
    async def test_disconnect_sets_connected_false(self):
        """Test that disconnect sets _is_connected to False."""
        backend = SerialSensorBackend("/dev/ttyUSB0")

        # Manually set connected state
        backend._is_connected = True
        assert backend._is_connected is True

        # Disconnect should set it to False
        await backend.disconnect()
        assert backend._is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_safe_to_call_multiple_times(self):
        """Test that disconnect can be called multiple times safely."""
        backend = SerialSensorBackend("/dev/ttyUSB0")

        # Call disconnect multiple times
        await backend.disconnect()
        await backend.disconnect()
        await backend.disconnect()

        # Should still be False
        assert backend._is_connected is False

    @pytest.mark.asyncio
    async def test_read_data_not_implemented(self):
        """Test that read_data raises NotImplementedError."""
        backend = SerialSensorBackend("/dev/ttyUSB0")

        with pytest.raises(NotImplementedError, match="Serial backend not yet implemented"):
            await backend.read_data("READ_TEMP")

    def test_is_connected_always_false(self):
        """Test that is_connected always returns False."""
        backend = SerialSensorBackend("/dev/ttyUSB0")

        # Should return False initially
        assert backend.is_connected() is False

        # Even if we manually set _is_connected, the method should still return False
        # (though this tests the current implementation behavior)
        backend._is_connected = True
        # Note: The current implementation returns False, so this tests that behavior
        assert backend.is_connected() is False
