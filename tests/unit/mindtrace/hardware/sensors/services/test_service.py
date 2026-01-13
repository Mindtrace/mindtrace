"""
Unit tests for SensorManagerService.

Tests cover service initialization, endpoint registration, sensor operations,
error handling, and integration with the underlying SensorManager.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from mindtrace.hardware.services.sensors.models import (
    SensorConnectionRequest,
    SensorConnectionResponse,
    SensorConnectionStatus,
    SensorDataRequest,
    SensorDataResponse,
    SensorListRequest,
    SensorListResponse,
    SensorStatusRequest,
    SensorStatusResponse,
)
from mindtrace.hardware.services.sensors.service import SensorManagerService
from mindtrace.hardware.sensors.core.manager import SensorManager


class TestSensorManagerService:
    """Test cases for SensorManagerService class."""

    def test_service_initialization_default_manager(self):
        """Test service initialization with default manager."""
        service = SensorManagerService()

        assert service._manager is not None
        assert isinstance(service._manager, SensorManager)
        assert service._last_data_times == {}

    def test_service_initialization_custom_manager(self):
        """Test service initialization with custom manager."""
        custom_manager = Mock(spec=SensorManager)
        service = SensorManagerService(manager=custom_manager)

        assert service._manager is custom_manager
        assert service._last_data_times == {}

    def test_manager_property(self):
        """Test manager property access."""
        custom_manager = Mock(spec=SensorManager)
        service = SensorManagerService(manager=custom_manager)

        assert service.manager is custom_manager

    @pytest.mark.asyncio
    async def test_connect_sensor_success(self):
        """Test successful sensor connection."""
        mock_manager = Mock(spec=SensorManager)
        mock_sensor = AsyncMock()
        mock_manager.register_sensor.return_value = mock_sensor

        service = SensorManagerService(manager=mock_manager)

        request = SensorConnectionRequest(
            sensor_id="test_sensor",
            backend_type="mqtt",
            config={"broker_url": "mqtt://test:1883"},
            address="test/topic",
        )

        response = await service.connect_sensor(request)

        assert isinstance(response, SensorConnectionResponse)
        assert response.success is True
        assert response.sensor_id == "test_sensor"
        assert response.status == SensorConnectionStatus.CONNECTED
        assert "Successfully connected to mqtt sensor" in response.message

        mock_manager.register_sensor.assert_called_once_with(
            sensor_id="test_sensor",
            backend_type="mqtt",
            connection_params={"broker_url": "mqtt://test:1883"},
            address="test/topic",
        )
        mock_sensor.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_sensor_registration_failure(self):
        """Test sensor connection with registration failure."""
        mock_manager = Mock(spec=SensorManager)
        mock_manager.register_sensor.side_effect = ValueError("Invalid backend type")

        service = SensorManagerService(manager=mock_manager)

        request = SensorConnectionRequest(
            sensor_id="test_sensor", backend_type="invalid", config={}, address="test/topic"
        )

        response = await service.connect_sensor(request)

        assert isinstance(response, SensorConnectionResponse)
        assert response.success is False
        assert response.sensor_id == "test_sensor"
        assert response.status == SensorConnectionStatus.ERROR
        assert "Failed to connect sensor: Invalid backend type" in response.message

    @pytest.mark.asyncio
    async def test_connect_sensor_connection_failure(self):
        """Test sensor connection with connection failure."""
        mock_manager = Mock(spec=SensorManager)
        mock_sensor = AsyncMock()
        mock_sensor.connect.side_effect = ConnectionError("Connection refused")
        mock_manager.register_sensor.return_value = mock_sensor

        service = SensorManagerService(manager=mock_manager)

        request = SensorConnectionRequest(
            sensor_id="test_sensor",
            backend_type="mqtt",
            config={"broker_url": "mqtt://test:1883"},
            address="test/topic",
        )

        response = await service.connect_sensor(request)

        assert response.success is False
        assert response.status == SensorConnectionStatus.ERROR
        assert "Failed to connect sensor: Connection refused" in response.message

    @pytest.mark.asyncio
    async def test_disconnect_sensor_success(self):
        """Test successful sensor disconnection."""
        mock_manager = Mock(spec=SensorManager)
        mock_sensor = AsyncMock()
        mock_manager.get_sensor.return_value = mock_sensor

        service = SensorManagerService(manager=mock_manager)
        service._last_data_times = {"test_sensor": 123456.0}

        request = SensorStatusRequest(sensor_id="test_sensor")

        response = await service.disconnect_sensor(request)

        assert isinstance(response, SensorConnectionResponse)
        assert response.success is True
        assert response.sensor_id == "test_sensor"
        assert response.status == SensorConnectionStatus.DISCONNECTED
        assert "Successfully disconnected sensor" in response.message

        mock_sensor.disconnect.assert_called_once()
        mock_manager.remove_sensor.assert_called_once_with("test_sensor")
        assert "test_sensor" not in service._last_data_times

    @pytest.mark.asyncio
    async def test_disconnect_sensor_not_found(self):
        """Test disconnecting non-existent sensor."""
        mock_manager = Mock(spec=SensorManager)
        mock_manager.get_sensor.return_value = None

        service = SensorManagerService(manager=mock_manager)

        request = SensorStatusRequest(sensor_id="nonexistent")

        response = await service.disconnect_sensor(request)

        # Should still succeed even if sensor doesn't exist
        assert response.success is True
        assert response.status == SensorConnectionStatus.DISCONNECTED

    @pytest.mark.asyncio
    async def test_disconnect_sensor_error(self):
        """Test sensor disconnection with error."""
        mock_manager = Mock(spec=SensorManager)
        mock_sensor = AsyncMock()
        mock_sensor.disconnect.side_effect = ConnectionError("Disconnect failed")
        mock_manager.get_sensor.return_value = mock_sensor

        service = SensorManagerService(manager=mock_manager)

        request = SensorStatusRequest(sensor_id="test_sensor")

        response = await service.disconnect_sensor(request)

        assert response.success is False
        assert response.status == SensorConnectionStatus.ERROR
        assert "Failed to disconnect sensor: Disconnect failed" in response.message

    @pytest.mark.asyncio
    async def test_read_sensor_data_success(self):
        """Test successful sensor data reading."""
        mock_manager = Mock(spec=SensorManager)
        mock_sensor = AsyncMock()
        test_data = {"temperature": 23.5, "humidity": 45.2}
        mock_sensor.read.return_value = test_data
        mock_manager.get_sensor.return_value = mock_sensor

        service = SensorManagerService(manager=mock_manager)

        request = SensorDataRequest(sensor_id="test_sensor")

        with patch("time.time", return_value=123456.0):
            response = await service.read_sensor_data(request)

        assert isinstance(response, SensorDataResponse)
        assert response.success is True
        assert response.sensor_id == "test_sensor"
        assert response.data == test_data
        assert response.timestamp == 123456.0
        assert "Data read successfully" in response.message
        assert service._last_data_times["test_sensor"] == 123456.0

    @pytest.mark.asyncio
    async def test_read_sensor_data_no_data(self):
        """Test reading sensor data when no data available."""
        mock_manager = Mock(spec=SensorManager)
        mock_sensor = AsyncMock()
        mock_sensor.read.return_value = None
        mock_manager.get_sensor.return_value = mock_sensor

        service = SensorManagerService(manager=mock_manager)

        request = SensorDataRequest(sensor_id="test_sensor")

        with patch("time.time", return_value=123456.0):
            response = await service.read_sensor_data(request)

        assert response.success is True
        assert response.data is None
        assert response.timestamp == 123456.0
        assert "No data available" in response.message

    @pytest.mark.asyncio
    async def test_read_sensor_data_sensor_not_found(self):
        """Test reading data from non-existent sensor."""
        mock_manager = Mock(spec=SensorManager)
        mock_manager.get_sensor.return_value = None

        service = SensorManagerService(manager=mock_manager)

        request = SensorDataRequest(sensor_id="nonexistent")

        response = await service.read_sensor_data(request)

        assert response.success is False
        assert response.sensor_id == "nonexistent"
        assert response.data is None
        assert response.timestamp is None
        assert "Sensor 'nonexistent' not found" in response.message

    @pytest.mark.asyncio
    async def test_read_sensor_data_read_error(self):
        """Test reading sensor data with read error."""
        mock_manager = Mock(spec=SensorManager)
        mock_sensor = AsyncMock()
        mock_sensor.read.side_effect = TimeoutError("Read timeout")
        mock_manager.get_sensor.return_value = mock_sensor

        service = SensorManagerService(manager=mock_manager)

        request = SensorDataRequest(sensor_id="test_sensor")

        response = await service.read_sensor_data(request)

        assert response.success is False
        assert response.data is None
        assert "Failed to read sensor data: Read timeout" in response.message

    @pytest.mark.asyncio
    async def test_get_sensor_status_success(self):
        """Test getting sensor status successfully."""
        mock_manager = Mock(spec=SensorManager)
        mock_sensor = Mock()
        mock_sensor._backend = Mock()
        mock_sensor._backend.__class__.__name__ = "MQTTSensorBackend"
        mock_sensor._address = "test/topic"
        mock_manager.get_sensor.return_value = mock_sensor

        service = SensorManagerService(manager=mock_manager)
        service._last_data_times = {"test_sensor": 123456.0}

        request = SensorStatusRequest(sensor_id="test_sensor")

        response = await service.get_sensor_status(request)

        assert isinstance(response, SensorStatusResponse)
        assert response.success is True
        assert response.sensor_info is not None
        assert response.sensor_info.sensor_id == "test_sensor"
        assert response.sensor_info.backend_type == "mqtt"
        assert response.sensor_info.address == "test/topic"
        assert response.sensor_info.status == SensorConnectionStatus.CONNECTED
        assert response.sensor_info.last_data_time == 123456.0
        assert "Status retrieved successfully" in response.message

    @pytest.mark.asyncio
    async def test_get_sensor_status_not_found(self):
        """Test getting status for non-existent sensor."""
        mock_manager = Mock(spec=SensorManager)
        mock_manager.get_sensor.return_value = None

        service = SensorManagerService(manager=mock_manager)

        request = SensorStatusRequest(sensor_id="nonexistent")

        response = await service.get_sensor_status(request)

        assert response.success is False
        assert response.sensor_info is None
        assert "Sensor 'nonexistent' not found" in response.message

    @pytest.mark.asyncio
    async def test_get_sensor_status_error(self):
        """Test getting sensor status with error."""
        mock_manager = Mock(spec=SensorManager)
        mock_manager.get_sensor.side_effect = Exception("Manager error")

        service = SensorManagerService(manager=mock_manager)

        request = SensorStatusRequest(sensor_id="test_sensor")

        response = await service.get_sensor_status(request)

        assert response.success is False
        assert response.sensor_info is None
        assert "Failed to get sensor status: Manager error" in response.message

    @pytest.mark.asyncio
    async def test_list_sensors_success(self):
        """Test listing sensors successfully."""
        mock_manager = Mock(spec=SensorManager)
        mock_manager.list_sensors.return_value = ["sensor1", "sensor2"]

        # Mock the _sensors dict access
        mock_sensor1 = Mock()
        mock_sensor1._backend.__class__.__name__ = "MQTTSensorBackend"
        mock_sensor1._address = "topic1"

        mock_sensor2 = Mock()
        mock_sensor2._backend.__class__.__name__ = "HTTPSensorBackend"
        mock_sensor2._address = "endpoint2"

        mock_manager._sensors = {"sensor1": mock_sensor1, "sensor2": mock_sensor2}

        service = SensorManagerService(manager=mock_manager)
        service._last_data_times = {"sensor1": 123456.0}

        request = SensorListRequest(include_status=True)

        response = await service.list_sensors(request)

        assert isinstance(response, SensorListResponse)
        assert response.success is True
        assert len(response.sensors) == 2
        assert response.count == 2
        assert "Retrieved 2 sensors" in response.message

        # Check sensor1 info
        sensor1_info = next(s for s in response.sensors if s.sensor_id == "sensor1")
        assert sensor1_info.backend_type == "mqtt"
        assert sensor1_info.address == "topic1"
        assert sensor1_info.last_data_time == 123456.0

        # Check sensor2 info
        sensor2_info = next(s for s in response.sensors if s.sensor_id == "sensor2")
        assert sensor2_info.backend_type == "http"
        assert sensor2_info.address == "endpoint2"
        assert sensor2_info.last_data_time is None

    @pytest.mark.asyncio
    async def test_list_sensors_no_status(self):
        """Test listing sensors without status information."""
        mock_manager = Mock(spec=SensorManager)
        mock_manager.list_sensors.return_value = ["sensor1"]

        mock_sensor = Mock()
        mock_sensor._backend.__class__.__name__ = "MQTTSensorBackend"
        mock_sensor._address = "topic1"
        mock_manager._sensors = {"sensor1": mock_sensor}

        service = SensorManagerService(manager=mock_manager)
        service._last_data_times = {"sensor1": 123456.0}

        request = SensorListRequest(include_status=False)

        response = await service.list_sensors(request)

        assert response.success is True
        assert len(response.sensors) == 1
        # When include_status=False, last_data_time should be None
        assert response.sensors[0].last_data_time is None

    @pytest.mark.asyncio
    async def test_list_sensors_empty(self):
        """Test listing sensors when no sensors are registered."""
        mock_manager = Mock(spec=SensorManager)
        mock_manager.list_sensors.return_value = []
        mock_manager._sensors = {}

        service = SensorManagerService(manager=mock_manager)

        request = SensorListRequest(include_status=False)

        response = await service.list_sensors(request)

        assert response.success is True
        assert len(response.sensors) == 0
        assert response.count == 0
        assert "Retrieved 0 sensors" in response.message

    @pytest.mark.asyncio
    async def test_list_sensors_error(self):
        """Test listing sensors with error."""
        mock_manager = Mock(spec=SensorManager)
        mock_manager.list_sensors.side_effect = Exception("Manager error")

        service = SensorManagerService(manager=mock_manager)

        request = SensorListRequest(include_status=False)

        response = await service.list_sensors(request)

        assert response.success is False
        assert len(response.sensors) == 0
        assert response.count == 0
        assert "Failed to list sensors: Manager error" in response.message

    @pytest.mark.asyncio
    async def test_list_sensors_with_missing_sensor_data(self):
        """Test listing sensors when some sensors are missing from _sensors dict."""
        mock_manager = Mock(spec=SensorManager)
        mock_manager.list_sensors.return_value = ["sensor1", "sensor2"]

        # Only sensor1 exists in _sensors dict, sensor2 is missing
        mock_sensor1 = Mock()
        mock_sensor1._backend.__class__.__name__ = "MQTTSensorBackend"
        mock_sensor1._address = "topic1"

        mock_manager._sensors = {"sensor1": mock_sensor1}  # sensor2 missing

        service = SensorManagerService(manager=mock_manager)

        request = SensorListRequest(include_status=True)

        response = await service.list_sensors(request)

        # Should only return sensor1, skip sensor2 since it's not in _sensors
        assert response.success is True
        assert len(response.sensors) == 1
        assert response.count == 1
        assert response.sensors[0].sensor_id == "sensor1"

    def test_backend_type_extraction(self):
        """Test backend type name extraction from class names."""
        mock_manager = Mock(spec=SensorManager)
        _ = SensorManagerService(manager=mock_manager)

        # Test different backend class names
        test_cases = [
            ("MQTTSensorBackend", "mqtt"),
            ("HTTPSensorBackend", "http"),
            ("SerialSensorBackend", "serial"),
            ("CustomSensorBackend", "custom"),
            ("SensorBackend", ""),  # Edge case
        ]

        for class_name, expected_type in test_cases:
            mock_backend = Mock()
            mock_backend.__class__.__name__ = class_name

            # Extract type using the same logic as the service
            backend_type = class_name.replace("SensorBackend", "").lower()
            assert backend_type == expected_type

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test service handling multiple concurrent operations."""
        import asyncio

        mock_manager = Mock(spec=SensorManager)
        mock_sensor = AsyncMock()
        mock_manager.get_sensor.return_value = mock_sensor
        mock_manager.register_sensor.return_value = mock_sensor

        service = SensorManagerService(manager=mock_manager)

        # Create multiple concurrent requests
        connect_request = SensorConnectionRequest(
            sensor_id="sensor1", backend_type="mqtt", config={"broker_url": "mqtt://test:1883"}, address="test/topic"
        )

        read_request = SensorDataRequest(sensor_id="sensor1")
        status_request = SensorStatusRequest(sensor_id="sensor1")

        # Execute operations concurrently
        results = await asyncio.gather(
            service.connect_sensor(connect_request),
            service.read_sensor_data(read_request),
            service.get_sensor_status(status_request),
            return_exceptions=True,
        )

        # All operations should complete (though some may fail due to sensor not existing)
        assert len(results) == 3
        for result in results:
            assert not isinstance(result, Exception)

    @pytest.mark.asyncio
    async def test_data_time_tracking(self):
        """Test that data read times are properly tracked."""
        mock_manager = Mock(spec=SensorManager)
        mock_sensor = AsyncMock()
        mock_sensor.read.return_value = {"test": "data"}
        mock_manager.get_sensor.return_value = mock_sensor

        service = SensorManagerService(manager=mock_manager)

        # Read data multiple times
        request = SensorDataRequest(sensor_id="test_sensor")

        with patch("time.time", return_value=100.0):
            response1 = await service.read_sensor_data(request)

        with patch("time.time", return_value=200.0):
            response2 = await service.read_sensor_data(request)

        assert response1.timestamp == 100.0
        assert response2.timestamp == 200.0
        assert service._last_data_times["test_sensor"] == 200.0  # Should be updated
