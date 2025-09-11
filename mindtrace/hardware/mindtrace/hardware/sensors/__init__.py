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
from .simulators.base import SensorSimulatorBackend
from .simulators.mqtt import MQTTSensorSimulator
from .simulators.http import HTTPSensorSimulator
from .simulators.serial import SerialSensorSimulator
from .core.simulator import SensorSimulator
from .core.factory import create_simulator_backend

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