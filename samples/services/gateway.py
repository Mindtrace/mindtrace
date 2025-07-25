#!/usr/bin/env python3
"""
Gateway Service example showing how to:
1. Launch a Gateway service
2. Register other services with the Gateway
3. Make requests through the Gateway to registered services
4. Use ProxyConnectionManager for transparent service routing
"""

import asyncio

import httpx
import requests

from mindtrace.services import Gateway
from mindtrace.services.sample.echo_service import EchoService


def sync_gateway_example():
    """Synchronous Gateway example."""
    print("Starting sync Gateway example...")

    # Launch Gateway service on port 8090
    gateway_cm = Gateway.launch(port=8090, wait_for_launch=True, timeout=15)
    print("Gateway launched successfully!")

    # Launch EchoService on port 8091 
    echo_cm = EchoService.launch(port=8091, wait_for_launch=True, timeout=15)
    print("EchoService launched successfully!")

    try:
        # Register the EchoService with the Gateway
        gateway_cm.register_app(name="echo", url="http://localhost:8091/")
        print("EchoService registered with Gateway!")

        # Make a request through the Gateway to the registered EchoService
        # This goes: Client -> Gateway (8090) -> EchoService (8091)
        gateway_url = "http://localhost:8090"
        echo_payload = {"message": "Hello through Gateway!", "delay": 0.0}
        
        response = requests.post(f"{gateway_url}/echo/echo", json=echo_payload)
        result = response.json()
        print(f"Gateway forwarded result: {result}")

        # Make another request with different message
        echo_payload2 = {"message": "Second message via Gateway", "delay": 0.5}
        response2 = requests.post(f"{gateway_url}/echo/echo", json=echo_payload2)
        result2 = response2.json()
        print(f"Gateway forwarded result 2: {result2}")

        # Test Gateway's built-in endpoints
        status_response = requests.post(f"{gateway_url}/status")  # Equivalent to gateway_cm.status()
        print(f"Gateway status: {status_response.json()}")

    finally:
        # Clean up in reverse order
        echo_cm.shutdown()
        gateway_cm.shutdown()
        print("Services shut down successfully!")


def proxy_connection_manager_example():
    """Example demonstrating the ProxyConnectionManager functionality."""
    print("\nStarting ProxyConnectionManager example...")

    # Launch Gateway service on port 8097
    gateway_cm = Gateway.launch(port=8097, wait_for_launch=True, timeout=15)
    print("Gateway launched successfully!")

    # Launch EchoService on port 8098 
    echo_cm = EchoService.launch(port=8098, wait_for_launch=True, timeout=15)
    print("EchoService launched successfully!")

    try:
        # Register the EchoService with the Gateway INCLUDING the connection manager
        # This enables the ProxyConnectionManager functionality
        result = gateway_cm.register_app(
            name="echo", 
            url="http://localhost:8098/", 
            connection_manager=echo_cm  # Provide the connection manager to the Gateway to enable ProxyConnectionManager functionality
        )
        print(f"EchoService registered with Gateway: {result}")
        print(f"Registered apps: {gateway_cm.registered_apps}")

        # Now we can use the proxy! This looks like direct service access but routes through Gateway
        print("\n--- Testing ProxyConnectionManager ---")
        
        # Direct call to echo service (for comparison)
        direct_result = echo_cm.echo(message="Direct call to EchoService")
        print(f"Direct call result: {direct_result.echoed}")
        
        # Proxied call through Gateway (same API, but routes through the Gateway)
        proxy_result = gateway_cm.echo.echo(message="Proxied call through Gateway")
        print(f"Proxied call result: {proxy_result}")
        
        # Test that the proxy preserves the original service's methods
        print(f"Echo service has 'echo' method: {hasattr(echo_cm, 'echo')}")
        print(f"Gateway proxy has 'echo' method: {hasattr(gateway_cm.echo, 'echo')}")
        
        # Test gateway service status methods work normally
        gateway_status = gateway_cm.status()
        print(f"Gateway status: {gateway_status}")
        
        # Test that we can access the original service through the proxy
        try:
            proxy_status = gateway_cm.echo.status()
            print(f"Echo service status via proxy: {proxy_status}")
        except Exception as e:
            print(f"Proxy status call failed (expected for echo service): {e}")

    finally:
        # Clean up in reverse order
        echo_cm.shutdown()
        gateway_cm.shutdown()
        print("Services shut down successfully!")


