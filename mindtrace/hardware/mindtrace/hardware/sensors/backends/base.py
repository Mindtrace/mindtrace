"""
Base sensor backend interface.

This module defines the abstract interface that all sensor backends must implement.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class SensorBackend(ABC):
    """
    Abstract base class for all sensor backends.

    This interface abstracts different communication patterns:
    - MQTT: Push-based (subscribe to topics, cache messages)
    - HTTP: Pull-based (make requests on-demand)
    - Serial: Pull-based (send commands, read responses)
    - Modbus: Pull-based (read registers)
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
    async def read_data(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Read sensor data from the specified address.

        For different backends, 'address' means:
        - MQTT: topic name (returns cached message)
        - HTTP: endpoint path (makes GET request)
        - Serial: sensor command (send command, read response)
        - Modbus: register address (read holding registers)

        Args:
            address: Backend-specific address/identifier

        Returns:
            Dictionary with sensor data, or None if no data available

        Raises:
            ConnectionError: If backend not connected
            TimeoutError: If read operation times out
            ValueError: If address is invalid
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
