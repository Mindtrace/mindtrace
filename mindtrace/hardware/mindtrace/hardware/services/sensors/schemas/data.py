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
        input_schema=SensorDataRequest,
        output_schema=SensorDataResponse,
    )
