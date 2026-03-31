"""
Unit tests for HTTP sensor simulator backend.

Tests cover HTTP simulator initialization, connection, publishing, and error scenarios.
Currently tests placeholder implementation that raises NotImplementedError.
"""

import pytest

from mindtrace.hardware.sensors.simulators.http import HTTPSensorSimulator


class TestHTTPSensorSimulator:
    """Test cases for HTTPSensorSimulator class."""

    def test_http_simulator_initialization_basic(self):
        """Test basic HTTP simulator initialization."""
        simulator = HTTPSensorSimulator("http://api.example.com")

        assert simulator.base_url == "http://api.example.com"
        assert simulator.auth_token is None
        assert simulator.timeout == 30.0
        assert simulator.kwargs == {}
        assert not simulator.is_connected()

    def test_http_simulator_initialization_full_config(self):
        """Test HTTP simulator initialization with all parameters."""
        simulator = HTTPSensorSimulator(
            "https://api.sensors.com/",
            auth_token="token123",
            timeout=60.0,
            headers={"Custom-Header": "value"},
        )

        # URL should have trailing slash stripped
        assert simulator.base_url == "https://api.sensors.com"
        assert simulator.auth_token == "token123"
        assert simulator.timeout == 60.0
        assert simulator.kwargs == {"headers": {"Custom-Header": "value"}}
        assert not simulator.is_connected()

    def test_http_simulator_initialization_url_stripping(self):
        """Test URL trailing slash stripping."""
        # Test with trailing slash
        simulator1 = HTTPSensorSimulator("http://api.example.com/")
        assert simulator1.base_url == "http://api.example.com"

        # Test without trailing slash
        simulator2 = HTTPSensorSimulator("http://api.example.com")
        assert simulator2.base_url == "http://api.example.com"

        # Test with multiple trailing slashes
        simulator3 = HTTPSensorSimulator("http://api.example.com///")
        assert simulator3.base_url == "http://api.example.com"

    def test_http_simulator_initialization_kwargs(self):
        """Test that additional kwargs are properly stored."""
        extra_kwargs = {"verify_ssl": False, "max_retries": 3}
        simulator = HTTPSensorSimulator("http://api.example.com", **extra_kwargs)

        assert simulator.kwargs == extra_kwargs

    @pytest.mark.asyncio
    async def test_connect_not_implemented(self):
        """Test that connect raises NotImplementedError."""
        simulator = HTTPSensorSimulator("http://api.example.com")

        with pytest.raises(NotImplementedError, match="HTTP simulator backend not yet implemented"):
            await simulator.connect()

    @pytest.mark.asyncio
    async def test_disconnect_sets_connected_false(self):
        """Test that disconnect sets _is_connected to False."""
        simulator = HTTPSensorSimulator("http://api.example.com")

        # Manually set connected state
        simulator._is_connected = True
        assert simulator._is_connected is True

        # Disconnect should set it to False
        await simulator.disconnect()
        assert simulator._is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_safe_to_call_multiple_times(self):
        """Test that disconnect can be called multiple times safely."""
        simulator = HTTPSensorSimulator("http://api.example.com")

        # Call disconnect multiple times
        await simulator.disconnect()
        await simulator.disconnect()
        await simulator.disconnect()

        # Should still be False
        assert simulator._is_connected is False

    @pytest.mark.asyncio
    async def test_publish_data_not_implemented(self):
        """Test that publish_data raises NotImplementedError."""
        simulator = HTTPSensorSimulator("http://api.example.com")

        with pytest.raises(NotImplementedError, match="HTTP simulator backend not yet implemented"):
            await simulator.publish_data("/sensors/temperature", {"temperature": 25.5})

    def test_is_connected_always_false(self):
        """Test that is_connected always returns False."""
        simulator = HTTPSensorSimulator("http://api.example.com")

        # Should return False initially
        assert simulator.is_connected() is False

        # Even if we manually set _is_connected, the method should still return False
        # (though this tests the current implementation behavior)
        simulator._is_connected = True
        # Note: The current implementation returns False, so this tests that behavior
        assert simulator.is_connected() is False
