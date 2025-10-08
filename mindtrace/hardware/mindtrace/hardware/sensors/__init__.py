"""
MindTrace Hardware Sensor System.

A unified sensor system that abstracts different communication backends
(MQTT, HTTP, Serial, Modbus) behind a simple AsyncSensor interface.
"""

from .backends.base import SensorBackend
from .backends.http import HTTPSensorBackend
from .backends.mqtt import MQTTSensorBackend
from .backends.serial import SerialSensorBackend
from .core.factory import create_backend, create_simulator_backend
from .core.manager import SensorManager
from .core.sensor import AsyncSensor
from .core.simulator import SensorSimulator
from .simulators.base import SensorSimulatorBackend
from .simulators.http import HTTPSensorSimulator
from .simulators.mqtt import MQTTSensorSimulator
from .simulators.serial import SerialSensorSimulator

__all__ = [
    # Core classes
    "AsyncSensor",
    "SensorManager",
    "SensorSimulator",
    # Backend interface and implementations
    "SensorBackend",
    "MQTTSensorBackend",
    "HTTPSensorBackend",
    "SerialSensorBackend",
    # Simulator interface and implementations
    "SensorSimulatorBackend",
    "MQTTSensorSimulator",
    "HTTPSensorSimulator",
    "SerialSensorSimulator",
    # Factory functions
    "create_backend",
    "create_simulator_backend",
]
