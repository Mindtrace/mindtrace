import json

import pytest

from urllib3.util.url import parse_url
import requests
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from mindtrace.services import generate_connection_manager
from mindtrace.services.core.types import EndpointsOutput, HeartbeatOutput, PIDFileOutput, ServerIDOutput, StatusOutput
from mindtrace.services.sample.echo_service import EchoInput, EchoOutput, EchoService


class TestServiceIntegration:
    """Simplified integration tests for service functionality"""

    def test_connection_manager_generation_without_service(self):
        """Test that we can generate connection managers without launching services"""
        ConnectionManager = generate_connection_manager(EchoService)

        # Verify it has the expected methods
        assert hasattr(ConnectionManager, "echo")
        assert hasattr(ConnectionManager, "aecho")

        # Create an instance (won't work for actual calls but tests the creation)
        manager = ConnectionManager(url=parse_url("http://localhost:8080"))
        assert str(manager.url) == "http://localhost:8080"

    @pytest.mark.asyncio
    async def test_service_launch_and_basic_functionality(self, echo_service_manager):
        """Test service functionality using the launched service from conftest.py"""
        if echo_service_manager is None:
            # Service didn't start - verify connection manager creation still works
            print("Service didn't start, testing connection manager behavior")

            ConnectionManager = generate_connection_manager(EchoService)
            manager = ConnectionManager(url=parse_url("http://localhost:8090"))

            # These should fail with connection errors, not other errors
            with pytest.raises((requests.exceptions.ConnectionError, Exception)) as exc_info:
                manager.echo(message="This should fail")

            # Verify it's a connection error, not a coding error
            assert "connection" in str(exc_info.value).lower() or "refused" in str(exc_info.value).lower()

            print("Connection manager behavior is correct for non-running service")
            return

        # Service is running - test full functionality
        print("Service launched successfully!")

        # Test sync call
        result = echo_service_manager.echo(message="Integration test message")
        assert isinstance(result, EchoOutput)
        assert result.echoed == "Integration test message"

        # Test async call
        async_result = await echo_service_manager.aecho(message="Async integration test")
        assert isinstance(async_result, EchoOutput)
        assert async_result.echoed == "Async integration test"

        input_message = EchoInput(message="Pre-validated test message")
        result = echo_service_manager.echo(input_message)
        assert isinstance(result, EchoOutput)
        assert result.echoed == "Pre-validated test message"

        async_result = await echo_service_manager.aecho(input_message)
        assert isinstance(async_result, EchoOutput)
        assert async_result.echoed == "Pre-validated test message"

        with pytest.raises(ValueError, match="must be called with"):
            echo_service_manager.echo(EchoOutput(echoed="should fail"))

        with pytest.raises(ValueError, match="must be called with"):
            echo_service_manager.echo(EchoInput(message="should fail"), "can't have a second argument")

        with pytest.raises(ValueError, match="must be called with"):
            echo_service_manager.echo(EchoInput(message="should fail"), message="can't have things both ways")

        with pytest.raises(ValueError, match="must be called with"):
            await echo_service_manager.aecho(EchoOutput(echoed="should fail"))

        with pytest.raises(ValueError, match="must be called with"):
            await echo_service_manager.aecho(EchoInput(message="should fail"), "can't have a second argument")

        with pytest.raises(ValueError, match="must be called with"):
            await echo_service_manager.aecho(EchoInput(message="should fail"), message="can't have things both ways")

        print("All integration tests passed!")

    @pytest.mark.asyncio
    async def test_default_service_endpoints(self, echo_service_manager):
        """Test all default Service endpoints (sync and async versions)"""

        # Test endpoints endpoint (sync)
        endpoints_result = echo_service_manager.endpoints()
        assert isinstance(endpoints_result, EndpointsOutput)
        assert "echo" in endpoints_result.endpoints  # Our custom endpoint

        # Default endpoints should also be present
        default_endpoint_names = ["endpoints", "status", "heartbeat", "server_id", "pid_file", "shutdown"]
        for endpoint_name in default_endpoint_names:
            assert endpoint_name in endpoints_result.endpoints, f"Missing default endpoint: {endpoint_name}"

        # Test endpoints endpoint (async)
        aendpoints_result = await echo_service_manager.aendpoints()
        assert isinstance(aendpoints_result, EndpointsOutput)
        assert aendpoints_result.endpoints == endpoints_result.endpoints  # Should be the same

        # Test status endpoint (sync)
        status_result = echo_service_manager.status()
        assert isinstance(status_result, StatusOutput)
        assert status_result.status.value in ["Available", "Down"]  # ServerStatus enum values

        # Test status endpoint (async)
        astatus_result = await echo_service_manager.astatus()
        assert isinstance(astatus_result, StatusOutput)
        assert astatus_result.status == status_result.status

        # Test heartbeat endpoint (sync)
        heartbeat_result = echo_service_manager.heartbeat()
        assert isinstance(heartbeat_result, HeartbeatOutput)
        assert heartbeat_result.heartbeat is not None
        assert heartbeat_result.heartbeat.status is not None

        # Test heartbeat endpoint (async)
        aheartbeat_result = await echo_service_manager.aheartbeat()
        assert isinstance(aheartbeat_result, HeartbeatOutput)
        assert aheartbeat_result.heartbeat is not None

        # Test server_id endpoint (sync)
        server_id_result = echo_service_manager.server_id()
        assert isinstance(server_id_result, ServerIDOutput)
        assert server_id_result.server_id is not None

        # Test server_id endpoint (async)
        aserver_id_result = await echo_service_manager.aserver_id()
        assert isinstance(aserver_id_result, ServerIDOutput)
        assert aserver_id_result.server_id == server_id_result.server_id

        # Test pid_file endpoint (sync)
        pid_file_result = echo_service_manager.pid_file()
        assert isinstance(pid_file_result, PIDFileOutput)
        # PID file might be None if not configured, that's okay
        assert pid_file_result.pid_file is not None

        # Test pid_file endpoint (async)
        apid_file_result = await echo_service_manager.apid_file()
        assert isinstance(apid_file_result, PIDFileOutput)
        assert apid_file_result.pid_file == pid_file_result.pid_file

        # Note: Not testing shutdown endpoint as it would terminate the service
        # But we can verify the method exists
        assert hasattr(echo_service_manager, "shutdown"), "Missing shutdown method"
        assert hasattr(echo_service_manager, "ashutdown"), "Missing ashutdown method"

        print("All default service endpoints tested successfully!")

    def test_url_construction_logic(self):
        """Test URL construction without requiring a running service"""
        ConnectionManager = generate_connection_manager(EchoService)

        # Test different URL formats
        test_urls = [
            "http://localhost:8080",
            "http://localhost:8080/",
            "https://example.com",
            "https://example.com/",
        ]

        for url in test_urls:
            manager = ConnectionManager(url=parse_url(url))
            assert manager.url is not None

            # The URL should be stored properly
            url_str = str(manager.url)
            assert url_str == url or url_str == url.rstrip("/")

    @pytest.mark.asyncio
    async def test_echo_service_import_and_instantiation(self):
        """Test that we can import and instantiate the echo service"""
        try:
            service = EchoService(port=8091, host="localhost")

            # Verify service has the expected endpoints
            assert "echo" in service.endpoints
            assert service.endpoints["echo"].name == "echo"
            assert service.endpoints["echo"].input_schema is not None and service.endpoints["echo"].input_schema.__name__ == "EchoInput"
            assert service.endpoints["echo"].output_schema is not None and service.endpoints["echo"].output_schema.__name__ == "EchoOutput"

            # Verify connection manager generation works
            ConnectionManager = generate_connection_manager(EchoService)
            assert ConnectionManager.__name__ == "EchoServiceConnectionManager"

            print("Service import and instantiation works correctly")

        except Exception as e:
            # This shouldn't fail since we're just importing and creating, not launching
            pytest.fail(f"Service instantiation failed: {e}")

    def test_task_registration(self):
        """Test that services register their tasks correctly"""
        service = EchoService(port=8092, host="localhost")

        # Check that echo task is registered
        assert "echo" in service.endpoints
        echo_task = service.endpoints["echo"]

        assert echo_task.name == "echo"
        assert echo_task.input_schema is not None and echo_task.input_schema.__name__ == "EchoInput"
        assert echo_task.output_schema is not None and echo_task.output_schema.__name__ == "EchoOutput"

        # Verify the generated connection manager has the right methods
        ConnectionManager = generate_connection_manager(EchoService)

        # Check method existence
        assert hasattr(ConnectionManager, "echo")
        assert hasattr(ConnectionManager, "aecho")

        # Check method documentation
        echo_method = getattr(ConnectionManager, "echo")
        aecho_method = getattr(ConnectionManager, "aecho")

        assert "echo" in echo_method.__doc__
        assert "Async version" in aecho_method.__doc__



class TestMCPServiceIntegration:
    """Integration tests for MCP functionality"""

    @pytest.mark.asyncio
    async def test_mcp_server_accessible(self, echo_mcp_manager):
        endpoints_result = echo_mcp_manager.endpoints()
        # The MCP app is mounted at /mcp-server
        base_url = "http://localhost:8093"
        mcp_url = f"{base_url}/mcp-server/mcp/"
        # Use the MCP client to connect and call the 'echo' tool
        async with streamablehttp_client(mcp_url) as (read, write, session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                # List available tools
                tools = await session.list_tools()
                tool_names = [tool.name for tool in tools.tools]
                assert "echo" in tool_names

                # Call the 'echo' tool
                result = await session.call_tool("echo", {"payload": {"message": "Alice"}})
                # The result is in result.content[0].text as a JSON string
                assert hasattr(result, "content")
                assert len(result.content) > 0
                text_content = result.content[0].text
                data = json.loads(text_content)
                assert "echoed" in data
                assert data["echoed"] == "Alice"