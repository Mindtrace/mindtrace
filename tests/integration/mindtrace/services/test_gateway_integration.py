import asyncio
import time

import pytest
import requests

from mindtrace.services import Gateway
from mindtrace.services.samples.echo_service import EchoService


class TestGatewayCoreFunctionality:
    """Test core Gateway functionality including launch, registration, and basic operations."""

    @pytest.mark.asyncio
    async def test_gateway_launch_and_connectivity(self, gateway_manager):
        """Test that Gateway launches successfully and is accessible."""
        # Test basic connectivity
        assert gateway_manager is not None
        assert gateway_manager.url is not None

        # Test gateway status endpoint
        status = gateway_manager.status()
        assert status is not None

        # Test gateway heartbeat
        heartbeat = gateway_manager.heartbeat()
        assert heartbeat is not None

    @pytest.mark.asyncio
    async def test_gateway_app_registration_sync(self, gateway_manager, echo_service_for_gateway):
        """Test synchronous app registration with Gateway."""
        # Register echo service with gateway
        _ = gateway_manager.register_app(name="echoer", url=str(echo_service_for_gateway.url))

        # Verify registration was successful (register_app returns None but registers successfully)
        # The actual verification is that we can make requests to the registered app

        # Test that the app is accessible through gateway
        gateway_url = str(gateway_manager.url).rstrip("/")
        response = requests.post(f"{gateway_url}/echoer/echo", json={"message": "test", "delay": 0.0})
        assert response.status_code == 200

        result_data = response.json()
        assert "echoed" in result_data
        assert result_data["echoed"] == "test"

    @pytest.mark.asyncio
    async def test_gateway_app_registration_async(self, gateway_manager, echo_service_for_gateway):
        """Test asynchronous app registration with Gateway."""
        # Register echo service with gateway asynchronously
        _ = await gateway_manager.aregister_app(name="async_echoer", url=str(echo_service_for_gateway.url))

        # Verify registration was successful (aregister_app returns None but registers successfully)
        # The actual verification is that we can make requests to the registered app

        # Test that the app is accessible through gateway
        gateway_url = str(gateway_manager.url).rstrip("/")
        response = requests.post(f"{gateway_url}/async_echoer/echo", json={"message": "async test", "delay": 0.0})
        assert response.status_code == 200

        result_data = response.json()
        assert "echoed" in result_data
        assert result_data["echoed"] == "async test"

    @pytest.mark.asyncio
    async def test_gateway_request_forwarding(self, gateway_manager, echo_service_for_gateway):
        """Test that Gateway properly forwards requests to registered services."""
        # Register service
        gateway_manager.register_app("echoer", str(echo_service_for_gateway.url))

        # Test different HTTP methods
        gateway_url = str(gateway_manager.url).rstrip("/")

        # POST request (main service endpoint)
        response = requests.post(f"{gateway_url}/echoer/echo", json={"message": "forwarded", "delay": 0.0})
        assert response.status_code == 200
        assert response.json()["echoed"] == "forwarded"

        # Test with delay
        start_time = time.time()
        response = requests.post(f"{gateway_url}/echoer/echo", json={"message": "delayed", "delay": 0.1})
        end_time = time.time()
        assert response.status_code == 200
        assert response.json()["echoed"] == "delayed"
        assert end_time - start_time >= 0.1  # Should respect delay

    @pytest.mark.asyncio
    async def test_gateway_unregistered_app_error(self, gateway_manager):
        """Test that Gateway returns proper error for unregistered apps."""
        gateway_url = str(gateway_manager.url).rstrip("/")

        # Try to access unregistered app
        response = requests.post(f"{gateway_url}/nonexistent/echo", json={"message": "test"})
        assert response.status_code == 404
        assert "not found" in response.text.lower()

    @pytest.mark.asyncio
    async def test_gateway_multiple_apps(self, gateway_manager, echo_service_for_gateway):
        """Test registering and using multiple apps with Gateway."""
        # Register multiple instances of echo service with different names
        gateway_manager.register_app("echo1", str(echo_service_for_gateway.url))
        gateway_manager.register_app("echo2", str(echo_service_for_gateway.url))

        gateway_url = str(gateway_manager.url).rstrip("/")

        # Test both apps work independently
        response1 = requests.post(f"{gateway_url}/echo1/echo", json={"message": "app1", "delay": 0.0})
        response2 = requests.post(f"{gateway_url}/echo2/echo", json={"message": "app2", "delay": 0.0})

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json()["echoed"] == "app1"
        assert response2.json()["echoed"] == "app2"


