#!/usr/bin/env python3
"""
Combined MCP client demo for EchoService.

This script can:
- launch a service and get an MCP client
- connect to an existing service via MCP
- launch a service and access the MCP client via the connection manager

It also performs one tool call ("echo").
"""

import asyncio
import argparse

from mindtrace.services.sample.echo_mcp import EchoService


async def run_with_client(mcp_client, message: str):
    async with mcp_client:
        tools = await mcp_client.list_tools()
        print("\n" + "=" * 50 + "\n")
        print(f"Available tools: {[tool.name for tool in tools]}")
        print("\n" + "=" * 50 + "\n")

        # Perform one tool call
        print("Calling 'echo' tool...")
        result = await mcp_client.call_tool("echo", {"payload": {"message": message}})
        print("Tool response:", result)


async def main():
    parser = argparse.ArgumentParser(description="Combined MCP client demo for EchoService")
    parser.add_argument("--mode", choices=["launch", "connect", "manager"], default="launch",
                        help="How to obtain the MCP client: launch|connect|manager")
    parser.add_argument("--host", default="localhost", help="Host for the service")
    parser.add_argument("--port", type=int, default=8000, help="Port for the service")
    parser.add_argument("--url", default=None, help="Full URL for connect mode (e.g., http://localhost:8000/)")
    parser.add_argument("--message", default="Hello MCP!", help="Message for the echo tool")

    args = parser.parse_args()

    print("Preparing MCP client...")
    try:
        if args.mode == "launch":
            mcp_client = EchoService.mcp.launch(
                host=args.host,
                port=args.port,
                wait_for_launch=True,
                timeout=10,
            )
        elif args.mode == "connect":
            cm =EchoService.mcp.launch(
                host=args.host,
                port=args.port,
                wait_for_launch=True,
                timeout=10,
            )
            url = args.url or f"http://{args.host}:{args.port}/"
            mcp_client = EchoService.mcp.connect(url)
        else:  # manager
            cm = EchoService.launch(
                host=args.host,
                port=args.port,
                wait_for_launch=True,
                timeout=10,
            )
            mcp_client = cm.mcp_client

        await run_with_client(mcp_client, args.message)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())

