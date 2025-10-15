"""
Simple sensor manager implementation.

This module implements a minimal SensorManager that can register/remove sensors
and perform bulk read operations across multiple sensors.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from .factory import create_backend
from .sensor import AsyncSensor

logger = logging.getLogger(__name__)


class SensorManager:
    """
    Simple manager for multiple sensors.

    This manager provides basic functionality:
    - Register sensors with different backends
    - Remove sensors by ID
    - Read from all sensors in parallel

    The manager keeps sensors in a registry and delegates operations to them.
    """

    def __init__(self):
        """Initialize sensor manager."""
        self._sensors: Dict[str, AsyncSensor] = {}
        logger.debug("Created SensorManager")

    def register_sensor(
        self, sensor_id: str, backend_type: str, connection_params: Dict[str, Any], address: str
    ) -> AsyncSensor:
        """
        Register a new sensor with the manager.

        Args:
            sensor_id: Unique identifier for the sensor
            backend_type: Type of backend ("mqtt", "http", "serial")
            connection_params: Backend-specific connection parameters
            address: Backend-specific address (topic, endpoint, command)

        Returns:
            The created AsyncSensor instance

        Raises:
            ValueError: If sensor_id already exists or parameters are invalid

        Examples:
            # Register MQTT sensor
            sensor = manager.register_sensor(
                "temp001",
                "mqtt",
                {"broker_url": "mqtt://localhost:1883"},
                "sensors/temperature"
            )

            # Register HTTP sensor
            sensor = manager.register_sensor(
                "temp002",
                "http",
                {"base_url": "http://api.sensors.com"},
                "/sensors/temperature"
            )
        """
        if not sensor_id or not isinstance(sensor_id, str):
            raise ValueError("sensor_id must be a non-empty string")

        sensor_id = sensor_id.strip()
        if sensor_id in self._sensors:
            raise ValueError(f"Sensor '{sensor_id}' is already registered")

        try:
            # Create backend using factory
            backend = create_backend(backend_type, **connection_params)

            # Create sensor
            sensor = AsyncSensor(sensor_id, backend, address)

            # Register in manager
            self._sensors[sensor_id] = sensor

            logger.info(f"Registered sensor '{sensor_id}' with {backend_type} backend")
            return sensor

        except Exception as e:
            logger.error(f"Failed to register sensor '{sensor_id}': {e}")
            raise

    def remove_sensor(self, sensor_id: str) -> None:
        """
        Remove a sensor from the manager.

        Args:
            sensor_id: ID of sensor to remove

        Raises:
            ValueError: If sensor_id doesn't exist
        """
        if sensor_id not in self._sensors:
            raise ValueError(f"Sensor '{sensor_id}' is not registered")

        sensor = self._sensors.pop(sensor_id)
        logger.info(f"Removed sensor '{sensor.sensor_id}'")

        # Note: We don't auto-disconnect here to avoid blocking.
        # User should disconnect manually if needed.

    def get_sensor(self, sensor_id: str) -> Optional[AsyncSensor]:
        """
        Get a sensor by ID.

        Args:
            sensor_id: ID of sensor to get

        Returns:
            AsyncSensor instance or None if not found
        """
        return self._sensors.get(sensor_id)

    def list_sensors(self) -> List[str]:
        """
        Get list of all registered sensor IDs.

        Returns:
            List of sensor IDs
        """
        return list(self._sensors.keys())

    @property
    def sensor_count(self) -> int:
        """Get number of registered sensors."""
        return len(self._sensors)

    async def connect_all(self) -> Dict[str, bool]:
        """
        Connect all registered sensors.

        Returns:
            Dictionary mapping sensor IDs to connection success (True/False)
        """
        if not self._sensors:
            return {}

        logger.info(f"Connecting {len(self._sensors)} sensors...")

        async def connect_sensor(sensor_id: str, sensor: AsyncSensor) -> tuple[str, bool]:
            try:
                await sensor.connect()
                logger.debug(f"Connected sensor '{sensor_id}'")
                return sensor_id, True
            except Exception as e:
                logger.warning(f"Failed to connect sensor '{sensor_id}': {e}")
                return sensor_id, False

        # Connect all sensors in parallel
        tasks = [connect_sensor(sensor_id, sensor) for sensor_id, sensor in self._sensors.items()]

        results = await asyncio.gather(*tasks)
        return dict(results)

    async def disconnect_all(self) -> None:
        """
        Disconnect all registered sensors.
        """
        if not self._sensors:
            return

        logger.info(f"Disconnecting {len(self._sensors)} sensors...")

        async def disconnect_sensor(sensor: AsyncSensor) -> None:
            try:
                await sensor.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting sensor: {e}")

        # Disconnect all sensors in parallel
        tasks = [disconnect_sensor(sensor) for sensor in self._sensors.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def read_all(self) -> Dict[str, Dict[str, Any]]:
        """
        Read data from all registered sensors.

        Returns:
            Dictionary mapping sensor IDs to their data (or error info)

        Examples:
            {
                "temp001": {"temperature": 23.5, "unit": "C"},
                "temp002": {"error": "Not connected"},
                "humid001": {"humidity": 65.2, "unit": "%"}
            }
        """
        if not self._sensors:
            return {}

        logger.debug(f"Reading from {len(self._sensors)} sensors...")

        async def read_sensor(sensor_id: str, sensor: AsyncSensor) -> tuple[str, Dict[str, Any]]:
            try:
                data = await sensor.read()
                if data is not None:
                    return sensor_id, data
                else:
                    return sensor_id, {"error": "No data available"}
            except Exception as e:
                logger.warning(f"Failed to read from sensor '{sensor_id}': {e}")
                return sensor_id, {"error": str(e)}

        # Read from all sensors in parallel
        tasks = [read_sensor(sensor_id, sensor) for sensor_id, sensor in self._sensors.items()]

        results = await asyncio.gather(*tasks)
        return dict(results)

    def __len__(self) -> int:
        """Number of registered sensors."""
        return len(self._sensors)

    def __contains__(self, sensor_id: str) -> bool:
        """Check if sensor ID is registered."""
        return sensor_id in self._sensors

    def __repr__(self) -> str:
        """String representation."""
        return f"SensorManager(sensors={len(self._sensors)})"
