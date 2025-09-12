"""Sensor task schemas for service operations."""

from .lifecycle import SensorLifecycleSchemas
from .data import SensorDataSchemas

__all__ = [
    "SensorLifecycleSchemas",
    "SensorDataSchemas",
]