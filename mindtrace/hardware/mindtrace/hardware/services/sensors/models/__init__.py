"""Sensor API models for request/response data structures."""

from mindtrace.hardware.core.types import ServiceStatus

from .requests import (
    SensorConnectionRequest,
    SensorDataRequest,
    SensorListRequest,
    SensorStatusRequest,
)
from .responses import (
    HealthCheckResponse,
    SensorConnectionResponse,
    SensorConnectionStatus,
    SensorDataResponse,
    SensorInfo,
    SensorListResponse,
    SensorStatusResponse,
)

__all__ = [
    # Request models
    "SensorConnectionRequest",
    "SensorDataRequest",
    "SensorStatusRequest",
    "SensorListRequest",
    # Response models
    "SensorConnectionResponse",
    "SensorDataResponse",
    "SensorStatusResponse",
    "SensorListResponse",
    "SensorInfo",
    "SensorConnectionStatus",
    "HealthCheckResponse",
    "ServiceStatus",
]