class TestProxyConnectionManager:
    """Test ProxyConnectionManager functionality and routing behavior."""

    @pytest.mark.asyncio
    async def test_proxy_creation_and_configuration(self, gateway_manager, echo_service_for_gateway):
        """Test ProxyConnectionManager creation and basic configuration."""
        # Create connection managers
        echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
        gateway_cm = Gateway.connect(url=gateway_manager.url)

        # Register service with gateway and create proxy
        gateway_cm.register_app("echoer", str(echo_service_for_gateway.url), echo_cm)

        # Get the proxy connection manager
        proxy_cm = getattr(gateway_cm, "echoer")

        # Verify proxy configuration
        assert proxy_cm.gateway_url == str(gateway_manager.url).rstrip("/")
        assert proxy_cm.app_name == "echoer"
        assert proxy_cm.original_cm == echo_cm

        # Verify proxy has the expected methods
        assert hasattr(proxy_cm, "echo")
        assert hasattr(proxy_cm, "aecho")
        assert callable(proxy_cm.echo)
        assert callable(proxy_cm.aecho)

    @pytest.mark.asyncio
    async def test_proxy_sync_method_routing(self, gateway_manager, echo_service_for_gateway):
        """Test that ProxyConnectionManager routes sync methods through gateway."""
        # Set up connection managers
        echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
        gateway_cm = Gateway.connect(url=gateway_manager.url)

        # Register service with gateway
        gateway_cm.register_app("echoer", str(echo_service_for_gateway.url), echo_cm)
        proxy_cm = getattr(gateway_cm, "echoer")

        # Mock the original connection manager to detect direct calls
        direct_calls = []
        original_echo = echo_cm.echo

        def mock_echo(*args, **kwargs):
            direct_calls.append(("echo", args, kwargs))
            return original_echo(*args, **kwargs)

        echo_cm.echo = mock_echo

        # Call through proxy - should NOT call original directly
        result = proxy_cm.echo(message="proxy test", delay=0.0)

        # Verify no direct calls were made
        assert len(direct_calls) == 0, f"Direct calls detected: {direct_calls}"

        # Verify result came through gateway
        assert hasattr(result, "echoed")
        assert result.echoed == "proxy test"

    @pytest.mark.asyncio
    async def test_proxy_async_method_routing(self, gateway_manager, echo_service_for_gateway):
        """Test that ProxyConnectionManager routes async methods through gateway."""
        # Set up connection managers
        echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
        gateway_cm = Gateway.connect(url=gateway_manager.url)

        # Register service with gateway
        gateway_cm.register_app("echoer", str(echo_service_for_gateway.url), echo_cm)
        proxy_cm = getattr(gateway_cm, "echoer")

        # Mock the original connection manager to detect direct calls
        direct_calls = []
        original_aecho = echo_cm.aecho

        async def mock_aecho(*args, **kwargs):
            direct_calls.append(("aecho", args, kwargs))
            return await original_aecho(*args, **kwargs)

        echo_cm.aecho = mock_aecho

        # Call through proxy - should NOT call original directly
        result = await proxy_cm.aecho(message="async proxy test", delay=0.0)

        # Verify no direct calls were made
        assert len(direct_calls) == 0, f"Direct calls detected: {direct_calls}"

        # Verify result came through gateway
        assert hasattr(result, "echoed")
        assert result.echoed == "async proxy test"

    @pytest.mark.asyncio
    async def test_proxy_schema_validation(self, gateway_manager, echo_service_for_gateway):
        """Test that ProxyConnectionManager properly validates schemas."""
        # Set up connection managers
        echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
        gateway_cm = Gateway.connect(url=gateway_manager.url)

        # Register service with gateway
        gateway_cm.register_app("echoer", str(echo_service_for_gateway.url), echo_cm)
        proxy_cm = getattr(gateway_cm, "echoer")

        # Test with valid input
        result = proxy_cm.echo(message="valid message", delay=0.0)
        assert result.echoed == "valid message"

        # Test with invalid input (missing required field)
        with pytest.raises(Exception):
            proxy_cm.echo(delay=0.0)  # Missing 'message' field

    @pytest.mark.asyncio
    async def test_proxy_vs_direct_comparison(self, gateway_manager, echo_service_for_gateway):
        """Compare proxy behavior with direct connection manager behavior."""
        # Create both direct and proxy connection managers
        direct_cm = EchoService.connect(url=echo_service_for_gateway.url)
        gateway_cm = Gateway.connect(url=gateway_manager.url)

        # Register service with gateway to create proxy
        gateway_cm.register_app("echoer", str(echo_service_for_gateway.url), direct_cm)
        proxy_cm = getattr(gateway_cm, "echoer")

        # Test that both work but route differently
        direct_result = direct_cm.echo(message="direct", delay=0.0)
        proxy_result = proxy_cm.echo(message="proxy", delay=0.0)

        assert direct_result.echoed == "direct"
        assert proxy_result.echoed == "proxy"

        # Verify they have different routing behavior
        assert str(direct_cm.url) == str(echo_service_for_gateway.url)
        assert proxy_cm.gateway_url == str(gateway_manager.url).rstrip("/")

    @pytest.mark.asyncio
    async def test_proxy_error_handling(self, gateway_manager, echo_service_for_gateway):
        """Test ProxyConnectionManager error handling scenarios."""
        # Set up connection managers
        echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
        gateway_cm = Gateway.connect(url=gateway_manager.url)

        # Register service with gateway
        gateway_cm.register_app("echoer", str(echo_service_for_gateway.url), echo_cm)
        proxy_cm = getattr(gateway_cm, "echoer")

        # Test with invalid gateway URL
        bad_proxy = type(proxy_cm)(
            gateway_url="http://localhost:9999",  # Non-existent gateway
            app_name="echoer",
            original_cm=echo_cm,
        )

        with pytest.raises(Exception):
            bad_proxy.echo(message="test", delay=0.0)


