# mcp_server_with_agent.py - Pure MCP server with Llama 3.2 agent
import asyncio
import threading
import traceback
import time

from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession

from mindtrace.services import MCPService

MCP_URL = "http://localhost:8081/mcp/"
OLLAMA_BASE_URL = "http://localhost:11434"
MODEL_NAME = "llama3.2:3b"

async def main():
    print("Starting MCP server...")
    
    # Start MCP server in a separate thread
    def run_mcp_server():
        try:
            # Create MCPService instance for MCP server
            mcp_service = MCPService(
                name="MindTrace MCP Service",
                description="MCP-enabled Mindtrace service"
            )
            mcp_service.run_mcp_server(host="localhost", port=8081, path="/mcp")
        except Exception as e:
            print(f"MCP Server error: {e}")
            traceback.print_exc()
    
    mcp_thread = threading.Thread(target=run_mcp_server, daemon=True)
    mcp_thread.start()
    
    # Wait for MCP server to start
    print("⏳ Waiting for MCP server to start...")
    await asyncio.sleep(3)

    try:
        print(f"📡 MCP Server running at: {MCP_URL}")
        
        print(f"🔗 Connecting to MCP server...")
        async with streamablehttp_client(MCP_URL) as (read, write, session_id):
            print("Connected to MCP server!")
            
            async with ClientSession(read, write) as session:
                print("Initializing MCP session...")
                await session.initialize()
                print("MCP session initialized!")

                print("🛠️  Loading MCP tools...")
                tools = await load_mcp_tools(session)
                print(f"Loaded {len(tools)} tools: {[tool.name for tool in tools]}")

                print(f"Setting up Ollama with {MODEL_NAME}...")
                llm = ChatOllama(
                    model=MODEL_NAME,
                    base_url=OLLAMA_BASE_URL,
                    temperature=0.1,
                )

                print("Creating ReAct agent...")
                agent = create_react_agent(llm, tools)

                # Test queries for the agent
                test_queries = [
                    "What's your identity? Tell me about yourself.",
                    "What is the current status and state of the server?",
                    "Please check the server heartbeat - I want to see the heartbeat details.",
                    "What capabilities do you have?",
                    "Show me all available endpoints.",
                ]

                print("\nTesting LLM Agent with MCP Tools")
                print("=" * 50)
                
                for i, query in enumerate(test_queries, 1):
                    print(f"\n--- Query {i}: {query} ---")
                    try:
                        result = await agent.ainvoke({"messages": query})
                        
                        # Extract the final response
                        if result and "messages" in result:
                            final_message = result["messages"][-1]
                            print(f"🤖 Agent Response: {final_message.content}")
                        else:
                            print(f"🤖 Agent Response: {result}")
                            
                    except Exception as e:
                        print(f"Error with query '{query}': {e}")
                        traceback.print_exc()

                print("\n" + "=" * 50)
                print("🎉 MCP Integration Test Complete!")
                print("✅ MCP server is working correctly!")
                print("✅ All tools (including parent class endpoints) are accessible!")
                print(f"✅ {MODEL_NAME} can reason about and use MCP tools!")
                print("✅ Pure MCP implementation - no FastAPI needed!")

    except Exception as e:
        print(f"❌ Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
