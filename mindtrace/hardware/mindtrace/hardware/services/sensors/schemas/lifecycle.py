"""Task schemas for sensor lifecycle operations."""

from mindtrace.core import TaskSchema

from ..models import (
    SensorConnectionRequest,
    SensorConnectionResponse,
    SensorListRequest,
    SensorListResponse,
    SensorStatusRequest,
    SensorStatusResponse,
)


class SensorLifecycleSchemas:
    """Task schemas for sensor lifecycle management."""

    connect_sensor = TaskSchema(
        name="connect_sensor",
        description="Connect to a sensor with specified backend configuration",
        parameters=SensorConnectionRequest,
        return_type=SensorConnectionResponse,
    )

    disconnect_sensor = TaskSchema(
        name="disconnect_sensor",
        description="Disconnect from a connected sensor",
        parameters=SensorStatusRequest,  # Only needs sensor_id
        return_type=SensorConnectionResponse,
    )

    get_sensor_status = TaskSchema(
        name="get_sensor_status",
        description="Get current status and information for a sensor",
        parameters=SensorStatusRequest,
        return_type=SensorStatusResponse,
    )

    list_sensors = TaskSchema(
        name="list_sensors",
        description="List all registered sensors with optional status information",
        parameters=SensorListRequest,
        return_type=SensorListResponse,
    )
