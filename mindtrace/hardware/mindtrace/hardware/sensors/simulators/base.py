"""
Base sensor simulator backend interface.

This module defines the abstract interface that all sensor simulator backends must implement.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Union


class SensorSimulatorBackend(ABC):
    """
    Abstract base class for all sensor simulator backends.

    This interface abstracts different communication patterns for publishing:
    - MQTT: Publish messages to topics
    - HTTP: POST data to endpoints
    - Serial: Send data/commands to serial ports
    - Modbus: Write to registers
    """

    @abstractmethod
    async def connect(self) -> None:
        """
        Establish connection to the backend.

        Raises:
            ConnectionError: If connection fails
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close connection to the backend.

        Should be safe to call multiple times.
        """
        pass

    @abstractmethod
    async def publish_data(self, address: str, data: Union[Dict[str, Any], Any]) -> None:
        """
        Publish sensor data to the specified address.

        For different backends, 'address' means:
        - MQTT: topic name to publish to
        - HTTP: endpoint path to POST to
        - Serial: sensor command or data format
        - Modbus: register address to write to

        Args:
            address: Backend-specific address/identifier
            data: Data to publish (dict, primitive, or complex object)

        Raises:
            ConnectionError: If backend not connected
            TimeoutError: If publish operation times out
            ValueError: If address is invalid or data cannot be serialized
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if backend is currently connected.

        Returns:
            True if connected, False otherwise
        """
        pass