class TestGatewayEndToEndIntegration:
    """Test complete end-to-end integration scenarios."""

    @pytest.mark.asyncio
    async def test_complete_request_flow(self, gateway_manager, echo_service_for_gateway):
        """Test complete request flow: Client → Gateway → Service → Response."""
        # Set up the complete system
        echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
        gateway_cm = Gateway.connect(url=gateway_manager.url)

        # Register service with gateway
        gateway_cm.register_app("echoer", str(echo_service_for_gateway.url), echo_cm)
        proxy_cm = getattr(gateway_cm, "echoer")

        # Test complete flow
        message = "Hello from end-to-end test!"
        result = proxy_cm.echo(message=message, delay=0.0)

        # Verify the complete flow worked
        assert result.echoed == message

        # Verify the request actually went through the gateway
        # by checking that the proxy didn't call the original CM directly
        assert proxy_cm.gateway_url == str(gateway_manager.url).rstrip("/")
        assert proxy_cm.app_name == "echoer"

    @pytest.mark.asyncio
    async def test_concurrent_requests_through_gateway(self, gateway_manager, echo_service_for_gateway):
        """Test handling of concurrent requests through gateway."""
        # Set up the system
        echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
        gateway_cm = Gateway.connect(url=gateway_manager.url)
        gateway_cm.register_app("echoer", str(echo_service_for_gateway.url), echo_cm)
        proxy_cm = getattr(gateway_cm, "echoer")

        # Create concurrent requests
        async def make_request(i):
            return await proxy_cm.aecho(message=f"concurrent message {i}", delay=0.1)

        # Run concurrent requests
        start_time = time.time()
        tasks = [make_request(i) for i in range(5)]
        results = await asyncio.gather(*tasks)
        end_time = time.time()

        # Verify all requests completed successfully
        assert len(results) == 5
        for i, result in enumerate(results):
            assert result.echoed == f"concurrent message {i}"

        # Verify concurrent execution (should be faster than sequential)
        # 5 requests with 0.1s delay each = 0.5s sequential, should be < 0.5s concurrent
        assert end_time - start_time < 0.5


