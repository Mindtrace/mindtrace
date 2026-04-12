from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from urllib3.util.url import parse_url

from mindtrace.services.core.types import ServerStatus
from mindtrace.services.gateway.gateway import Gateway, GatewayConnectionManager
from mindtrace.services.gateway.proxy_connection_manager import ProxyConnectionManager
from mindtrace.services.gateway.types import AppConfig


class TestGateway:
    """Test suite for the Gateway class."""

    @pytest.fixture
    def gateway(self):
        """Create a Gateway instance for testing."""
        gateway = Gateway()
        return gateway

    @pytest.fixture
    def mock_app_config(self):
        """Create a mock AppConfig for testing."""
        return AppConfig(name="test-service", url="http://localhost:8001/")

    def test_init(self, gateway):
        """Test Gateway initialization."""
        # Test that basic attributes are set
        assert hasattr(gateway, "registered_routers")
        assert hasattr(gateway, "client")
        assert gateway.registered_routers == {}
        assert isinstance(gateway.client, httpx.AsyncClient)

        # Test that CORS middleware was added
        # Note: We can't easily test middleware addition without inspecting FastAPI internals

    def test_init_adds_register_app_endpoint(self):
        """Test that Gateway declares the register_app endpoint."""
        assert "register_app" in Gateway.__endpoints__
        spec = Gateway.__endpoints__["register_app"]
        assert spec.method_name == "register_app"

    def test_register_app(self, gateway, mock_app_config):
        """Test the register_app method."""
        with patch.object(gateway.app, "add_api_route") as mock_add_route:
            gateway.register_app(mock_app_config)

            # Test that the app is registered
            assert gateway.registered_routers["test-service"] == "http://localhost:8001/"

            # Test that the API route is added
            mock_add_route.assert_called_once()
            call_args = mock_add_route.call_args
            assert call_args[0][0] == "/test-service/{path:path}"
            assert call_args[1]["methods"] == ["GET", "POST", "PUT", "DELETE", "PATCH"]

    def test_register_app_with_url_object(self, gateway):
        """Test the register_app method with Url object instead of string."""
        # Create AppConfig with Url object
        url_obj = parse_url("http://localhost:8002/")
        app_config = AppConfig(name="url-service", url=url_obj)

        with patch.object(gateway.app, "add_api_route") as mock_add_route:
            gateway.register_app(app_config)

            # Test that the app is registered with string conversion
            assert gateway.registered_routers["url-service"] == "http://localhost:8002/"

            # Test that the API route is added
            mock_add_route.assert_called_once()
            call_args = mock_add_route.call_args
            assert call_args[0][0] == "/url-service/{path:path}"
            assert call_args[1]["methods"] == ["GET", "POST", "PUT", "DELETE", "PATCH"]

    @pytest.mark.asyncio
    async def test_register_app_forwarder_function(self, gateway, mock_app_config):
        """Test that the forwarder function created by register_app works correctly."""
        # Mock the forward_request method to test the forwarder function
        with patch.object(gateway, "forward_request") as mock_forward:
            mock_forward.return_value = JSONResponse(content={"test": "response"})

            # Mock add_api_route to capture the forwarder function
            with patch.object(gateway.app, "add_api_route") as mock_add_route:
                # Register the app - this creates the forwarder function
                gateway.register_app(mock_app_config)

                # Get the forwarder function that was passed to add_api_route
                forwarder_func = mock_add_route.call_args[0][1]  # Second positional argument

            # Create a mock request
            mock_request = Mock(spec=Request)

            # Call the forwarder function directly
            result = await forwarder_func(mock_request, path="test-path")

            # Verify that forward_request was called with the correct arguments
            mock_forward.assert_called_once_with(mock_request, "test-service", "test-path")
            assert result == mock_forward.return_value

    @pytest.mark.asyncio
    async def test_forward_request_success(self, gateway, mock_app_config):
        """Test successful request forwarding."""
        # Setup
        gateway.registered_routers["test-service"] = "http://localhost:8001/"

        mock_request = Mock(spec=Request)
        mock_request.method = "POST"
        mock_request.headers = {"Content-Type": "application/json"}
        mock_request.body = AsyncMock(return_value=b'{"test": "data"}')

        mock_response = Mock()
        mock_response.json.return_value = {"result": "success"}
        mock_response.status_code = 200

        with patch.object(gateway.client, "request", return_value=mock_response) as mock_client_request:
            result = await gateway.forward_request(mock_request, "test-service", "endpoint")

            # Test that the request was forwarded correctly
            mock_client_request.assert_called_once_with(
                "POST",
                "http://localhost:8001/endpoint",
                headers={"Content-Type": "application/json"},
                content=b'{"test": "data"}',
            )

            # Test that the response is returned correctly
            assert isinstance(result, JSONResponse)

    @pytest.mark.asyncio
    async def test_forward_request_app_not_found(self, gateway):
        """Test forwarding request to non-existent app."""
        mock_request = Mock(spec=Request)

        with pytest.raises(HTTPException) as exc_info:
            await gateway.forward_request(mock_request, "nonexistent-service", "endpoint")

        assert exc_info.value.status_code == 404
        assert "App 'nonexistent-service' not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_forward_request_network_error(self, gateway, mock_app_config):
        """Test forwarding request with network error."""
        gateway.registered_routers["test-service"] = "http://localhost:8001/"

        mock_request = Mock(spec=Request)
        mock_request.method = "GET"
        mock_request.headers = {}
        mock_request.body = AsyncMock(return_value=b"")

        with patch.object(gateway.client, "request", side_effect=httpx.RequestError("Network error")):
            with pytest.raises(HTTPException) as exc_info:
                await gateway.forward_request(mock_request, "test-service", "endpoint")

            assert exc_info.value.status_code == 500
            assert "Network error" in str(exc_info.value.detail)

    @patch("mindtrace.services.gateway.gateway.ifnone_url")
    def test_connect_success(self, mock_ifnone_url):
        """Test successful connection to Gateway returns a GatewayConnectionManager."""
        mock_url = "http://localhost:8090/"
        mock_ifnone_url.return_value = mock_url

        with patch.object(Gateway, "status_at_host", return_value=ServerStatus.AVAILABLE):
            result = Gateway.connect(url=mock_url)

            assert result is not None
            assert isinstance(result, GatewayConnectionManager)

    @patch("mindtrace.services.gateway.gateway.ifnone_url")
    def test_connect_service_unavailable(self, mock_ifnone_url):
        """Test connection to unavailable Gateway."""
        mock_url = "http://localhost:8090/"
        mock_ifnone_url.return_value = mock_url

        with patch.object(Gateway, "status_at_host", return_value=ServerStatus.DOWN):
            with pytest.raises(HTTPException) as exc_info:
                Gateway.connect(url=mock_url)

            assert exc_info.value.status_code == 503
            assert "Server failed to connect: ServerStatus.DOWN" in str(exc_info.value.detail)

    @patch("mindtrace.services.gateway.gateway.ifnone_url")
    def test_connect_service_other_status(self, mock_ifnone_url):
        """Test connection to Gateway with other non-available status."""
        mock_url = "http://localhost:8090/"
        mock_ifnone_url.return_value = mock_url

        # Test with different non-available status
        with patch.object(Gateway, "status_at_host", return_value=ServerStatus.LAUNCHING):
            with pytest.raises(HTTPException) as exc_info:
                Gateway.connect(url=mock_url)

            assert exc_info.value.status_code == 503
            assert "Server failed to connect: ServerStatus.LAUNCHING" in str(exc_info.value.detail)

    def test_gateway_cm_register_app_with_proxy(self, gateway, mock_app_config):
        """Test GatewayConnectionManager register_app with ProxyConnectionManager."""
        with patch.object(Gateway, "status_at_host", return_value=ServerStatus.AVAILABLE):
            cm = Gateway.connect(url="http://localhost:8090/")
            assert isinstance(cm, GatewayConnectionManager)

            mock_original_cm = Mock()
            mock_original_cm._service_endpoints = {"echo": Mock(input_schema=None, output_schema=None, name="echo")}

            with (
                patch("mindtrace.services.gateway.gateway.httpx") as mock_httpx,
                patch("mindtrace.services.gateway.gateway.ProxyConnectionManager") as mock_proxy_class,
            ):
                mock_response = Mock()
                mock_response.status_code = 200
                mock_httpx.post.return_value = mock_response

                mock_proxy_instance = Mock()
                mock_proxy_class.return_value = mock_proxy_instance

                cm.register_app(name="test-service", url="http://localhost:8001/", connection_manager=mock_original_cm)

                mock_proxy_class.assert_called_once()
                assert hasattr(cm, "test-service")
                assert getattr(cm, "test-service") is mock_proxy_instance
                assert "test-service" in cm.registered_apps

    @pytest.mark.asyncio
    async def test_gateway_cm_aregister_app_with_proxy(self, gateway):
        """Test GatewayConnectionManager async register_app with ProxyConnectionManager."""
        with patch.object(Gateway, "status_at_host", return_value=ServerStatus.AVAILABLE):
            cm = Gateway.connect(url="http://localhost:8090/")
            assert isinstance(cm, GatewayConnectionManager)

            mock_original_cm = Mock()
            mock_original_cm._service_endpoints = {"echo": Mock(input_schema=None, output_schema=None, name="echo")}

            with (
                patch("httpx.AsyncClient") as mock_async_client_class,
                patch("mindtrace.services.gateway.gateway.ProxyConnectionManager") as mock_proxy_class,
            ):
                mock_client = AsyncMock()
                mock_response = Mock()
                mock_response.status_code = 200
                mock_client.post.return_value = mock_response
                mock_async_client_class.return_value.__aenter__.return_value = mock_client

                mock_proxy_instance = Mock()
                mock_proxy_class.return_value = mock_proxy_instance

                await cm.aregister_app(
                    name="async-service", url="http://localhost:8002/", connection_manager=mock_original_cm
                )

                mock_proxy_class.assert_called_once()
                assert hasattr(cm, "async-service")

    def test_gateway_cm_register_app_without_proxy(self, gateway):
        """Test GatewayConnectionManager register_app without ProxyConnectionManager."""
        with patch.object(Gateway, "status_at_host", return_value=ServerStatus.AVAILABLE):
            cm = Gateway.connect(url="http://localhost:8090/")
            assert isinstance(cm, GatewayConnectionManager)

            with patch("mindtrace.services.gateway.gateway.httpx") as mock_httpx:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_httpx.post.return_value = mock_response

                cm.register_app(name="simple-service", url="http://localhost:8003/")

                assert len(cm._registered_apps) == 0
                assert len(cm.registered_apps) == 0


