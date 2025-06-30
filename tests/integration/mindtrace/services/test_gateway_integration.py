import asyncio
import time
from unittest.mock import patch

import pytest
import pytest_asyncio
import requests
from urllib3.util.url import Url, parse_url

from mindtrace.services.gateway.gateway import Gateway
from mindtrace.services.gateway.types import AppConfig
from mindtrace.services.sample.echo_service import EchoService


class TestGatewayBasicFunctionality:
    """Test basic Gateway functionality with real service interactions."""

    @pytest.mark.asyncio
    async def test_gateway_launch_and_connection(self, gateway_manager):
        """Test that Gateway can be launched and connected to."""
        # Test that the gateway manager is available
        assert gateway_manager is not None
        
        # Test that we can make a request to the gateway using the status endpoint
        response = requests.post(f"{gateway_manager.url}status", timeout=10)
        assert response.status_code == 200
        
        # Verify the response contains expected status information
        response_data = response.json()
        assert "status" in response_data

    @pytest.mark.asyncio
    async def test_gateway_service_registration(self, gateway_manager, echo_service_for_gateway):
        """Test registering a real service with the Gateway."""
        # Register the echo service with the gateway
        app_config = AppConfig(
            name="echo", 
            url=str(echo_service_for_gateway.url)
        )
        
        # Register the echo service with the gateway
        # The registration should succeed without raising an exception
        gateway_manager.register_app(
            name=app_config.name,
            url=app_config.url
        )

    @pytest.mark.asyncio
    async def test_gateway_request_forwarding(self, gateway_manager, echo_service_for_gateway):
        """Test that Gateway properly forwards requests to registered services."""
        # Register the echo service
        app_config = AppConfig(name="echo", url=str(echo_service_for_gateway.url))
        gateway_manager.register_app(name=app_config.name, url=app_config.url)
        
        # Give the registration time to take effect
        await asyncio.sleep(0.1)
        
        # Make a request through the gateway to the echo service
        gateway_url = str(gateway_manager.url).rstrip('/')
        echo_endpoint = f"{gateway_url}/echo/echo"
        
        response = requests.post(
            echo_endpoint,
            json={"message": "Hello through Gateway!"},
            timeout=10
        )
        
        assert response.status_code == 200
        response_data = response.json()
        assert "echoed" in response_data
        assert response_data["echoed"] == "Hello through Gateway!"

    @pytest.mark.asyncio
    async def test_gateway_request_forwarding_with_url_object(self, gateway_manager, echo_service_for_gateway):
        """Test that Gateway properly handles Url objects for service registration and request forwarding."""
        # Register the echo service using a Url object instead of string
        echo_url = parse_url(str(echo_service_for_gateway.url))
        app_config = AppConfig(name="echo-url", url=echo_url)
        gateway_manager.register_app(name=app_config.name, url=app_config.url)
        
        # Give the registration time to take effect
        await asyncio.sleep(0.1)
        
        # Make a request through the gateway to the echo service
        gateway_url = str(gateway_manager.url).rstrip('/')
        echo_endpoint = f"{gateway_url}/echo-url/echo"
        
        response = requests.post(
            echo_endpoint,
            json={"message": "Hello through Gateway with Url object!"},
            timeout=10
        )
        
        assert response.status_code == 200
        response_data = response.json()
        assert "echoed" in response_data
        assert response_data["echoed"] == "Hello through Gateway with Url object!"

    @pytest.mark.asyncio
    async def test_gateway_cors_headers(self, gateway_manager):
        """Test that Gateway properly handles CORS headers."""
        # Make an OPTIONS request to check CORS headers
        response = requests.options(
            f"{gateway_manager.url}status",
            headers={"Origin": "http://localhost:3000"},
            timeout=10
        )
        
        # Should have CORS headers
        assert "Access-Control-Allow-Origin" in response.headers
        assert response.headers["Access-Control-Allow-Origin"] == "*"


