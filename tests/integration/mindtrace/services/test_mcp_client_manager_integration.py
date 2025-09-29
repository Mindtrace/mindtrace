import json

import pytest
import requests

from mindtrace.services.samples.echo_mcp import EchoService


async def _extract_echoed(result):
    # Try multiple possible return formats
    try:
        if isinstance(result, dict) and "echoed" in result:
            return result["echoed"]
        if hasattr(result, "echoed"):
            return getattr(result, "echoed")
        if isinstance(result, list) and result and hasattr(result[0], "text"):
            data = json.loads(result[0].text)
            return data.get("echoed")
    except Exception:
        return None
    return None


@pytest.mark.asyncio
async def test_mcp_client_manager_connect_integration(echo_mcp_manager):
    # Ensure service is up via a simple call
    _ = echo_mcp_manager.endpoints()

    # Use MCPClientManager.connect to create a client and call a tool
    mcp_client = EchoService.mcp.connect("http://localhost:8093/")
    async with mcp_client:
        tools = await mcp_client.list_tools()
        tool_names = [tool.name for tool in tools]
        assert "echo" in tool_names

        sent = "MCPManager Connect"
        result = await mcp_client.call_tool("echo", {"payload": {"message": sent}})
        echoed = await _extract_echoed(result)
        assert echoed == sent


@pytest.mark.asyncio
async def test_mcp_client_manager_launch_integration():
    host = "localhost"
    port = 8094
    base_url = f"http://{host}:{port}"
    mcp_client = EchoService.mcp.launch(host=host, port=port, wait_for_launch=True, timeout=30)

    try:
        async with mcp_client:
            tools = await mcp_client.list_tools()
            tool_names = [tool.name for tool in tools]
            assert "echo" in tool_names

            sent = "MCPManager Launch"
            result = await mcp_client.call_tool("echo", {"payload": {"message": sent}})
            echoed = await _extract_echoed(result)
            assert echoed == sent
    finally:
        # Cleanup the launched service
        try:
            requests.request("POST", f"{base_url}/shutdown", timeout=10)
        except Exception:
            pass
