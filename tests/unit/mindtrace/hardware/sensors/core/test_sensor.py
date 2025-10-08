"""
Unit tests for AsyncSensor class.

Tests cover the complete lifecycle of sensor operations including connection,
data reading, error handling, and async context management.
"""

import pytest

from mindtrace.hardware.sensors.core.sensor import AsyncSensor


class TestAsyncSensor:
    """Test cases for AsyncSensor class."""

    def test_sensor_initialization_valid(self, mock_mqtt_backend):
        """Test successful sensor initialization with valid parameters."""
        sensor = AsyncSensor("test_sensor", mock_mqtt_backend, "test/topic")

        assert sensor.sensor_id == "test_sensor"
        assert sensor._address == "test/topic"
        assert sensor._backend == mock_mqtt_backend

    def test_sensor_initialization_strips_whitespace(self, mock_mqtt_backend):
        """Test that sensor initialization strips whitespace from strings."""
        sensor = AsyncSensor("  test_sensor  ", mock_mqtt_backend, "  test/topic  ")

        assert sensor.sensor_id == "test_sensor"
        assert sensor._address == "test/topic"

    def test_sensor_initialization_invalid_sensor_id(self, mock_mqtt_backend):
        """Test sensor initialization with invalid sensor_id."""
        with pytest.raises(ValueError, match="sensor_id must be a non-empty string"):
            AsyncSensor("", mock_mqtt_backend, "test/topic")

        with pytest.raises(ValueError, match="sensor_id must be a non-empty string"):
            AsyncSensor(None, mock_mqtt_backend, "test/topic")

        with pytest.raises(ValueError, match="sensor_id must be a non-empty string"):
            AsyncSensor(123, mock_mqtt_backend, "test/topic")

    def test_sensor_initialization_invalid_address(self, mock_mqtt_backend):
        """Test sensor initialization with invalid address."""
        with pytest.raises(ValueError, match="address must be a non-empty string"):
            AsyncSensor("test_sensor", mock_mqtt_backend, "")

        with pytest.raises(ValueError, match="address must be a non-empty string"):
            AsyncSensor("test_sensor", mock_mqtt_backend, None)

    def test_sensor_initialization_invalid_backend(self):
        """Test sensor initialization with invalid backend."""
        with pytest.raises(TypeError, match="backend must be a SensorBackend instance"):
            AsyncSensor("test_sensor", "not_a_backend", "test/topic")

        with pytest.raises(TypeError, match="backend must be a SensorBackend instance"):
            AsyncSensor("test_sensor", None, "test/topic")

    def test_is_connected_property(self, mock_mqtt_backend):
        """Test is_connected property delegates to backend."""
        sensor = AsyncSensor("test_sensor", mock_mqtt_backend, "test/topic")

        mock_mqtt_backend.is_connected.return_value = False
        assert not sensor.is_connected

        mock_mqtt_backend.is_connected.return_value = True
        assert sensor.is_connected

        mock_mqtt_backend.is_connected.assert_called()

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_mqtt_backend):
        """Test successful sensor connection."""
        sensor = AsyncSensor("test_sensor", mock_mqtt_backend, "test/topic")

        await sensor.connect()

        mock_mqtt_backend.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self, mock_mqtt_backend):
        """Test sensor connection failure."""
        sensor = AsyncSensor("test_sensor", mock_mqtt_backend, "test/topic")

        mock_mqtt_backend.connect.side_effect = Exception("Connection failed")

        with pytest.raises(ConnectionError, match="Failed to connect sensor test_sensor"):
            await sensor.connect()

        mock_mqtt_backend.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_success(self, mock_mqtt_backend):
        """Test successful sensor disconnection."""
        sensor = AsyncSensor("test_sensor", mock_mqtt_backend, "test/topic")

        await sensor.disconnect()

        mock_mqtt_backend.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_with_error(self, mock_mqtt_backend):
        """Test sensor disconnection with error (should not raise)."""
        sensor = AsyncSensor("test_sensor", mock_mqtt_backend, "test/topic")

        mock_mqtt_backend.disconnect.side_effect = Exception("Disconnect error")

        # Should not raise exception, only log warning
        await sensor.disconnect()

        mock_mqtt_backend.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_success(self, mock_mqtt_backend, sample_sensor_data):
        """Test successful data reading."""
        sensor = AsyncSensor("test_sensor", mock_mqtt_backend, "test/topic")

        mock_mqtt_backend.is_connected.return_value = True
        mock_mqtt_backend.read_data.return_value = sample_sensor_data

        data = await sensor.read()

        assert data == sample_sensor_data
        mock_mqtt_backend.read_data.assert_called_once_with("test/topic")

    @pytest.mark.asyncio
    async def test_read_no_data(self, mock_mqtt_backend):
        """Test reading when no data is available."""
        sensor = AsyncSensor("test_sensor", mock_mqtt_backend, "test/topic")

        mock_mqtt_backend.is_connected.return_value = True
        mock_mqtt_backend.read_data.return_value = None

        data = await sensor.read()

        assert data is None
        mock_mqtt_backend.read_data.assert_called_once_with("test/topic")

    @pytest.mark.asyncio
    async def test_read_not_connected(self, mock_mqtt_backend):
        """Test reading when sensor is not connected."""
        sensor = AsyncSensor("test_sensor", mock_mqtt_backend, "test/topic")

        mock_mqtt_backend.is_connected.return_value = False

        with pytest.raises(ConnectionError, match="Sensor test_sensor is not connected"):
            await sensor.read()

        mock_mqtt_backend.read_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_backend_error(self, mock_mqtt_backend):
        """Test reading with backend error."""
        sensor = AsyncSensor("test_sensor", mock_mqtt_backend, "test/topic")

        mock_mqtt_backend.is_connected.return_value = True
        mock_mqtt_backend.read_data.side_effect = TimeoutError("Read timeout")

        with pytest.raises(TimeoutError, match="Read timeout"):
            await sensor.read()

        mock_mqtt_backend.read_data.assert_called_once_with("test/topic")

    @pytest.mark.asyncio
    async def test_context_manager_success(self, mock_mqtt_backend, sample_sensor_data):
        """Test async context manager with successful operations."""
        sensor = AsyncSensor("test_sensor", mock_mqtt_backend, "test/topic")

        mock_mqtt_backend.is_connected.return_value = True
        mock_mqtt_backend.read_data.return_value = sample_sensor_data

        async with sensor as s:
            assert s is sensor
            data = await s.read()
            assert data == sample_sensor_data

        mock_mqtt_backend.connect.assert_called_once()
        mock_mqtt_backend.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_connect_error(self, mock_mqtt_backend):
        """Test async context manager with connection error."""
        sensor = AsyncSensor("test_sensor", mock_mqtt_backend, "test/topic")

        mock_mqtt_backend.connect.side_effect = Exception("Connection failed")

        with pytest.raises(ConnectionError):
            async with sensor:
                pass

        mock_mqtt_backend.connect.assert_called_once()
        mock_mqtt_backend.disconnect.assert_not_called()

    @pytest.mark.asyncio
    async def test_context_manager_disconnect_error(self, mock_mqtt_backend):
        """Test async context manager with disconnect error."""
        sensor = AsyncSensor("test_sensor", mock_mqtt_backend, "test/topic")

        mock_mqtt_backend.disconnect.side_effect = Exception("Disconnect error")

        # Should not raise exception from disconnect error
        async with sensor:
            pass

        mock_mqtt_backend.connect.assert_called_once()
        mock_mqtt_backend.disconnect.assert_called_once()

    def test_sensor_repr(self, mock_mqtt_backend):
        """Test sensor string representation."""
        sensor = AsyncSensor("test_sensor", mock_mqtt_backend, "test/topic")

        mock_mqtt_backend.is_connected.return_value = False
        repr_str = repr(sensor)

        assert "AsyncSensor" in repr_str
        assert "test_sensor" in repr_str
        assert "disconnected" in repr_str

        mock_mqtt_backend.is_connected.return_value = True
        repr_str = repr(sensor)
        assert "connected" in repr_str
