#!/usr/bin/env python3
"""
Gateway Service example showing how to:
1. Launch a Gateway service
2. Register other services with the Gateway
3. Make requests through the Gateway to registered services
"""

import asyncio
import requests

from mindtrace.services import Gateway, AppConfig
from mindtrace.services.sample.echo_service import EchoService, EchoInput


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
        status_response = requests.post(f"{gateway_url}/status")
        print(f"Gateway status: {status_response.json()}")

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
    import httpx
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
        # Register both services with different names
        gateway_cm.register_app(name="echo1", url="http://localhost:8095/")
        gateway_cm.register_app(name="echo2", url="http://localhost:8096/")
        print("Both services registered with Gateway!")

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
    
    # Run async example
    asyncio.run(async_gateway_example())
    
    # Run multiple services example
    multiple_services_example()
    
    print("\nAll Gateway examples completed!")