async def async_gateway_example():
    """Asynchronous Gateway example."""
    print("\nStarting async Gateway example...")

    # Launch Gateway service on port 8092
    gateway_cm = Gateway.launch(port=8092, wait_for_launch=True, timeout=15)
    print("Gateway launched successfully!")

    # Launch EchoService on port 8093
    echo_cm = EchoService.launch(port=8093, wait_for_launch=True, timeout=15)
    print("EchoService launched successfully!")

    try:
        # Register the EchoService with the Gateway
        await gateway_cm.aregister_app(name="echo", url="http://localhost:8093/")
        print("EchoService registered with Gateway!")

        # Make concurrent async requests through the Gateway
        gateway_url = "http://localhost:8092"
        
        # Create multiple requests
        async with asyncio.TaskGroup() as tg:
            tasks = []
            for i in range(3):
                echo_payload = {"message": f"Async message {i} via Gateway", "delay": 0.1}
                # Note: We use httpx directly here for async HTTP requests
                # In a real application, you might want to create async methods on the connection manager
                task = tg.create_task(make_async_request(gateway_url, echo_payload))
                tasks.append(task)

        # Process results
        for i, task in enumerate(tasks):
            result = task.result()
            print(f"Async Gateway result {i}: {result}")

        # Test Gateway heartbeat
        heartbeat = await gateway_cm.aheartbeat()
        print(f"Gateway heartbeat: {heartbeat}")

    finally:
        # Clean up in reverse order
        await echo_cm.ashutdown()
        await gateway_cm.ashutdown()
        print("Services shut down successfully!")


async def make_async_request(gateway_url: str, payload: dict):
    """Helper function to make async HTTP requests."""
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{gateway_url}/echo/echo", json=payload)
        return response.json()


def multiple_services_example():
    """Example showing multiple services registered with one Gateway."""
    print("\nStarting multiple services example...")

    # Launch Gateway
    gateway_cm = Gateway.launch(port=8094, wait_for_launch=True, timeout=15)
    print("Gateway launched!")

    # Launch multiple EchoServices on different ports
    echo_cm1 = EchoService.launch(port=8095, wait_for_launch=True, timeout=15)
    echo_cm2 = EchoService.launch(port=8096, wait_for_launch=True, timeout=15)
    print("Multiple EchoServices launched!")

    try:
        # Register both services with different names - with ProxyConnectionManager
        result1 = gateway_cm.register_app(name="echo1", url="http://localhost:8095/", connection_manager=echo_cm1)
        result2 = gateway_cm.register_app(name="echo2", url="http://localhost:8096/", connection_manager=echo_cm2)
        print(f"Both services registered with Gateway!")
        print(f"Registration results: {result1}, {result2}")

        # Make requests to different registered services through the same Gateway
        gateway_url = "http://localhost:8094"
        
        # Request to first service
        response1 = requests.post(f"{gateway_url}/echo1/echo", 
                                 json={"message": "Hello to service 1!"})
        print(f"Service 1 response: {response1.json()}")
        
        # Request to second service  
        response2 = requests.post(f"{gateway_url}/echo2/echo",
                                 json={"message": "Hello to service 2!"})
        print(f"Service 2 response: {response2.json()}")

        # Test ProxyConnectionManager for both services
        print("\n--- Testing Multiple Proxy Connections ---")
        proxy_result1 = gateway_cm.echo1.echo(message="Proxy call to service 1")
        proxy_result2 = gateway_cm.echo2.echo(message="Proxy call to service 2")
        print(f"Proxy result 1: {proxy_result1}")
        print(f"Proxy result 2: {proxy_result2}")

        # Check Gateway endpoints
        endpoints_response = requests.post(f"{gateway_url}/endpoints")
        print(f"Gateway endpoints: {endpoints_response.json()}")

    finally:
        # Clean up all services
        echo_cm1.shutdown()
        echo_cm2.shutdown()
        gateway_cm.shutdown()
        print("All services shut down successfully!")


if __name__ == "__main__":
    # Run sync example
    sync_gateway_example()
    
    # Run ProxyConnectionManager example
    proxy_connection_manager_example()
    
    # Run async example
    asyncio.run(async_gateway_example())
    
    # Run multiple services example
    multiple_services_example()
    
    print("\nAll Gateway examples completed!")
