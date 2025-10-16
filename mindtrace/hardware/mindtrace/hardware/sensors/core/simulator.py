"""
SensorSimulator class for publishing sensor data.

This module implements the main SensorSimulator class that provides a simple,
unified interface for publishing sensor data to all simulator backends (MQTT, HTTP, Serial, etc.).
"""

import logging
from typing import Any, Dict, Union

from ..simulators.base import SensorSimulatorBackend

logger = logging.getLogger(__name__)


class SensorSimulator:
    """
    Unified sensor simulator interface.

    This class provides a simple, consistent API for publishing sensor data
    regardless of the underlying communication backend (MQTT, HTTP, Serial, etc.).

    The simulator abstracts different communication patterns:
    - MQTT: Publish messages to topics
    - HTTP: POST data to REST endpoints
    - Serial: Send data/commands to serial devices

    All backends are hidden behind the same connect/disconnect/publish interface.
    This is perfect for integration testing and sensor data simulation.
    """

    def __init__(self, simulator_id: str, backend: SensorSimulatorBackend, address: str):
        """
        Initialize SensorSimulator with a backend.

        Args:
            simulator_id: Unique identifier for this simulator
            backend: Backend implementation (MQTT, HTTP, Serial, etc.)
            address: Backend-specific address (topic, endpoint, command, etc.)

        Raises:
            ValueError: If simulator_id or address is empty
            TypeError: If backend is not a SensorSimulatorBackend instance
        """
        if not simulator_id or not isinstance(simulator_id, str):
            raise ValueError("simulator_id must be a non-empty string")

        if not address or not isinstance(address, str):
            raise ValueError("address must be a non-empty string")

        if not isinstance(backend, SensorSimulatorBackend):
            raise TypeError("backend must be a SensorSimulatorBackend instance")

        self._simulator_id = simulator_id.strip()
        self._backend = backend
        self._address = address.strip()

        logger.debug(f"Created SensorSimulator {self._simulator_id} with backend {type(self._backend).__name__}")

    @property
    def simulator_id(self) -> str:
        """Get the simulator ID."""
        return self._simulator_id

    @property
    def is_connected(self) -> bool:
        """
        Check if simulator backend is connected.

        Returns:
            True if backend is connected, False otherwise
        """
        return self._backend.is_connected()

    async def connect(self) -> None:
        """
        Connect the simulator backend.

        This establishes the connection to the underlying communication system
        (MQTT broker, HTTP server, serial port, etc.).

        Raises:
            ConnectionError: If connection fails
        """
        try:
            await self._backend.connect()
            logger.info(f"Simulator {self._simulator_id} connected successfully")
        except Exception as e:
            logger.error(f"Failed to connect simulator {self._simulator_id}: {e}")
            raise ConnectionError(f"Failed to connect simulator {self._simulator_id}: {e}") from e

    async def disconnect(self) -> None:
        """
        Disconnect the simulator backend.

        This closes the connection to the underlying communication system.
        Safe to call multiple times.
        """
        try:
            await self._backend.disconnect()
            logger.info(f"Simulator {self._simulator_id} disconnected")
        except Exception as e:
            logger.warning(f"Error disconnecting simulator {self._simulator_id}: {e}")

    async def publish(self, data: Union[Dict[str, Any], Any]) -> None:
        """
        Publish sensor data.

        This method abstracts different communication patterns:
        - MQTT: Publishes message to topic
        - HTTP: Makes POST request to endpoint
        - Serial: Sends data to serial port

        Args:
            data: Data to publish (dict, primitive, or complex object)

        Raises:
            ConnectionError: If backend is not connected
            TimeoutError: If publish operation times out
            ValueError: If address is invalid or data cannot be serialized
        """
        if not self.is_connected:
            raise ConnectionError(f"Simulator {self._simulator_id} is not connected")

        try:
            await self._backend.publish_data(self._address, data)
            logger.debug(f"Simulator {self._simulator_id} published data: {data}")
        except Exception as e:
            logger.error(f"Failed to publish from simulator {self._simulator_id}: {e}")
            raise

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

    def __repr__(self) -> str:
        """String representation of simulator."""
        backend_name = type(self._backend).__name__
        connected = "connected" if self.is_connected else "disconnected"
        return f"SensorSimulator(id='{self._simulator_id}', backend={backend_name}, {connected})"
