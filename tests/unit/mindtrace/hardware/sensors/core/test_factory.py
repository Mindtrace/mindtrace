"""
Unit tests for sensor factory functions.

Tests cover backend and simulator backend creation, registration,
and factory function error handling.
"""

import pytest
from unittest.mock import Mock, patch
from mindtrace.hardware.sensors.core.factory import (
    create_backend, create_simulator_backend,
    register_backend, register_simulator_backend,
    get_available_backends, get_available_simulator_backends
)


class TestSensorFactory:
    """Test cases for sensor factory functions."""

    def test_create_mqtt_backend_success(self):
        """Test creating MQTT sensor backend."""
        backend = create_backend("mqtt", broker_url="mqtt://localhost:1883")
        
        from mindtrace.hardware.sensors.backends.mqtt import MQTTSensorBackend
        assert isinstance(backend, MQTTSensorBackend)
        assert backend.broker_url == "mqtt://localhost:1883"

    def test_create_mqtt_backend_with_params(self):
        """Test creating MQTT backend with additional parameters."""
        backend = create_backend(
            "mqtt",
            broker_url="mqtt://test.broker:1883",
            identifier="test_client",
            username="user",
            password="pass"
        )
        
        from mindtrace.hardware.sensors.backends.mqtt import MQTTSensorBackend
        assert isinstance(backend, MQTTSensorBackend)
        assert backend.identifier == "test_client"
        assert backend.username == "user"
        assert backend.password == "pass"

    @pytest.mark.asyncio
    async def test_create_http_backend_not_implemented(self):
        """Test creating HTTP backend raises NotImplementedError."""
        # HTTP backend can be created but methods raise NotImplementedError
        backend = create_backend("http", base_url="http://api.test.com")
        
        with pytest.raises(NotImplementedError, match="HTTP backend not yet implemented"):
            await backend.connect()

    @pytest.mark.asyncio
    async def test_create_serial_backend_not_implemented(self):
        """Test creating Serial backend raises NotImplementedError."""
        # Serial backend can be created but methods raise NotImplementedError
        backend = create_backend("serial", port="/dev/ttyUSB0")
        
        with pytest.raises(NotImplementedError, match="Serial backend not yet implemented"):
            await backend.connect()

    def test_create_backend_unknown_type(self):
        """Test creating backend with unknown type."""
        with pytest.raises(ValueError, match="Unknown backend type 'unknown'"):
            create_backend("unknown", param="value")

    def test_create_mqtt_simulator_success(self):
        """Test creating MQTT sensor simulator."""
        simulator = create_simulator_backend("mqtt", broker_url="mqtt://localhost:1883")
        
        from mindtrace.hardware.sensors.simulators.mqtt import MQTTSensorSimulator
        assert isinstance(simulator, MQTTSensorSimulator)
        assert simulator.broker_url == "mqtt://localhost:1883"

    def test_create_mqtt_simulator_with_params(self):
        """Test creating MQTT simulator with additional parameters."""
        simulator = create_simulator_backend(
            "mqtt",
            broker_url="mqtt://sim.broker:1883",
            identifier="sim_client",
            username="sim_user",
            password="sim_pass"
        )
        
        from mindtrace.hardware.sensors.simulators.mqtt import MQTTSensorSimulator
        assert isinstance(simulator, MQTTSensorSimulator)
        assert simulator.identifier == "sim_client"
        assert simulator.username == "sim_user"
        assert simulator.password == "sim_pass"

    @pytest.mark.asyncio
    async def test_create_http_simulator_not_implemented(self):
        """Test creating HTTP simulator raises NotImplementedError."""
        # HTTP simulator can be created but methods raise NotImplementedError
        simulator = create_simulator_backend("http", base_url="http://api.test.com")
        
        with pytest.raises(NotImplementedError, match="HTTP simulator backend not yet implemented"):
            await simulator.connect()

    @pytest.mark.asyncio
    async def test_create_serial_simulator_not_implemented(self):
        """Test creating Serial simulator raises NotImplementedError."""
        # Serial simulator can be created but methods raise NotImplementedError
        simulator = create_simulator_backend("serial", port="/dev/ttyUSB0")
        
        with pytest.raises(NotImplementedError, match="Serial simulator backend not yet implemented"):
            await simulator.connect()

    def test_create_simulator_backend_unknown_type(self):
        """Test creating simulator backend with unknown type."""
        with pytest.raises(ValueError, match="Unknown simulator backend type 'unknown'"):
            create_simulator_backend("unknown", param="value")

    def test_get_available_backends(self):
        """Test getting list of available backend types."""
        backends = get_available_backends()
        
        assert "mqtt" in backends
        assert "http" in backends
        assert "serial" in backends
        assert isinstance(backends, dict)

    def test_get_available_simulator_backends(self):
        """Test getting list of available simulator backend types."""
        simulators = get_available_simulator_backends()
        
        assert "mqtt" in simulators
        assert "http" in simulators
        assert "serial" in simulators
        assert isinstance(simulators, dict)

    def test_register_custom_backend(self):
        """Test registering custom sensor backend."""
        from mindtrace.hardware.sensors.backends.base import SensorBackend
        
        class CustomBackend(SensorBackend):
            def __init__(self, custom_param=None):
                self.custom_param = custom_param
                
            async def connect(self):
                pass
                
            async def disconnect(self):
                pass
                
            async def read_data(self, address):
                return {"custom": self.custom_param}
                
            def is_connected(self):
                return True
        
        # Register custom backend
        register_backend("custom", CustomBackend)
        
        # Verify it's available
        assert "custom" in get_available_backends()
        
        # Create instance using factory
        backend = create_backend("custom", custom_param="test_value")
        assert isinstance(backend, CustomBackend)
        assert backend.custom_param == "test_value"

    def test_register_custom_simulator_backend(self):
        """Test registering custom sensor simulator backend."""
        from mindtrace.hardware.sensors.simulators.base import SensorSimulatorBackend
        
        class CustomSimulator(SensorSimulatorBackend):
            def __init__(self, custom_param=None):
                self.custom_param = custom_param
                
            async def connect(self):
                pass
                
            async def disconnect(self):
                pass
                
            async def publish_data(self, address, data):
                pass
                
            def is_connected(self):
                return True
        
        # Register custom simulator
        register_simulator_backend("custom", CustomSimulator)
        
        # Verify it's available
        assert "custom" in get_available_simulator_backends()
        
        # Create instance using factory
        simulator = create_simulator_backend("custom", custom_param="test_value")
        assert isinstance(simulator, CustomSimulator)
        assert simulator.custom_param == "test_value"

    def test_register_backend_invalid_class(self):
        """Test registering backend with invalid class."""
        class NotABackend:
            pass
            
        with pytest.raises(TypeError, match="Backend class must inherit from SensorBackend"):
            register_backend("invalid", NotABackend)

    def test_register_simulator_invalid_class(self):
        """Test registering simulator with invalid class."""
        class NotASimulator:
            pass
            
        with pytest.raises(TypeError, match="Backend class must inherit from SensorSimulatorBackend"):
            register_simulator_backend("invalid", NotASimulator)

    def test_register_backend_override_existing(self):
        """Test overriding existing backend type."""
        from mindtrace.hardware.sensors.backends.base import SensorBackend
        from mindtrace.hardware.sensors.core.factory import BACKEND_REGISTRY
        
        class OverrideBackend(SensorBackend):
            def __init__(self, **kwargs):  # Accept kwargs to handle broker_url
                pass
            async def connect(self):
                pass
            async def disconnect(self):
                pass
            async def read_data(self, address):
                return {"override": True}
            def is_connected(self):
                return False
        
        # Store original backend for cleanup
        original_mqtt_backend = BACKEND_REGISTRY["mqtt"]
        
        try:
            # Override existing mqtt backend
            original_backends = get_available_backends().copy()
            register_backend("mqtt", OverrideBackend)
            
            # Should still have same number of backends
            assert len(get_available_backends()) == len(original_backends)
            
            # Creating mqtt backend should use override
            backend = create_backend("mqtt", broker_url="mqtt://test:1883")
            assert isinstance(backend, OverrideBackend)
        finally:
            # Restore original backend to avoid affecting other tests
            BACKEND_REGISTRY["mqtt"] = original_mqtt_backend

    @patch('mindtrace.hardware.sensors.core.factory.BACKEND_REGISTRY', {"test_type": Mock})
    def test_factory_with_mocked_registry(self):
        """Test factory behavior with mocked backend registry."""
        mock_class = Mock()
        mock_instance = Mock()
        mock_class.return_value = mock_instance
        
        with patch('mindtrace.hardware.sensors.core.factory.BACKEND_REGISTRY', {"test_type": mock_class}):
            backend = create_backend("test_type", param1="value1", param2="value2")
            
            assert backend is mock_instance
            mock_class.assert_called_once_with(param1="value1", param2="value2")

    def test_factory_empty_parameters(self):
        """Test factory functions with no parameters."""
        # MQTT backend requires broker_url, so this should fail
        with pytest.raises(TypeError):
            create_backend("mqtt")
            
        with pytest.raises(TypeError):
            create_simulator_backend("mqtt")

    def test_case_insensitive_backend_types(self):
        """Test that backend type lookup is case insensitive."""
        backend1 = create_backend("mqtt", broker_url="mqtt://test:1883")
        backend2 = create_backend("MQTT", broker_url="mqtt://test:1883")
        backend3 = create_backend("Mqtt", broker_url="mqtt://test:1883")
        
        from mindtrace.hardware.sensors.backends.mqtt import MQTTSensorBackend
        assert isinstance(backend1, MQTTSensorBackend)
        assert isinstance(backend2, MQTTSensorBackend)
        assert isinstance(backend3, MQTTSensorBackend)