class TestProxyConnectionManagerIntegration:
    """Test ProxyConnectionManager integration with Gateway."""

    @pytest.fixture
    def mock_original_cm(self):
        """Create a mock original connection manager with service endpoints."""
        mock_cm = Mock()
        mock_cm.echo = Mock(return_value={"echoed": "test"})
        mock_cm._service_endpoints = {
            "echo": Mock(input_schema=None, output_schema=None, name="echo"),
            "status": Mock(input_schema=None, output_schema=None, name="status"),
        }
        return mock_cm

    @pytest.fixture
    def proxy_cm(self, mock_original_cm):
        """Create a ProxyConnectionManager for testing."""
        return ProxyConnectionManager(
            gateway_url="http://localhost:8090", app_name="test-service", original_cm=mock_original_cm
        )

    def test_proxy_method_call_success(self, proxy_cm):
        """Test successful method call through proxy."""
        with patch("mindtrace.services.gateway.proxy_connection_manager.httpx") as mock_httpx:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"echoed": "test message"}
            mock_httpx.post.return_value = mock_response

            # Get the dynamically created method directly from instance dict to avoid __getattribute__
            instance_dict = object.__getattribute__(proxy_cm, "__dict__")
            echo_method = instance_dict["echo"]

            # Test calling a method through the proxy
            result = echo_method(message="test message")

            # Verify the request was made correctly
            mock_httpx.post.assert_called_once_with(
                "http://localhost:8090/test-service/echo", json={"message": "test message"}, timeout=60
            )

            assert result == {"echoed": "test message"}

    def test_proxy_method_call_no_args(self, proxy_cm):
        """Test method call with no arguments through proxy."""
        with patch("mindtrace.services.gateway.proxy_connection_manager.httpx") as mock_httpx:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_httpx.post.return_value = mock_response

            # Get the dynamically created method directly from instance dict to avoid __getattribute__
            instance_dict = object.__getattribute__(proxy_cm, "__dict__")
            status_method = instance_dict["status"]

            # Test calling a no-arg method
            _ = status_method()

            # Verify POST was used (all proxy methods use POST)
            mock_httpx.post.assert_called_once_with("http://localhost:8090/test-service/status", json={}, timeout=60)

    def test_proxy_method_call_failure(self, proxy_cm):
        """Test failed method call through proxy."""
        with patch("mindtrace.services.gateway.proxy_connection_manager.httpx") as mock_httpx:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_httpx.post.return_value = mock_response

            # Get the dynamically created method directly from instance dict to avoid __getattribute__
            instance_dict = object.__getattribute__(proxy_cm, "__dict__")
            echo_method = instance_dict["echo"]

            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                echo_method(message="test")

            assert exc_info.value.status_code == 500

    def test_proxy_attribute_access(self, proxy_cm, mock_original_cm):
        """Test accessing internal attributes of proxy."""
        # Test direct attribute access using object.__getattribute__ to avoid HTTP requests
        assert object.__getattribute__(proxy_cm, "gateway_url") == "http://localhost:8090"
        assert object.__getattribute__(proxy_cm, "app_name") == "test-service"
        assert object.__getattribute__(proxy_cm, "original_cm") == mock_original_cm

    def test_proxy_missing_method(self, proxy_cm):
        """Test that __getattr__ fallback works correctly without recursion."""
        # This test verifies that accessing a truly non-existent attribute
        # eventually falls back to __getattr__ and raises the correct error
        # without causing infinite recursion
        with pytest.raises(AttributeError) as exc_info:
            # Access a non-existent attribute that should fall back to __getattr__
            _ = proxy_cm.nonexistent_attribute

        # The error message should come from __getattr__ fallback
        assert "ProxyConnectionManager" in str(exc_info.value)
        assert "has no attribute 'nonexistent_attribute'" in str(exc_info.value)


class TestGatewayEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def gateway(self):
        """Create a Gateway instance for testing."""
        return Gateway()

    def test_register_app_with_trailing_slash(self, gateway):
        """Test registering app with trailing slash in URL."""
        app_config = AppConfig(name="test-service", url="http://localhost:8001/")

        with patch.object(gateway.app, "add_api_route"):
            gateway.register_app(app_config)

            assert gateway.registered_routers["test-service"] == "http://localhost:8001/"

    def test_register_app_without_trailing_slash(self, gateway):
        """Test registering app without trailing slash in URL."""
        app_config = AppConfig(name="test-service", url="http://localhost:8001")

        with patch.object(gateway.app, "add_api_route"):
            gateway.register_app(app_config)

            assert gateway.registered_routers["test-service"] == "http://localhost:8001"

    @pytest.mark.asyncio
    async def test_forward_request_empty_path(self, gateway):
        """Test forwarding request with empty path."""
        gateway.registered_routers["test-service"] = "http://localhost:8001/"

        mock_request = Mock(spec=Request)
        mock_request.method = "GET"
        mock_request.headers = {}
        mock_request.body = AsyncMock(return_value=b"")

        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.status_code = 200

        with patch.object(gateway.client, "request", return_value=mock_response) as mock_client_request:
            await gateway.forward_request(mock_request, "test-service", "")

            # Test that empty path results in correct URL
            mock_client_request.assert_called_once_with("GET", "http://localhost:8001/", headers={}, content=b"")

    @pytest.mark.asyncio
    async def test_forward_request_url_construction_with_trailing_slash(self, gateway):
        """Test URL construction when app URL has trailing slash."""
        gateway.registered_routers["test-service"] = "http://localhost:8001/"

        mock_request = Mock(spec=Request)
        mock_request.method = "POST"
        mock_request.headers = {}
        mock_request.body = AsyncMock(return_value=b"{}")

        mock_response = Mock()
        mock_response.json.return_value = {"result": "success"}
        mock_response.status_code = 200

        with patch.object(gateway.client, "request", return_value=mock_response) as mock_client_request:
            await gateway.forward_request(mock_request, "test-service", "echo")

            # Should construct URL correctly without double slash
            mock_client_request.assert_called_once_with(
                "POST",
                "http://localhost:8001/echo",  # Correct: no double slash
                headers={},
                content=b"{}",
            )

    @pytest.mark.asyncio
    async def test_forward_request_url_construction_without_trailing_slash(self, gateway):
        """Test URL construction when app URL has no trailing slash."""
        gateway.registered_routers["test-service"] = "http://localhost:8001"  # No trailing slash

        mock_request = Mock(spec=Request)
        mock_request.method = "POST"
        mock_request.headers = {}
        mock_request.body = AsyncMock(return_value=b"{}")

        mock_response = Mock()
        mock_response.json.return_value = {"result": "success"}
        mock_response.status_code = 200

        with patch.object(gateway.client, "request", return_value=mock_response) as mock_client_request:
            await gateway.forward_request(mock_request, "test-service", "echo")

            # Should construct URL correctly by adding the missing slash
            mock_client_request.assert_called_once_with(
                "POST",
                "http://localhost:8001/echo",  # Correct: slash added between URL and path
                headers={},
                content=b"{}",
            )
