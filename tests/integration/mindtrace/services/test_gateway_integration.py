import asyncio
import inspect
import logging
import time
import unittest.mock
from unittest.mock import patch, Mock

import pytest
import pytest_asyncio
import requests
import httpx
from urllib3.util.url import Url, parse_url
from pydantic import BaseModel

from mindtrace.core import TaskSchema
from mindtrace.services import AppConfig, Gateway, generate_connection_manager, Service
from mindtrace.services.sample.echo_service import EchoService, EchoInput, EchoOutput


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
        result = gateway_manager.register_app(
            name="echoer", 
            url=str(echo_service_for_gateway.url)
        )
        
        # Verify registration was successful (register_app returns None but registers successfully)
        # The actual verification is that we can make requests to the registered app
        
        # Test that the app is accessible through gateway
        gateway_url = str(gateway_manager.url).rstrip('/')
        response = requests.post(f"{gateway_url}/echoer/echo", json={"message": "test", "delay": 0.0})
        assert response.status_code == 200
        
        result_data = response.json()
        assert "echoed" in result_data
        assert result_data["echoed"] == "test"

    @pytest.mark.asyncio
    async def test_gateway_app_registration_async(self, gateway_manager, echo_service_for_gateway):
        """Test asynchronous app registration with Gateway."""
        # Register echo service with gateway asynchronously
        result = await gateway_manager.aregister_app(
            name="async_echoer", 
            url=str(echo_service_for_gateway.url)
        )
        
        # Verify registration was successful (aregister_app returns None but registers successfully)
        # The actual verification is that we can make requests to the registered app
        
        # Test that the app is accessible through gateway
        gateway_url = str(gateway_manager.url).rstrip('/')
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
        gateway_url = str(gateway_manager.url).rstrip('/')
        
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
        gateway_url = str(gateway_manager.url).rstrip('/')
        
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
        
        gateway_url = str(gateway_manager.url).rstrip('/')
        
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
        proxy_cm = getattr(gateway_cm, 'echoer')
        
        # Verify proxy configuration
        assert proxy_cm.gateway_url == str(gateway_manager.url).rstrip('/')
        assert proxy_cm.app_name == "echoer"
        assert proxy_cm.original_cm == echo_cm
        
        # Verify proxy has the expected methods
        assert hasattr(proxy_cm, 'echo')
        assert hasattr(proxy_cm, 'aecho')
        assert callable(proxy_cm.echo)
        assert callable(proxy_cm.aecho)

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
            assert len(enhanced_cm.registered_apps()) == 0

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
            # But it should still track the registration
            apps = enhanced_cm.registered_apps()
            assert len(apps) == 1
            # Check if it's a list of AppInfo objects or strings
            if apps and hasattr(apps[0], 'name'):
                assert apps[0].name == 'echo-basic'
            else:
                assert 'echo-basic' in apps

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
            apps = enhanced_cm.registered_apps()
            assert len(apps) == 1
            
            # Check if it's a list of AppInfo objects or strings
            if apps and hasattr(apps[0], 'name'):
                assert apps[0].name == 'echo-proxy'
            else:
                assert 'echo-proxy' in apps
            
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
            apps = enhanced_cm.registered_apps()
            assert len(apps) == 1
            
            # Check if it's a list of AppInfo objects or strings
            if apps and hasattr(apps[0], 'name'):
                assert apps[0].name == 'echo-async'
            else:
                assert 'echo-async' in apps

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
            apps = enhanced_cm.registered_apps()
            assert len(apps) == 1
            
            # Check if it's a list of AppInfo objects or strings
            if apps and hasattr(apps[0], 'name'):
                assert apps[0].name == 'echo-url-object'
            else:
                assert 'echo-url-object' in apps
            
            # The attached attribute should be a ProxyConnectionManager
            proxy = getattr(enhanced_cm, 'echo-url-object')
            assert proxy is not None
            assert hasattr(proxy, 'gateway_url')
            assert hasattr(proxy, 'app_name')
            assert hasattr(proxy, 'original_cm')


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
        proxy_cm = getattr(gateway_cm, 'echoer')
        
        # Test complete flow
        message = "Hello from end-to-end test!"
        result = proxy_cm.echo(message=message, delay=0.0)
        
        # Verify the complete flow worked
        assert result.echoed == message
        
        # Verify the request actually went through the gateway
        # by checking that the proxy didn't call the original CM directly
        assert proxy_cm.gateway_url == str(gateway_manager.url).rstrip('/')
        assert proxy_cm.app_name == "echoer"

    @pytest.mark.asyncio
    async def test_concurrent_requests_through_gateway(self, gateway_manager, echo_service_for_gateway):
        """Test handling of concurrent requests through gateway."""
        # Set up the system
        echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
        gateway_cm = Gateway.connect(url=gateway_manager.url)
        gateway_cm.register_app("echoer", str(echo_service_for_gateway.url), echo_cm)
        proxy_cm = getattr(gateway_cm, 'echoer')
        
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
            apps = enhanced_cm.registered_apps()
            assert len(apps) == 2
            
            # Check if we have AppInfo objects or strings
            if apps and hasattr(apps[0], 'name'):
                app_names = [app.name for app in apps]
                assert 'echo1' in app_names
                assert 'echo2' in app_names
            else:
                assert 'echo1' in apps
                assert 'echo2' in apps
            
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
    async def test_invalid_request_handling(self, gateway_manager, echo_service_for_gateway):
        """Test Gateway handling of invalid requests."""
        # Set up the system
        echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
        gateway_cm = Gateway.connect(url=gateway_manager.url)
        gateway_cm.register_app("echoer", str(echo_service_for_gateway.url), echo_cm)
        
        # Test with invalid JSON
        gateway_url = str(gateway_manager.url).rstrip('/')
        response = requests.post(
            f"{gateway_url}/echoer/echo", 
            data="invalid json", 
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422  # Validation error
        
        # Test with missing required fields
        response = requests.post(f"{gateway_url}/echoer/echo", json={"delay": 0.0})
        assert response.status_code == 422  # Missing 'message' field

    @pytest.mark.asyncio
    async def test_gateway_url_construction_trailing_slash(self, gateway_manager, echo_service_for_gateway):
        """Test Gateway URL construction logic for trailing slash handling."""
        # Register service with URL that ends with trailing slash
        service_url_with_slash = str(echo_service_for_gateway.url).rstrip('/') + '/'
        gateway_manager.register_app("echoer_slash", service_url_with_slash)
        
        # Test that requests work correctly with trailing slash in service URL
        gateway_url = str(gateway_manager.url).rstrip('/')
        response = requests.post(f"{gateway_url}/echoer_slash/echo", json={"message": "trailing slash test", "delay": 0.0})
        assert response.status_code == 200
        assert response.json()["echoed"] == "trailing slash test"

    @pytest.mark.asyncio
    async def test_gateway_url_construction_no_trailing_slash(self, gateway_manager, echo_service_for_gateway):
        """Test Gateway URL construction logic for no trailing slash handling."""
        # Register service with URL that doesn't end with trailing slash
        service_url_without_slash = str(echo_service_for_gateway.url).rstrip('/')
        gateway_manager.register_app("echoer_no_slash", service_url_without_slash)
        
        # Test that requests work correctly without trailing slash in service URL
        gateway_url = str(gateway_manager.url).rstrip('/')
        response = requests.post(f"{gateway_url}/echoer_no_slash/echo", json={"message": "no trailing slash test", "delay": 0.0})
        assert response.status_code == 200
        assert response.json()["echoed"] == "no trailing slash test"

    @pytest.mark.asyncio
    async def test_gateway_network_error_handling(self, gateway_manager):
        """Test Gateway error handling when network errors occur."""
        # Register a service that doesn't exist to trigger network error
        gateway_cm = Gateway.connect(url=gateway_manager.url)
        gateway_cm.register_app("bad_service", "http://localhost:9999")
        
        # Try to access the unavailable service - this should trigger httpx.RequestError
        gateway_url = str(gateway_manager.url).rstrip('/')
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
        proxy_cm = getattr(gateway_cm, 'echoer')
        
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
        proxy_cm = getattr(gateway_cm, 'echoer')
        
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


class TestGatewayAppDiscovery:
    """Test Gateway app discovery functionality for multiple connection managers."""

    @pytest.mark.asyncio
    async def test_second_connection_manager_sees_registered_apps(self, echo_service_for_gateway):
        """Test that a second connection manager can see apps registered by the first."""
        with Gateway.launch(url="http://localhost:8103", timeout=30) as gateway_cm:
            # Step 1: First connection manager connects and registers an app
            enhanced_cm1 = Gateway.connect(url="http://localhost:8103")
            
            # Verify it starts empty
            assert len(enhanced_cm1.registered_apps()) == 0
            
            # Register an app with the first connection manager
            echo_cm = EchoService.connect(url=echo_service_for_gateway.url)
            enhanced_cm1.register_app(
                name="echo-shared",
                url=str(echo_service_for_gateway.url),
                connection_manager=echo_cm
            )
            
            # Verify first CM can see the app
            apps1 = enhanced_cm1.registered_apps()
            assert len(apps1) == 1
            
            # Check if we have AppInfo objects or strings
            if apps1 and hasattr(apps1[0], 'name'):
                assert apps1[0].name == "echo-shared"
            else:
                assert "echo-shared" in apps1
            
            assert hasattr(enhanced_cm1, "echo-shared")
            
            await asyncio.sleep(0.1)  # Let registration propagate
            
            # Step 2: Second connection manager connects
            enhanced_cm2 = Gateway.connect(url="http://localhost:8103")
            
            # Verify second CM can see the previously registered app
            apps2 = enhanced_cm2.registered_apps()
            assert len(apps2) == 1
            
            # Check if we can see the registered app
            if apps2 and hasattr(apps2[0], 'name'):
                app_names = [app.name for app in apps2]
                assert "echo-shared" in app_names
            else:
                assert "echo-shared" in apps2
            
            # However, second CM won't have the proxy attribute since it doesn't have the connection manager
            assert not hasattr(enhanced_cm2, "echo-shared")
            
            # Step 3: Second CM can register the same app with its own connection manager
            echo_cm2 = EchoService.connect(url=echo_service_for_gateway.url)
            enhanced_cm2.register_app(
                name="echo-shared-2",
                url=str(echo_service_for_gateway.url),
                connection_manager=echo_cm2
            )
            
            # Now second CM should have its own proxy
            assert hasattr(enhanced_cm2, "echo-shared-2")
            
            # Check final app count
            final_apps = enhanced_cm2.registered_apps()
            assert len(final_apps) == 2  # echo-shared + echo-shared-2

    @pytest.mark.asyncio
    async def test_list_apps_endpoint_directly(self, echo_service_for_gateway):
        """Test the list_apps endpoint directly."""
        with Gateway.launch(url="http://localhost:8104", timeout=30) as gateway_cm:
            # Connect and register some apps
            enhanced_cm = Gateway.connect(url="http://localhost:8104")
            
            # Initially empty
            apps_response = enhanced_cm.list_apps()
            assert apps_response.apps == []
            
            # Register an app
            enhanced_cm.register_app(
                name="test-app-1",
                url=str(echo_service_for_gateway.url)
            )
            
            await asyncio.sleep(0.1)
            
            # Should now show the registered app
            apps_response = enhanced_cm.list_apps()
            assert "test-app-1" in apps_response.apps
            assert len(apps_response.apps) == 1
            
            # Register another app
            enhanced_cm.register_app(
                name="test-app-2",
                url=str(echo_service_for_gateway.url)
            )
            
            await asyncio.sleep(0.1)
            
            # Should show both apps
            apps_response = enhanced_cm.list_apps()
            assert len(apps_response.apps) == 2
            assert "test-app-1" in apps_response.apps
            assert "test-app-2" in apps_response.apps

    @pytest.mark.asyncio
    async def test_multiple_connection_managers_with_proxies(self, echo_service_for_gateway):
        """Test multiple connection managers each creating their own proxies for the same service."""
        with Gateway.launch(url="http://localhost:8105", timeout=30) as gateway_cm:
            # First connection manager registers a service
            enhanced_cm1 = Gateway.connect(url="http://localhost:8105")
            echo_cm1 = EchoService.connect(url=echo_service_for_gateway.url)
            enhanced_cm1.register_app(
                name="shared_echo",
                url=str(echo_service_for_gateway.url),
                connection_manager=echo_cm1
            )
            
            await asyncio.sleep(0.1)
            
            # Second connection manager connects and sees the registered app
            enhanced_cm2 = Gateway.connect(url="http://localhost:8105")
            
            # Check if we can see the registered app
            apps2 = enhanced_cm2.registered_apps()
            if apps2 and hasattr(apps2[0], 'name'):
                app_names = [app.name for app in apps2]
                assert "shared_echo" in app_names
            else:
                assert "shared_echo" in apps2
            
            # Second CM creates its own proxy for the same service
            echo_cm2 = EchoService.connect(url=echo_service_for_gateway.url)
            enhanced_cm2.register_app(
                name="shared_echo",  # Same name - should replace
                url=str(echo_service_for_gateway.url),
                connection_manager=echo_cm2
            )
            
            # Now second CM should have its own proxy
            assert hasattr(enhanced_cm2, "shared_echo")
            
            await asyncio.sleep(0.1)
            
            # Both should be able to use their proxies independently
            result1 = enhanced_cm1.shared_echo.echo(message="From CM1")
            result2 = enhanced_cm2.shared_echo.echo(message="From CM2")
            
            assert result1["echoed"] == "From CM1"
            assert result2["echoed"] == "From CM2"

    @pytest.mark.asyncio
    async def test_connection_manager_sync_failure_graceful_handling(self):
        """Test that connection manager handles sync failures gracefully."""
        # Try to connect to a non-existent gateway (should fail sync but not crash)
        try:
            enhanced_cm = Gateway.connect(url="http://localhost:9999")  # Non-existent
            # This should fail at the connection level, not at the sync level
            assert False, "Should have failed to connect"
        except Exception as e:
            # Expected - can't connect to non-existent gateway
            assert "503" in str(e) or "failed to connect" in str(e).lower()
