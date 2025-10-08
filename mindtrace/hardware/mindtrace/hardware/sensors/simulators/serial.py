"""
Serial sensor simulator backend implementation (placeholder).

This module will implement the SensorSimulatorBackend interface for serial/USB communication.
Currently this is a placeholder that raises NotImplementedError.
"""

from typing import Any, Dict, Union

from .base import SensorSimulatorBackend


class SerialSensorSimulator(SensorSimulatorBackend):
    """
    Serial backend for sensor simulation (placeholder).

    This backend will connect to serial/USB ports and send sensor data commands.
    It implements a push-based pattern where we send sensor data to simulate
    physical sensor devices.

    Future implementation will:
    - Connect to serial ports (e.g., /dev/ttyUSB0, COM3)
    - Send sensor data in various formats (JSON, CSV, custom protocols)
    - Simulate sensor response patterns and timing
    - Handle communication protocols and handshaking
    """

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 5.0, **kwargs):
        """
        Initialize Serial simulator backend.

        Args:
            port: Serial port path (e.g., "/dev/ttyUSB0" or "COM3")
            baudrate: Serial communication baudrate
            timeout: Communication timeout in seconds
            **kwargs: Additional serial parameters (parity, stopbits, etc.)
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.kwargs = kwargs
        self._is_connected = False

    async def connect(self) -> None:
        """
        Open serial port connection.

        Raises:
            NotImplementedError: Serial simulator not yet implemented
        """
        raise NotImplementedError("Serial simulator backend not yet implemented")

    async def disconnect(self) -> None:
        """
        Close serial port connection.
        """
        self._is_connected = False

    async def publish_data(self, address: str, data: Union[Dict[str, Any], Any]) -> None:
        """
        Send sensor data via serial port.

        Args:
            address: Command type or data format identifier (e.g., "TEMP_DATA", "JSON_FORMAT")
            data: Data to send (will be formatted according to address)

        Raises:
            NotImplementedError: Serial simulator not yet implemented
        """
        raise NotImplementedError("Serial simulator backend not yet implemented")

    def is_connected(self) -> bool:
        """
        Check if serial port is open.

        Returns:
            Always False until implementation is complete
        """
        return False
