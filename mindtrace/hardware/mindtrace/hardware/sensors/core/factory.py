"""
Backend factory for creating sensor backends.

This module provides factory functions to create different types of
sensor backends based on type strings and parameters.
"""

from typing import Dict, Any
from ..backends.base import SensorBackend
from ..backends.mqtt import MQTTSensorBackend
from ..backends.http import HTTPSensorBackend
from ..backends.serial import SerialSensorBackend


# Registry of available backend types
BACKEND_REGISTRY = {
    "mqtt": MQTTSensorBackend,
    "http": HTTPSensorBackend,
    "serial": SerialSensorBackend,
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