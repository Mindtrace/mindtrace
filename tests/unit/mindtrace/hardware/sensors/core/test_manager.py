"""
Unit tests for SensorManager class.

Tests cover sensor registration, bulk operations, parallel execution,
and error handling for multiple sensors.
"""

import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch
from mindtrace.hardware.sensors.core.manager import SensorManager
from mindtrace.hardware.sensors.core.sensor import AsyncSensor


class TestSensorManager:
    """Test cases for SensorManager class."""

    def test_manager_initialization(self):
        """Test successful manager initialization."""
        manager = SensorManager()
        
        assert len(manager) == 0
        assert manager.sensor_count == 0
        assert manager.list_sensors() == []
        
    @patch('mindtrace.hardware.sensors.core.manager.create_backend')
    def test_register_sensor_success(self, mock_create_backend, mock_mqtt_backend, sample_mqtt_config):
        """Test successful sensor registration."""
        manager = SensorManager()
        mock_create_backend.return_value = mock_mqtt_backend
        
        sensor = manager.register_sensor(
            "test_sensor",
            "mqtt",
            sample_mqtt_config,
            "test/topic"
        )
        
        assert isinstance(sensor, AsyncSensor)
        assert "test_sensor" in manager
        assert len(manager) == 1
        assert manager.sensor_count == 1
        assert manager.list_sensors() == ["test_sensor"]
        
        mock_create_backend.assert_called_once_with("mqtt", **sample_mqtt_config)
        
    @patch('mindtrace.hardware.sensors.core.manager.create_backend')
    def test_register_multiple_sensors(self, mock_create_backend, mock_mqtt_backend, sample_mqtt_config):
        """Test registering multiple sensors."""
        manager = SensorManager()
        mock_create_backend.return_value = mock_mqtt_backend
        
        sensor1 = manager.register_sensor("sensor1", "mqtt", sample_mqtt_config, "topic1")
        sensor2 = manager.register_sensor("sensor2", "mqtt", sample_mqtt_config, "topic2")
        
        assert len(manager) == 2
        assert "sensor1" in manager
        assert "sensor2" in manager
        assert set(manager.list_sensors()) == {"sensor1", "sensor2"}
        
    def test_register_sensor_invalid_id(self):
        """Test sensor registration with invalid sensor_id."""
        manager = SensorManager()
        
        with pytest.raises(ValueError, match="sensor_id must be a non-empty string"):
            manager.register_sensor("", "mqtt", {}, "topic")
            
        with pytest.raises(ValueError, match="sensor_id must be a non-empty string"):
            manager.register_sensor(None, "mqtt", {}, "topic")
            
        with pytest.raises(ValueError, match="sensor_id must be a non-empty string"):
            manager.register_sensor(123, "mqtt", {}, "topic")
            
    @patch('mindtrace.hardware.sensors.core.manager.create_backend')
    def test_register_sensor_duplicate_id(self, mock_create_backend, mock_mqtt_backend, sample_mqtt_config):
        """Test registering sensor with duplicate ID."""
        manager = SensorManager()
        mock_create_backend.return_value = mock_mqtt_backend
        
        manager.register_sensor("test_sensor", "mqtt", sample_mqtt_config, "topic")
        
        with pytest.raises(ValueError, match="Sensor 'test_sensor' is already registered"):
            manager.register_sensor("test_sensor", "mqtt", sample_mqtt_config, "topic2")
            
    @patch('mindtrace.hardware.sensors.core.manager.create_backend')
    def test_register_sensor_strips_whitespace(self, mock_create_backend, mock_mqtt_backend, sample_mqtt_config):
        """Test that registration strips whitespace from sensor_id."""
        manager = SensorManager()
        mock_create_backend.return_value = mock_mqtt_backend
        
        sensor = manager.register_sensor("  test_sensor  ", "mqtt", sample_mqtt_config, "topic")
        
        assert "test_sensor" in manager
        assert sensor.sensor_id == "test_sensor"
        
    @patch('mindtrace.hardware.sensors.core.manager.create_backend')
    def test_register_sensor_backend_error(self, mock_create_backend, sample_mqtt_config):
        """Test sensor registration with backend creation error."""
        manager = SensorManager()
        mock_create_backend.side_effect = ValueError("Invalid backend type")
        
        with pytest.raises(ValueError, match="Invalid backend type"):
            manager.register_sensor("test_sensor", "invalid", sample_mqtt_config, "topic")
            
        assert len(manager) == 0

    @patch('mindtrace.hardware.sensors.core.manager.create_backend')
    def test_remove_sensor_success(self, mock_create_backend, mock_mqtt_backend, sample_mqtt_config):
        """Test successful sensor removal."""
        manager = SensorManager()
        mock_create_backend.return_value = mock_mqtt_backend
        
        manager.register_sensor("test_sensor", "mqtt", sample_mqtt_config, "topic")
        assert len(manager) == 1
        
        manager.remove_sensor("test_sensor")
        
        assert len(manager) == 0
        assert "test_sensor" not in manager
        
    def test_remove_sensor_not_found(self):
        """Test removing non-existent sensor."""
        manager = SensorManager()
        
        with pytest.raises(ValueError, match="Sensor 'nonexistent' is not registered"):
            manager.remove_sensor("nonexistent")
            
    @patch('mindtrace.hardware.sensors.core.manager.create_backend')
    def test_get_sensor_success(self, mock_create_backend, mock_mqtt_backend, sample_mqtt_config):
        """Test getting sensor by ID."""
        manager = SensorManager()
        mock_create_backend.return_value = mock_mqtt_backend
        
        registered_sensor = manager.register_sensor("test_sensor", "mqtt", sample_mqtt_config, "topic")
        retrieved_sensor = manager.get_sensor("test_sensor")
        
        assert retrieved_sensor is registered_sensor
        assert retrieved_sensor.sensor_id == "test_sensor"
        
    def test_get_sensor_not_found(self):
        """Test getting non-existent sensor."""
        manager = SensorManager()
        
        sensor = manager.get_sensor("nonexistent")
        assert sensor is None

    @pytest.mark.asyncio
    @patch('mindtrace.hardware.sensors.core.manager.create_backend')
    async def test_connect_all_success(self, mock_create_backend, mock_mqtt_backend, sample_mqtt_config):
        """Test connecting all sensors successfully."""
        manager = SensorManager()
        mock_create_backend.return_value = mock_mqtt_backend
        
        # Register multiple sensors
        manager.register_sensor("sensor1", "mqtt", sample_mqtt_config, "topic1")
        manager.register_sensor("sensor2", "mqtt", sample_mqtt_config, "topic2")
        
        results = await manager.connect_all()
        
        assert results == {"sensor1": True, "sensor2": True}
        assert mock_mqtt_backend.connect.call_count == 2

    @pytest.mark.asyncio
    @patch('mindtrace.hardware.sensors.core.manager.create_backend')
    async def test_connect_all_partial_failure(self, mock_create_backend, sample_mqtt_config):
        """Test connecting all sensors with some failures."""
        from mindtrace.hardware.sensors.backends.base import SensorBackend
        
        manager = SensorManager()
        
        # Create two different backends - one successful, one failing
        success_backend = AsyncMock(spec=SensorBackend)
        failure_backend = AsyncMock(spec=SensorBackend)
        failure_backend.connect.side_effect = ConnectionError("Connection failed")
        
        mock_create_backend.side_effect = [success_backend, failure_backend]
        
        manager.register_sensor("sensor1", "mqtt", sample_mqtt_config, "topic1")
        manager.register_sensor("sensor2", "mqtt", sample_mqtt_config, "topic2")
        
        results = await manager.connect_all()
        
        assert results == {"sensor1": True, "sensor2": False}
        success_backend.connect.assert_called_once()
        failure_backend.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_all_empty_manager(self):
        """Test connecting all sensors when manager is empty."""
        manager = SensorManager()
        
        results = await manager.connect_all()
        
        assert results == {}

    @pytest.mark.asyncio
    @patch('mindtrace.hardware.sensors.core.manager.create_backend')
    async def test_disconnect_all_success(self, mock_create_backend, mock_mqtt_backend, sample_mqtt_config):
        """Test disconnecting all sensors."""
        manager = SensorManager()
        mock_create_backend.return_value = mock_mqtt_backend
        
        manager.register_sensor("sensor1", "mqtt", sample_mqtt_config, "topic1")
        manager.register_sensor("sensor2", "mqtt", sample_mqtt_config, "topic2")
        
        await manager.disconnect_all()
        
        assert mock_mqtt_backend.disconnect.call_count == 2

    @pytest.mark.asyncio
    @patch('mindtrace.hardware.sensors.core.manager.create_backend')
    async def test_disconnect_all_with_errors(self, mock_create_backend, sample_mqtt_config):
        """Test disconnecting all sensors with some errors."""
        from mindtrace.hardware.sensors.backends.base import SensorBackend
        
        manager = SensorManager()
        
        # Create backend that raises error on disconnect
        error_backend = AsyncMock(spec=SensorBackend)
        error_backend.disconnect.side_effect = ConnectionError("Disconnect failed")
        
        mock_create_backend.return_value = error_backend
        
        manager.register_sensor("sensor1", "mqtt", sample_mqtt_config, "topic1")
        
        # Should not raise exception, just log warnings
        await manager.disconnect_all()
        
        error_backend.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_all_empty_manager(self):
        """Test disconnecting all sensors when manager is empty."""
        manager = SensorManager()
        
        # Should not raise exception
        await manager.disconnect_all()

    @pytest.mark.asyncio
    @patch('mindtrace.hardware.sensors.core.manager.create_backend')
    async def test_read_all_success(self, mock_create_backend, mock_mqtt_backend, sample_mqtt_config, sample_sensor_data):
        """Test reading from all sensors successfully."""
        manager = SensorManager()
        mock_create_backend.return_value = mock_mqtt_backend
        mock_mqtt_backend.is_connected.return_value = True  # Mock as connected
        mock_mqtt_backend.read_data.return_value = sample_sensor_data
        
        manager.register_sensor("sensor1", "mqtt", sample_mqtt_config, "topic1")
        manager.register_sensor("sensor2", "mqtt", sample_mqtt_config, "topic2")
        
        results = await manager.read_all()
        
        assert "sensor1" in results
        assert "sensor2" in results
        assert results["sensor1"] == sample_sensor_data
        assert results["sensor2"] == sample_sensor_data
        assert mock_mqtt_backend.read_data.call_count == 2

    @pytest.mark.asyncio
    @patch('mindtrace.hardware.sensors.core.manager.create_backend')
    async def test_read_all_with_no_data(self, mock_create_backend, mock_mqtt_backend, sample_mqtt_config):
        """Test reading from all sensors when some return no data."""
        manager = SensorManager()
        mock_create_backend.return_value = mock_mqtt_backend
        mock_mqtt_backend.is_connected.return_value = True  # Mock as connected
        mock_mqtt_backend.read_data.return_value = None
        
        manager.register_sensor("sensor1", "mqtt", sample_mqtt_config, "topic1")
        
        results = await manager.read_all()
        
        assert results["sensor1"] == {"error": "No data available"}

    @pytest.mark.asyncio
    @patch('mindtrace.hardware.sensors.core.manager.create_backend')
    async def test_read_all_with_errors(self, mock_create_backend, sample_mqtt_config):
        """Test reading from all sensors with some errors."""
        from mindtrace.hardware.sensors.backends.base import SensorBackend
        
        manager = SensorManager()
        
        error_backend = AsyncMock(spec=SensorBackend)
        error_backend.is_connected.return_value = True  # Mock as connected
        error_backend.read_data.side_effect = TimeoutError("Read timeout")
        
        mock_create_backend.return_value = error_backend
        
        manager.register_sensor("sensor1", "mqtt", sample_mqtt_config, "topic1")
        
        results = await manager.read_all()
        
        assert results["sensor1"] == {"error": "Read timeout"}

    @pytest.mark.asyncio
    async def test_read_all_empty_manager(self):
        """Test reading from all sensors when manager is empty."""
        manager = SensorManager()
        
        results = await manager.read_all()
        
        assert results == {}

    def test_manager_len_and_contains(self):
        """Test manager length and containment operations."""
        manager = SensorManager()
        
        assert len(manager) == 0
        assert "test_sensor" not in manager
        
        # Mock the registration to avoid backend creation
        with patch('mindtrace.hardware.sensors.core.manager.create_backend') as mock_create:
            from mindtrace.hardware.sensors.backends.base import SensorBackend
            mock_backend = AsyncMock(spec=SensorBackend)
            mock_create.return_value = mock_backend
            
            manager.register_sensor("test_sensor", "mqtt", {}, "topic")
            
            assert len(manager) == 1
            assert "test_sensor" in manager
            assert "other_sensor" not in manager

    def test_manager_repr(self):
        """Test manager string representation."""
        manager = SensorManager()
        
        repr_str = repr(manager)
        assert "SensorManager" in repr_str
        assert "sensors=0" in repr_str
        
        with patch('mindtrace.hardware.sensors.core.manager.create_backend') as mock_create:
            from mindtrace.hardware.sensors.backends.base import SensorBackend
            mock_backend = AsyncMock(spec=SensorBackend)
            mock_create.return_value = mock_backend
            
            manager.register_sensor("test_sensor", "mqtt", {}, "topic")
            
            repr_str = repr(manager)
            assert "sensors=1" in repr_str