class TestGatewayEnhancedConnectionManager:
    """Test Gateway's enhanced connection manager functionality."""

    @pytest.mark.asyncio
    async def test_gateway_connect_returns_enhanced_cm(self):
        """Test that Gateway.connect() returns an enhanced connection manager."""
        # Launch a gateway for this test
        with Gateway.launch(url="http://localhost:8093", timeout=30) as gateway_cm:
            # Connect to the gateway to get enhanced connection manager
            enhanced_cm = Gateway.connect(url="http://localhost:8093")
            
            # Test that enhanced methods are available
            assert hasattr(enhanced_cm, 'register_app')
            assert hasattr(enhanced_cm, 'aregister_app')
            assert hasattr(enhanced_cm, 'registered_apps')
            assert hasattr(enhanced_cm, '_registered_apps')
            
            # Test that registered_apps starts empty
            assert len(enhanced_cm.registered_apps) == 0

    @pytest.mark.asyncio
    async def test_enhanced_cm_service_registration_sync(self, echo_service_for_gateway):
        """Test service registration through enhanced connection manager (sync)."""
        with Gateway.launch(url="http://localhost:8094", timeout=30) as gateway_cm:
            enhanced_cm = Gateway.connect(url="http://localhost:8094")
            
            # Register service without connection manager (basic registration)
            result = enhanced_cm.register_app(
                name="echo-basic",
                url=str(echo_service_for_gateway.url)
            )
            
            # Should not create proxy since no connection_manager provided
            assert not hasattr(enhanced_cm, 'echo-basic')
            assert len(enhanced_cm.registered_apps) == 0

    @pytest.mark.asyncio
    async def test_enhanced_cm_service_registration_with_proxy(self, echo_service_for_gateway):
        """Test service registration with ProxyConnectionManager creation."""
        with Gateway.launch(url="http://localhost:8095", timeout=30) as gateway_cm:
            enhanced_cm = Gateway.connect(url="http://localhost:8095")
            
            # Create a connection manager for the echo service
            echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
            
            # Register service with connection manager (should create proxy)
            result = enhanced_cm.register_app(
                name="echo-proxy",
                url=str(echo_service_for_gateway.url),
                connection_manager=echo_cm
            )
            
            # Should create proxy and attach it
            assert hasattr(enhanced_cm, 'echo-proxy')
            assert 'echo-proxy' in enhanced_cm.registered_apps
            assert len(enhanced_cm.registered_apps) == 1
            
            # The attached attribute should be a ProxyConnectionManager
            proxy = getattr(enhanced_cm, 'echo-proxy')
            assert proxy is not None
            assert hasattr(proxy, 'gateway_url')
            assert hasattr(proxy, 'app_name')
            assert hasattr(proxy, 'original_cm')

    @pytest.mark.asyncio
    async def test_enhanced_cm_async_registration(self, echo_service_for_gateway):
        """Test async service registration through enhanced connection manager."""
        with Gateway.launch(url="http://localhost:8096", timeout=30) as gateway_cm:
            enhanced_cm = Gateway.connect(url="http://localhost:8096")
            
            # Create a connection manager for the echo service  
            echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
            
            # Register service asynchronously
            result = await enhanced_cm.aregister_app(
                name="echo-async",
                url=str(echo_service_for_gateway.url),
                connection_manager=echo_cm
            )
            
            # Should create proxy and attach it
            assert hasattr(enhanced_cm, 'echo-async')
            assert 'echo-async' in enhanced_cm.registered_apps
            assert len(enhanced_cm.registered_apps) == 1

    @pytest.mark.asyncio
    async def test_enhanced_cm_service_registration_with_url_object(self, echo_service_for_gateway):
        """Test enhanced connection manager registration with Url objects."""
        with Gateway.launch(url="http://localhost:8102", timeout=30) as gateway_cm:
            enhanced_cm = Gateway.connect(url="http://localhost:8102")
            
            # Create a connection manager for the echo service
            echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
            
            # Register service with Url object (should create proxy)
            echo_url = parse_url(str(echo_service_for_gateway.url))
            result = enhanced_cm.register_app(
                name="echo-url-object",
                url=echo_url,
                connection_manager=echo_cm
            )
            
            # Should create proxy and attach it
            assert hasattr(enhanced_cm, 'echo-url-object')
            assert 'echo-url-object' in enhanced_cm.registered_apps
            assert len(enhanced_cm.registered_apps) == 1
            
            # The attached attribute should be a ProxyConnectionManager
            proxy = getattr(enhanced_cm, 'echo-url-object')
            assert proxy is not None
            assert hasattr(proxy, 'gateway_url')
            assert hasattr(proxy, 'app_name')
            assert hasattr(proxy, 'original_cm')


