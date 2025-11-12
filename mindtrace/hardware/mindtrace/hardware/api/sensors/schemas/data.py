"""Task schemas for sensor data operations."""

from mindtrace.core import TaskSchema

from ..models import (
    SensorDataRequest,
    SensorDataResponse,
)


class SensorDataSchemas:
    """Task schemas for sensor data access."""

    read_sensor_data = TaskSchema(
        name="read_sensor_data",
        description="Read the latest data from a connected sensor",
        parameters=SensorDataRequest,
        return_type=SensorDataResponse,
    )
