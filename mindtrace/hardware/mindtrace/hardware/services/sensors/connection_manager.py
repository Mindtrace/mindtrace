"""Connection manager for typed sensor service client access."""

from typing import Any, Dict, Optional

from pydantic import BaseModel

from mindtrace.services import ConnectionManager

from .models import (
    SensorConnectionRequest,
    SensorConnectionResponse,
    SensorDataRequest,
    SensorDataResponse,
    SensorListRequest,
    SensorListResponse,
    SensorStatusRequest,
    SensorStatusResponse,
)


class SensorConnectionManager(ConnectionManager):
    """Strongly-typed connection manager for sensor service operations."""

    async def call_endpoint(self, endpoint: str, request: BaseModel) -> Dict[str, Any]:
        raise NotImplementedError

    async def connect_sensor(
        self, sensor_id: str, backend_type: str, config: Dict[str, Any], address: str
    ) -> SensorConnectionResponse:
        """Connect to a sensor with specified configuration.

        Args:
            sensor_id: Unique identifier for the sensor
            backend_type: Backend type (mqtt, http, serial)
            config: Backend-specific configuration
            address: Sensor address (topic, endpoint, or port)

        Returns:
            Response indicating success/failure of connection
        """
        request = SensorConnectionRequest(
            sensor_id=sensor_id, backend_type=backend_type, config=config, address=address
        )

        response = await self.call_endpoint("connect_sensor", request)
        return SensorConnectionResponse(**response)

    async def disconnect_sensor(self, sensor_id: str) -> SensorConnectionResponse:
        """Disconnect from a connected sensor.

        Args:
            sensor_id: Unique identifier for the sensor to disconnect

        Returns:
            Response indicating success/failure of disconnection
        """
        request = SensorStatusRequest(sensor_id=sensor_id)

        response = await self.call_endpoint("disconnect_sensor", request)
        return SensorConnectionResponse(**response)

    async def read_sensor_data(self, sensor_id: str, timeout: Optional[float] = None) -> SensorDataResponse:
        """Read data from a connected sensor.

        Args:
            sensor_id: Unique identifier for the sensor
            timeout: Optional read timeout in seconds

        Returns:
            Response containing sensor data or error information
        """
        request = SensorDataRequest(sensor_id=sensor_id, timeout=timeout)

        response = await self.call_endpoint("read_sensor_data", request)
        return SensorDataResponse(**response)

    async def get_sensor_status(self, sensor_id: str) -> SensorStatusResponse:
        """Get status information for a sensor.

        Args:
            sensor_id: Unique identifier for the sensor

        Returns:
            Response containing sensor status information
        """
        request = SensorStatusRequest(sensor_id=sensor_id)

        response = await self.call_endpoint("get_sensor_status", request)
        return SensorStatusResponse(**response)

    async def list_sensors(self, include_status: bool = False) -> SensorListResponse:
        """List all registered sensors.

        Args:
            include_status: Whether to include connection status for each sensor

        Returns:
            Response containing list of sensors
        """
        request = SensorListRequest(include_status=include_status)

        response = await self.call_endpoint("list_sensors", request)
        return SensorListResponse(**response)

    # Convenience methods for common operations

    async def connect_mqtt_sensor(
        self, sensor_id: str, broker_url: str, identifier: str, address: str
    ) -> SensorConnectionResponse:
        """Connect to an MQTT sensor with simplified parameters.

        Args:
            sensor_id: Unique identifier for the sensor
            broker_url: MQTT broker URL (e.g., "mqtt://localhost:1883")
            identifier: Client identifier for MQTT connection
            address: MQTT topic to subscribe to

        Returns:
            Response indicating success/failure of connection
        """
        config = {"broker_url": broker_url, "identifier": identifier}

        return await self.connect_sensor(sensor_id=sensor_id, backend_type="mqtt", config=config, address=address)

    async def connect_http_sensor(
        self, sensor_id: str, base_url: str, address: str, headers: Optional[Dict[str, str]] = None
    ) -> SensorConnectionResponse:
        """Connect to an HTTP sensor with simplified parameters.

        Args:
            sensor_id: Unique identifier for the sensor
            base_url: Base URL for HTTP requests
            address: Endpoint path for sensor data
            headers: Optional HTTP headers

        Returns:
            Response indicating success/failure of connection
        """
        config = {"base_url": base_url, "headers": headers or {}}

        return await self.connect_sensor(sensor_id=sensor_id, backend_type="http", config=config, address=address)

    async def connect_serial_sensor(
        self, sensor_id: str, port: str, baudrate: int = 9600, timeout: float = 1.0
    ) -> SensorConnectionResponse:
        """Connect to a serial sensor with simplified parameters.

        Args:
            sensor_id: Unique identifier for the sensor
            port: Serial port (e.g., "/dev/ttyUSB0" or "COM1")
            baudrate: Serial communication baud rate
            timeout: Serial read timeout

        Returns:
            Response indicating success/failure of connection
        """
        config = {"port": port, "baudrate": baudrate, "timeout": timeout}

        return await self.connect_sensor(
            sensor_id=sensor_id,
            backend_type="serial",
            config=config,
            address=port,  # For serial, address is the same as port
        )