class TestGatewayProxyConnectionManager:
    """Test ProxyConnectionManager functionality in integration scenarios."""

    @pytest.mark.asyncio
    async def test_proxy_method_call_through_gateway(self, echo_service_for_gateway):
        """Test calling service methods through ProxyConnectionManager via Gateway."""
        with Gateway.launch(url="http://localhost:8097", timeout=30) as gateway_cm:
            enhanced_cm = Gateway.connect(url="http://localhost:8097")
            
            # Register echo service with proxy
            echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
            enhanced_cm.register_app(
                name="echo",
                url=str(echo_service_for_gateway.url),
                connection_manager=echo_cm
            )
            
            # Give registration time to take effect
            await asyncio.sleep(0.1)
            
            # Call echo method through the proxy
            proxy = enhanced_cm.echo
            result = proxy.echo(message="Hello through proxy!")
            
            # Should get the expected response
            assert result is not None
            assert "echoed" in result
            assert result["echoed"] == "Hello through proxy!"

    @pytest.mark.asyncio
    async def test_proxy_property_access_through_gateway(self, echo_service_for_gateway):
        """Test accessing service properties through ProxyConnectionManager."""
        with Gateway.launch(url="http://localhost:8098", timeout=30) as gateway_cm:
            enhanced_cm = Gateway.connect(url="http://localhost:8098")
            
            # Register echo service with proxy
            echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
            enhanced_cm.register_app(
                name="echo",
                url=str(echo_service_for_gateway.url),
                connection_manager=echo_cm
            )
            
            # Give registration time to take effect
            await asyncio.sleep(0.1)
            
            # Access a property through the proxy
            proxy = enhanced_cm.echo
            try:
                # Note: This will make a GET request to /echo/status
                status = proxy.status
                # If the echo service has a status endpoint, this should work
                assert status is not None
            except Exception as e:
                # If the echo service doesn't have a status property endpoint,
                # we should get a reasonable error
                assert "404" in str(e) or "Failed to get property" in str(e) or "Method Not Allowed" in str(e)

    @pytest.mark.asyncio
    async def test_proxy_multiple_services(self, echo_service_for_gateway):
        """Test managing multiple services through ProxyConnectionManager."""
        with Gateway.launch(url="http://localhost:8099", timeout=30) as gateway_cm:
            enhanced_cm = Gateway.connect(url="http://localhost:8099")
            
            # Register first echo service
            echo_cm1 = EchoService.connect(url=echo_service_for_gateway.url)
            enhanced_cm.register_app(
                name="echo1",
                url=str(echo_service_for_gateway.url),
                connection_manager=echo_cm1
            )
            
            # Register second echo service (same service, different name)
            echo_cm2 = EchoService.connect(url=echo_service_for_gateway.url)
            enhanced_cm.register_app(
                name="echo2", 
                url=str(echo_service_for_gateway.url),
                connection_manager=echo_cm2
            )
            
            # Should have both services registered
            assert len(enhanced_cm.registered_apps) == 2
            assert 'echo1' in enhanced_cm.registered_apps
            assert 'echo2' in enhanced_cm.registered_apps
            
            # Should have both proxy attributes
            assert hasattr(enhanced_cm, 'echo1')
            assert hasattr(enhanced_cm, 'echo2')
            
            # Give registration time to take effect
            await asyncio.sleep(0.1)
            
            # Should be able to call methods on both services
            result1 = enhanced_cm.echo1.echo(message="Hello from echo1!")
            result2 = enhanced_cm.echo2.echo(message="Hello from echo2!")
            
            assert result1["echoed"] == "Hello from echo1!"
            assert result2["echoed"] == "Hello from echo2!"


