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
        input_schema=SensorConnectionRequest,
        output_schema=SensorConnectionResponse,
    )

    disconnect_sensor = TaskSchema(
        name="disconnect_sensor",
        input_schema=SensorStatusRequest,
        output_schema=SensorConnectionResponse,
    )

    get_sensor_status = TaskSchema(
        name="get_sensor_status",
        input_schema=SensorStatusRequest,
        output_schema=SensorStatusResponse,
    )

    list_sensors = TaskSchema(
        name="list_sensors",
        input_schema=SensorListRequest,
        output_schema=SensorListResponse,
    )
