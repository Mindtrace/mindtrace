#!/usr/bin/env python3
"""
Sample script demonstrating EchoService usage in both sync and async modes.

This script shows how to:
1. Launch an EchoService
2. Connect to it using a connection manager
3. Make both synchronous and asynchronous calls
4. Properly clean up resources
"""

import asyncio
import time

from mindtrace.services import ServerStatus, generate_connection_manager
from mindtrace.services.sample.echo_service import EchoService


def sync_example():
    """Demonstrate synchronous usage of EchoService."""
    print("Launching EchoService...")
    
    # Launch the service on a specific port
    connection_manager = EchoService.launch(
        port=8080, 
        host="localhost",
        wait_for_launch=True,  # Wait for service to be ready
        timeout=30
    )
    
    print("Service launched successfully!")
    print(f"Service URL: {connection_manager.url}")
    
    try:
        # Make some synchronous calls
        print("\n--- Synchronous Calls ---")
        
        # Basic echo call
        result1 = connection_manager.echo(message="Hello, World!")
        print(f"Sent: 'Hello, World!'")
        print(f"Received: '{result1.echoed}'")
        
        # Another call with different message
        result2 = connection_manager.echo(message="Sync mode is working!")
        print(f"Sent: 'Sync mode is working!'")
        print(f"Received: '{result2.echoed}'")
        
        # Raw output call (returns raw dict instead of validated object)
        job_result = connection_manager.echo(message="Raw output call", validate_output=False)
        print(f"Sent (raw output): 'Raw output call'")
        print(f"Raw result: {job_result}")
        
    except Exception as e:
        print(f"Error during sync calls: {e}")
    
    finally:
        # Cleanup: shutdown the service
        print("\nShutting down service...")
        try:
            connection_manager.shutdown()
            print("Service shutdown successfully!")
        except Exception as e:
            print(f"Error during shutdown: {e}")


async def async_example():
    """Demonstrate asynchronous usage of EchoService."""
    print("\nLaunching EchoService for async demo...")
    
    # Launch the service on a different port for async demo
    connection_manager = EchoService.launch(
        port=8081, 
        host="localhost",
        wait_for_launch=True,
        timeout=30
    )
    
    print("Service launched successfully!")
    print(f"Service URL: {connection_manager.url}")
    
    try:
        # Make some asynchronous calls
        print("\n--- Asynchronous Calls ---")
        
        # Basic async echo call
        result1 = await connection_manager.aecho(message="Hello, Async World!")
        print(f"Sent: 'Hello, Async World!'")
        print(f"Received: '{result1.echoed}'")
        
        # Multiple concurrent calls
        print("\nMaking 3 concurrent calls...")
        start_time = time.time()
        
        tasks = [
            connection_manager.aecho(message=f"Concurrent message {i}")
            for i in range(1, 4)
        ]
        
        results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        print(f"Completed 3 calls in {end_time - start_time:.2f} seconds")
        
        for i, result in enumerate(results, 1):
            print(f"Result {i}: '{result.echoed}'")
        
        # Raw output async call
        job_result = await connection_manager.aecho(
            message="Async raw output call", 
            validate_output=False
        )
        print(f"Sent (async raw output): 'Async raw output call'")
        print(f"Raw result: {job_result}")
        
    except Exception as e:
        print(f"Error during async calls: {e}")
    
    finally:
        # Cleanup: shutdown the service
        print("\nShutting down async service...")
        try:
            await connection_manager.ashutdown()
            print("Async service shutdown successfully!")
        except Exception as e:
            print(f"Error during async shutdown: {e}")


def connection_manager_demo():
    """Demonstrate creating connection manager without launching service."""
    print("\n--- Connection Manager Demo ---")
    
    # Generate a connection manager class
    EchoConnectionManager = generate_connection_manager(EchoService)
    print(f"Generated connection manager: {EchoConnectionManager.__name__}")
    
    # Show available methods
    methods = [attr for attr in dir(EchoConnectionManager) 
              if not attr.startswith('_') and callable(getattr(EchoConnectionManager, attr))]
    print(f"Available methods: {methods}")
    
    # Launch the service and test the main endpoints:
    with EchoService.launch(port=8080, wait_for_launch=True, timeout=15) as cm:
        print(f"Created manager instance for: {cm.url}")
        print(f"Status: {cm.status()}")
        print(f"Heartbeat: {cm.heartbeat()}")
        print(f"Server ID: {cm.server_id()}")
        print(f"PID File: {cm.pid_file()}")
        # Test that the service is available
        status_result = cm.status()
        assert status_result.status == ServerStatus.AVAILABLE, f"Expected status to be available, got {status_result.status}"
            
    # Test that the service is down after the context manager shuts it down
    status_result = cm.status()
    assert status_result.status == ServerStatus.DOWN, f"Expected status to be down, got {status_result.status}"
    print("Service status check passed!")


def main():
    """Main function to run all examples."""
    print("EchoService Demo Script")
    print("=" * 50)
    
    # 1. Connection manager demo (no service needed)
    connection_manager_demo()
    
    # 2. Synchronous example
    print("\n" + "=" * 50)
    print("SYNCHRONOUS EXAMPLE")
    print("=" * 50)
    sync_example()
    
    # 3. Asynchronous example
    print("\n" + "=" * 50)
    print("ASYNCHRONOUS EXAMPLE")
    print("=" * 50)
    asyncio.run(async_example())
    
    print("\nAll examples completed!")


if __name__ == "__main__":
    main()