class TestGatewayErrorHandling:
    """Test Gateway error handling in integration scenarios."""

    @pytest.mark.asyncio
    async def test_gateway_service_not_found(self, gateway_manager):
        """Test Gateway behavior when requesting non-existent service."""
        # Try to make a request to a non-registered service
        gateway_url = str(gateway_manager.url).rstrip('/')
        response = requests.post(
            f"{gateway_url}/nonexistent/echo",
            json={"message": "test"},
            timeout=10
        )
        
        # Should get 404 for non-existent service
        assert response.status_code == 404
        assert "not found" in response.text.lower()

    @pytest.mark.asyncio
    async def test_gateway_service_unavailable(self, gateway_manager):
        """Test Gateway behavior when registered service becomes unavailable."""
        # Register a service with an invalid URL
        gateway_manager.register_app(
            name="unavailable",
            url="http://localhost:9999"  # Nothing running on this port
        )
        
        # Give registration time to take effect
        await asyncio.sleep(0.1)
        
        # Try to make a request to the unavailable service
        gateway_url = str(gateway_manager.url).rstrip('/')
        response = requests.post(
            f"{gateway_url}/unavailable/echo",
            json={"message": "test"},
            timeout=10
        )
        
        # Should get 500 for unavailable service
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_proxy_connection_manager_service_down(self, echo_service_for_gateway):
        """Test ProxyConnectionManager behavior when service goes down."""
        with Gateway.launch(url="http://localhost:8100", timeout=30) as gateway_cm:
            enhanced_cm = Gateway.connect(url="http://localhost:8100")
            
            # Register echo service with proxy
            echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
            enhanced_cm.register_app(
                name="echo",
                url=str(echo_service_for_gateway.url),
                connection_manager=echo_cm
            )
            
            # Give registration time to take effect
            await asyncio.sleep(0.1)
            
            # Temporarily patch requests to simulate service being down
            def mock_request_failure(*args, **kwargs):
                raise requests.ConnectionError("Service unavailable")
            
            with patch('requests.post', side_effect=mock_request_failure):
                # Try to call method through proxy
                proxy = enhanced_cm.echo
                
                with pytest.raises(requests.ConnectionError):
                    proxy.echo(message="This should fail")


