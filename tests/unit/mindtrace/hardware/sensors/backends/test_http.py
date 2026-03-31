"""
Unit tests for HTTP sensor backend.

Tests cover HTTP backend initialization, connection, reading, and error scenarios.
Currently tests placeholder implementation that raises NotImplementedError.
"""

import pytest

from mindtrace.hardware.sensors.backends.http import HTTPSensorBackend


class TestHTTPSensorBackend:
    """Test cases for HTTPSensorBackend class."""

    def test_http_backend_initialization_basic(self):
        """Test basic HTTP backend initialization."""
        backend = HTTPSensorBackend("http://api.example.com")

        assert backend.base_url == "http://api.example.com"
        assert backend.auth_token is None
        assert backend.timeout == 30.0
        assert backend.kwargs == {}
        assert not backend.is_connected()

    def test_http_backend_initialization_full_config(self):
        """Test HTTP backend initialization with all parameters."""
        backend = HTTPSensorBackend(
            "https://api.sensors.com/",
            auth_token="token123",
            timeout=60.0,
            headers={"Custom-Header": "value"},
        )

        # URL should have trailing slash stripped
        assert backend.base_url == "https://api.sensors.com"
        assert backend.auth_token == "token123"
        assert backend.timeout == 60.0
        assert backend.kwargs == {"headers": {"Custom-Header": "value"}}
        assert not backend.is_connected()

    def test_http_backend_initialization_url_stripping(self):
        """Test URL trailing slash stripping."""
        # Test with trailing slash
        backend1 = HTTPSensorBackend("http://api.example.com/")
        assert backend1.base_url == "http://api.example.com"

        # Test without trailing slash
        backend2 = HTTPSensorBackend("http://api.example.com")
        assert backend2.base_url == "http://api.example.com"

        # Test with multiple trailing slashes
        backend3 = HTTPSensorBackend("http://api.example.com///")
        assert backend3.base_url == "http://api.example.com"

    def test_http_backend_initialization_kwargs(self):
        """Test that additional kwargs are properly stored."""
        extra_kwargs = {"verify_ssl": False, "max_retries": 3}
        backend = HTTPSensorBackend("http://api.example.com", **extra_kwargs)

        assert backend.kwargs == extra_kwargs

    @pytest.mark.asyncio
    async def test_connect_not_implemented(self):
        """Test that connect raises NotImplementedError."""
        backend = HTTPSensorBackend("http://api.example.com")

        with pytest.raises(NotImplementedError, match="HTTP backend not yet implemented"):
            await backend.connect()

    @pytest.mark.asyncio
    async def test_disconnect_sets_connected_false(self):
        """Test that disconnect sets _is_connected to False."""
        backend = HTTPSensorBackend("http://api.example.com")

        # Manually set connected state
        backend._is_connected = True
        assert backend._is_connected is True

        # Disconnect should set it to False
        await backend.disconnect()
        assert backend._is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_safe_to_call_multiple_times(self):
        """Test that disconnect can be called multiple times safely."""
        backend = HTTPSensorBackend("http://api.example.com")

        # Call disconnect multiple times
        await backend.disconnect()
        await backend.disconnect()
        await backend.disconnect()

        # Should still be False
        assert backend._is_connected is False

    @pytest.mark.asyncio
    async def test_read_data_not_implemented(self):
        """Test that read_data raises NotImplementedError."""
        backend = HTTPSensorBackend("http://api.example.com")

        with pytest.raises(NotImplementedError, match="HTTP backend not yet implemented"):
            await backend.read_data("/sensors/temperature/current")

    def test_is_connected_always_false(self):
        """Test that is_connected always returns False."""
        backend = HTTPSensorBackend("http://api.example.com")

        # Should return False initially
        assert backend.is_connected() is False

        # Even if we manually set _is_connected, the method should still return False
        # (though this tests the current implementation behavior)
        backend._is_connected = True
        # Note: The current implementation returns False, so this tests that behavior
        assert backend.is_connected() is False
