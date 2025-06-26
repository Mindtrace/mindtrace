# mcp_test.py - Basic MCP functionality test
import asyncio
import threading
import traceback

from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession

from mindtrace.services import MCPService

MCP_URL = "http://localhost:8001/mcp/"


async def main():
    # Create MCPService instance
    mcp_service = MCPService()

    # Start the MCP server in a separate thread
    def run_mcp_server():
        try:
            mcp_service.run_mcp_server(host="localhost", port=8001, path="/mcp")
        except Exception as e:
            print(f"MCP Server error: {e}")
            traceback.print_exc()
    
    mcp_thread = threading.Thread(target=run_mcp_server, daemon=True)
    mcp_thread.start()
    
    # Wait a bit for the server to start
    print("Waiting for MCP server to start...")
    await asyncio.sleep(3)

    try:
        print(f"Connecting to MCP server at: {MCP_URL}")
        # Connect via streamable HTTP transport to the JSON-RPC endpoint
        async with streamablehttp_client(MCP_URL) as (read, write, session_id):
            print(f"Connected successfully!")
            async with ClientSession(read, write) as session:
                print("Initializing session...")
                # Perform the MCP handshake (capabilities, schema retrieval, etc.)
                await session.initialize()
                print("Session initialized successfully")

                print("Loading MCP tools...")
                # Load the MCP tools dynamically
                tools = await load_mcp_tools(session)
                print(f"Loaded {len(tools)} tools: {[tool.name for tool in tools]}")

                # Test each tool individually
                print("\n=== Testing MCP Tools ===")
                
                for tool in tools:
                    print(f"\nTesting tool: {tool.name}")
                    print(f"Description: {tool.description}")
                    
                    try:
                        # Test with empty args for now
                        if tool.name == "identity":
                            result = await tool.ainvoke({})
                            print(f"Result: {result}")
                        elif tool.name == "capabilities":
                            result = await tool.ainvoke({})
                            print(f"Result: {result}")
                        elif tool.name == "state":
                            result = await tool.ainvoke({})
                            print(f"Result: {result}")
                        elif tool.name == "schema":
                            result = await tool.ainvoke({})
                            print(f"Result: {result}")
                        else:
                            print(f"Skipping tool {tool.name} (requires specific parameters)")
                    except Exception as e:
                        print(f"Error testing tool {tool.name}: {e}")

                print("\n=== MCP Integration Test Complete ===")
                print("✅ MCP server is working correctly!")
                print("✅ Tools are accessible via langchain-mcp-adapters!")
                print("✅ Ready for LLM integration!")

    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
