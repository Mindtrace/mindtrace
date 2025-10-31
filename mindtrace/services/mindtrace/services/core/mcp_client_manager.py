from typing import TYPE_CHECKING, Type

from fastmcp import Client
from urllib3.util.url import Url

if TYPE_CHECKING:  # pragma: no cover
    from mindtrace.services import Service


class MCPClientManager:
    """Manager for MCP client operations for a service class."""

    def __init__(self, service_cls: Type["Service"]):
        """Initialize the MCP client manager.

        Args:
            service_cls: The service class this manager is bound to.
        """
        self.service_cls = service_cls

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return MCPClientManager(obj.__class__)

    def connect(self, url: str | Url | None = None) -> "Client":
        """Connect to an existing service via MCP protocol.

        Args:
            url: The URL of the service. If None, uses the default URL for this service type.

        Returns:
            FastMCP Client instance for MCP protocol communication

        Example::
            from mindtrace.services.samples.echo_mcp import EchoService
            # Connect to a running EchoService
            mcp_client = EchoService.mcp.connect("http://localhost:8000")

            # Use default URL
            mcp_client = EchoService.mcp.connect()

            # Use the connected client
            async with mcp_client:
                tools = await mcp_client.list_tools()
                print(f"Available tools: {tools}")
        """
        # Build the URL with priority logic
        service_url = self.service_cls.build_url(url=url)
        # Build MCP URL from centralized class helper
        mcp_mount_path, mcp_http_app_path = self.service_cls.get_mcp_paths()
        mcp_url = f"{str(service_url).rstrip('/')}{mcp_mount_path}{mcp_http_app_path}"
        return Client(mcp_url)

    def launch(self, **launch_kwargs) -> "Client":
        """Launch a new service and return an MCP client for it.

        Launches a new service instance using the service's launch method,
        then returns an MCP client connected to the newly launched service.

        Args:
            **launch_kwargs: Arguments passed to the service's launch method

        Returns:
            FastMCP Client instance connected to the newly launched service

        Example::
            from mindtrace.services.samples.echo_mcp import EchoService

            mcp_client = EchoService.mcp.launch(
                                                host="localhost",
                                                port=8000,
                                                wait_for_launch=True,
                                                timeout=10
                                                )

            print(f"Service launched and MCP client created: {mcp_client}")
            async with mcp_client:
                tools = await mcp_client.list_tools()
                print(f"Available tools: {tools}")
        """
        connection_manager = self.service_cls.launch(**launch_kwargs)
        mcp_mount_path, mcp_http_app_path = self.service_cls.get_mcp_paths()
        mcp_url = f"{str(connection_manager.url).rstrip('/')}{mcp_mount_path}{mcp_http_app_path}"
        return Client(mcp_url)