class TestGatewayPerformanceAndTiming:
    """Test Gateway performance and timing characteristics."""

    @pytest.mark.asyncio
    async def test_gateway_request_latency(self, gateway_manager, echo_service_for_gateway):
        """Test that Gateway introduces minimal latency."""
        # Register echo service
        gateway_manager.register_app(
            name="echo",
            url=str(echo_service_for_gateway.url)
        )
        
        await asyncio.sleep(0.1)
        
        # Time direct request to echo service
        start_time = time.time()
        direct_response = requests.post(
            f"{str(echo_service_for_gateway.url)}echo",
            json={"message": "Direct request"},
            timeout=10
        )
        direct_time = time.time() - start_time
        
        # Time request through gateway
        start_time = time.time()
        gateway_response = requests.post(
            f"{str(gateway_manager.url).rstrip('/')}/echo/echo",
            json={"message": "Gateway request"},
            timeout=10
        )
        gateway_time = time.time() - start_time
        
        # Both should succeed
        assert direct_response.status_code == 200
        assert gateway_response.status_code == 200
        
        # Gateway should add minimal overhead (allowing for some variance)
        # This is just a sanity check - actual performance depends on many factors
        assert gateway_time < direct_time * 3  # Allow 3x overhead for integration test

    @pytest.mark.asyncio
    async def test_gateway_concurrent_requests(self, gateway_manager, echo_service_for_gateway):
        """Test Gateway handling of concurrent requests."""
        # Register echo service
        gateway_manager.register_app(
            name="echo",
            url=str(echo_service_for_gateway.url)
        )
        
        await asyncio.sleep(0.1)
        
        # Make concurrent requests
        async def make_request(message):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{str(gateway_manager.url).rstrip('/')}/echo/echo",
                    json={"message": message},
                    timeout=10
                )
            )
        
        # Send 5 concurrent requests
        tasks = [make_request(f"Message {i}") for i in range(5)]
        responses = await asyncio.gather(*tasks)
        
        # All should succeed
        for i, response in enumerate(responses):
            assert response.status_code == 200
            data = response.json()
            assert data["echoed"] == f"Message {i}"


class TestGatewayComplexScenarios:
    """Test complex real-world Gateway usage scenarios."""

    @pytest.mark.asyncio
    async def test_gateway_service_replacement(self, gateway_manager, echo_service_for_gateway):
        """Test replacing a service registration with a new URL."""
        # Register echo service initially
        gateway_manager.register_app(
            name="echo",
            url=str(echo_service_for_gateway.url)
        )
        
        await asyncio.sleep(0.1)
        
        # Make a request to verify it works
        response1 = requests.post(
            f"{str(gateway_manager.url).rstrip('/')}/echo/echo",
            json={"message": "First registration"},
            timeout=10
        )
        assert response1.status_code == 200
        
        # Re-register with same name (should replace)
        gateway_manager.register_app(
            name="echo",
            url=str(echo_service_for_gateway.url)  # Same URL but simulates replacement
        )
        
        await asyncio.sleep(0.1)
        
        # Should still work
        response2 = requests.post(
            f"{str(gateway_manager.url).rstrip('/')}/echo/echo",
            json={"message": "Second registration"},
            timeout=10
        )
        assert response2.status_code == 200
        assert response2.json()["echoed"] == "Second registration"

    @pytest.mark.asyncio
    async def test_gateway_with_proxy_full_workflow(self, echo_service_for_gateway):
        """Test complete workflow: Gateway + Service + ProxyConnectionManager."""
        with Gateway.launch(url="http://localhost:8101", timeout=30) as gateway_cm:
            # Step 1: Connect to gateway to get enhanced connection manager
            enhanced_cm = Gateway.connect(url="http://localhost:8101")
            
            # Step 2: Create connection manager for echo service
            echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
            
            # Step 3: Register echo service with proxy
            enhanced_cm.register_app(
                name="echo",
                url=str(echo_service_for_gateway.url),
                connection_manager=echo_cm
            )
            
            await asyncio.sleep(0.1)
            
            # Step 4: Use proxy to call service methods
            proxy = enhanced_cm.echo
            
            # Test different method calls
            echo_result = proxy.echo(message="Hello World!")
            assert echo_result["echoed"] == "Hello World!"
            
            # Test with different parameters
            echo_result2 = proxy.echo(message="Test Message", delay=0.0)
            assert echo_result2["echoed"] == "Test Message"
            
            # Test status method (if available)
            try:
                status_result = proxy.status()
                assert status_result is not None
            except Exception as e:
                # Expected if echo service doesn't have status endpoint or method not allowed
                assert "404" in str(e) or "Failed" in str(e) or "Method Not Allowed" in str(e)
            
            # Verify the proxy attributes
            assert proxy.gateway_url == "http://localhost:8101"
            assert proxy.app_name == "echo"
            assert proxy.original_cm == echo_cm
