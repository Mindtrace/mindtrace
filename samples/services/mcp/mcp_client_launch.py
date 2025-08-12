#!/usr/bin/env python3
"""
Example demonstrating the new MCP client functionality in the Service class.

This shows how to use service.mcp.launch() method to get FastMCP Client instances for interacting with services via the MCP protocol.
"""
import asyncio
from mindtrace.services.sample.echo_mcp import EchoService


async def main():
    print("Launching service and getting MCP client...")
    try:
        # Launch the service and get an MCP client
        mcp_client = EchoService.mcp.launch(
            host="localhost", 
            port=8000,
            wait_for_launch=True,
            timeout=10
        )
        
        print(f"Service launched and MCP client created: {mcp_client}")
        async with mcp_client:
            tools = await mcp_client.list_tools()
            print("\n" + "="*50 + "\n")
            print(f"Available tools: {[tool.name for tool in tools]}")
            print("\n" + "="*50 + "\n")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 