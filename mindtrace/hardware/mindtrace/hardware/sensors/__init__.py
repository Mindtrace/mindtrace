"""
MindTrace Hardware Sensor System.

A unified sensor system that abstracts different communication backends
(MQTT, HTTP, Serial, Modbus) behind a simple AsyncSensor interface.
"""

from .backends.base import SensorBackend
from .backends.mqtt import MQTTSensorBackend
from .backends.http import HTTPSensorBackend
from .backends.serial import SerialSensorBackend
from .core.sensor import AsyncSensor
from .core.manager import SensorManager
from .core.factory import create_backend

__all__ = [
    # Core classes
    "AsyncSensor",
    "SensorManager",
    
    # Backend interface and implementations
    "SensorBackend",
    "MQTTSensorBackend", 
    "HTTPSensorBackend",
    "SerialSensorBackend",
    
    # Factory function
    "create_backend",
]