"""
Unit tests for MQTT sensor simulator backend.

Tests cover MQTT simulator initialization, connection, publishing, and error scenarios.
Uses mocked aiomqtt to avoid requiring actual MQTT broker.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

# Skip all tests if aiomqtt is not available
try:
    import aiomqtt  # noqa: F401

    from mindtrace.hardware.sensors.simulators.mqtt import MQTTSensorSimulator
except ImportError:
    pytest.skip("aiomqtt is required for MQTT tests", allow_module_level=True)


class TestMQTTSensorSimulator:
    """Test cases for MQTTSensorSimulator class."""

    def test_mqtt_simulator_initialization_basic(self):
        """Test basic MQTT simulator initialization."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        assert simulator.broker_url == "mqtt://localhost:1883"
        assert simulator.hostname == "localhost"
        assert simulator.port == 1883
        assert simulator.identifier is None
        assert simulator.username is None
        assert simulator.password is None
        assert simulator.keepalive == 60
        assert not simulator.is_connected()

    def test_mqtt_simulator_initialization_full_config(self):
        """Test MQTT simulator initialization with all parameters."""
        simulator = MQTTSensorSimulator(
            "mqtt://broker.example.com:8883",
            identifier="sim_client",
            username="sim_user",
            password="sim_pass",
            keepalive=30,
        )

        assert simulator.broker_url == "mqtt://broker.example.com:8883"
        assert simulator.hostname == "broker.example.com"
        assert simulator.port == 8883
        assert simulator.identifier == "sim_client"
        assert simulator.username == "sim_user"
        assert simulator.password == "sim_pass"
        assert simulator.keepalive == 30

    def test_mqtt_simulator_initialization_url_parsing(self):
        """Test URL parsing edge cases."""
        # Test default port
        simulator1 = MQTTSensorSimulator("mqtt://localhost")
        assert simulator1.hostname == "localhost"
        assert simulator1.port == 1883

        # Test custom port
        simulator2 = MQTTSensorSimulator("mqtt://localhost:8883")
        assert simulator2.hostname == "localhost"
        assert simulator2.port == 8883

        # Test IP address
        simulator3 = MQTTSensorSimulator("mqtt://192.168.1.100:1883")
        assert simulator3.hostname == "192.168.1.100"
        assert simulator3.port == 1883

    def test_mqtt_simulator_initialization_missing_aiomqtt(self):
        """Test MQTT simulator initialization when aiomqtt is not available."""
        with patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt", None):
            with pytest.raises(ImportError, match="aiomqtt is required for MQTT simulator"):
                MQTTSensorSimulator("mqtt://localhost:1883")

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_connect_success(self, mock_aiomqtt):
        """Test successful MQTT simulator connection."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        # Mock the client
        mock_client = AsyncMock()
        mock_aiomqtt.Client.return_value = mock_client

        await simulator.connect()

        assert simulator.is_connected()
        mock_aiomqtt.Client.assert_called_once_with(
            hostname="localhost", port=1883, identifier=None, username=None, password=None, keepalive=60
        )
        mock_client.__aenter__.assert_called_once()

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_connect_with_credentials(self, mock_aiomqtt):
        """Test MQTT simulator connection with credentials."""
        simulator = MQTTSensorSimulator(
            "mqtt://broker.test:1883", identifier="sim123", username="simuser", password="simpass", keepalive=30
        )

        mock_client = AsyncMock()
        mock_aiomqtt.Client.return_value = mock_client

        await simulator.connect()

        mock_aiomqtt.Client.assert_called_once_with(
            hostname="broker.test", port=1883, identifier="sim123", username="simuser", password="simpass", keepalive=30
        )

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_connect_failure(self, mock_aiomqtt):
        """Test MQTT simulator connection failure."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        mock_client = AsyncMock()
        mock_client.__aenter__.side_effect = ConnectionError("Connection refused")
        mock_aiomqtt.Client.return_value = mock_client

        with pytest.raises(ConnectionError, match="Failed to connect MQTT simulator to broker"):
            await simulator.connect()

        assert not simulator.is_connected()
        assert simulator._client is None

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_connect_already_connected(self, mock_aiomqtt):
        """Test connecting when already connected."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        mock_client = AsyncMock()
        mock_aiomqtt.Client.return_value = mock_client

        # First connection
        await simulator.connect()
        assert simulator.is_connected()

        # Second connection should be no-op
        await simulator.connect()

        # Client should only be created once
        mock_aiomqtt.Client.assert_called_once()

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_disconnect_success(self, mock_aiomqtt):
        """Test successful MQTT simulator disconnection."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        mock_client = AsyncMock()
        mock_aiomqtt.Client.return_value = mock_client

        # Connect first
        await simulator.connect()
        assert simulator.is_connected()

        # Disconnect
        await simulator.disconnect()

        assert not simulator.is_connected()
        assert simulator._client is None
        mock_client.__aexit__.assert_called_once_with(None, None, None)

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self):
        """Test disconnecting when not connected."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        # Should not raise exception
        await simulator.disconnect()
        assert not simulator.is_connected()

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_disconnect_with_error(self, mock_aiomqtt):
        """Test disconnection with error."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        mock_client = AsyncMock()
        mock_client.__aexit__.side_effect = Exception("Disconnect error")
        mock_aiomqtt.Client.return_value = mock_client

        await simulator.connect()

        # Should handle disconnect error gracefully
        await simulator.disconnect()
        assert not simulator.is_connected()
        assert simulator._client is None

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_publish_data_dict(self, mock_aiomqtt):
        """Test publishing dictionary data."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        mock_client = AsyncMock()
        mock_aiomqtt.Client.return_value = mock_client

        await simulator.connect()

        test_data = {"temperature": 25.5, "humidity": 60.0}
        await simulator.publish_data("sensors/test", test_data)

        # Verify publish was called with JSON payload
        mock_client.publish.assert_called_once()
        args = mock_client.publish.call_args
        assert args[0][0] == "sensors/test"  # topic

        # Parse the JSON payload to verify it's correct
        payload = args[0][1]
        parsed_data = json.loads(payload)
        assert parsed_data == test_data

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_publish_data_list(self, mock_aiomqtt):
        """Test publishing list data."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        mock_client = AsyncMock()
        mock_aiomqtt.Client.return_value = mock_client

        await simulator.connect()

        test_data = [1, 2, 3, "test"]
        await simulator.publish_data("sensors/test", test_data)

        # Verify publish was called with JSON payload
        mock_client.publish.assert_called_once()
        args = mock_client.publish.call_args
        payload = args[0][1]
        parsed_data = json.loads(payload)
        assert parsed_data == test_data

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_publish_data_primitives(self, mock_aiomqtt):
        """Test publishing primitive data types."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        mock_client = AsyncMock()
        mock_aiomqtt.Client.return_value = mock_client

        await simulator.connect()

        # Test integer
        await simulator.publish_data("sensors/int", 42)
        args = mock_client.publish.call_args
        assert args[0][1] == "42"

        # Test float
        mock_client.reset_mock()
        await simulator.publish_data("sensors/float", 3.14)
        args = mock_client.publish.call_args
        assert args[0][1] == "3.14"

        # Test boolean
        mock_client.reset_mock()
        await simulator.publish_data("sensors/bool", True)
        args = mock_client.publish.call_args
        assert args[0][1] == "True"

        # Test string
        mock_client.reset_mock()
        await simulator.publish_data("sensors/str", "hello world")
        args = mock_client.publish.call_args
        assert args[0][1] == "hello world"

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_publish_data_custom_objects(self, mock_aiomqtt):
        """Test publishing custom objects with JSON serialization fallback."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        mock_client = AsyncMock()
        mock_aiomqtt.Client.return_value = mock_client

        await simulator.connect()

        # Test object that can be JSON serialized
        class SerializableObj:
            def __init__(self, value):
                self.value = value

        # This will fail JSON serialization and fall back to str()
        obj = SerializableObj(42)
        await simulator.publish_data("sensors/obj", obj)

        args = mock_client.publish.call_args
        payload = args[0][1]
        # Should contain string representation
        assert "SerializableObj" in payload

    @pytest.mark.asyncio
    async def test_publish_data_not_connected(self):
        """Test publishing data when not connected."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        with pytest.raises(ConnectionError, match="MQTT simulator not connected to broker"):
            await simulator.publish_data("test/topic", {"data": "test"})

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_publish_data_invalid_topic(self, mock_aiomqtt):
        """Test publishing data with invalid topic names."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        mock_client = AsyncMock()
        mock_aiomqtt.Client.return_value = mock_client

        await simulator.connect()

        # Test empty string topic
        with pytest.raises(ValueError, match="Topic name must be a non-empty string"):
            await simulator.publish_data("", {"data": "test"})

        # Test None topic
        with pytest.raises(ValueError, match="Topic name must be a non-empty string"):
            await simulator.publish_data(None, {"data": "test"})

        # Test non-string topic
        with pytest.raises(ValueError, match="Topic name must be a non-empty string"):
            await simulator.publish_data(123, {"data": "test"})

        # Test whitespace-only topic
        with pytest.raises(ValueError, match="Topic name cannot be empty"):
            await simulator.publish_data("   ", {"data": "test"})

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_publish_data_no_client(self, mock_aiomqtt):
        """Test publishing when client is None despite being marked as connected."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        # Manually set connected state but no client (edge case)
        simulator._is_connected = True
        simulator._client = None

        with pytest.raises(ConnectionError, match="MQTT client not initialized"):
            await simulator.publish_data("test/topic", {"data": "test"})

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_publish_data_publish_failure(self, mock_aiomqtt):
        """Test handling publish failures."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        mock_client = AsyncMock()
        mock_client.publish.side_effect = Exception("Publish failed")
        mock_aiomqtt.Client.return_value = mock_client

        await simulator.connect()

        with pytest.raises(Exception, match="Publish failed"):
            await simulator.publish_data("test/topic", {"data": "test"})

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_connection_lifecycle(self, mock_aiomqtt):
        """Test complete connection lifecycle."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883", identifier="test_sim")

        mock_client = AsyncMock()
        mock_aiomqtt.Client.return_value = mock_client

        # Initially not connected
        assert not simulator.is_connected()

        # Connect
        await simulator.connect()
        assert simulator.is_connected()

        # Publish some data
        await simulator.publish_data("sensors/temp", {"temperature": 22.5})
        mock_client.publish.assert_called_once_with("sensors/temp", '{"temperature":22.5}')

        # Disconnect
        await simulator.disconnect()
        assert not simulator.is_connected()

        # Verify client lifecycle
        mock_aiomqtt.Client.assert_called_once()
        mock_client.__aenter__.assert_called_once()
        mock_client.__aexit__.assert_called_once()


class TestMQTTSensorSimulatorCoverage:
    """Additional tests to improve MQTT simulator coverage."""

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_connect_exception_cleanup(self, mock_aiomqtt):
        """Test that connection exceptions properly clean up state."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        mock_client = AsyncMock()
        mock_client.__aenter__.side_effect = RuntimeError("Network error")
        mock_aiomqtt.Client.return_value = mock_client

        with pytest.raises(ConnectionError):
            await simulator.connect()

        # Verify cleanup occurred
        assert not simulator.is_connected()
        assert simulator._client is None

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_disconnect_finally_cleanup(self, mock_aiomqtt):
        """Test that disconnect finally block always cleans up state."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        mock_client = AsyncMock()
        mock_client.__aexit__.side_effect = RuntimeError("Disconnect error")
        mock_aiomqtt.Client.return_value = mock_client

        await simulator.connect()

        # Disconnect should handle error but still clean up
        await simulator.disconnect()

        # Verify finally block executed
        assert not simulator.is_connected()
        assert simulator._client is None

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_publish_data_json_serialization_edge_cases(self, mock_aiomqtt):
        """Test edge cases in JSON serialization for publish_data."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        mock_client = AsyncMock()
        mock_aiomqtt.Client.return_value = mock_client

        await simulator.connect()

        # Test object that fails JSON serialization
        class NonSerializable:
            def __str__(self):
                return "custom_string_representation"

        obj = NonSerializable()
        await simulator.publish_data("test/topic", obj)

        # Should fall back to string representation
        args = mock_client.publish.call_args
        assert args[0][1] == "custom_string_representation"

    @patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt")
    @pytest.mark.asyncio
    async def test_publish_data_topic_validation_edge_cases(self, mock_aiomqtt):
        """Test edge cases in topic validation."""
        simulator = MQTTSensorSimulator("mqtt://localhost:1883")

        mock_client = AsyncMock()
        mock_aiomqtt.Client.return_value = mock_client

        await simulator.connect()

        # Test topic with whitespace that becomes empty after strip
        with pytest.raises(ValueError, match="Topic name cannot be empty"):
            await simulator.publish_data("  \t\n  ", {"data": "test"})

        # Test valid topic with leading/trailing whitespace (should work after strip)
        await simulator.publish_data("  valid/topic  ", {"data": "test"})
        args = mock_client.publish.call_args
        assert args[0][0] == "valid/topic"  # Should be stripped

    def test_initialization_kwargs_handling(self):
        """Test that additional kwargs are properly stored."""
        extra_kwargs = {"will_message": "test_will", "clean_session": False}
        simulator = MQTTSensorSimulator("mqtt://localhost:1883", **extra_kwargs)

        assert simulator.kwargs == extra_kwargs

        # Verify kwargs would be passed to client
        with patch("mindtrace.hardware.sensors.simulators.mqtt.aiomqtt") as mock_aiomqtt:
            mock_client = AsyncMock()
            mock_aiomqtt.Client.return_value = mock_client

            async def test_kwargs():
                await simulator.connect()

                # Verify kwargs were passed through
                mock_aiomqtt.Client.assert_called_once_with(
                    hostname="localhost",
                    port=1883,
                    identifier=None,
                    username=None,
                    password=None,
                    keepalive=60,
                    **extra_kwargs,
                )

            import asyncio

            asyncio.run(test_kwargs())
