"""
Unified AsyncSensor class.

This module implements the main AsyncSensor class that provides a simple,
unified interface for all sensor backends (MQTT, HTTP, Serial, etc.).
"""

import logging
from typing import Any, Dict, Optional

from ..backends.base import SensorBackend

logger = logging.getLogger(__name__)


class AsyncSensor:
    """
    Unified async sensor interface.

    This class provides a simple, consistent API for reading sensor data
    regardless of the underlying communication backend (MQTT, HTTP, Serial, etc.).

    The sensor abstracts different communication patterns:
    - MQTT: Push-based (messages are cached when received)
    - HTTP: Pull-based (requests made on-demand)
    - Serial: Pull-based (commands sent on-demand)

    All backends are hidden behind the same connect/disconnect/read interface.
    """

    def __init__(self, sensor_id: str, backend: SensorBackend, address: str):
        """
        Initialize AsyncSensor with a backend.

        Args:
            sensor_id: Unique identifier for this sensor
            backend: Backend implementation (MQTT, HTTP, Serial, etc.)
            address: Backend-specific address (topic, endpoint, command, etc.)

        Raises:
            ValueError: If sensor_id or address is empty
            TypeError: If backend is not a SensorBackend instance
        """
        if not sensor_id or not isinstance(sensor_id, str):
            raise ValueError("sensor_id must be a non-empty string")

        if not address or not isinstance(address, str):
            raise ValueError("address must be a non-empty string")

        if not isinstance(backend, SensorBackend):
            raise TypeError("backend must be a SensorBackend instance")

        self._sensor_id = sensor_id.strip()
        self._backend = backend
        self._address = address.strip()

        logger.debug(f"Created AsyncSensor {self._sensor_id} with backend {type(self._backend).__name__}")

    @property
    def sensor_id(self) -> str:
        """Get the sensor ID."""
        return self._sensor_id

    @property
    def is_connected(self) -> bool:
        """
        Check if sensor backend is connected.

        Returns:
            True if backend is connected, False otherwise
        """
        return self._backend.is_connected()

    async def connect(self) -> None:
        """
        Connect the sensor backend.

        This establishes the connection to the underlying communication system
        (MQTT broker, HTTP server, serial port, etc.).

        Raises:
            ConnectionError: If connection fails
        """
        try:
            await self._backend.connect()
            logger.info(f"Sensor {self._sensor_id} connected successfully")
        except Exception as e:
            logger.error(f"Failed to connect sensor {self._sensor_id}: {e}")
            raise ConnectionError(f"Failed to connect sensor {self._sensor_id}: {e}") from e

    async def disconnect(self) -> None:
        """
        Disconnect the sensor backend.

        This closes the connection to the underlying communication system.
        Safe to call multiple times.
        """
        try:
            await self._backend.disconnect()
            logger.info(f"Sensor {self._sensor_id} disconnected")
        except Exception as e:
            logger.warning(f"Error disconnecting sensor {self._sensor_id}: {e}")

    async def read(self) -> Optional[Dict[str, Any]]:
        """
        Read sensor data.

        This method abstracts different communication patterns:
        - MQTT: Returns cached message from topic
        - HTTP: Makes GET request to endpoint
        - Serial: Sends command and reads response

        Returns:
            Dictionary with sensor data, or None if no data available

        Raises:
            ConnectionError: If backend is not connected
            TimeoutError: If read operation times out
            ValueError: If address is invalid
        """
        if not self.is_connected:
            raise ConnectionError(f"Sensor {self._sensor_id} is not connected")

        try:
            data = await self._backend.read_data(self._address)
            if data is not None:
                logger.debug(f"Sensor {self._sensor_id} read data: {data}")
            else:
                logger.debug(f"Sensor {self._sensor_id} read no data")
            return data
        except Exception as e:
            logger.error(f"Failed to read from sensor {self._sensor_id}: {e}")
            raise

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

    def __repr__(self) -> str:
        """String representation of sensor."""
        backend_name = type(self._backend).__name__
        connected = "connected" if self.is_connected else "disconnected"
        return f"AsyncSensor(id='{self._sensor_id}', backend={backend_name}, {connected})"
