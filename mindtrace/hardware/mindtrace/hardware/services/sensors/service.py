"""Sensor Manager Service providing MCP endpoints for sensor operations."""

import time
from typing import Dict, Optional

from mindtrace.hardware.sensors import SensorManager
from mindtrace.services import Service

from .models import (
    SensorConnectionRequest,
    SensorConnectionResponse,
    SensorConnectionStatus,
    SensorDataRequest,
    SensorDataResponse,
    SensorInfo,
    SensorListRequest,
    SensorListResponse,
    SensorStatusRequest,
    SensorStatusResponse,
)
from .schemas import SensorDataSchemas, SensorLifecycleSchemas


class SensorManagerService(Service):
    """Service wrapper for SensorManager with MCP endpoint registration."""

    def __init__(self, manager: Optional[SensorManager] = None, **kwargs):
        """Initialize the sensor manager service.

        Args:
            manager: Optional SensorManager instance. If None, creates a new one.
            **kwargs: Additional arguments passed to the Service base class
        """
        super().__init__(**kwargs)
        self._manager = manager or SensorManager()
        self._last_data_times: Dict[str, float] = {}

        # Register MCP endpoints
        self._register_endpoints()

    def _register_endpoints(self) -> None:
        """Register all sensor management endpoints as MCP tools."""

        # Lifecycle management endpoints
        self.add_endpoint(
            path="/connect_sensor", schema=SensorLifecycleSchemas.connect_sensor, func=self.connect_sensor, as_tool=True
        )

        self.add_endpoint(
            path="/disconnect_sensor",
            schema=SensorLifecycleSchemas.disconnect_sensor,
            func=self.disconnect_sensor,
            as_tool=True,
        )

        self.add_endpoint(
            path="/get_sensor_status",
            schema=SensorLifecycleSchemas.get_sensor_status,
            func=self.get_sensor_status,
            as_tool=True,
        )

        self.add_endpoint(
            path="/list_sensors", schema=SensorLifecycleSchemas.list_sensors, func=self.list_sensors, as_tool=True
        )

        # Data access endpoints
        self.add_endpoint(
            path="/read_sensor_data",
            schema=SensorDataSchemas.read_sensor_data,
            func=self.read_sensor_data,
            as_tool=True,
        )

    async def connect_sensor(self, request: SensorConnectionRequest) -> SensorConnectionResponse:
        """Connect to a sensor with specified configuration.

        Args:
            request: Connection request with sensor configuration

        Returns:
            Response indicating success/failure of connection
        """
        try:
            # Register and connect sensor using the manager
            sensor = self._manager.register_sensor(
                sensor_id=request.sensor_id,
                backend_type=request.backend_type,
                connection_params=request.config,
                address=request.address,
            )

            # Connect the sensor
            await sensor.connect()

            return SensorConnectionResponse(
                success=True,
                sensor_id=request.sensor_id,
                status=SensorConnectionStatus.CONNECTED,
                message=f"Successfully connected to {request.backend_type} sensor",
            )

        except Exception as e:
            return SensorConnectionResponse(
                success=False,
                sensor_id=request.sensor_id,
                status=SensorConnectionStatus.ERROR,
                message=f"Failed to connect sensor: {str(e)}",
            )

    async def disconnect_sensor(self, request: SensorStatusRequest) -> SensorConnectionResponse:
        """Disconnect from a connected sensor.

        Args:
            request: Request containing sensor_id to disconnect

        Returns:
            Response indicating success/failure of disconnection
        """
        try:
            # Get and disconnect sensor
            sensor = self._manager.get_sensor(request.sensor_id)
            if sensor:
                await sensor.disconnect()
                # Remove from manager
                self._manager.remove_sensor(request.sensor_id)

            # Clean up tracking data
            self._last_data_times.pop(request.sensor_id, None)

            return SensorConnectionResponse(
                success=True,
                sensor_id=request.sensor_id,
                status=SensorConnectionStatus.DISCONNECTED,
                message="Successfully disconnected sensor",
            )

        except Exception as e:
            return SensorConnectionResponse(
                success=False,
                sensor_id=request.sensor_id,
                status=SensorConnectionStatus.ERROR,
                message=f"Failed to disconnect sensor: {str(e)}",
            )

    async def read_sensor_data(self, request: SensorDataRequest) -> SensorDataResponse:
        """Read data from a connected sensor.

        Args:
            request: Request specifying sensor and read parameters

        Returns:
            Response containing sensor data or error information
        """
        try:
            # Get sensor and read data
            sensor = self._manager.get_sensor(request.sensor_id)
            if not sensor:
                raise ValueError(f"Sensor '{request.sensor_id}' not found")

            # Read data from sensor
            data = await sensor.read()

            # Update last data time tracking
            current_time = time.time()
            self._last_data_times[request.sensor_id] = current_time

            return SensorDataResponse(
                success=True,
                sensor_id=request.sensor_id,
                data=data,
                timestamp=current_time,
                message="Data read successfully" if data else "No data available",
            )

        except Exception as e:
            return SensorDataResponse(
                success=False,
                sensor_id=request.sensor_id,
                data=None,
                timestamp=None,
                message=f"Failed to read sensor data: {str(e)}",
            )

    async def get_sensor_status(self, request: SensorStatusRequest) -> SensorStatusResponse:
        """Get status information for a sensor.

        Args:
            request: Request containing sensor_id

        Returns:
            Response containing sensor status information
        """
        try:
            # Get sensor from manager
            sensor = self._manager.get_sensor(request.sensor_id)

            if sensor:
                sensor_info = SensorInfo(
                    sensor_id=request.sensor_id,
                    backend_type=type(sensor._backend).__name__.replace("SensorBackend", "").lower(),
                    address=sensor._address,
                    status=SensorConnectionStatus.CONNECTED,  # Assume connected if in registry
                    last_data_time=self._last_data_times.get(request.sensor_id),
                )

                return SensorStatusResponse(
                    success=True, sensor_info=sensor_info, message="Status retrieved successfully"
                )
            else:
                return SensorStatusResponse(
                    success=False, sensor_info=None, message=f"Sensor '{request.sensor_id}' not found"
                )

        except Exception as e:
            return SensorStatusResponse(
                success=False, sensor_info=None, message=f"Failed to get sensor status: {str(e)}"
            )

    async def list_sensors(self, request: SensorListRequest) -> SensorListResponse:
        """List all registered sensors.

        Args:
            request: Request with listing options

        Returns:
            Response containing list of sensors
        """
        try:
            # Get all sensors from manager (this returns List[str], not a dict)
            sensor_ids = self._manager.list_sensors()

            sensors = []
            for sensor_id in sensor_ids:
                # Get sensor instance to check its properties
                sensor = self._manager._sensors.get(sensor_id)
                if sensor:
                    # Build sensor info
                    sensor_info = SensorInfo(
                        sensor_id=sensor_id,
                        backend_type=type(sensor._backend).__name__.replace("SensorBackend", "").lower(),
                        address=sensor._address,
                        status=SensorConnectionStatus.CONNECTED,  # Assume connected if in registry
                        last_data_time=self._last_data_times.get(sensor_id) if request.include_status else None,
                    )
                    sensors.append(sensor_info)

            return SensorListResponse(
                success=True, sensors=sensors, count=len(sensors), message=f"Retrieved {len(sensors)} sensors"
            )

        except Exception as e:
            return SensorListResponse(success=False, sensors=[], count=0, message=f"Failed to list sensors: {str(e)}")

    @property
    def manager(self) -> SensorManager:
        """Get the underlying SensorManager instance."""
        return self._manager
