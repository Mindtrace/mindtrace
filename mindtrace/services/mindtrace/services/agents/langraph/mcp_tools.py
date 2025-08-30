from contextlib import asynccontextmanager
from typing import Callable, Optional

from langchain_mcp_adapters.tools import load_mcp_tools
from fastmcp import Client

from mindtrace.core import Mindtrace


class MCPToolSession(Mindtrace):
    """Context-managed MCP session that loads tools for a service.

    Connects to an existing MCP service using a provided URL (or an injected
    `fastmcp.Client`), and allows custom tool loaders (default:
    `langchain_mcp_adapters.tools.load_mcp_tools`).

    Example (connect by URL):
        async with MCPToolSession(url="http://localhost:8000").open() as sess:
            ...

    Example (use existing client):
        client = Client("http://localhost:8000/mcp-server/mcp")
        async with MCPToolSession(client=client).open() as sess:
            ...
    """

    def __init__(
        self,
        *,
        url: Optional[str] = None,
        client: Optional[Client] = None,
        tools_loader: Optional[Callable] = None,
    ):
        super().__init__()
        self._url = url
        self._client = client
        self._tools_loader = tools_loader or load_mcp_tools
        self.tools = []
        self.tools_by_name = {}

    @asynccontextmanager
    async def open(self):
        """Open the MCP client, load tools, and yield this session instance.

        If an existing `Client` was injected, it will be used. Otherwise, a new
        `Client` will be constructed from the provided `url`.
        """
        mcp_client = self._client
        if mcp_client is None:
            if not self._url:
                raise ValueError("Either `client` or `url` must be provided for MCPToolSession")
            mcp_client = Client(self._url if self._url.endswith("/mcp-server/mcp") else f"{self._url.rstrip('/')}/mcp-server/mcp")
        try:
            async with mcp_client:
                self._client = mcp_client
                session = mcp_client.session
                self.tools = await self._tools_loader(session)
                self.tools_by_name = {t.name: t for t in self.tools}
                yield self
        finally:
            self._client = None
