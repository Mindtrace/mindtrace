"""
Serial sensor backend implementation (placeholder).

This module will implement the SensorBackend interface for serial/USB communication.
Currently this is a placeholder that raises NotImplementedError.
"""

from typing import Any, Dict, Optional

from .base import SensorBackend


class SerialSensorBackend(SensorBackend):
    """
    Serial backend for sensor communication (placeholder).

    This backend will connect to sensors via serial/USB ports and send commands
    to read sensor data. It implements a pull-based pattern where we send commands
    and read responses on-demand.

    Future implementation will:
    - Connect to serial ports (e.g., /dev/ttyUSB0, COM3)
    - Send sensor commands and read responses
    - Parse sensor data (JSON, CSV, or custom formats)
    - Handle timeouts and communication errors
    """

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 5.0, **kwargs):
        """
        Initialize Serial backend.

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
            NotImplementedError: Serial backend not yet implemented
        """
        raise NotImplementedError("Serial backend not yet implemented")

    async def disconnect(self) -> None:
        """
        Close serial port connection.
        """
        self._is_connected = False

    async def read_data(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Send command to sensor and read response.

        Args:
            address: Sensor command (e.g., "READ_TEMP", "GET_HUMIDITY")

        Returns:
            Parsed sensor response data, or None if command fails

        Raises:
            NotImplementedError: Serial backend not yet implemented
        """
        raise NotImplementedError("Serial backend not yet implemented")

    def is_connected(self) -> bool:
        """
        Check if serial port is open.

        Returns:
            Always False until implementation is complete
        """
        return False
