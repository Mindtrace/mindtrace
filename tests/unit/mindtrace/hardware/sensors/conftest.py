"""
Test configuration and fixtures for sensor unit tests.

This module provides common fixtures and utilities for testing the sensor system
including mock backends, test data, and async test support.
"""

import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio


# Test data fixtures
@pytest.fixture
def sample_sensor_data():
    """Sample sensor data for testing."""
    return {
        "temperature": 23.5,
        "humidity": 65.2,
        "timestamp": "2024-01-15T10:30:00Z",
        "unit_temp": "C",
        "unit_humidity": "%",
    }


@pytest.fixture
def sample_mqtt_config():
    """Sample MQTT configuration for testing."""
    return {
        "broker_url": "mqtt://test.broker:1883",
        "identifier": "test_sensor",
        "username": "test_user",
        "password": "test_pass",
    }


@pytest.fixture
def sample_http_config():
    """Sample HTTP configuration for testing."""
    return {"base_url": "http://api.sensors.test", "auth_token": "test_token_123", "timeout": 30.0}


@pytest.fixture
def sample_serial_config():
    """Sample Serial configuration for testing."""
    return {"port": "/dev/ttyUSB0", "baudrate": 9600, "timeout": 5.0}


# Event loop fixture
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Mock backend fixtures
@pytest_asyncio.fixture
async def mock_mqtt_backend():
    """Create a mock MQTT backend for testing."""
    from mindtrace.hardware.sensors.backends.base import SensorBackend

    backend = AsyncMock(spec=SensorBackend)
    backend.is_connected.return_value = False
    backend.connect = AsyncMock()
    backend.disconnect = AsyncMock()
    backend.read_data = AsyncMock()
    return backend


@pytest_asyncio.fixture
async def mock_http_backend():
    """Create a mock HTTP backend for testing."""
    from mindtrace.hardware.sensors.backends.base import SensorBackend

    backend = AsyncMock(spec=SensorBackend)
    backend.is_connected.return_value = False
    backend.connect = AsyncMock()
    backend.disconnect = AsyncMock()
    backend.read_data = AsyncMock()
    return backend


@pytest_asyncio.fixture
async def mock_serial_backend():
    """Create a mock Serial backend for testing."""
    from mindtrace.hardware.sensors.backends.base import SensorBackend

    backend = AsyncMock(spec=SensorBackend)
    backend.is_connected.return_value = False
    backend.connect = AsyncMock()
    backend.disconnect = AsyncMock()
    backend.read_data = AsyncMock()
    return backend


# Mock simulator backend fixtures
@pytest_asyncio.fixture
async def mock_mqtt_simulator():
    """Create a mock MQTT simulator backend for testing."""
    from mindtrace.hardware.sensors.simulators.base import SensorSimulatorBackend

    simulator = AsyncMock(spec=SensorSimulatorBackend)
    simulator.is_connected.return_value = False
    simulator.connect = AsyncMock()
    simulator.disconnect = AsyncMock()
    simulator.publish_data = AsyncMock()
    return simulator


@pytest_asyncio.fixture
async def mock_http_simulator():
    """Create a mock HTTP simulator backend for testing."""
    from mindtrace.hardware.sensors.simulators.base import SensorSimulatorBackend

    simulator = AsyncMock(spec=SensorSimulatorBackend)
    simulator.is_connected.return_value = False
    simulator.connect = AsyncMock()
    simulator.disconnect = AsyncMock()
    simulator.publish_data = AsyncMock()
    return simulator


@pytest_asyncio.fixture
async def mock_serial_simulator():
    """Create a mock Serial simulator backend for testing."""
    from mindtrace.hardware.sensors.simulators.base import SensorSimulatorBackend

    simulator = AsyncMock(spec=SensorSimulatorBackend)
    simulator.is_connected.return_value = False
    simulator.connect = AsyncMock()
    simulator.disconnect = AsyncMock()
    simulator.publish_data = AsyncMock()
    return simulator


# Real backend test fixtures (require external dependencies)
@pytest.fixture
def mqtt_test_available():
    """Check if MQTT testing dependencies are available."""
    try:
        import aiomqtt  # noqa: F401

        return True
    except ImportError:
        return False


@pytest.fixture
def http_test_available():
    """Check if HTTP testing dependencies are available."""
    try:
        import aiohttp  # noqa: F401

        return True
    except ImportError:
        return False


@pytest.fixture
def serial_test_available():
    """Check if Serial testing dependencies are available."""
    try:
        import serial  # noqa: F401

        return True
    except ImportError:
        return False


# Error simulation utilities
class MockConnectionError(Exception):
    """Mock connection error for testing."""

    pass


class MockTimeoutError(Exception):
    """Mock timeout error for testing."""

    pass


@pytest.fixture
def error_scenarios():
    """Common error scenarios for testing."""
    return {
        "connection_failed": MockConnectionError("Failed to connect to broker"),
        "read_timeout": MockTimeoutError("Read operation timed out"),
        "invalid_data": ValueError("Invalid sensor data format"),
        "network_error": ConnectionError("Network unreachable"),
    }


# Test utilities
def create_mock_sensor_manager():
    """Create a mock sensor manager for testing."""
    manager = Mock()
    manager._sensors = {}
    manager.register_sensor = Mock()
    manager.remove_sensor = Mock()
    manager.get_sensor = Mock()
    manager.list_sensors = Mock()
    manager.connect_all = AsyncMock()
    manager.disconnect_all = AsyncMock()
    manager.read_all = AsyncMock()
    return manager


def assert_sensor_data_valid(data: Dict[str, Any]):
    """Assert that sensor data has expected structure."""
    assert isinstance(data, dict)
    assert len(data) > 0
    # Common sensor data should have at least one measurement
    numeric_fields = [k for k, v in data.items() if isinstance(v, (int, float))]
    assert len(numeric_fields) > 0, "Sensor data should contain at least one numeric measurement"
