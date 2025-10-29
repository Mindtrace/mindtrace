"""
Backend factory for creating sensor backends and simulators.

This module provides factory functions to create different types of
sensor backends and simulator backends based on type strings and parameters.
"""

from typing import Dict

from ..backends.base import SensorBackend
from ..backends.http import HTTPSensorBackend
from ..backends.mqtt import MQTTSensorBackend
from ..backends.serial import SerialSensorBackend
from ..simulators.base import SensorSimulatorBackend
from ..simulators.http import HTTPSensorSimulator
from ..simulators.mqtt import MQTTSensorSimulator
from ..simulators.serial import SerialSensorSimulator

# Registry of available backend types
BACKEND_REGISTRY = {
    "mqtt": MQTTSensorBackend,
    "http": HTTPSensorBackend,
    "serial": SerialSensorBackend,
}

# Registry of available simulator backend types
SIMULATOR_REGISTRY = {
    "mqtt": MQTTSensorSimulator,
    "http": HTTPSensorSimulator,
    "serial": SerialSensorSimulator,
}


def create_backend(backend_type: str, **params) -> SensorBackend:
    """
    Create a sensor backend of the specified type.

    Args:
        backend_type: Type of backend ("mqtt", "http", "serial")
        **params: Backend-specific parameters

    Returns:
        Instantiated backend

    Raises:
        ValueError: If backend_type is unknown
        TypeError: If required parameters are missing

    Examples:
        # MQTT backend
        mqtt_backend = create_backend("mqtt", broker_url="mqtt://localhost:1883")

        # HTTP backend
        http_backend = create_backend("http", base_url="http://api.sensors.com")

        # Serial backend
        serial_backend = create_backend("serial", port="/dev/ttyUSB0", baudrate=9600)
    """
    backend_type = backend_type.lower().strip()

    if backend_type not in BACKEND_REGISTRY:
        available = ", ".join(BACKEND_REGISTRY.keys())
        raise ValueError(f"Unknown backend type '{backend_type}'. Available: {available}")

    backend_class = BACKEND_REGISTRY[backend_type]

    try:
        return backend_class(**params)
    except TypeError as e:
        raise TypeError(f"Invalid parameters for {backend_type} backend: {e}") from e


def register_backend(backend_type: str, backend_class: type) -> None:
    """
    Register a custom backend type.

    Args:
        backend_type: Name for the backend type
        backend_class: Backend class that implements SensorBackend

    Raises:
        TypeError: If backend_class doesn't inherit from SensorBackend
    """
    if not issubclass(backend_class, SensorBackend):
        raise TypeError("Backend class must inherit from SensorBackend")

    BACKEND_REGISTRY[backend_type.lower().strip()] = backend_class


def get_available_backends() -> Dict[str, type]:
    """
    Get all available backend types.

    Returns:
        Dictionary mapping backend names to classes
    """
    return BACKEND_REGISTRY.copy()


def create_simulator_backend(backend_type: str, **params) -> SensorSimulatorBackend:
    """
    Create a sensor simulator backend of the specified type.

    Args:
        backend_type: Type of backend ("mqtt", "http", "serial")
        **params: Backend-specific parameters

    Returns:
        Instantiated simulator backend

    Raises:
        ValueError: If backend_type is unknown
        TypeError: If required parameters are missing

    Examples:
        # MQTT simulator backend
        mqtt_sim = create_simulator_backend("mqtt", broker_url="mqtt://localhost:1883")

        # HTTP simulator backend
        http_sim = create_simulator_backend("http", base_url="http://api.sensors.com")

        # Serial simulator backend
        serial_sim = create_simulator_backend("serial", port="/dev/ttyUSB0", baudrate=9600)
    """
    backend_type = backend_type.lower().strip()

    if backend_type not in SIMULATOR_REGISTRY:
        available = ", ".join(SIMULATOR_REGISTRY.keys())
        raise ValueError(f"Unknown simulator backend type '{backend_type}'. Available: {available}")

    backend_class = SIMULATOR_REGISTRY[backend_type]

    try:
        return backend_class(**params)
    except TypeError as e:
        raise TypeError(f"Invalid parameters for {backend_type} simulator backend: {e}") from e


def register_simulator_backend(backend_type: str, backend_class: type) -> None:
    """
    Register a custom simulator backend type.

    Args:
        backend_type: Name for the backend type
        backend_class: Backend class that implements SensorSimulatorBackend

    Raises:
        TypeError: If backend_class doesn't inherit from SensorSimulatorBackend
    """
    if not issubclass(backend_class, SensorSimulatorBackend):
        raise TypeError("Backend class must inherit from SensorSimulatorBackend")

    SIMULATOR_REGISTRY[backend_type.lower().strip()] = backend_class


def get_available_simulator_backends() -> Dict[str, type]:
    """
    Get all available simulator backend types.

    Returns:
        Dictionary mapping simulator backend names to classes
    """
    return SIMULATOR_REGISTRY.copy()
