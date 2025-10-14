"""
MQTT sensor backend implementation.

This module implements the SensorBackend interface for MQTT communication.
It uses a push-based model where messages are cached when received.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

try:
    import aiomqtt
except ImportError:
    aiomqtt = None

from .base import SensorBackend

logger = logging.getLogger(__name__)


class MQTTSensorBackend(SensorBackend):
    """
    MQTT backend for sensor communication.

    This backend connects to an MQTT broker and subscribes to topics.
    Messages are cached when received, and read_data() returns the latest cached message.

    This implements a push-based pattern where data comes to us, unlike HTTP/Serial
    which are pull-based where we request data on-demand.
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
        Initialize MQTT backend.

        Args:
            broker_url: MQTT broker URL (e.g., "mqtt://localhost:1883")
            identifier: MQTT client identifier (auto-generated if None)
            username: MQTT username (optional)
            password: MQTT password (optional)
            keepalive: MQTT keepalive interval in seconds
            **kwargs: Additional MQTT client parameters
        """
        if aiomqtt is None:
            raise ImportError("aiomqtt is required for MQTT backend. Install with: pip install aiomqtt")

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
        self._message_cache: Dict[str, Dict[str, Any]] = {}
        self._subscribed_topics: set[str] = set()
        self._listen_task: Optional[asyncio.Task] = None

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

            # Start message listening task
            self._listen_task = asyncio.create_task(self._message_listener())

            logger.info(f"Connected to MQTT broker at {self.hostname}:{self.port}")

        except Exception as e:
            self._is_connected = False
            self._client = None
            raise ConnectionError(f"Failed to connect to MQTT broker: {e}") from e

    async def disconnect(self) -> None:
        """
        Disconnect from MQTT broker.
        """
        if not self._is_connected:
            return

        try:
            # Cancel message listener
            if self._listen_task and not self._listen_task.done():
                self._listen_task.cancel()
                try:
                    await self._listen_task
                except asyncio.CancelledError:
                    pass

            # Disconnect client
            if self._client:
                await self._client.__aexit__(None, None, None)
                self._client = None

            self._is_connected = False
            self._subscribed_topics.clear()
            self._message_cache.clear()

            logger.info("Disconnected from MQTT broker")

        except Exception as e:
            logger.warning(f"Error during MQTT disconnect: {e}")
        finally:
            self._is_connected = False
            self._client = None

    async def read_data(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Read cached data from MQTT topic.

        For MQTT, the address is the topic name. If we haven't subscribed to this
        topic yet, we'll subscribe and wait briefly for a message.

        Args:
            address: MQTT topic name

        Returns:
            Latest cached message for the topic, or None if no data available

        Raises:
            ConnectionError: If not connected to broker
            ValueError: If topic name is invalid
        """
        if not self._is_connected:
            raise ConnectionError("Not connected to MQTT broker")

        if not address or not isinstance(address, str):
            raise ValueError("Topic name must be a non-empty string")

        topic = address.strip()
        if not topic:
            raise ValueError("Topic name cannot be empty")

        # Subscribe to topic if not already subscribed
        if topic not in self._subscribed_topics:
            await self._subscribe_to_topic(topic)

        # Return cached message if available
        return self._message_cache.get(topic)

    def is_connected(self) -> bool:
        """
        Check if connected to MQTT broker.

        Returns:
            True if connected, False otherwise
        """
        return self._is_connected

    async def _subscribe_to_topic(self, topic: str) -> None:
        """
        Subscribe to an MQTT topic.

        Args:
            topic: Topic to subscribe to
        """
        if not self._client or not self._is_connected:
            raise ConnectionError("Not connected to MQTT broker")

        try:
            await self._client.subscribe(topic)
            self._subscribed_topics.add(topic)
            logger.debug(f"Subscribed to topic: {topic}")
        except Exception as e:
            logger.error(f"Failed to subscribe to topic {topic}: {e}")
            raise

    async def _message_listener(self) -> None:
        """
        Background task to listen for MQTT messages and cache them.
        """
        if not self._client:
            return

        try:
            async for message in self._client.messages:
                topic = str(message.topic)
                payload = message.payload

                try:
                    # Try to parse as JSON first
                    if isinstance(payload, (bytes, bytearray)):
                        payload_str = payload.decode("utf-8")
                    else:
                        payload_str = str(payload)

                    try:
                        data = json.loads(payload_str)
                    except json.JSONDecodeError:
                        # If not JSON, store as raw string
                        data = {"raw": payload_str}

                    # Cache the message
                    self._message_cache[topic] = data
                    logger.debug(f"Cached message for topic {topic}: {data}")

                except Exception as e:
                    logger.warning(f"Error processing message from topic {topic}: {e}")
                    # Store raw payload on error
                    self._message_cache[topic] = {"raw": str(payload), "error": str(e)}

        except asyncio.CancelledError:
            logger.debug("MQTT message listener cancelled")
        except Exception as e:
            logger.error(f"MQTT message listener error: {e}")
            # Connection lost, mark as disconnected
            self._is_connected = False
