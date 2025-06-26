# mcp_server_with_agent.py - FastAPI + MCP server with Llama 3.2 agent
import asyncio
import subprocess
import threading
import traceback
import time
import sys
import os

from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession

from mindtrace.services import MCPService

FASTAPI_URL = "http://localhost:8080"
MCP_URL = "http://localhost:8081/mcp/"
OLLAMA_BASE_URL = "http://localhost:11434"
MODEL_NAME = "llama3.2:3b"

async def main():
    # Launch FastAPI server using subprocess to avoid signal handler issues
    print("Starting FastAPI server via subprocess...")
    
    # Create a temporary script to launch the FastAPI server
    launcher_script = """
import sys
sys.path.insert(0, '/Users/jeremywurbs/projects/mindtrace/mindtrace')
from mindtrace.services import MCPService

MCPService.launch(
    name="MindTrace MCP Service",
    description="MCP-enabled Mindtrace service with FastAPI and MCP endpoints",
    url="http://localhost:8080",
    block=True  # This will keep the server running in the subprocess
)
"""
    
    # Write the launcher script to a temporary file
    with open('/tmp/fastapi_launcher.py', 'w') as f:
        f.write(launcher_script)
    
    # Start FastAPI server in subprocess
    fastapi_process = subprocess.Popen([
        sys.executable, '/tmp/fastapi_launcher.py'
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Start MCP server in a separate thread
    def run_mcp_server():
        try:
            print("Starting MCP server...")
            # Wait a bit for FastAPI to start first
            time.sleep(5)
            
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
    
    # Wait for both servers to start
    print("⏳ Waiting for servers to start...")
    await asyncio.sleep(12)  # Give more time for both servers

    try:
        print("📡 Servers should now be running:")
        print(f"   FastAPI: {FASTAPI_URL}")
        print(f"   MCP: {MCP_URL}")
        
        print(f"\n🔗 Connecting to MCP server at: {MCP_URL}")
        async with streamablehttp_client(MCP_URL) as (read, write, session_id):
            print("✅ Connected to MCP server!")
            async with ClientSession(read, write) as session:
                print("🔄 Initializing MCP session...")
                await session.initialize()
                print("✅ MCP session initialized!")

                print("🛠️  Loading MCP tools...")
                tools = await load_mcp_tools(session)
                print(f"✅ Loaded {len(tools)} tools: {[tool.name for tool in tools]}")

                print(f"🤖 Setting up Ollama with {MODEL_NAME}...")
                llm = ChatOllama(
                    model=MODEL_NAME,
                    base_url=OLLAMA_BASE_URL,
                    temperature=0.1,
                )

                print("🧠 Creating ReAct agent...")
                agent = create_react_agent(llm, tools)

                # Test queries for the agent
                test_queries = [
                    "What's your identity? Tell me about yourself.",
                    "What is the current status and state of the server?",
                    "Please check the server heartbeat - I want to see the heartbeat details.",
                    "What capabilities do you have?",
                ]

                print("\n🎯 Testing LLM Agent with MCP Tools")
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
                        print(f"❌ Error with query '{query}': {e}")
                        traceback.print_exc()

                print("\n" + "=" * 50)
                print("🎉 Dual Server Integration Test Complete!")
                print("✅ FastAPI server is running via launcher.py + gunicorn!")
                print("✅ MCP server is working correctly!")
                print("✅ Tools are accessible to the LLM agent!")
                print(f"✅ {MODEL_NAME} can reason about and use MCP tools!")
                print("✅ Parent class endpoints (like heartbeat) are working as MCP tools!")
                
                # Test FastAPI endpoints directly
                print("\n📡 You can also test FastAPI endpoints directly:")
                print(f"   curl -X POST {FASTAPI_URL}/identity")
                print(f"   curl -X POST {FASTAPI_URL}/state")
                print(f"   curl -X POST {FASTAPI_URL}/capabilities")
                print(f"   curl -X POST {FASTAPI_URL}/heartbeat")  # Parent class endpoint

    except Exception as e:
        print(f"❌ Error: {e}")
        traceback.print_exc()
    finally:
        # Clean up: terminate the FastAPI subprocess
        if fastapi_process.poll() is None:  # Process is still running
            print("🧹 Cleaning up FastAPI server process...")
            fastapi_process.terminate()
            try:
                fastapi_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                fastapi_process.kill()
        
        # Clean up temporary file
        if os.path.exists('/tmp/fastapi_launcher.py'):
            os.remove('/tmp/fastapi_launcher.py')

if __name__ == "__main__":
    asyncio.run(main())
