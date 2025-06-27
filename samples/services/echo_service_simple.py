#!/usr/bin/env python3
"""
Simple EchoService example showing basic sync and async usage.
"""

import asyncio

from mindtrace.services.sample.echo_service import EchoService


def quick_sync_example():
    """Quick synchronous example."""
    print("Starting sync example...")

    # Launch service and get connection manager
    cm = EchoService.launch(port=8080, wait_for_launch=True, timeout=15)

    try:
        # Make a simple call
        result = cm.echo(message="Hello from sync!")
        print(f"Result: {result.echoed}")

    finally:
        cm.shutdown()


async def quick_async_example():
    """Quick asynchronous example."""
    print("Starting async example...")

    # Launch service and get connection manager
    cm = EchoService.launch(port=8081, wait_for_launch=True, timeout=15)

    try:
        # Make async calls
        result = await cm.aecho(message="Hello from async!")
        print(f"Result: {result.echoed}")

        # Concurrent calls
        tasks = [cm.aecho(message=f"Message {i}") for i in range(3)]
        results = await asyncio.gather(*tasks)

        for i, res in enumerate(results):
            print(f"Concurrent result {i}: {res.echoed}")

    finally:
        await cm.ashutdown()


if __name__ == "__main__":
    # Run sync example
    quick_sync_example()

    # Run async example
    asyncio.run(quick_async_example())

    print("Done!")
