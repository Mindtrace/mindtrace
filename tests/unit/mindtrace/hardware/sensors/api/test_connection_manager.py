"""
Unit tests for SensorConnectionManager.

Tests cover connection manager initialization, endpoint calls, convenience methods,
and error handling scenarios.

NOTE: These tests are currently deferred as the service infrastructure (MCP client communication)
is not fully implemented. The SensorConnectionManager needs the base infrastructure to be 
completed before these tests can be properly implemented and run.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from mindtrace.hardware.api.sensors.connection_manager import SensorConnectionManager

# Skip all connection manager tests due to missing service infrastructure
pytestmark = pytest.mark.skip(reason="Service infrastructure not implemented - SensorConnectionManager needs MCP client support")
from mindtrace.hardware.api.sensors.models import (
    SensorConnectionRequest,
    SensorConnectionResponse,
    SensorDataRequest,
    SensorDataResponse,
    SensorStatusRequest,
    SensorStatusResponse,
    SensorListRequest,
    SensorListResponse,
    SensorInfo,
    SensorConnectionStatus,
)


class TestSensorConnectionManager:
    """Test cases for SensorConnectionManager class."""

    def test_connection_manager_initialization_default(self):
        """Test connection manager initialization with default service name."""
        manager = SensorConnectionManager()
        
        # Should call parent constructor with default service name
        assert hasattr(manager, '_service_name') or hasattr(manager, 'service_name')

    def test_connection_manager_initialization_custom_service(self):
        """Test connection manager initialization with custom service name."""
        custom_name = "custom_sensor_service"
        manager = SensorConnectionManager(service_name=custom_name)
        
        # Should call parent constructor with custom service name
        assert hasattr(manager, '_service_name') or hasattr(manager, 'service_name')

    @pytest.mark.asyncio
    async def test_connect_sensor_success(self):
        """Test successful sensor connection."""
        manager = SensorConnectionManager()
        
        # Mock the call_endpoint method
        mock_response = {
            "success": True,
            "sensor_id": "test_sensor",
            "status": "connected",
            "message": "Successfully connected"
        }
        
        with patch.object(manager, 'call_endpoint', new_callable=AsyncMock, return_value=mock_response):
            result = await manager.connect_sensor(
                sensor_id="test_sensor",
                backend_type="mqtt",
                config={"broker_url": "mqtt://test:1883"},
                address="test/topic"
            )
            
            assert isinstance(result, SensorConnectionResponse)
            assert result.success is True
            assert result.sensor_id == "test_sensor"
            assert result.status == SensorConnectionStatus.CONNECTED
            assert "Successfully connected" in result.message
            
            # Verify the endpoint was called correctly
            manager.call_endpoint.assert_called_once()
            args = manager.call_endpoint.call_args
            assert args[0][0] == "connect_sensor"
            request = args[0][1]
            assert isinstance(request, SensorConnectionRequest)
            assert request.sensor_id == "test_sensor"
            assert request.backend_type == "mqtt"
            assert request.config == {"broker_url": "mqtt://test:1883"}
            assert request.address == "test/topic"

    @pytest.mark.asyncio
    async def test_disconnect_sensor_success(self):
        """Test successful sensor disconnection."""
        manager = SensorConnectionManager()
        
        mock_response = {
            "success": True,
            "sensor_id": "test_sensor",
            "status": "disconnected",
            "message": "Successfully disconnected"
        }
        
        with patch.object(manager, 'call_endpoint', new_callable=AsyncMock, return_value=mock_response):
            result = await manager.disconnect_sensor("test_sensor")
            
            assert isinstance(result, SensorConnectionResponse)
            assert result.success is True
            assert result.sensor_id == "test_sensor"
            assert result.status == SensorConnectionStatus.DISCONNECTED
            
            # Verify the endpoint was called correctly
            manager.call_endpoint.assert_called_once()
            args = manager.call_endpoint.call_args
            assert args[0][0] == "disconnect_sensor"
            request = args[0][1]
            assert isinstance(request, SensorStatusRequest)
            assert request.sensor_id == "test_sensor"

    @pytest.mark.asyncio
    async def test_read_sensor_data_success(self):
        """Test successful sensor data reading."""
        manager = SensorConnectionManager()
        
        mock_response = {
            "success": True,
            "sensor_id": "test_sensor",
            "data": {"temperature": 23.5, "humidity": 45.2},
            "timestamp": 1640995200.0,
            "message": "Data read successfully"
        }
        
        with patch.object(manager, 'call_endpoint', new_callable=AsyncMock, return_value=mock_response):
            result = await manager.read_sensor_data("test_sensor", timeout=5.0)
            
            assert isinstance(result, SensorDataResponse)
            assert result.success is True
            assert result.sensor_id == "test_sensor"
            assert result.data == {"temperature": 23.5, "humidity": 45.2}
            assert result.timestamp == 1640995200.0
            
            # Verify the endpoint was called correctly
            manager.call_endpoint.assert_called_once()
            args = manager.call_endpoint.call_args
            assert args[0][0] == "read_sensor_data"
            request = args[0][1]
            assert isinstance(request, SensorDataRequest)
            assert request.sensor_id == "test_sensor"
            assert request.timeout == 5.0

    @pytest.mark.asyncio
    async def test_read_sensor_data_no_timeout(self):
        """Test reading sensor data without timeout parameter."""
        manager = SensorConnectionManager()
        
        mock_response = {
            "success": True,
            "sensor_id": "test_sensor",
            "data": None,
            "timestamp": None,
            "message": "No data available"
        }
        
        with patch.object(manager, 'call_endpoint', new_callable=AsyncMock, return_value=mock_response):
            result = await manager.read_sensor_data("test_sensor")
            
            # Verify timeout is None when not provided
            args = manager.call_endpoint.call_args
            request = args[0][1]
            assert request.timeout is None

    @pytest.mark.asyncio
    async def test_get_sensor_status_success(self):
        """Test getting sensor status successfully."""
        manager = SensorConnectionManager()
        
        mock_response = {
            "success": True,
            "sensor_info": {
                "sensor_id": "test_sensor",
                "backend_type": "mqtt",
                "address": "test/topic",
                "status": "connected",
                "last_data_time": 1640995200.0
            },
            "message": "Status retrieved successfully"
        }
        
        with patch.object(manager, 'call_endpoint', new_callable=AsyncMock, return_value=mock_response):
            result = await manager.get_sensor_status("test_sensor")
            
            assert isinstance(result, SensorStatusResponse)
            assert result.success is True
            assert result.sensor_info is not None
            assert result.sensor_info.sensor_id == "test_sensor"
            assert result.sensor_info.backend_type == "mqtt"
            assert result.sensor_info.status == SensorConnectionStatus.CONNECTED
            
            # Verify the endpoint was called correctly
            manager.call_endpoint.assert_called_once()
            args = manager.call_endpoint.call_args
            assert args[0][0] == "get_sensor_status"
            request = args[0][1]
            assert isinstance(request, SensorStatusRequest)
            assert request.sensor_id == "test_sensor"

    @pytest.mark.asyncio
    async def test_list_sensors_with_status(self):
        """Test listing sensors with status information."""
        manager = SensorConnectionManager()
        
        mock_response = {
            "success": True,
            "sensors": [
                {
                    "sensor_id": "sensor1",
                    "backend_type": "mqtt",
                    "address": "topic1",
                    "status": "connected",
                    "last_data_time": 1640995200.0
                },
                {
                    "sensor_id": "sensor2",
                    "backend_type": "http",
                    "address": "endpoint2",
                    "status": "connected",
                    "last_data_time": None
                }
            ],
            "count": 2,
            "message": "Retrieved 2 sensors"
        }
        
        with patch.object(manager, 'call_endpoint', new_callable=AsyncMock, return_value=mock_response):
            result = await manager.list_sensors(include_status=True)
            
            assert isinstance(result, SensorListResponse)
            assert result.success is True
            assert len(result.sensors) == 2
            assert result.count == 2
            
            # Check first sensor
            assert result.sensors[0].sensor_id == "sensor1"
            assert result.sensors[0].backend_type == "mqtt"
            assert result.sensors[0].last_data_time == 1640995200.0
            
            # Verify the endpoint was called correctly
            manager.call_endpoint.assert_called_once()
            args = manager.call_endpoint.call_args
            assert args[0][0] == "list_sensors"
            request = args[0][1]
            assert isinstance(request, SensorListRequest)
            assert request.include_status is True

    @pytest.mark.asyncio
    async def test_list_sensors_without_status(self):
        """Test listing sensors without status information."""
        manager = SensorConnectionManager()
        
        mock_response = {
            "success": True,
            "sensors": [],
            "count": 0,
            "message": "Retrieved 0 sensors"
        }
        
        with patch.object(manager, 'call_endpoint', new_callable=AsyncMock, return_value=mock_response):
            result = await manager.list_sensors(include_status=False)
            
            assert result.success is True
            assert result.count == 0
            
            # Verify include_status is False
            args = manager.call_endpoint.call_args
            request = args[0][1]
            assert request.include_status is False

    @pytest.mark.asyncio
    async def test_connect_mqtt_sensor_convenience_method(self):
        """Test MQTT sensor convenience method."""
        manager = SensorConnectionManager()
        
        mock_response = {
            "success": True,
            "sensor_id": "mqtt_sensor",
            "status": "connected",
            "message": "Successfully connected to MQTT sensor"
        }
        
        with patch.object(manager, 'call_endpoint', new_callable=AsyncMock, return_value=mock_response):
            result = await manager.connect_mqtt_sensor(
                sensor_id="mqtt_sensor",
                broker_url="mqtt://localhost:1883",
                identifier="test_client",
                address="sensors/temperature"
            )
            
            assert result.success is True
            assert result.sensor_id == "mqtt_sensor"
            
            # Verify the endpoint was called with correct parameters
            args = manager.call_endpoint.call_args
            request = args[0][1]
            assert request.backend_type == "mqtt"
            assert request.config == {
                "broker_url": "mqtt://localhost:1883",
                "identifier": "test_client"
            }
            assert request.address == "sensors/temperature"

    @pytest.mark.asyncio
    async def test_connect_http_sensor_convenience_method(self):
        """Test HTTP sensor convenience method."""
        manager = SensorConnectionManager()
        
        mock_response = {
            "success": True,
            "sensor_id": "http_sensor",
            "status": "connected",
            "message": "Successfully connected to HTTP sensor"
        }
        
        with patch.object(manager, 'call_endpoint', new_callable=AsyncMock, return_value=mock_response):
            result = await manager.connect_http_sensor(
                sensor_id="http_sensor",
                base_url="http://api.sensors.com",
                address="/sensors/temperature",
                headers={"Authorization": "Bearer token123"}
            )
            
            assert result.success is True
            assert result.sensor_id == "http_sensor"
            
            # Verify the endpoint was called with correct parameters
            args = manager.call_endpoint.call_args
            request = args[0][1]
            assert request.backend_type == "http"
            assert request.config == {
                "base_url": "http://api.sensors.com",
                "headers": {"Authorization": "Bearer token123"}
            }
            assert request.address == "/sensors/temperature"

    @pytest.mark.asyncio
    async def test_connect_http_sensor_no_headers(self):
        """Test HTTP sensor convenience method without headers."""
        manager = SensorConnectionManager()
        
        mock_response = {
            "success": True,
            "sensor_id": "http_sensor",
            "status": "connected",
            "message": "Successfully connected"
        }
        
        with patch.object(manager, 'call_endpoint', new_callable=AsyncMock, return_value=mock_response):
            await manager.connect_http_sensor(
                sensor_id="http_sensor",
                base_url="http://api.sensors.com",
                address="/sensors/temperature"
            )
            
            # Verify headers defaults to empty dict
            args = manager.call_endpoint.call_args
            request = args[0][1]
            assert request.config["headers"] == {}

    @pytest.mark.asyncio
    async def test_connect_serial_sensor_convenience_method(self):
        """Test serial sensor convenience method."""
        manager = SensorConnectionManager()
        
        mock_response = {
            "success": True,
            "sensor_id": "serial_sensor",
            "status": "connected",
            "message": "Successfully connected to Serial sensor"
        }
        
        with patch.object(manager, 'call_endpoint', new_callable=AsyncMock, return_value=mock_response):
            result = await manager.connect_serial_sensor(
                sensor_id="serial_sensor",
                port="/dev/ttyUSB0",
                baudrate=115200,
                timeout=2.0
            )
            
            assert result.success is True
            assert result.sensor_id == "serial_sensor"
            
            # Verify the endpoint was called with correct parameters
            args = manager.call_endpoint.call_args
            request = args[0][1]
            assert request.backend_type == "serial"
            assert request.config == {
                "port": "/dev/ttyUSB0",
                "baudrate": 115200,
                "timeout": 2.0
            }
            assert request.address == "/dev/ttyUSB0"  # Address should be same as port

    @pytest.mark.asyncio
    async def test_connect_serial_sensor_default_params(self):
        """Test serial sensor convenience method with default parameters."""
        manager = SensorConnectionManager()
        
        mock_response = {
            "success": True,
            "sensor_id": "serial_sensor",
            "status": "connected",
            "message": "Successfully connected"
        }
        
        with patch.object(manager, 'call_endpoint', new_callable=AsyncMock, return_value=mock_response):
            await manager.connect_serial_sensor(
                sensor_id="serial_sensor",
                port="/dev/ttyUSB0"
            )
            
            # Verify default values are used
            args = manager.call_endpoint.call_args
            request = args[0][1]
            assert request.config["baudrate"] == 9600
            assert request.config["timeout"] == 1.0

    @pytest.mark.asyncio
    async def test_endpoint_call_error_handling(self):
        """Test error handling when endpoint calls fail."""
        manager = SensorConnectionManager()
        
        # Mock call_endpoint to raise an exception
        with patch.object(manager, 'call_endpoint', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("Connection failed")
            
            with pytest.raises(Exception, match="Connection failed"):
                await manager.connect_sensor(
                    sensor_id="test_sensor",
                    backend_type="mqtt",
                    config={"broker_url": "mqtt://test:1883"},
                    address="test/topic"
                )

    @pytest.mark.asyncio
    async def test_multiple_concurrent_operations(self):
        """Test handling multiple concurrent operations."""
        import asyncio
        
        manager = SensorConnectionManager()
        
        # Mock different responses for different operations
        mock_responses = [
            {
                "success": True,
                "sensor_id": "sensor1",
                "status": "connected",
                "message": "Connected"
            },
            {
                "success": True,
                "sensor_id": "sensor2",
                "data": {"temp": 25.0},
                "timestamp": 1640995200.0,
                "message": "Data read"
            },
            {
                "success": True,
                "sensors": [],
                "count": 0,
                "message": "No sensors"
            }
        ]
        
        with patch.object(manager, 'call_endpoint', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = mock_responses
            
            # Execute multiple operations concurrently
            results = await asyncio.gather(
                manager.connect_sensor("sensor1", "mqtt", {"broker_url": "mqtt://test:1883"}, "topic1"),
                manager.read_sensor_data("sensor2"),
                manager.list_sensors(include_status=False),
                return_exceptions=True
            )
            
            # All operations should complete successfully
            assert len(results) == 3
            assert all(not isinstance(result, Exception) for result in results)
            assert results[0].sensor_id == "sensor1"
            assert results[1].data == {"temp": 25.0}
            assert results[2].count == 0

    @pytest.mark.asyncio
    async def test_response_deserialization(self):
        """Test that responses are properly deserialized to typed objects."""
        manager = SensorConnectionManager()
        
        # Test with response containing nested objects
        mock_response = {
            "success": True,
            "sensor_info": {
                "sensor_id": "complex_sensor",
                "backend_type": "mqtt",
                "address": "complex/topic",
                "status": "connected",
                "last_data_time": 1640995200.5
            },
            "message": "Status retrieved"
        }
        
        with patch.object(manager, 'call_endpoint', new_callable=AsyncMock, return_value=mock_response):
            result = await manager.get_sensor_status("complex_sensor")
            
            # Verify nested object deserialization
            assert isinstance(result, SensorStatusResponse)
            assert isinstance(result.sensor_info, SensorInfo)
            assert result.sensor_info.last_data_time == 1640995200.5
            assert result.sensor_info.status == SensorConnectionStatus.CONNECTED

    def test_parameter_validation_through_pydantic_models(self):
        """Test that invalid parameters are caught by Pydantic models."""
        # Test SensorConnectionRequest validation
        with pytest.raises(ValueError):
            SensorConnectionRequest(
                sensor_id="",  # Invalid: empty sensor_id
                backend_type="mqtt",
                config={},
                address="test/topic"
            )

    @pytest.mark.asyncio
    async def test_convenience_methods_parameter_handling(self):
        """Test that convenience methods properly handle all parameter types."""
        manager = SensorConnectionManager()
        
        mock_response = {"success": True, "sensor_id": "test", "status": "connected", "message": "OK"}
        
        with patch.object(manager, 'call_endpoint', new_callable=AsyncMock, return_value=mock_response):
            # Test all convenience methods with various parameter types
            await manager.connect_mqtt_sensor(
                sensor_id="mqtt_test",
                broker_url="mqtt://broker:1883",
                identifier="client_123",
                address="sensors/data"
            )
            
            await manager.connect_http_sensor(
                sensor_id="http_test",
                base_url="https://api.example.com",
                address="/data",
                headers={"Custom-Header": "value"}
            )
            
            await manager.connect_serial_sensor(
                sensor_id="serial_test",
                port="COM1",
                baudrate=115200,
                timeout=5.0
            )
            
            # Verify all calls were made
            assert manager.call_endpoint.call_count == 3