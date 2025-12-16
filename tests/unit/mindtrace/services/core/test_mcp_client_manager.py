from unittest.mock import Mock, patch

from urllib3.util.url import parse_url

from mindtrace.services.core.mcp_client_manager import MCPClientManager
from mindtrace.services.core.service import Service


class MyService(Service):
    pass


class TestMCPClientManagerInitialization:
    def test_service_injects_mcp_manager_on_subclass(self):
        assert isinstance(MyService.mcp, MCPClientManager)
        assert MyService.mcp.service_cls is MyService

    def test_instance_still_has_fastmcp_attribute(self):
        service = Service()
        # Instance attribute should be a FastMCP app, not the manager
        from fastmcp import FastMCP

        assert isinstance(service.mcp, FastMCP)


class TestMCPClientManagerConnect:
    @patch("mindtrace.services.core.mcp_client_manager.Client")
    @patch.object(MyService, "build_url")
    def test_connect_uses_built_url_and_appends_mcp_path(self, mock_build_url, mock_client):
        mock_build_url.return_value = parse_url("http://example.com:9000/")
        mock_client_instance = Mock()
        mock_client.return_value = mock_client_instance

        result = MyService.mcp.connect(url="http://example.com:9000/")

        # Expect trailing slash stripped then MCP path appended
        mock_client.assert_called_once_with("http://example.com:9000/mcp-server/mcp")
        assert result is mock_client_instance

    @patch("mindtrace.services.core.mcp_client_manager.Client")
    @patch.object(MyService, "build_url")
    def test_connect_with_default_url(self, mock_build_url, mock_client):
        mock_build_url.return_value = parse_url("http://default-host:8000")
        mock_client_instance = Mock()
        mock_client.return_value = mock_client_instance

        result = MyService.mcp.connect()

        mock_client.assert_called_once_with("http://default-host:8000/mcp-server/mcp")
        assert result is mock_client_instance


class TestMCPClientManagerLaunch:
    @patch("mindtrace.services.core.mcp_client_manager.Client")
    @patch.object(MyService, "launch")
    def test_launch_returns_client_for_launched_service(self, mock_launch, mock_client):
        cm = Mock()
        cm.url = parse_url("http://localhost:7777")
        mock_launch.return_value = cm

        mock_client_instance = Mock()
        mock_client.return_value = mock_client_instance

        result = MyService.mcp.launch(host="localhost", port=7777, wait_for_launch=True)

        mock_launch.assert_called_once()
        mock_client.assert_called_once_with("http://localhost:7777/mcp-server/mcp")
        assert result is mock_client_instance


class TestMCPClientManagerGetDescriptor:
    def test_get_descriptor_from_class_returns_new_manager(self):
        """Test that accessing mcp from class returns new MCPClientManager."""
        # When accessing from class (obj is None), should return new manager
        manager = MyService.mcp
        # Accessing from class should return a new manager instance
        class_access = MCPClientManager.__get__(manager, None, MyService)
        assert isinstance(class_access, MCPClientManager)
        assert class_access.service_cls is MyService
