"""
Unit tests for SensorSimulator class.

Tests cover the complete lifecycle of sensor simulation including connection,
data publishing, error handling, and async context management.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from mindtrace.hardware.sensors.core.simulator import SensorSimulator
from mindtrace.hardware.sensors.simulators.base import SensorSimulatorBackend


class TestSensorSimulator:
    """Test cases for SensorSimulator class."""

    def test_simulator_initialization_valid(self, mock_mqtt_simulator):
        """Test successful simulator initialization with valid parameters."""
        simulator = SensorSimulator("test_sim", mock_mqtt_simulator, "test/topic")
        
        assert simulator.simulator_id == "test_sim"
        assert simulator._address == "test/topic"
        assert simulator._backend == mock_mqtt_simulator
        
    def test_simulator_initialization_strips_whitespace(self, mock_mqtt_simulator):
        """Test that simulator initialization strips whitespace from strings."""
        simulator = SensorSimulator("  test_sim  ", mock_mqtt_simulator, "  test/topic  ")
        
        assert simulator.simulator_id == "test_sim"
        assert simulator._address == "test/topic"
        
    def test_simulator_initialization_invalid_id(self, mock_mqtt_simulator):
        """Test simulator initialization with invalid simulator_id."""
        with pytest.raises(ValueError, match="simulator_id must be a non-empty string"):
            SensorSimulator("", mock_mqtt_simulator, "test/topic")
            
        with pytest.raises(ValueError, match="simulator_id must be a non-empty string"):
            SensorSimulator(None, mock_mqtt_simulator, "test/topic")
            
        with pytest.raises(ValueError, match="simulator_id must be a non-empty string"):
            SensorSimulator(123, mock_mqtt_simulator, "test/topic")
            
    def test_simulator_initialization_invalid_address(self, mock_mqtt_simulator):
        """Test simulator initialization with invalid address."""
        with pytest.raises(ValueError, match="address must be a non-empty string"):
            SensorSimulator("test_sim", mock_mqtt_simulator, "")
            
        with pytest.raises(ValueError, match="address must be a non-empty string"):
            SensorSimulator("test_sim", mock_mqtt_simulator, None)
            
    def test_simulator_initialization_invalid_backend(self):
        """Test simulator initialization with invalid backend."""
        with pytest.raises(TypeError, match="backend must be a SensorSimulatorBackend instance"):
            SensorSimulator("test_sim", "not_a_backend", "test/topic")
            
        with pytest.raises(TypeError, match="backend must be a SensorSimulatorBackend instance"):
            SensorSimulator("test_sim", None, "test/topic")

    def test_is_connected_property(self, mock_mqtt_simulator):
        """Test is_connected property delegates to backend."""
        simulator = SensorSimulator("test_sim", mock_mqtt_simulator, "test/topic")
        
        mock_mqtt_simulator.is_connected.return_value = False
        assert not simulator.is_connected
        
        mock_mqtt_simulator.is_connected.return_value = True
        assert simulator.is_connected
        
        mock_mqtt_simulator.is_connected.assert_called()

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_mqtt_simulator):
        """Test successful simulator connection."""
        simulator = SensorSimulator("test_sim", mock_mqtt_simulator, "test/topic")
        
        await simulator.connect()
        
        mock_mqtt_simulator.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self, mock_mqtt_simulator):
        """Test simulator connection failure."""
        simulator = SensorSimulator("test_sim", mock_mqtt_simulator, "test/topic")
        
        mock_mqtt_simulator.connect.side_effect = Exception("Connection failed")
        
        with pytest.raises(ConnectionError, match="Failed to connect simulator test_sim"):
            await simulator.connect()
            
        mock_mqtt_simulator.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_success(self, mock_mqtt_simulator):
        """Test successful simulator disconnection."""
        simulator = SensorSimulator("test_sim", mock_mqtt_simulator, "test/topic")
        
        await simulator.disconnect()
        
        mock_mqtt_simulator.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_with_error(self, mock_mqtt_simulator):
        """Test simulator disconnection with error (should not raise)."""
        simulator = SensorSimulator("test_sim", mock_mqtt_simulator, "test/topic")
        
        mock_mqtt_simulator.disconnect.side_effect = Exception("Disconnect error")
        
        # Should not raise exception, only log warning
        await simulator.disconnect()
        
        mock_mqtt_simulator.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_dict_data(self, mock_mqtt_simulator, sample_sensor_data):
        """Test publishing dictionary data."""
        simulator = SensorSimulator("test_sim", mock_mqtt_simulator, "test/topic")
        
        mock_mqtt_simulator.is_connected.return_value = True
        
        await simulator.publish(sample_sensor_data)
        
        mock_mqtt_simulator.publish_data.assert_called_once_with("test/topic", sample_sensor_data)

    @pytest.mark.asyncio
    async def test_publish_primitive_data(self, mock_mqtt_simulator):
        """Test publishing primitive data types."""
        simulator = SensorSimulator("test_sim", mock_mqtt_simulator, "test/topic")
        
        mock_mqtt_simulator.is_connected.return_value = True
        
        # Test string
        await simulator.publish("temperature_reading")
        mock_mqtt_simulator.publish_data.assert_called_with("test/topic", "temperature_reading")
        
        # Test number
        await simulator.publish(23.5)
        mock_mqtt_simulator.publish_data.assert_called_with("test/topic", 23.5)
        
        # Test boolean
        await simulator.publish(True)
        mock_mqtt_simulator.publish_data.assert_called_with("test/topic", True)

    @pytest.mark.asyncio
    async def test_publish_complex_data(self, mock_mqtt_simulator):
        """Test publishing complex data structures."""
        simulator = SensorSimulator("test_sim", mock_mqtt_simulator, "test/topic")
        
        mock_mqtt_simulator.is_connected.return_value = True
        
        complex_data = {
            "sensors": [
                {"id": "temp1", "value": 23.5},
                {"id": "temp2", "value": 24.1}
            ],
            "metadata": {
                "timestamp": "2024-01-15T10:30:00Z",
                "location": "office"
            }
        }
        
        await simulator.publish(complex_data)
        
        mock_mqtt_simulator.publish_data.assert_called_once_with("test/topic", complex_data)

    @pytest.mark.asyncio
    async def test_publish_not_connected(self, mock_mqtt_simulator):
        """Test publishing when simulator is not connected."""
        simulator = SensorSimulator("test_sim", mock_mqtt_simulator, "test/topic")
        
        mock_mqtt_simulator.is_connected.return_value = False
        
        with pytest.raises(ConnectionError, match="Simulator test_sim is not connected"):
            await simulator.publish({"test": "data"})
            
        mock_mqtt_simulator.publish_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_backend_error(self, mock_mqtt_simulator):
        """Test publishing with backend error."""
        simulator = SensorSimulator("test_sim", mock_mqtt_simulator, "test/topic")
        
        mock_mqtt_simulator.is_connected.return_value = True
        mock_mqtt_simulator.publish_data.side_effect = TimeoutError("Publish timeout")
        
        with pytest.raises(TimeoutError, match="Publish timeout"):
            await simulator.publish({"test": "data"})
            
        mock_mqtt_simulator.publish_data.assert_called_once_with("test/topic", {"test": "data"})

    @pytest.mark.asyncio
    async def test_context_manager_success(self, mock_mqtt_simulator, sample_sensor_data):
        """Test async context manager with successful operations."""
        simulator = SensorSimulator("test_sim", mock_mqtt_simulator, "test/topic")
        
        mock_mqtt_simulator.is_connected.return_value = True
        
        async with simulator as s:
            assert s is simulator
            await s.publish(sample_sensor_data)
            
        mock_mqtt_simulator.connect.assert_called_once()
        mock_mqtt_simulator.disconnect.assert_called_once()
        mock_mqtt_simulator.publish_data.assert_called_once_with("test/topic", sample_sensor_data)

    @pytest.mark.asyncio
    async def test_context_manager_connect_error(self, mock_mqtt_simulator):
        """Test async context manager with connection error."""
        simulator = SensorSimulator("test_sim", mock_mqtt_simulator, "test/topic")
        
        mock_mqtt_simulator.connect.side_effect = Exception("Connection failed")
        
        with pytest.raises(ConnectionError):
            async with simulator:
                pass
                
        mock_mqtt_simulator.connect.assert_called_once()
        mock_mqtt_simulator.disconnect.assert_not_called()

    @pytest.mark.asyncio
    async def test_context_manager_disconnect_error(self, mock_mqtt_simulator):
        """Test async context manager with disconnect error."""
        simulator = SensorSimulator("test_sim", mock_mqtt_simulator, "test/topic")
        
        mock_mqtt_simulator.disconnect.side_effect = Exception("Disconnect error")
        
        # Should not raise exception from disconnect error
        async with simulator:
            pass
            
        mock_mqtt_simulator.connect.assert_called_once()
        mock_mqtt_simulator.disconnect.assert_called_once()

    def test_simulator_repr(self, mock_mqtt_simulator):
        """Test simulator string representation."""
        simulator = SensorSimulator("test_sim", mock_mqtt_simulator, "test/topic")
        
        mock_mqtt_simulator.is_connected.return_value = False
        repr_str = repr(simulator)
        
        assert "SensorSimulator" in repr_str
        assert "test_sim" in repr_str
        assert "disconnected" in repr_str
        
        mock_mqtt_simulator.is_connected.return_value = True
        repr_str = repr(simulator)
        assert "connected" in repr_str