"""
Integration tests for the complete sensor system.

Tests cover end-to-end scenarios combining multiple components:
- Manager + Backend + Core sensor components
- Service + Manager integration
- Factory + Manager + Backend integration
- Error propagation across layers
- Performance and concurrency scenarios
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from mindtrace.hardware.api.sensors.models import (
    SensorConnectionRequest,
    SensorConnectionStatus,
    SensorDataRequest,
    SensorListRequest,
    SensorStatusRequest,
)
from mindtrace.hardware.api.sensors.service import SensorManagerService
from mindtrace.hardware.sensors.backends.base import SensorBackend
from mindtrace.hardware.sensors.core.factory import create_simulator_backend
from mindtrace.hardware.sensors.core.manager import SensorManager
from mindtrace.hardware.sensors.core.simulator import SensorSimulator


class TestSensorSystemIntegration:
    """Integration tests for the complete sensor system."""

    @pytest.mark.asyncio
    async def test_complete_sensor_lifecycle_with_manager(self, sample_mqtt_config, sample_sensor_data):
        """Test complete sensor lifecycle using SensorManager."""
        manager = SensorManager()

        # Mock the factory to return a mock backend
        with patch("mindtrace.hardware.sensors.core.manager.create_backend") as mock_create:
            mock_backend = AsyncMock(spec=SensorBackend)
            mock_backend.is_connected.return_value = True
            mock_backend.read_data.return_value = sample_sensor_data
            mock_create.return_value = mock_backend

            # Register and connect sensor
            sensor = manager.register_sensor("temp_sensor", "mqtt", sample_mqtt_config, "sensors/temp")
            await sensor.connect()

            # Read data
            data = await sensor.read()
            assert data == sample_sensor_data

            # Check sensor is in manager
            assert "temp_sensor" in manager
            assert len(manager) == 1

            # Disconnect and remove
            await sensor.disconnect()
            manager.remove_sensor("temp_sensor")

            assert "temp_sensor" not in manager
            assert len(manager) == 0

    @pytest.mark.asyncio
    async def test_service_manager_integration(self, sample_mqtt_config, sample_sensor_data):
        """Test SensorManagerService integration with underlying SensorManager."""
        # Create service with custom manager
        manager = SensorManager()
        service = SensorManagerService(manager=manager)

        # Ensure service uses the provided manager
        service._manager = manager

        # Mock the factory
        with patch("mindtrace.hardware.sensors.core.manager.create_backend") as mock_create:
            # Create a proper mock class to get the correct type name
            class MockMQTTSensorBackend(AsyncMock):
                pass

            mock_backend = MockMQTTSensorBackend(spec=SensorBackend)
            mock_backend.is_connected.return_value = True
            mock_backend.read_data.return_value = sample_sensor_data
            mock_create.return_value = mock_backend

            # Connect sensor through service
            connect_request = SensorConnectionRequest(
                sensor_id="service_sensor", backend_type="mqtt", config=sample_mqtt_config, address="sensors/temp"
            )

            connect_response = await service.connect_sensor(connect_request)
            assert connect_response.success is True
            assert connect_response.status == SensorConnectionStatus.CONNECTED

            # Verify sensor is in the underlying manager
            assert "service_sensor" in manager
            sensor = manager.get_sensor("service_sensor")
            assert sensor is not None

            # Read data through service
            read_request = SensorDataRequest(sensor_id="service_sensor")
            read_response = await service.read_sensor_data(read_request)

            assert read_response.success is True
            assert read_response.data == sample_sensor_data
            assert read_response.timestamp is not None

            # Get status through service
            status_request = SensorStatusRequest(sensor_id="service_sensor")
            status_response = await service.get_sensor_status(status_request)

            assert status_response.success is True
            assert status_response.sensor_info.sensor_id == "service_sensor"
            assert status_response.sensor_info.backend_type == "mockmqtt"

            # List sensors through service
            list_request = SensorListRequest(include_status=True)
            list_response = await service.list_sensors(list_request)

            assert list_response.success is True
            assert list_response.count == 1
            assert list_response.sensors[0].sensor_id == "service_sensor"

            # Disconnect through service
            disconnect_response = await service.disconnect_sensor(status_request)
            assert disconnect_response.success is True
            assert disconnect_response.status == SensorConnectionStatus.DISCONNECTED

            # Verify sensor is removed from manager
            assert "service_sensor" not in manager

    @pytest.mark.asyncio
    async def test_factory_manager_integration(self, sample_mqtt_config):
        """Test factory function integration with manager."""
        manager = SensorManager()

        # Test that manager can use factory-created backends
        with patch("mindtrace.hardware.sensors.backends.mqtt.aiomqtt") as mock_aiomqtt:
            mock_client = AsyncMock()
            mock_aiomqtt.Client.return_value = mock_client

            # Register sensor with MQTT backend (will use factory internally)
            sensor = manager.register_sensor("factory_sensor", "mqtt", sample_mqtt_config, "test/topic")

            # Verify sensor was created with correct backend type
            assert sensor._sensor_id == "factory_sensor"
            assert sensor._address == "test/topic"

            # Connect should work through the factory-created backend
            await sensor.connect()

            # Verify MQTT client was created correctly
            mock_aiomqtt.Client.assert_called_once()
            mock_client.__aenter__.assert_called_once()

            await sensor.disconnect()

    @pytest.mark.asyncio
    async def test_multiple_sensors_concurrent_operations(self, sample_mqtt_config, sample_sensor_data):
        """Test concurrent operations with multiple sensors."""
        manager = SensorManager()

        # Create multiple mock backends
        backends = {}
        for i in range(3):
            backend = AsyncMock(spec=SensorBackend)
            backend.is_connected.return_value = True
            backend.read_data.return_value = {**sample_sensor_data, "sensor_id": i}
            backends[f"sensor_{i}"] = backend

        with patch("mindtrace.hardware.sensors.core.manager.create_backend") as mock_create:

            def backend_side_effect(*args, **kwargs):
                # Return appropriate backend based on call order
                return backends[f"sensor_{mock_create.call_count - 1}"]

            mock_create.side_effect = backend_side_effect

            # Register multiple sensors
            sensors = []
            for i in range(3):
                sensor = manager.register_sensor(f"sensor_{i}", "mqtt", sample_mqtt_config, f"topic_{i}")
                sensors.append(sensor)

            # Connect all sensors concurrently
            connect_results = await manager.connect_all()
            assert all(connect_results.values())

            # Read from all sensors concurrently
            read_results = await manager.read_all()

            for i in range(3):
                sensor_id = f"sensor_{i}"
                assert sensor_id in read_results
                assert read_results[sensor_id]["sensor_id"] == i

            # Disconnect all sensors
            await manager.disconnect_all()

    @pytest.mark.asyncio
    async def test_error_propagation_across_layers(self, sample_mqtt_config):
        """Test error propagation from backend through manager to service."""
        manager = SensorManager()
        service = SensorManagerService(manager=manager)

        # Create a backend that will fail at different points
        with patch("mindtrace.hardware.sensors.core.manager.create_backend") as mock_create:
            mock_backend = AsyncMock(spec=SensorBackend)
            mock_backend.connect.side_effect = ConnectionError("MQTT broker unavailable")
            mock_create.return_value = mock_backend

            # Test error propagation through service layer
            connect_request = SensorConnectionRequest(
                sensor_id="error_sensor", backend_type="mqtt", config=sample_mqtt_config, address="sensors/error"
            )

            response = await service.connect_sensor(connect_request)

            # Error should be captured and returned in response
            assert response.success is False
            assert response.status == SensorConnectionStatus.ERROR
            assert "MQTT broker unavailable" in response.message

            # Sensor should not be registered due to connection failure
            assert "error_sensor" not in manager

    @pytest.mark.asyncio
    async def test_backend_factory_error_handling(self):
        """Test error handling in backend factory integration."""
        manager = SensorManager()

        # Test unknown backend type
        with pytest.raises(ValueError, match="Unknown backend type"):
            manager.register_sensor("bad_sensor", "unknown_backend", {}, "address")

        # Test missing required parameters
        with pytest.raises(TypeError):
            manager.register_sensor("incomplete_sensor", "mqtt", {}, "topic")  # Missing broker_url

    @pytest.mark.asyncio
    async def test_sensor_simulator_integration(self, sample_mqtt_config):
        """Test SensorSimulator integration with factory and backends."""

        with patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt") as mock_aiomqtt:
            mock_client = AsyncMock()
            mock_aiomqtt.Client.return_value = mock_client

            # Create simulator using factory
            simulator_backend = create_simulator_backend("mqtt", **sample_mqtt_config)
            simulator = SensorSimulator("temp_simulator", simulator_backend, "sensors/temp/data")

            # Test simulator lifecycle
            await simulator.connect()

            test_data = {"temperature": 25.5, "timestamp": 1640995200}
            await simulator.publish(test_data)

            await simulator.disconnect()

            # Verify MQTT operations were called
            mock_aiomqtt.Client.assert_called_once()
            mock_client.__aenter__.assert_called_once()
            mock_client.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_mixed_backend_types_integration(self, sample_mqtt_config):
        """Test integration with multiple backend types."""
        manager = SensorManager()

        # Mock different backend types
        mock_backends = {
            "mqtt": AsyncMock(spec=SensorBackend),
            "http": AsyncMock(spec=SensorBackend),
            "serial": AsyncMock(spec=SensorBackend),
        }

        for backend in mock_backends.values():
            backend.is_connected.return_value = True
            backend.read_data.return_value = {"value": 100}

        with patch("mindtrace.hardware.sensors.core.manager.create_backend") as mock_create:

            def backend_factory(*args, **kwargs):
                backend_type = args[0] if args else kwargs.get("backend_type", "mqtt")
                return mock_backends[backend_type]

            mock_create.side_effect = backend_factory

            # Register sensors with different backend types
            manager.register_sensor("mqtt_sensor", "mqtt", sample_mqtt_config, "mqtt/topic")
            manager.register_sensor("http_sensor", "http", {"base_url": "http://api.com"}, "/data")
            manager.register_sensor("serial_sensor", "serial", {"port": "/dev/ttyUSB0"}, "/dev/ttyUSB0")

            # Connect all sensors
            results = await manager.connect_all()
            assert all(results.values())

            # Read from all sensors
            read_results = await manager.read_all()
            assert len(read_results) == 3
            assert all("value" in data for data in read_results.values())

            # Disconnect all
            await manager.disconnect_all()

    @pytest.mark.asyncio
    async def test_service_persistence_across_operations(self, sample_mqtt_config, sample_sensor_data):
        """Test that service maintains state across multiple operations."""
        service = SensorManagerService()

        with patch("mindtrace.hardware.sensors.core.manager.create_backend") as mock_create:
            mock_backend = AsyncMock(spec=SensorBackend)
            mock_backend.is_connected.return_value = True
            mock_backend.read_data.return_value = sample_sensor_data
            mock_create.return_value = mock_backend

            # Connect sensor
            connect_request = SensorConnectionRequest(
                sensor_id="persistent_sensor",
                backend_type="mqtt",
                config=sample_mqtt_config,
                address="sensors/persistent",
            )

            await service.connect_sensor(connect_request)

            # Read data (should update last_data_times)
            read_request = SensorDataRequest(sensor_id="persistent_sensor")
            first_read = await service.read_sensor_data(read_request)

            # Verify data time tracking
            assert "persistent_sensor" in service._last_data_times
            first_timestamp = service._last_data_times["persistent_sensor"]

            # Read again after a small delay
            await asyncio.sleep(0.01)
            second_read = await service.read_sensor_data(read_request)
            second_timestamp = service._last_data_times["persistent_sensor"]

            # Timestamp should be updated
            assert second_timestamp > first_timestamp
            assert second_read.timestamp > first_read.timestamp

            # Disconnect should clean up tracking data
            status_request = SensorStatusRequest(sensor_id="persistent_sensor")
            await service.disconnect_sensor(status_request)

            assert "persistent_sensor" not in service._last_data_times

    @pytest.mark.asyncio
    async def test_context_manager_integration(self, sample_mqtt_config, sample_sensor_data):
        """Test sensor context manager integration with manager."""
        manager = SensorManager()

        with patch("mindtrace.hardware.sensors.core.manager.create_backend") as mock_create:
            mock_backend = AsyncMock(spec=SensorBackend)
            mock_backend.is_connected.return_value = True
            mock_backend.read_data.return_value = sample_sensor_data
            mock_create.return_value = mock_backend

            # Register sensor
            sensor = manager.register_sensor("ctx_sensor", "mqtt", sample_mqtt_config, "sensors/ctx")

            # Use sensor as context manager
            async with sensor:
                # Should be connected inside context
                assert sensor.is_connected

                # Can read data
                data = await sensor.read()
                assert data == sample_sensor_data

            # Should be disconnected after context
            mock_backend.disconnect.assert_called()

    def test_manager_thread_safety_simulation(self, sample_mqtt_config):
        """Test manager thread safety by simulating concurrent access."""
        import queue
        import threading

        manager = SensorManager()
        results = queue.Queue()
        errors = queue.Queue()

        def worker_register_sensor(worker_id):
            try:
                sensor_id = f"worker_{worker_id}_sensor"
                with patch("mindtrace.hardware.sensors.core.manager.create_backend") as mock_create:
                    mock_backend = AsyncMock(spec=SensorBackend)
                    mock_create.return_value = mock_backend

                    sensor = manager.register_sensor(sensor_id, "mqtt", sample_mqtt_config, f"topic_{worker_id}")
                    results.put(f"Worker {worker_id}: registered {sensor_id}")

                    # Try to get the sensor back
                    retrieved = manager.get_sensor(sensor_id)
                    assert retrieved is sensor
                    results.put(f"Worker {worker_id}: retrieved {sensor_id}")

            except Exception as e:
                errors.put(f"Worker {worker_id} error: {e}")

        # Create multiple worker threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker_register_sensor, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check results
        assert errors.empty(), f"Errors occurred: {list(errors.queue)}"
        assert results.qsize() == 10  # 5 workers * 2 operations each

        # Verify all sensors were registered
        assert len(manager) == 5

    @pytest.mark.asyncio
    async def test_performance_multiple_sensors(self, sample_mqtt_config, sample_sensor_data):
        """Test performance with many sensors (stress test)."""
        import time

        manager = SensorManager()
        num_sensors = 50  # Reasonable number for unit tests

        with patch("mindtrace.hardware.sensors.core.manager.create_backend") as mock_create:
            # Create mock backend that responds quickly
            mock_backend = AsyncMock(spec=SensorBackend)
            mock_backend.is_connected.return_value = True
            mock_backend.read_data.return_value = sample_sensor_data
            mock_create.return_value = mock_backend

            # Register many sensors
            start_time = time.time()

            for i in range(num_sensors):
                manager.register_sensor(f"perf_sensor_{i}", "mqtt", sample_mqtt_config, f"topic_{i}")

            registration_time = time.time() - start_time

            # Connect all sensors
            start_time = time.time()
            connect_results = await manager.connect_all()
            connect_time = time.time() - start_time

            # Read from all sensors
            start_time = time.time()
            read_results = await manager.read_all()
            read_time = time.time() - start_time

            # Verify all operations completed successfully
            assert len(connect_results) == num_sensors
            assert all(connect_results.values())
            assert len(read_results) == num_sensors

            # Performance assertions (reasonable thresholds for unit tests)
            assert registration_time < 5.0  # 5 seconds max for registration
            assert connect_time < 10.0  # 10 seconds max for connection
            assert read_time < 10.0  # 10 seconds max for reading

            print(f"Performance metrics for {num_sensors} sensors:")
            print(f"  Registration: {registration_time:.3f}s")
            print(f"  Connection: {connect_time:.3f}s")
            print(f"  Reading: {read_time:.3f}s")
