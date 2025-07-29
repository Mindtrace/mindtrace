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

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from mindtrace.services.sample.echo_mcp import EchoService


async def mcp_example():
    """Demonstrate synchronous usage of EchoService."""
    print("Launching EchoService...")

    # Launch the service on a specific port
    connection_manager = EchoService.launch(
        port=8080,
        host="localhost",
        wait_for_launch=True,  # Wait for service to be ready
        timeout=30,
    )
    mcp_url = str(connection_manager.url) + "mcp-server/mcp/"
    print("Service launched successfully!")
    print(f"Service URL: {connection_manager.url}")
    print(f"MCP Service URl: {mcp_url}")

    try:
        # Make some synchronous calls
        print("\n--- Synchronous Calls ---")

        # Basic echo call
        result1 = connection_manager.echo(message="Hello, World!")
        print("Sent: 'Hello, World!'")
        print(f"Received: '{result1.echoed}'")

        print("\n--- MCP Tool Calls ---")
        # setup MCP client
        async with streamablehttp_client(mcp_url) as (read, write, session_id):
            async with ClientSession(read, write) as session:
                print("Initializing session...")
                await session.initialize()
                print("Session ready!")

                # List tools
                tools = await session.list_tools()
                print("=" * 50)
                print("Available tools:")
                print("=" * 50)
                for tool in tools.tools:
                    print(f" - {tool.name}: {tool.description or 'No description'}")
                    print(f" - {tool.name}: {tool.inputSchema.items() or 'No Input Schema'}")
                    # print(f" - {tool.name}: {tool.outputSchema.items() or 'No Output Schema'}")

                # # Call your  tool
                print("=" * 50)
                print("Call Echo tool:")
                print("=" * 50)
                result = await session.call_tool("echo", {"payload": {"message": "Alice"}})
                print("Tool response:", result)
                print("=" * 50)
                print("Call Reverse Echo tool:")
                print("=" * 50)
                result = await session.call_tool("reverse_message", {"payload": {"message": "Alice"}})
                print("Tool response:", result)

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


def main():
    """Main function to run all examples."""
    print("EchoService MCP Demo Script")
    print("=" * 50)

    # 1. EchoService example
    print("\n" + "=" * 50)
    print("EchoService MCP Example")
    print("=" * 50)
    asyncio.run(mcp_example())

    print("\nAll examples completed!")


if __name__ == "__main__":
    main()
