"""
MQTT sensor simulator backend implementation.

This module implements the SensorSimulatorBackend interface for MQTT communication.
It publishes sensor data to MQTT topics for testing and integration purposes.
"""

import json
import logging
from typing import Any, Dict, Optional, Union
from urllib.parse import urlparse

try:
    import aiomqtt
except ImportError:
    aiomqtt = None

from .base import SensorSimulatorBackend

logger = logging.getLogger(__name__)


class MQTTSensorSimulator(SensorSimulatorBackend):
    """
    MQTT backend for sensor simulation.

    This backend connects to an MQTT broker and publishes sensor data to topics.
    It's designed for testing and integration scenarios where you need to simulate
    sensor data streams that can be consumed by AsyncSensor instances.
    """

    def __init__(
        self,
        broker_url: str,
        identifier: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        keepalive: int = 60,
        **kwargs,
    ):
        """
        Initialize MQTT simulator backend.

        Args:
            broker_url: MQTT broker URL (e.g., "mqtt://localhost:1883")
            identifier: MQTT client identifier (auto-generated if None)
            username: MQTT username (optional)
            password: MQTT password (optional)
            keepalive: MQTT keepalive interval in seconds
            **kwargs: Additional MQTT client parameters
        """
        if aiomqtt is None:
            raise ImportError("aiomqtt is required for MQTT simulator. Install with: pip install aiomqtt")

        self.broker_url = broker_url
        self.identifier = identifier
        self.username = username
        self.password = password
        self.keepalive = keepalive
        self.kwargs = kwargs

        # Parse broker URL
        parsed = urlparse(broker_url)
        self.hostname = parsed.hostname or "localhost"
        self.port = parsed.port or 1883

        # Connection state
        self._client: Optional[aiomqtt.Client] = None
        self._is_connected = False

    async def connect(self) -> None:
        """
        Connect to MQTT broker.

        Raises:
            ConnectionError: If connection to broker fails
        """
        if self._is_connected:
            return

        try:
            # Create MQTT client
            self._client = aiomqtt.Client(
                hostname=self.hostname,
                port=self.port,
                identifier=self.identifier,
                username=self.username,
                password=self.password,
                keepalive=self.keepalive,
                **self.kwargs,
            )

            # Connect to broker
            await self._client.__aenter__()
            self._is_connected = True

            logger.info(f"MQTT simulator connected to broker at {self.hostname}:{self.port}")

        except Exception as e:
            self._is_connected = False
            self._client = None
            raise ConnectionError(f"Failed to connect MQTT simulator to broker: {e}") from e

    async def disconnect(self) -> None:
        """
        Disconnect from MQTT broker.
        """
        if not self._is_connected:
            return

        try:
            # Disconnect client
            if self._client:
                await self._client.__aexit__(None, None, None)
                self._client = None

            self._is_connected = False

            logger.info("MQTT simulator disconnected from broker")

        except Exception as e:
            logger.warning(f"Error during MQTT simulator disconnect: {e}")
        finally:
            self._is_connected = False
            self._client = None

    async def publish_data(self, address: str, data: Union[Dict[str, Any], Any]) -> None:
        """
        Publish sensor data to MQTT topic.

        Args:
            address: MQTT topic name to publish to
            data: Data to publish (will be JSON-encoded if dict/list)

        Raises:
            ConnectionError: If not connected to broker
            ValueError: If topic name is invalid
            TimeoutError: If publish operation times out
        """
        if not self._is_connected:
            raise ConnectionError("MQTT simulator not connected to broker")

        if not address or not isinstance(address, str):
            raise ValueError("Topic name must be a non-empty string")

        topic = address.strip()
        if not topic:
            raise ValueError("Topic name cannot be empty")

        if not self._client:
            raise ConnectionError("MQTT client not initialized")

        try:
            # Prepare payload
            if isinstance(data, (dict, list)):
                # JSON-encode structured data
                payload = json.dumps(data, separators=(",", ":"))
            elif isinstance(data, (int, float, bool)):
                # Convert primitives to string
                payload = str(data)
            elif isinstance(data, str):
                # Use string as-is
                payload = data
            else:
                # Try to JSON-encode other types
                try:
                    payload = json.dumps(data, separators=(",", ":"))
                except (TypeError, ValueError):
                    # Fallback to string conversion
                    payload = str(data)

            # Publish to topic
            await self._client.publish(topic, payload)

            logger.debug(f"Published to topic {topic}: {payload}")

        except Exception as e:
            logger.error(f"Failed to publish to topic {topic}: {e}")
            raise

    def is_connected(self) -> bool:
        """
        Check if connected to MQTT broker.

        Returns:
            True if connected, False otherwise
        """
        return self._is_connected
