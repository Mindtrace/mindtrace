from contextlib import asynccontextmanager
from typing import Callable, Optional

from langchain_mcp_adapters.tools import load_mcp_tools

from mindtrace.core import Mindtrace


class MCPToolSession(Mindtrace):
    """Context-managed MCP session that loads tools for a service.

    Supports launching a new service or connecting to an existing one, and allows
    custom tool loaders (default: `langchain_mcp_adapters.tools.load_mcp_tools`).

    Example (launch):
        async with MCPToolSession(EchoService, mode="launch").open() as sess:
            print(sess.tools)

    Example (connect):
        async with MCPToolSession(EchoService, mode="connect", url="http://localhost:8000").open() as sess:
            ...
    """

    def __init__(
        self,
        service_cls=None,
        *,
        mode: str = "launch",  # "launch" or "connect"
        url: Optional[str] = None,
        host: str = "localhost",
        port: int = 8000,
        timeout: int = 10,
        client=None,
        tools_loader: Optional[Callable] = None,
    ):
        super().__init__()
        self._service_cls = service_cls
        self._mode = mode
        self._url = url
        self._host = host
        self._port = port
        self._timeout = timeout
        self._client = client
        self._tools_loader = tools_loader or load_mcp_tools
        self.tools = []
        self.tools_by_name = {}

    @asynccontextmanager
    async def open(self):
        """Open the MCP client, load tools, and yield this session instance."""
        # If a client was injected, use it; otherwise, create via connect or launch
        mcp_client = self._client
        if mcp_client is None:
            if self._service_cls is None:
                raise ValueError("service_cls or client must be provided for MCPToolSession")
            if self._mode == "connect":
                mcp_client = self._service_cls.mcp.connect(self._url)
            else:
                mcp_client = self._service_cls.mcp.launch(
                    host=self._host, port=self._port, wait_for_launch=True, timeout=self._timeout
                )
        try:
            async with mcp_client:
                self._client = mcp_client
                session = mcp_client.session
                self.tools = await self._tools_loader(session)
                self.tools_by_name = {t.name: t for t in self.tools}
                yield self
        finally:
            self._client = None
