"""
HTTP sensor simulator backend implementation (placeholder).

This module will implement the SensorSimulatorBackend interface for HTTP/REST API communication.
Currently this is a placeholder that raises NotImplementedError.
"""

from typing import Any, Dict, Optional, Union

from .base import SensorSimulatorBackend


class HTTPSensorSimulator(SensorSimulatorBackend):
    """
    HTTP backend for sensor simulation (placeholder).

    This backend will connect to REST APIs and make HTTP POST requests to publish sensor data.
    It implements a push-based pattern where we send data to endpoints.

    Future implementation will:
    - Make HTTP POST requests to base_url + endpoint
    - Handle authentication headers
    - Send JSON payloads
    - Implement timeout and retry logic
    """

    def __init__(self, base_url: str, auth_token: Optional[str] = None, timeout: float = 30.0, **kwargs):
        """
        Initialize HTTP simulator backend.

        Args:
            base_url: Base URL for HTTP requests (e.g., "http://api.sensors.com")
            auth_token: Optional authentication token
            timeout: Request timeout in seconds
            **kwargs: Additional HTTP client parameters
        """
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout
        self.kwargs = kwargs
        self._is_connected = False

    async def connect(self) -> None:
        """
        Establish HTTP client connection.

        Raises:
            NotImplementedError: HTTP simulator not yet implemented
        """
        raise NotImplementedError("HTTP simulator backend not yet implemented")

    async def disconnect(self) -> None:
        """
        Close HTTP client connection.
        """
        self._is_connected = False

    async def publish_data(self, address: str, data: Union[Dict[str, Any], Any]) -> None:
        """
        Publish sensor data via HTTP POST request.

        Args:
            address: Endpoint path (e.g., "/sensors/temperature/data")
            data: Data to publish (will be JSON-encoded)

        Raises:
            NotImplementedError: HTTP simulator not yet implemented
        """
        raise NotImplementedError("HTTP simulator backend not yet implemented")

    def is_connected(self) -> bool:
        """
        Check if HTTP client is ready.

        Returns:
            Always False until implementation is complete
        """
        return False
