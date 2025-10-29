"""
HTTP sensor backend implementation (placeholder).

This module will implement the SensorBackend interface for HTTP/REST API communication.
Currently this is a placeholder that raises NotImplementedError.
"""

from typing import Any, Dict, Optional

from .base import SensorBackend


class HTTPSensorBackend(SensorBackend):
    """
    HTTP backend for sensor communication (placeholder).

    This backend will connect to REST APIs and make HTTP GET requests to read sensor data.
    It implements a pull-based pattern where we request data on-demand.

    Future implementation will:
    - Make HTTP GET requests to base_url + endpoint
    - Handle authentication headers
    - Parse JSON responses
    - Implement timeout and retry logic
    """

    def __init__(self, base_url: str, auth_token: Optional[str] = None, timeout: float = 30.0, **kwargs):
        """
        Initialize HTTP backend.

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
            NotImplementedError: HTTP backend not yet implemented
        """
        raise NotImplementedError("HTTP backend not yet implemented")

    async def disconnect(self) -> None:
        """
        Close HTTP client connection.
        """
        self._is_connected = False

    async def read_data(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Read sensor data via HTTP GET request.

        Args:
            address: Endpoint path (e.g., "/sensors/temperature/current")

        Returns:
            JSON response data, or None if request fails

        Raises:
            NotImplementedError: HTTP backend not yet implemented
        """
        raise NotImplementedError("HTTP backend not yet implemented")

    def is_connected(self) -> bool:
        """
        Check if HTTP client is ready.

        Returns:
            Always False until implementation is complete
        """
        return False