class TestGatewayErrorScenarios:
    """Test Gateway error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_service_unavailable(self, gateway_manager):
        """Test Gateway behavior when registered service is unavailable."""
        # Register a service that doesn't exist
        gateway_cm = Gateway.connect(url=gateway_manager.url)
        gateway_cm.register_app("bad_service", "http://localhost:9999")

        # Try to access the unavailable service
        gateway_url = str(gateway_manager.url).rstrip("/")
        response = requests.post(f"{gateway_url}/bad_service/echo", json={"message": "test"})

        # Should get an error response
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_gateway_timeout_handling(self, gateway_manager, echo_service_for_gateway):
        """Test Gateway timeout handling for slow services."""
        # Set up the system
        echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
        gateway_cm = Gateway.connect(url=gateway_manager.url)
        gateway_cm.register_app("echoer", str(echo_service_for_gateway.url), echo_cm)
        proxy_cm = getattr(gateway_cm, "echoer")

        # Test with a reasonable delay (should work)
        result = proxy_cm.echo(message="timeout test", delay=0.1)
        assert result.echoed == "timeout test"

        # Test with a very long delay (should timeout)
        with pytest.raises(Exception):
            proxy_cm.echo(message="timeout test", delay=10.0)

    @pytest.mark.asyncio
    async def test_invalid_request_handling(self, gateway_manager, echo_service_for_gateway):
        """Test Gateway handling of invalid requests."""
        # Set up the system
        echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
        gateway_cm = Gateway.connect(url=gateway_manager.url)
        gateway_cm.register_app("echoer", str(echo_service_for_gateway.url), echo_cm)

        # Test with invalid JSON
        gateway_url = str(gateway_manager.url).rstrip("/")
        response = requests.post(
            f"{gateway_url}/echoer/echo", data="invalid json", headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422  # Validation error

        # Test with missing required fields
        response = requests.post(f"{gateway_url}/echoer/echo", json={"delay": 0.0})
        assert response.status_code == 422  # Missing 'message' field

    @pytest.mark.asyncio
    async def test_gateway_url_construction_trailing_slash(self, gateway_manager, echo_service_for_gateway):
        """Test Gateway URL construction logic for trailing slash handling."""
        # Register service with URL that ends with trailing slash
        service_url_with_slash = str(echo_service_for_gateway.url).rstrip("/") + "/"
        gateway_manager.register_app("echoer_slash", service_url_with_slash)

        # Test that requests work correctly with trailing slash in service URL
        gateway_url = str(gateway_manager.url).rstrip("/")
        response = requests.post(
            f"{gateway_url}/echoer_slash/echo", json={"message": "trailing slash test", "delay": 0.0}
        )
        assert response.status_code == 200
        assert response.json()["echoed"] == "trailing slash test"

    @pytest.mark.asyncio
    async def test_gateway_url_construction_no_trailing_slash(self, gateway_manager, echo_service_for_gateway):
        """Test Gateway URL construction logic for no trailing slash handling."""
        # Register service with URL that doesn't end with trailing slash
        service_url_without_slash = str(echo_service_for_gateway.url).rstrip("/")
        gateway_manager.register_app("echoer_no_slash", service_url_without_slash)

        # Test that requests work correctly without trailing slash in service URL
        gateway_url = str(gateway_manager.url).rstrip("/")
        response = requests.post(
            f"{gateway_url}/echoer_no_slash/echo", json={"message": "no trailing slash test", "delay": 0.0}
        )
        assert response.status_code == 200
        assert response.json()["echoed"] == "no trailing slash test"

    @pytest.mark.asyncio
    async def test_gateway_network_error_handling(self, gateway_manager):
        """Test Gateway error handling when network errors occur."""
        # Register a service that doesn't exist to trigger network error
        gateway_cm = Gateway.connect(url=gateway_manager.url)
        gateway_cm.register_app("bad_service", "http://localhost:9999")

        # Try to access the unavailable service - this should trigger httpx.RequestError
        gateway_url = str(gateway_manager.url).rstrip("/")
        response = requests.post(f"{gateway_url}/bad_service/echo", json={"message": "test"})

        # Should get 500 error due to network failure (httpx.RequestError)
        assert response.status_code == 500
        assert "All connection attempts failed" in response.text

    @pytest.mark.asyncio
    async def test_gateway_connect_unavailable_service(self):
        """Test Gateway.connect when service is not available."""
        # Try to connect to a non-existent gateway
        with pytest.raises(Exception) as exc_info:
            Gateway.connect(url="http://localhost:9999", timeout=1)

        # Should raise an exception due to service unavailability
        assert "Server failed to connect" in str(exc_info.value)


class TestGatewayPerformance:
    """Test Gateway performance characteristics."""

    @pytest.mark.asyncio
    async def test_gateway_overhead_measurement(self, gateway_manager, echo_service_for_gateway):
        """Measure and verify Gateway overhead is reasonable."""
        # Set up direct and proxy connection managers
        direct_cm = EchoService.connect(url=echo_service_for_gateway.url)
        gateway_cm = Gateway.connect(url=gateway_manager.url)
        gateway_cm.register_app("echoer", str(echo_service_for_gateway.url), direct_cm)
        proxy_cm = getattr(gateway_cm, "echoer")

        # Measure direct call time
        start_time = time.time()
        direct_cm.echo(message="direct", delay=0.0)
        direct_time = time.time() - start_time

        # Measure proxy call time
        start_time = time.time()
        proxy_cm.echo(message="proxy", delay=0.0)
        proxy_time = time.time() - start_time

        # Gateway overhead should be reasonable (< 100ms for simple requests)
        overhead = proxy_time - direct_time
        assert overhead < 0.1, f"Gateway overhead too high: {overhead:.3f}s"

    @pytest.mark.asyncio
    async def test_gateway_connection_pooling(self, gateway_manager, echo_service_for_gateway):
        """Test that Gateway efficiently handles multiple connections."""
        # Set up the system
        echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
        gateway_cm = Gateway.connect(url=gateway_manager.url)
        gateway_cm.register_app("echoer", str(echo_service_for_gateway.url), echo_cm)
        proxy_cm = getattr(gateway_cm, "echoer")

        # Make multiple rapid requests
        start_time = time.time()
        for i in range(10):
            result = proxy_cm.echo(message=f"rapid {i}", delay=0.0)
            assert result.echoed == f"rapid {i}"
        end_time = time.time()

        # Should complete quickly
        total_time = end_time - start_time
        assert total_time < 1.0, f"Multiple requests took too long: {total_time:.3f}s"


class TestGatewayResourceManagement:
    """Test Gateway resource management and cleanup."""

    @pytest.mark.asyncio
    async def test_gateway_cleanup(self, gateway_manager, echo_service_for_gateway):
        """Test that Gateway properly cleans up resources."""
        # Set up the system
        echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
        gateway_cm = Gateway.connect(url=gateway_manager.url)
        gateway_cm.register_app("echoer", str(echo_service_for_gateway.url), echo_cm)
        proxy_cm = getattr(gateway_cm, "echoer")

        # Make some requests
        proxy_cm.echo(message="cleanup test", delay=0.0)

        # Verify gateway is still responsive after requests
        status = gateway_cm.status()
        assert status is not None

        # Test that we can still make requests
        result = proxy_cm.echo(message="post cleanup test", delay=0.0)
        assert result.echoed == "post cleanup test"

    @pytest.mark.asyncio
    async def test_gateway_registered_apps_property(self, gateway_manager, echo_service_for_gateway):
        """Test the registered_apps property of the enhanced Gateway connection manager."""
        # Set up the system
        echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
        gateway_cm = Gateway.connect(url=gateway_manager.url)

        # Initially no apps should be registered
        assert len(gateway_cm.registered_apps) == 0

        # Register an app
        gateway_cm.register_app("echoer", str(echo_service_for_gateway.url), echo_cm)

        # Verify app is in registered_apps
        assert "echoer" in gateway_cm.registered_apps
        assert len(gateway_cm.registered_apps) == 1

        # Register another app
        gateway_cm.register_app("echoer2", str(echo_service_for_gateway.url), echo_cm)

        # Verify both apps are registered
        assert "echoer" in gateway_cm.registered_apps
        assert "echoer2" in gateway_cm.registered_apps
        assert len(gateway_cm.registered_apps) == 2
