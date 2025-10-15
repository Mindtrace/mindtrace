"""Sensor task schemas for service operations."""

from .data import SensorDataSchemas
from .lifecycle import SensorLifecycleSchemas

__all__ = [
    "SensorLifecycleSchemas",
    "SensorDataSchemas",
]
